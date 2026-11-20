#!/usr/bin/env bash
# Repeatable audit of a running shared read layer (deploy/docker/compose/shared). Changes nothing durable.
#
#   scripts/shared_audit.sh ports | accounts | api | pipeline | sample | tests | t19 | t20 | t21 | t22 | phase7 | all
#
#   ports     no container of the shared stack publishes a host port
#   accounts  exact grant matrix, and each app account really cannot do what it must not (T10); no sensitive column names
#   api       the live Read API with a real token: 401, 403, 405, field denial, no field outside the contract (T9)
#   pipeline  no dead letters, no gap, no stopped source; a full reconcile finds drift 0 (T13-T18 live view)
#   sample    20 random shared rows per entity compared with the owner's own feed
#   tests     the unit and database tests (deploy/scripts/shared.sh test)
#   t19       Phase 7: a command applies once (the same idempotency key twice = one change, one outbox row, one log row)
#   t20       Phase 7: with the Helpdesk setting off, the shared-read path does nothing (the new tests; the legacy suites run separately)
#   t21       Phase 7: Helpdesk with the Read API stopped shows the "out of date" banner and still saves a ticket (stops and restarts the Read API)
#   t22       Phase 7: from the Helpdesk backend the ERPNext database server and the shared database cannot be reached, and Helpdesk's own
#             database login is refused on ERPNext's database (error 1142 or 1044)
#   phase7    t19 to t22 (they need the staging stacks of Phase 5: containers nxerp-hd-backend-1 and nxerp-erp-backend-1)
#   all       ports, accounts, api, pipeline, sample; exit 1 if any line is FAIL (phase7 is separate: it needs the staging stacks)
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


# ---- Phase 7 (T19 to T22): need the staging stacks (docker names below can be overridden) --------------------------------------------------
HD_BACKEND="${HD_BACKEND:-nxerp-hd-backend-1}"
HD_SITE="${HD_SITE:-hd.example.test}"
ERP_BACKEND="${ERP_BACKEND:-nxerp-erp-backend-1}"
ERP_SITE="${ERP_SITE:-erp.example.test}"
SHARED_API_CONTAINER="${SHARED_API_CONTAINER:-$PROJECT-shared-api-1}"
ACTING_USER="${NXERP_AUDIT_ACTING_USER:-}"

in_container() { # container args...: bench-style command in the bench directory
	local container="$1"
	shift
	MSYS_NO_PATHCONV=1 docker exec -w /home/frappe/frappe-bench "$container" "$@"
}

bench_exec() { # container site method [kwargs]: prints the last line of the output
	local container="$1" site="$2" method="$3" kwargs="${4:-}"
	if [ -n "$kwargs" ]; then
		in_container "$container" bench --site "$site" execute "$method" --kwargs "$kwargs" 2>/dev/null | tail -n 1
	else
		in_container "$container" bench --site "$site" execute "$method" 2>/dev/null | tail -n 1
	fi
}

stack_present() { # name container
	if docker ps --format '{{.Names}}' | grep -qx "$2"; then return 0; fi
	echo "UNVERIFIED $1 container $2 is not running; start the Phase 5 staging stacks (deploy/scripts/stack.sh) and retry"
	return 1
}

