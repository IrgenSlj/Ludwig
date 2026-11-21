#!/bin/sh
# Restore one instance from a backup pair made by backup.sh. This REPLACES the current
# database and data volume. Run from this folder:  sh restore.sh 20261121-020000
set -eu
stamp=${1:?usage: sh restore.sh <stamp>, e.g. 20261121-020000 (see the backups folder)}
set -a; . ./.env; set +a
dir=${BACKUP_DIR:-./backups}
[ -f "$dir/db-$stamp.dump" ] && [ -f "$dir/data-$stamp.tar.gz" ] || {
	echo "no backup $stamp in $dir" >&2; exit 1; }
compose="docker compose ${COMPOSE_ARGS:-}"
$compose stop caddy ludwig backup
$compose up -d --wait db
$compose run --rm --no-deps --entrypoint sh backup -c \
	"pg_restore --clean --if-exists --no-owner --dbname=ludwig /backups/db-$stamp.dump"
$compose run --rm --no-deps --user root --entrypoint sh \
	-v "$(cd "$dir" && pwd)":/backups:ro ludwig -c \
	"find /data -mindepth 1 -delete && tar -xzf /backups/data-$stamp.tar.gz -C /data && chown -R ludwig /data"
$compose up -d --wait
echo "restored $stamp"
