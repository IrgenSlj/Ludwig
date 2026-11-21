#!/bin/sh
# Backups for one instance: the database (pg_dump) and the data volume (uploads, reports,
# working packs), one pair of files per day in /backups, the last BACKUP_KEEP_DAYS kept.
#   sh backup.sh once    one backup now
#   sh backup.sh loop    one backup a day at BACKUP_HOUR (UTC); the compose service runs this
set -eu

once() {
	stamp=$(date -u +%Y%m%d-%H%M%S)
	pg_dump --format=custom --file="/backups/db-$stamp.dump.part"
	mv "/backups/db-$stamp.dump.part" "/backups/db-$stamp.dump"
	tar -czf "/backups/data-$stamp.tar.gz.part" -C /data .
	mv "/backups/data-$stamp.tar.gz.part" "/backups/data-$stamp.tar.gz"
	find /backups -maxdepth 1 \( -name 'db-*.dump' -o -name 'data-*.tar.gz' \) \
		-mtime +"${BACKUP_KEEP_DAYS:-14}" -delete
	echo "backup $stamp done"
}

case "${1:-once}" in
once) once ;;
loop)
	while true; do
		now=$(date -u +%s)
		next=$(date -u -d "$(date -u +%Y-%m-%d) ${BACKUP_HOUR:-2}:00" +%s)
		[ "$next" -le "$now" ] && next=$((next + 86400))
		sleep $((next - now))
		once || echo "backup failed" >&2
	done
	;;
*) echo "usage: backup.sh once|loop" >&2; exit 2 ;;
esac