audit_t19() {
	stack_present t19 "$HD_BACKEND" || return 0
	stack_present t19 "$ERP_BACKEND" || return 0
	[ -n "$ACTING_USER" ] || { echo "UNVERIFIED t19 set NXERP_AUDIT_ACTING_USER to a person on the ERPNext site who may edit customers"; return 0; }
	local customer key territory before_events first second after_events log_rows call
	customer="$(bench_exec "$ERP_BACKEND" "$ERP_SITE" frappe.db.get_value "{'doctype':'Customer','filters':{},'fieldname':'name'}")"
	[ -n "$customer" ] || { echo "UNVERIFIED t19 the ERPNext staging site has no customer (create the fake fixtures first)"; return 0; }
	key="audit-t19-$(date +%s)-$RANDOM"
	territory="$(bench_exec "$ERP_BACKEND" "$ERP_SITE" frappe.db.get_value "{'doctype':'Territory','filters':{'is_group':0,'name':['!=','$(bench_exec "$ERP_BACKEND" "$ERP_SITE" frappe.db.get_value "{'doctype':'Customer','filters':'$customer','fieldname':'territory'}")']},'fieldname':'name'}")"
	[ -n "$territory" ] || { echo "UNVERIFIED t19 no second Territory to change to"; return 0; }
	before_events="$(bench_exec "$ERP_BACKEND" "$ERP_SITE" frappe.db.count "{'dt':'NXERP Outbox Event','filters':{'entity_id':'$customer'}}")"
	call="{'entity_type':'customer','entity_id':'$customer','command':'request_change','fields':{'territory':'$territory'},'idempotency_key':'$key','acting_user':'$ACTING_USER'}"
	first="$(bench_exec "$HD_BACKEND" "$HD_SITE" helpdesk.integrations.shared.command_client.apply "$call" | cut -c1-120)"
	second="$(bench_exec "$HD_BACKEND" "$HD_SITE" helpdesk.integrations.shared.command_client.apply "$call" | cut -c1-120)"
	after_events="$(bench_exec "$ERP_BACKEND" "$ERP_SITE" frappe.db.count "{'dt':'NXERP Outbox Event','filters':{'entity_id':'$customer'}}")"
	log_rows="$(bench_exec "$ERP_BACKEND" "$ERP_SITE" frappe.db.count "{'dt':'NXERP Command Log','filters':{'idempotency_key':'$key'}}")"
	case "$first" in *"'ok': True"* | *'"ok": true'*) echo "PASS t19.first-call-applied" ;; *) echo "FAIL t19.first-call-applied $first" ; fail=1 ;; esac
	if [ "$first" = "$second" ]; then echo "PASS t19.repeat-returns-the-first-result"; else echo "FAIL t19.repeat-returns-the-first-result"; fail=1; fi
	if [ "$((after_events - before_events))" = 1 ]; then echo "PASS t19.exactly-one-outbox-row"; else echo "FAIL t19.exactly-one-outbox-row got $((after_events - before_events))"; fail=1; fi
	if [ "$log_rows" = 1 ]; then echo "PASS t19.one-log-row"; else echo "FAIL t19.one-log-row got $log_rows"; fail=1; fi
}

audit_t20() {
	stack_present t20 "$HD_BACKEND" || return 0
	local out
	out="$(in_container "$HD_BACKEND" bench --site "$HD_SITE" run-tests --app helpdesk --module helpdesk.integrations.shared.test_shared_integration 2>&1 | grep -E '^(Ran|OK|FAILED)' | tr '\n' ' ')"
	case "$out" in *OK*) echo "PASS t20.shared-read-tests ($out)" ;; *) echo "FAIL t20.shared-read-tests $out"; fail=1 ;; esac
	echo "INFO t20 the legacy Helpdesk suites with the setting off (test_hd_customer, test_erpnext_integration) run on a site that has ERPNext: bench run-tests --app helpdesk --module <module>"
}

audit_t21() {
	stack_present t21 "$HD_BACKEND" || return 0
	local hd_customer card
	hd_customer="$(bench_exec "$HD_BACKEND" "$HD_SITE" frappe.db.get_value "{'doctype':'HD Customer','filters':{'customer_ref_id':['is','set']},'fieldname':'name'}")"
	[ -n "$hd_customer" ] || { echo "UNVERIFIED t21 no HD Customer linked to NXERP (set customer_ref_id on a fake HD Customer first)"; return 0; }
	docker stop "$SHARED_API_CONTAINER" >/dev/null 2>&1 || { echo "UNVERIFIED t21 cannot stop $SHARED_API_CONTAINER"; return 0; }
	card="$(bench_exec "$HD_BACKEND" "$HD_SITE" helpdesk.integrations.shared.api.get_customer_card "{'hd_customer':'$hd_customer'}")"
	case "$card" in *"'banner': True"* | *'"banner": true'*) echo "PASS t21.banner-shown-when-the-read-api-is-down" ;; *) echo "FAIL t21.banner-shown-when-the-read-api-is-down $(printf '%s' "$card" | cut -c1-120)"; fail=1 ;; esac
	local ticket
	ticket="$(bench_exec "$HD_BACKEND" "$HD_SITE" frappe.client.insert "{'doc':{'doctype':'HD Ticket','subject':'T21 audit ticket','raised_by':'t21-audit@example.test','customer':'$hd_customer'}}" | cut -c1-80)"
	case "$ticket" in *HD\ Ticket* | *\"name\"* | *"'name'"*) echo "PASS t21.ticket-still-saves" ;; *) echo "FAIL t21.ticket-still-saves $ticket"; fail=1 ;; esac
	docker start "$SHARED_API_CONTAINER" >/dev/null 2>&1 && echo "INFO t21 the Read API was started again"
}

