# On-site installation

One container holds the service, the web app and the bundled rule packs. Files and
results stay on the machine that runs it. For a hosted instance per factory (HTTPS,
Postgres, backups) see [HOSTING.md](HOSTING.md).

```
docker build -t ludwig .
docker run -d --name ludwig -p 8000:8000 -v ludwig-data:/data ludwig
```

Open http://<host>:8000. Data (SQLite database, uploaded files stored by content hash, and
the working copy of the packs) lives in the `ludwig-data` volume; back up that volume.
Then add the first admin, after which everyone signs in:

```
docker exec -it ludwig ludwig user add <name> --admin
```

## Settings

| Variable | Default in the image | Meaning |
|---|---|---|
| `LUDWIG_API_TOKEN` | not set | a shared token for scripts (`Authorization: Bearer <token>`); people sign in with their own name instead |
| `LUDWIG_DATABASE_URL` | `sqlite:////data/ludwig.db` | e.g. `postgresql+psycopg://user:pass@db/ludwig` for Postgres |
| `LUDWIG_STORAGE_DIR` | `/data/storage` | uploaded files and reports |
| `LUDWIG_PACKS_DIR` | `/data/packs` | rule packs; at each start the released packs are installed or upgraded here, keeping the factory's limit values. Point it at a mounted folder to use your own packs as they are |
| `LUDWIG_RETENTION_DAYS` | not set | projects with no activity for this many days are deleted |
| `LUDWIG_SECURE_COOKIES` | not set | `1` when served over HTTPS (the hosted kit sets it) |
| `LUDWIG_SESSION_DAYS` | `14` | how long a sign-in lasts |
| `LUDWIG_MAX_UPLOAD_MB` | `200` | largest accepted file |
| `LUDWIG_ALLOWED_ORIGINS` | not set | extra origins allowed to change data from a browser |
| `LUDWIG_ASSIST_COMMAND` | not set | optional language-model command (prompt on stdin, answer on stdout), e.g. a local `ollama run <model>`; unset means nothing is sent to any model |

A factory pack (own limits, own ERP mapping) is mounted read-only:

```
docker run -d -p 8000:8000 -v ludwig-data:/data -v /srv/packs:/srv/packs:ro \
  -e LUDWIG_PACKS_DIR=/srv/packs ludwig
```

Until the first user is added (and without a token) the service is open to anyone who can
reach the port. To change limits from the web app (Packs), mount the packs folder writable.
