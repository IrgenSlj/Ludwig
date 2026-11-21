# Hosting one instance per factory

Each pilot factory gets its own server: Caddy (HTTPS), Ludwig, Postgres and a backup job,
from `deploy/compose.yaml`. Factories never share a database, so there are no company
accounts to keep apart.

## What you need

- A small Linux server in the EU (2 vCPU, 4 GB RAM, 40 GB disk is enough for a pilot)
  with Docker Engine and the Compose plugin.
- A DNS name for it, e.g. `ludwig.factory-name.nl`, with an A (and AAAA) record pointing
  at the server.
- Ports 80 and 443 open to the internet (Caddy needs 80 to get the certificate). Close
  everything else except SSH.

## First start

```
git clone <this repository> ludwig && cd ludwig/deploy
cp .env.example .env
# edit .env: LUDWIG_DOMAIN, POSTGRES_PASSWORD (openssl rand -base64 32), retention
LUDWIG_VERSION=$(git describe --always --dirty) docker compose up -d --build
docker compose exec ludwig ludwig user add <your-name> --admin
```

Open `https://<LUDWIG_DOMAIN>`, sign in, and add the factory's people under Users.
Ludwig sends no email: give each person a first password yourself and ask them to change
it (click their name, top right). A forgotten password is reset by an admin under Users.

The kit sets `LUDWIG_REQUIRE_LOGIN=1`, so the instance is never open: until the first
admin exists the sign-in page says how to add one, and nothing else answers.

## What runs

| Service | Image | Holds |
|---|---|---|
| caddy | caddy:2.11 | certificates (volume `caddy_data`); HTTPS, HTTP→HTTPS redirect, security headers, upload size limit |
| ludwig | built from this repository | uploads, reports, the factory's working packs (volume `ludwig_data`) |
| db | postgres:16 | projects, runs, findings, reviews, users, activity (volume `db_data`) |
| backup | postgres:16 | writes `db-<stamp>.dump` and `data-<stamp>.tar.gz` to `BACKUP_DIR` daily at `BACKUP_HOUR` UTC, keeps `BACKUP_KEEP_DAYS` |

Settings in `.env`: `LUDWIG_DOMAIN`, `POSTGRES_PASSWORD`, `LUDWIG_RETENTION_DAYS` (idle
projects are deleted after this many days; empty keeps them), `LUDWIG_MAX_UPLOAD_MB`,
`BACKUP_DIR`, `BACKUP_KEEP_DAYS`, `BACKUP_HOUR`, and optionally `LUDWIG_ASSIST_COMMAND`
(see INSTALL.md; leave empty unless the data agreement allows sending text to a model).

## Backups

The backup job keeps copies on the same server. Copy `BACKUP_DIR` off the server as well
(your hosting provider's backup or snapshot service, or `rsync`/`restic` to storage in
another location), or a lost server loses its backups with it.

A backup now: `docker compose exec backup sh /backup.sh once`.

Restore (replaces the current data):

```
sh restore.sh 20261121-020000     # the stamp in the backup file names
```

It stops Ludwig, restores the database dump and the data archive, and starts everything
again. Signed-in users stay signed in if their session was in the backup.

## Upgrades

```
git pull
LUDWIG_VERSION=$(git describe --always --dirty) docker compose up -d --build
```

Admins see the running version, the packs, the age of the newest backup and the free disk
space under Users, with a warning when a backup is late (over 26 hours) or the disk is
nearly full.

On start Ludwig migrates the database to the new schema and upgrades the packs: a pack
whose version changed is replaced by the new release, the factory's limit values are
carried over, new limits start at the release value, and the old copy is kept in
`/data/packs/.backup/`. The container log (`docker compose logs ludwig`) lists what changed.
Take a backup before an upgrade.

## Data agreement checklist

- Retention: set `LUDWIG_RETENTION_DAYS` to the period agreed with the factory. Idle
  projects and activity lines older than that are deleted.
- Deletion request: delete the project in the web app (Project data → Delete). Backups
  hold it until they age out (`BACKUP_KEEP_DAYS`).
- Handing data back: Project data → Export everything gives one zip per project.
- Who did what: Activity in the web app.
- Leaving the pilot: export each project, then `docker compose down -v` and delete
  `BACKUP_DIR`.