audit_t22() {
	stack_present t22 "$HD_BACKEND" || return 0
	local target result erp_db out code
	for target in mariadb-restricted:3306 mariadb-standard:3306 shared-db:3306; do
		result="$(in_container "$HD_BACKEND" bash -c "timeout 3 bash -c '</dev/tcp/${target%%:*}/${target##*:}' 2>/dev/null && echo REACHABLE || echo blocked" | tr -d '\r' | tail -n 1)"
		case "$target:$result" in
			mariadb-standard:3306:REACHABLE) echo "INFO t22 Helpdesk shares the standard database server with the identity site by design; its account grants decide (below)" ;;
			*:blocked) echo "PASS t22.cannot-reach-$target" ;;
			*) echo "FAIL t22.cannot-reach-$target the Helpdesk backend can open $target"; fail=1 ;;
		esac
	done
	stack_present t22 "$ERP_BACKEND" || return 0
	erp_db="$(printf 'SELECT DATABASE();\n' | MSYS_NO_PATHCONV=1 docker exec -i -w /home/frappe/frappe-bench "$ERP_BACKEND" bench --site "$ERP_SITE" mariadb 2>/dev/null | tr -d '\r' | awk 'NF {last = $0} END {print last}')"
	[ -n "$erp_db" ] || { echo "UNVERIFIED t22.login-denied-on-erp-database could not read ERPNext's database name"; return 0; }
	for verb in "SELECT 1 FROM \`$erp_db\`.tabCustomer LIMIT 1;" "DELETE FROM \`$erp_db\`.tabCustomer WHERE 1=0;"; do
		out="$(printf '%s\n' "$verb" | MSYS_NO_PATHCONV=1 docker exec -i -w /home/frappe/frappe-bench "$HD_BACKEND" bench --site "$HD_SITE" mariadb 2>&1 || true)"
		code="$(printf '%s' "$out" | sed -n 's/.*ERROR \([0-9][0-9]*\).*/\1/p' | head -n 1)"
		case "$code" in
			1142 | 1044) echo "PASS t22.helpdesk-login-denied-on-erp-database (${verb%% *} error $code)" ;;
			'') echo "FAIL t22.helpdesk-login-denied-on-erp-database the statement was not refused"; fail=1 ;;
			*) echo "FAIL t22.helpdesk-login-denied-on-erp-database error $code, expected 1142 or 1044"; fail=1 ;;
		esac
	done
}

case "${1:-all}" in
	ports) audit_ports ;;
	accounts) audit_accounts ;;
	api) run_tool shared-ops api ;;
	pipeline) audit_pipeline ;;
	sample) run_tool shared-ops sample ;;
	tests) "$SHARED" test 2>&1 | tail -n 4 ;;
	t19) audit_t19 ;;
	t20) audit_t20 ;;
	t21) audit_t21 ;;
	t22) audit_t22 ;;
	phase7) audit_t19; audit_t20; audit_t21; audit_t22 ;;
	all)
		audit_ports
		audit_accounts
		run_tool shared-ops api
		audit_pipeline
		run_tool shared-ops sample
		;;
	*) echo "usage: $0 ports|accounts|api|pipeline|sample|tests|t19|t20|t21|t22|phase7|all" >&2; exit 2 ;;
esac
exit "$fail"
