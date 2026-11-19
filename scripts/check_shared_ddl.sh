#!/usr/bin/env bash
# Run the shared read database DDL on a throwaway MariaDB 11.8 container and check it against the contracts.
#
#   scripts/check_shared_ddl.sh
#
# Needs Docker and python. Starts one container (random root password, never printed, removed on exit), runs
# apps/nxerp_platform/nxerp/shared_service/schema/0001_shared_model.sql twice, then checks:
#   - both runs succeed (the file is idempotent), 12 tables, utf8mb4 everywhere, no foreign keys;
#   - the real columns of every entity table equal the contract's fields (plus the system columns);
#   - the idempotent upsert pattern from the SQL header: an older event is ignored, a replay is a no-op, a newer
#     event wins, a tombstone sticks and a late older event cannot resurrect the row;
#   - the cursor moves with its transaction, and the dead-letter table refuses a duplicate event id.
# Nothing here touches production or any real data. Exit code 0 only if every check passes.
set -uo pipefail
export MSYS_NO_PATHCONV=1

REPO="$(cd "$(dirname "$0")/.." && pwd)"
# native path for a Windows python started from Git Bash (cygpath exists only there)
NATIVE_REPO="$(cygpath -m "$REPO" 2>/dev/null || echo "$REPO")"
SQL="$REPO/apps/nxerp_platform/nxerp/shared_service/schema/0001_shared_model.sql"
IMAGE="${MARIADB_IMAGE:-mariadb:11.8}"
NAME="nxerp-ddl-check-$$"
FAILS=0

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; FAILS=$((FAILS + 1)); }

command -v docker >/dev/null 2>&1 || { echo "UNVERIFIED docker is not installed; run: scripts/check_shared_ddl.sh"; exit 2; }
PY=""
for candidate in python3 python; do
	if "$candidate" -c 'pass' >/dev/null 2>&1; then PY="$candidate"; break; fi
done
[ -n "$PY" ] || { echo "UNVERIFIED no working python3 or python found"; exit 2; }
PW="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(18))')"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1; }
trap cleanup EXIT

docker run -d --name "$NAME" -e MARIADB_ROOT_PASSWORD="$PW" "$IMAGE" >/dev/null || { echo "FAIL could not start $IMAGE"; exit 2; }
m() { docker exec -i -e MYSQL_PWD="$PW" "$NAME" mariadb -uroot "$@" </dev/null; }
mf() { docker exec -i -e MYSQL_PWD="$PW" "$NAME" mariadb -uroot "$@"; }

for _ in $(seq 1 60); do m -e "SELECT 1" >/dev/null 2>&1 && break; sleep 2; done
m -e "SELECT 1" >/dev/null 2>&1 || { echo "FAIL mariadb did not become ready"; exit 2; }
echo "server: $(m -N -B -e 'SELECT VERSION()')"
m -e "CREATE DATABASE shared_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"

mf shared_test <"$SQL" && pass "ddl run 1" || fail "ddl run 1"
mf shared_test <"$SQL" && pass "ddl run 2 (idempotent)" || fail "ddl run 2 (idempotent)"
[ "$(m -N -B shared_test -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='shared_test'")" = "12" ] && pass "12 tables" || fail "12 tables"
[ "$(m -N -B shared_test -e "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='shared_test' AND character_set_name IS NOT NULL AND character_set_name<>'utf8mb4'")" = "0" ] && pass "every text column is utf8mb4" || fail "every text column is utf8mb4"
[ "$(m -N -B shared_test -e "SELECT COUNT(*) FROM information_schema.table_constraints WHERE table_schema='shared_test' AND constraint_type='FOREIGN KEY'")" = "0" ] && pass "no foreign keys" || fail "no foreign keys"

COLS="$(m -N -B shared_test -e "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='shared_test' ORDER BY table_name, ordinal_position")"
COLS_TSV="$COLS" CONTRACTS="$NATIVE_REPO/apps/nxerp_platform/nxerp/shared/contracts" "$PY" - <<'PY' || FAILS=$((FAILS + 1))
import json
import os
import pathlib
import sys

cols = {}
for line in os.environ["COLS_TSV"].splitlines():
	table, column = line.split("\t")
	cols.setdefault(table, set()).add(column)
system = {"source_app", "entity_id", "tenant_id", "source_modified", "last_seq", "contract_version", "deleted_at", "synced_at"}
files = sorted(pathlib.Path(os.environ["CONTRACTS"]).glob("*.json"))
if len(files) != 7:
	print(f"FAIL expected 7 contract files, found {len(files)} in {os.environ['CONTRACTS']}")
	sys.exit(1)
