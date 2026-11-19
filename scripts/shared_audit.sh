#!/usr/bin/env bash
# Repeatable audit of a running shared read layer (deploy/docker/compose/shared). Changes nothing durable.
#
#   scripts/shared_audit.sh ports | accounts | api | pipeline | sample | tests | all
#
#   ports     no container of the shared stack publishes a host port
#   accounts  exact grant matrix, and each app account really cannot do what it must not (T10); no sensitive column names
#   api       the live Read API with a real token: 401, 403, 405, field denial, no field outside the contract (T9)
#   pipeline  no dead letters, no gap, no stopped source; a full reconcile finds drift 0 (T13-T18 live view)
#   sample    20 random shared rows per entity compared with the owner's own feed
#   tests     the unit and database tests (deploy/scripts/shared.sh test)
#   all       everything above; exit 1 if any line is FAIL
#
# Output lines: "PASS name", "FAIL name reason", "INFO name text". Only names, counts and PASS/FAIL: never a token, password or row value.
# Needs the stack up (deploy/scripts/shared.sh up), a token file deploy/env/shared/secrets/read-helpdesk.token and the feed key file.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SHARED="$ROOT/deploy/scripts/shared.sh"
PROJECT="${SHARED_COMPOSE_PROJECT:-nxerp-shared}"
fail=0

# run_tool SERVICE CHECK: one-shot container; keep only the result lines
run_tool() {
	local out rc
	out="$("$SHARED" _tool "$1" "$2" 2>&1)"
	rc=$?
	printf '%s\n' "$out" | grep -E '^(PASS|FAIL|INFO) ' || true
	if [ "$rc" -ne 0 ]; then
		fail=1
		printf '%s
' "$out" | grep -q '^FAIL ' || echo "FAIL tool.${2:-probe} exit status $rc: $(printf '%s' "$out" | tail -n 1 | cut -c1-120)"
	fi
}

audit_ports() {
	local published
	published="$(docker ps --filter "label=com.docker.compose.project=$PROJECT" --format '{{.Names}} {{.Ports}}' | grep -E '(0\.0\.0\.0|127\.0\.0\.1|\[::\]):[0-9]+->' || true)"
	if [ -z "$published" ]; then echo "PASS ports.none-published"; else echo "FAIL ports.published $published"; fail=1; fi
}

audit_accounts() {
	run_tool shared-root-tool accounts
	run_tool shared-root-tool columns
	run_tool shared-ops probe
	local out rc
	out="$(MSYS_NO_PATHCONV=1 docker exec "$PROJECT-shared-api-1" /home/frappe/frappe-bench/env/bin/python -m nxerp.shared_service.audit probe 2>&1)"
	rc=$?
	printf '%s\n' "$out" | grep -E '^(PASS|FAIL|INFO) ' || true
	if [ "$rc" -ne 0 ]; then
		fail=1
		printf '%s
' "$out" | grep -q '^FAIL ' || echo "FAIL tool.${2:-probe} exit status $rc: $(printf '%s' "$out" | tail -n 1 | cut -c1-120)"
	fi
}

audit_pipeline() {
	local status
	status="$("$SHARED" status 2>&1 | grep '^{' | tail -n 1)"
	STATUS="$status" python - <<'PY' || fail=1
import json, os, sys
d = json.loads(os.environ["STATUS"])
m = d.get("metrics", {})
bad = 0
def check(name, ok, detail=""):
    global bad
    print(("PASS " + name) if ok else ("FAIL " + name + " " + detail))
    bad += (not ok)
check("pipeline.dead-letters-zero", d.get("unresolved_dead_letters") == 0, str(d.get("unresolved_dead_letters")))
check("pipeline.no-source-stopped", all(v == 0 for k, v in m.items() if k.endswith(".source_stopped")), "")
check("pipeline.no-gap", all(v == 0 for k, v in m.items() if k.endswith(".gap")), "")
for key, value in sorted(m.items()):
    if key.endswith(".lag_seconds"):
        print("INFO pipeline." + key + " " + str(round(value, 1)))
sys.exit(1 if bad else 0)
PY
	local report
	report="$("$SHARED" reconcile --full 2>&1 | grep '^{' | tail -n 1)"
	REPORT="$report" python - <<'PY' || fail=1
import json, os, sys
d = json.loads(os.environ["REPORT"])
ok = d.get("drift") == 0 and d.get("refused") == 0
print("PASS pipeline.full-reconcile-drift-zero" if ok else "FAIL pipeline.full-reconcile-drift-zero drift=%s refused=%s" % (d.get("drift"), d.get("refused")))
print("INFO pipeline.repaired " + str(d.get("repaired")))
sys.exit(0 if ok else 1)
PY
}

case "${1:-all}" in
	ports) audit_ports ;;
	accounts) audit_accounts ;;
	api) run_tool shared-ops api ;;
	pipeline) audit_pipeline ;;
	sample) run_tool shared-ops sample ;;
	tests) "$SHARED" test 2>&1 | tail -n 4 ;;
	all)
		audit_ports
		audit_accounts
		run_tool shared-ops api
		audit_pipeline
		run_tool shared-ops sample
		;;
	*) echo "usage: $0 ports|accounts|api|pipeline|sample|tests|all" >&2; exit 2 ;;
esac
exit "$fail"
