# On-site installation

One container holds the service, the web app and the bundled rule packs. Files and
results stay on the machine that runs it.

```
docker build -t ludwig .
docker run -d --name ludwig -p 8000:8000 -v ludwig-data:/data ludwig
```

Open http://<host>:8000. Data (SQLite database and uploaded files, stored by content hash)
lives in the `ludwig-data` volume; back up that volume.

## Settings

| Variable | Default in the image | Meaning |
|---|---|---|
| `LUDWIG_API_TOKEN` | not set | when set, every API call needs `Authorization: Bearer <token>`; the web app asks for it under "Access token" |
| `LUDWIG_DATABASE_URL` | `sqlite:////data/ludwig.db` | e.g. `postgresql+psycopg://user:pass@db/ludwig` for Postgres |
| `LUDWIG_STORAGE_DIR` | `/data/storage` | uploaded files and reports |
| `LUDWIG_PACKS_DIR` | `/app/packs` | rule packs; mount a folder here to use a factory's own pack |
| `LUDWIG_MAX_UPLOAD_MB` | `200` | largest accepted file |
| `LUDWIG_ALLOWED_ORIGINS` | not set | extra origins allowed to change data from a browser |

A factory pack (own limits, own ERP mapping) is mounted read-only:

```
docker run -d -p 8000:8000 -v ludwig-data:/data -v /srv/packs:/app/packs:ro ludwig
```

Without a token the service is open to anyone who can reach the port: run it on the
factory network only, or set `LUDWIG_API_TOKEN`.