bad = 0
for path in files:
	contract = json.loads(path.read_text(encoding="utf-8"))
	table = "entity_" + contract["entity_type"]
	have = cols.get(table, set()) - system
	want = {field["shared"] for field in contract["fields"]}
	if have != want:
		bad += 1
		print(f"FAIL {table} columns differ from the contract: missing {sorted(want - have)}, extra {sorted(have - want)}")
	else:
		print(f"PASS {table} columns equal the contract")
sys.exit(1 if bad else 0)
PY

upsert() { # modified seq name deleted_at_sql
	m shared_test -e "INSERT INTO entity_customer (source_app, entity_id, tenant_id, display_name, source_modified, last_seq, contract_version, deleted_at, synced_at) VALUES ('erpnext','CUST-T1','ORG-001','$3','$1',$2,1,$4,NOW(6)) ON DUPLICATE KEY UPDATE display_name=IF((VALUES(source_modified),VALUES(last_seq))>(source_modified,last_seq),VALUES(display_name),display_name), deleted_at=IF((VALUES(source_modified),VALUES(last_seq))>(source_modified,last_seq),VALUES(deleted_at),deleted_at), synced_at=IF((VALUES(source_modified),VALUES(last_seq))>(source_modified,last_seq),VALUES(synced_at),synced_at), contract_version=IF((VALUES(source_modified),VALUES(last_seq))>(source_modified,last_seq),VALUES(contract_version),contract_version), source_modified=GREATEST(source_modified,VALUES(source_modified)), last_seq=IF(VALUES(source_modified)>source_modified OR (VALUES(source_modified)=source_modified AND VALUES(last_seq)>last_seq),VALUES(last_seq),last_seq)"
}
state() { m -N -B shared_test -e "SELECT display_name, IFNULL(deleted_at,'-') FROM entity_customer WHERE entity_id='CUST-T1'" | tr '\t' ' '; }
expect() { local got; got="$(state)"; [ "$got" = "$2" ] && pass "$1" || fail "$1 (got [$got], want [$2])"; }

upsert '2026-11-18 10:00:00.000001' 5 'Example v1' NULL;                    expect "upsert: insert" "Example v1 -"
upsert '2026-11-18 09:00:00.000000' 4 'Older stale' NULL;                   expect "upsert: an older event is ignored" "Example v1 -"
upsert '2026-11-18 10:00:00.000001' 5 'Same stamp replay' NULL;             expect "upsert: a replay is a no-op" "Example v1 -"
upsert '2026-11-18 11:00:00.000000' 6 'Example v2' NULL;                    expect "upsert: a newer event wins" "Example v2 -"
upsert '2026-11-18 12:00:00.000000' 7 'Example v2' "'2026-11-18 12:00:00'"; expect "upsert: a tombstone sticks" "Example v2 2026-11-18 12:00:00.000000"
upsert '2026-11-18 11:30:00.000000' 6 'Late old upsert' NULL;               expect "upsert: a late older event cannot resurrect" "Example v2 2026-11-18 12:00:00.000000"

m shared_test -e "START TRANSACTION; INSERT INTO sync_cursor (source_app,last_seq,updated_at) VALUES ('erpnext',7,NOW(6)); ROLLBACK;"
[ "$(m -N -B shared_test -e 'SELECT COUNT(*) FROM sync_cursor')" = "0" ] && pass "cursor change rolls back with its transaction" || fail "cursor change rolls back with its transaction"
EVENT="INSERT INTO sync_dead_letter (event_id,source_app,entity_type,entity_id,event_json,error_text,created_at) VALUES ('evt-1','erpnext','customer','CUST-T1','{\"a\":1}','example',NOW(6))"
m shared_test -e "$EVENT" && pass "dead letter accepts an event (JSON column)" || fail "dead letter accepts an event"
DUP="$(m shared_test -e "$EVENT" 2>&1)"
echo "$DUP" | grep -q "Duplicate" && pass "dead letter refuses a duplicate event id" || fail "dead letter refuses a duplicate event id"

if [ "$FAILS" -eq 0 ]; then echo "check_shared_ddl: PASS on $(m -N -B -e 'SELECT VERSION()')"; else echo "check_shared_ddl: $FAILS check(s) FAILED"; fi
exit $((FAILS > 0))
