#!/usr/bin/env bash
# End-to-end test of the hosting kit on this machine (PLAN 6.13; CI runs it on every push):
# HTTPS on localhost, closed before the first admin, sign-in, a check on Postgres, a backup,
# wiping every volume, restoring, and the same data afterwards. Needs Docker, ports 80/443.
#   bash deploy/smoke-test.sh
set -euo pipefail
cd "$(dirname "$0")"
FIX=../fixtures
work=$(mktemp -d)
export COMPOSE_PROJECT_NAME=ludwigsmoke
cleanup() {
	docker compose down -v >/dev/null 2>&1 || true
	rm -f .env
	rm -rf "$work"
}
trap cleanup EXIT
[ -e .env ] && { echo "deploy/.env exists; this test writes its own, move yours first" >&2; exit 2; }

password=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
cat >.env <<EOF
LUDWIG_DOMAIN=localhost
POSTGRES_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
LUDWIG_RETENTION_DAYS=180
BACKUP_DIR=$work/backups
LUDWIG_VERSION=smoke
EOF
mkdir -p "$work/backups"

fail() { echo "FAIL: $*" >&2; docker compose logs --tail 50 ludwig >&2 || true; exit 1; }
api() { curl -sk -b "$work/jar" -c "$work/jar" -H 'Origin: https://localhost' "$@"; }
id() { python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'; }
code() { curl -sk -b "$work/jar" -o /dev/null -w '%{http_code}' "$@"; }
wait_up() {
	for _ in $(seq 1 60); do
		curl -sk https://localhost/health | grep -q ok && return 0
		sleep 2
	done
	fail "the instance did not answer on https://localhost"
}

docker compose up -d --build --wait
wait_up
[ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost/)" = 308 ] || fail "no HTTP->HTTPS redirect"
[ "$(code https://localhost/api/projects)" = 401 ] || fail "open before the first admin"
headers=$(curl -skI https://localhost/)
grep -qi "^content-security-policy: default-src 'self'" <<<"$headers" || fail "no CSP header"
grep -qi "^strict-transport-security" <<<"$headers" || fail "no HSTS header"

docker compose exec -T -e LUDWIG_NEW_PASSWORD="$password" ludwig ludwig user add admin --admin
api -H 'Content-Type: application/json' -d "{\"name\":\"admin\",\"password\":\"$password\"}" \
	https://localhost/api/auth/login >/dev/null
grep -q ludwig_session "$work/jar" || fail "no session cookie"
awk '/ludwig_session/ {print $4}' "$work/jar" | grep -q TRUE || fail "session cookie not Secure"
[ "$(code https://localhost/api/projects)" = 200 ] || fail "signed in but refused"

project=$(api -H 'Content-Type: application/json' -d '{"name":"smoke"}' https://localhost/api/projects | id)
upload() { api -F "role=$2" ${3:+-F for_upload=$3} -F "file=@$1" "https://localhost/api/projects/$project/uploads" | id; }
model=$(upload "$FIX/ifc/duplex_architectural_ifc2x3.ifc" architect)
export_=$(upload "$FIX/erp/duplex_erp_export_seeded.csv" erp)
mapping=$(upload "$FIX/erp/duplex_erp_export.mapping.yaml" mapping "$export_")
run=$(api -H 'Content-Type: application/json' \
	-d "{\"pack\":\"joinery-nl\",\"uploads\":[$model,$export_,$mapping]}" \
	"https://localhost/api/projects/$project/runs" | id)
summary=""
for _ in $(seq 1 60); do
	summary=$(api "https://localhost/api/runs/$run" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d["status"], json.dumps(d["summary"]["fails_by_severity"], sort_keys=True) if d["summary"] else "")')
	case $summary in done*|failed*) break ;; esac
	sleep 2
done
[ "$summary" = 'done {"blocker": 7, "warning": 1}' ] || fail "unexpected run result: $summary"
api https://localhost/api/status | grep -q '"version": *"smoke"' || fail "status does not show the version"

docker compose exec -T backup sh /backup.sh once
stamp=$(ls "$work/backups" | sed -n 's/^db-\(.*\)\.dump$/\1/p' | tail -1)
[ -n "$stamp" ] && [ -f "$work/backups/data-$stamp.tar.gz" ] || fail "no backup pair written"

docker compose down -v
sh restore.sh "$stamp"
wait_up
[ "$(code "https://localhost/api/runs/$run")" = 200 ] || fail "run gone after restore (or session lost)"
[ "$(code "https://localhost/api/runs/$run/reports/report.xlsx")" = 200 ] || fail "report gone after restore"
[ "$(code "https://localhost/api/projects/$project/export")" = 200 ] || fail "export fails after restore"
echo "smoke test passed: https, closed until admin, sign-in, check, backup, restore"
