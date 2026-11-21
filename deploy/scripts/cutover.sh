#!/usr/bin/env bash
# The operator command line for the cutover from the single-site stack to the isolated stacks (Phase 8B).
#
#   deploy/scripts/cutover.sh <subcommand> [options]          DRY RUN unless --yes is given
#
#   status                              the recorded state and the next undo
#   preflight                           the owner feed answers on the sync network; the projector is paused or re-pointed
#   freeze [--yes] [--queue-timeout S]  source: maintenance mode on, incoming Email Accounts recorded and disabled, outgoing queue drained; prints T0
#   unfreeze [--yes] [--restore-email]  source: maintenance mode off (and, with --restore-email, the recorded incoming accounts back on)
#   backup-source [--yes] [--label L]   backup of the source site (RP0, or RP-erp with --label rp-erp); prints the path
#   clone-hd [--yes] <backup-dir>       restore the backup into the Helpdesk site, uninstall erpnext and payments, prune, reserve the ticket
#                                       numbers, migrate; scheduler and inbound email stay DISABLED (a person enables them)
#   build-id [--yes]                    copy the identity data from the Helpdesk clone into the identity site
#   reconcile                           compare source and Helpdesk site (report with RESULT: PASS or FAIL); read-only
#   delta-export --since T [--yes]      everything created or changed on the Helpdesk site since T, as a bundle
#   delta-import [--yes] <bundle>       replay a bundle into the source site (skip identical, report different, never overwrite)
#   finalize-erp [--yes] --rp-final P   remove Helpdesk and telephony from the old site (needs decision D, a verified RP-final, a typed phrase)
#   move-erp [--yes] <backup-dir>       restore the finance data into the erp stack and compare counts (needs a typed phrase)
#
# Anything that changes data or a site needs --yes. The destructive ones also need a typed phrase: type it when asked, or, without a terminal,
# set NXERP_CUTOVER_CONFIRM to it. Every step prints its undo. Secrets are read from env files and the environment, never printed.
#
# The SOURCE (the old single-site stack) is described by:
#   NXERP_CUTOVER_SOURCE_PROJECT (required)  compose project, e.g. nxerp-scratch
#   NXERP_CUTOVER_SOURCE_SITE (required)     its site name
#   NXERP_CUTOVER_SOURCE_COMPOSE_FILE        default deploy/docker/compose/staging-like/compose.yaml
#   NXERP_CUTOVER_SOURCE_ENV_FILES           optional --env-file list, space separated
#   NXERP_DB_ROOT_PASSWORD                   the source database root password (backup and restore need it)
# Other settings: NXERP_CUTOVER_STATE_DIR (default deploy/env/cutover, git-ignored), NXERP_CUTOVER_TICKET_GAP (default 100000),
# NXERP_CUTOVER_PROJECTOR_REPOINTED=1 (acknowledges that the projector runs against the new owners), NXERP_CUTOVER_DECISION_D=GO,
# NXERP_BACKUP_AGE_RECIPIENT (encrypt backups), SHARED_COMPOSE_PROJECT (default nxerp-shared).
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1
# say where an unexpected failure happened (the message names the command, never its secrets: none are passed on a command line)
trap 'printf "[cutover.sh] FAILED at line %s (exit %s): %s
" "$LINENO" "$?" "$BASH_COMMAND" >&2' ERR

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
ENV_DIR=deploy/env/isolated
STATE_DIR="${NXERP_CUTOVER_STATE_DIR:-deploy/env/cutover}"
STATE="$STATE_DIR/state.env"
BENCH_DIR=/home/frappe/frappe-bench
SRC_PROJECT="${NXERP_CUTOVER_SOURCE_PROJECT:-}"
SRC_SITE="${NXERP_CUTOVER_SOURCE_SITE:-}"
SRC_COMPOSE="${NXERP_CUTOVER_SOURCE_COMPOSE_FILE:-deploy/docker/compose/staging-like/compose.yaml}"
SRC_ENV_FILES="${NXERP_CUTOVER_SOURCE_ENV_FILES:-}"
ERP_COUNT_DOCTYPES="Company Account Customer Supplier Item Sales_Invoice Purchase_Invoice Payment_Entry Journal_Entry GL_Entry"

log() { printf '[cutover.sh] %s\n' "$*" >&2; }
die() { printf '[cutover.sh] ERROR: %s\n' "$*" >&2; exit 1; }
undo() { printf '[cutover.sh] UNDO: %s\n' "$*" >&2; }
plan() { printf '[cutover.sh] DRY RUN: %s\n' "$*" >&2; }

env_value() { [ -f "$1" ] && sed -n "s/^$2=//p" "$1" | head -n 1 | tr -d '\r' || true; }
stack_site() { env_value "$ENV_DIR/$1.env" NXERP_SITE; }

# ---- state: what has been done, so an interrupted run can be resumed or rolled back (no secrets, no personal data) ----
state_set() {
	mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR" 2>/dev/null || true
	touch "$STATE" && chmod 600 "$STATE" 2>/dev/null || true
	grep -v "^$1=" "$STATE" >"$STATE.tmp" 2>/dev/null || true
	printf '%s=%s\n' "$1" "$2" >>"$STATE.tmp"
	mv "$STATE.tmp" "$STATE"
}
state_get() { env_value "$STATE" "$1"; }
step_done() { state_set "STEP_$1" "done@$(date -u +%FT%TZ)"; }

# ---- the source stack (the old single site) and the isolated stacks ----
need_source() {
	[ -n "$SRC_PROJECT" ] || die "set NXERP_CUTOVER_SOURCE_PROJECT (the old stack's compose project)"
	[ -n "$SRC_SITE" ] || die "set NXERP_CUTOVER_SOURCE_SITE (the old site's name)"
}
src_cid() { docker compose -p "$SRC_PROJECT" -f "$SRC_COMPOSE" ps -q backend | head -n 1; }
stack_cid() { docker compose -p "nxerp-$1" ps -q backend | head -n 1; }
# src_bench ARGS...: bench for the source site (same quoting rules as lib.sh bench_site)
src_bench() {
	(
		export NXERP_SITE="$SRC_SITE" NXERP_COMPOSE_FILE="$SRC_COMPOSE" NXERP_COMPOSE_PROJECT="$SRC_PROJECT" NXERP_ENV_FILES="$SRC_ENV_FILES" NXERP_SERVICE=backend
		# shellcheck source=deploy/scripts/lib.sh
		. deploy/scripts/lib.sh
		bench_site "$@"
	)
}
# src_script SCRIPT...: a deploy/scripts/*.sh script against the source stack
src_script() {
	local script="$1"
	shift
	(
		export NXERP_SITE="$SRC_SITE" NXERP_COMPOSE_FILE="$SRC_COMPOSE" NXERP_COMPOSE_PROJECT="$SRC_PROJECT" NXERP_ENV_FILES="$SRC_ENV_FILES" NXERP_SERVICE=backend
		"deploy/scripts/$script" "$@"
	)
}
stk() { deploy/scripts/stack.sh "$@"; }

# site_conf CID SITE KEY: one value from a site's site_config.json ("" when absent). Used for flags, never for secrets on a command line.
site_conf() {
	docker exec "$1" bash -lc "cd $BENCH_DIR && env/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], \"\"))' sites/$2/site_config.json $3"
}

# kwargs JSON for `bench execute`: the whole object is single-quoted for the remote shell
exec_fn() { # TARGET FN JSON  (TARGET: source | a stack name)
	local target="$1" fn="$2" json="$3"
	case "$json" in *"'"*) die "internal: single quote in kwargs" ;; *) ;; esac
	# a space inside the argument is mangled on its way through a Windows docker.exe; Python reads   inside a string as a space
	json="${json// /\\u0020}"
	# stdin from /dev/null: docker would otherwise swallow the rest of a `while read` loop that calls this
	if [ "$target" = source ]; then src_bench execute "$fn" --kwargs "'$json'" </dev/null; else stk "$target" bench execute "$fn" --kwargs "'$json'" </dev/null; fi
}
require_allowed() { # TARGET: the tools refuse without the site flag; check first so the message is ours
	local target="$1" cid site
	if [ "$target" = source ]; then cid="$(src_cid)"; site="$SRC_SITE"; else cid="$(stack_cid "$target")"; site="$(stack_site "$target")"; fi
	[ -n "$cid" ] || die "the $target backend is not running"
	[ "$(site_conf "$cid" "$site" nxerp_cutover_allowed | tr -d '\r')" = 1 ] ||
		die "nxerp_cutover_allowed is not 1 on the $target site. A person sets it on purpose: deploy/scripts/stack.sh $target bench set-config nxerp_cutover_allowed 1"
}

confirm() { # PHRASE: a typed confirmation for destructive steps
	local phrase="$1" typed="${NXERP_CUTOVER_CONFIRM:-}"
	if [ -z "$typed" ] && [ -t 0 ]; then
		printf 'Type exactly "%s" to continue: ' "$phrase" >&2
		read -r typed
	fi
	[ "$typed" = "$phrase" ] || die "confirmation phrase not given (expected: $phrase; without a terminal set NXERP_CUTOVER_CONFIRM)"
}

# incoming Email Accounts of a site, one name per line
incoming_accounts() { # TARGET
	exec_fn "$1" frappe.get_all '{"doctype":"Email Account","filters":{"enable_incoming":1},"pluck":"name"}' |
		tail -n 1 | python -c 'import json,sys; [print(n) for n in json.loads(sys.stdin.read().strip() or "[]")]' | tr -d '\r'
}
set_incoming() { # TARGET NAME 0|1  (straight to the database: saving the document would test the mail server connection)
	[ "$2" = "$(printf '%s' "$2" | tr -d "'\"\\\\")" ] || die "an Email Account name contains a quote or backslash; change it by hand"
	exec_fn "$1" frappe.db.set_value "{\"dt\":\"Email Account\",\"dn\":\"$2\",\"field\":\"enable_incoming\",\"val\":$3}" >/dev/null
	exec_fn "$1" frappe.clear_cache '{}' >/dev/null
}

erp_counts() { # TARGET: "<doctype> <count>" lines for a few finance tables
	local dt n
	for dt in $ERP_COUNT_DOCTYPES; do
		n="$(exec_fn "$1" frappe.db.count "{\"dt\":\"${dt//_/ }\"}" | tail -n 1 | tr -d '\r')"
		n="${n:-0}"
		printf '%s %s\n' "$dt" "$n"
	done
}

# copy the encryption key of a backup's site config into a stack's site, inside the container (the value is never printed). The backup's
# config goes in through stdin: no temporary file is left in the container.
copy_encryption_key() { # BACKUP_DIR STACK
	local cfg cid site code
	cfg="$(find "$1" -maxdepth 1 -name '*site_config_backup.json' | head -n 1)"
	[ -n "$cfg" ] || { log "no site config copy in $1 (an encrypted backup must be unpacked first): the encryption key was NOT copied"; return 1; }
	cid="$(stack_cid "$2")"
	site="$(stack_site "$2")"
	code='import json, sys
src = json.load(sys.stdin)
path = sys.argv[1]
conf = json.load(open(path))
if src.get("encryption_key") and conf.get("encryption_key") != src["encryption_key"]:
    conf["encryption_key"] = src["encryption_key"]
    json.dump(conf, open(path, "w"), indent=1)
    print("encryption key copied into the site config")
else:
    print("encryption key already equal or absent in the backup")'
	docker exec -i -w "$BENCH_DIR" "$cid" env/bin/python -c "$code" "sites/$site/site_config.json" <"$cfg"
}

post_rebuild_hint() {
	log "NEXT (shared layer): re-point its sources to the new owner sites, then rebuild from the owners' new feed heads:"
	log "  deploy/scripts/shared.sh repoint <reviewed-sources-file> ; deploy/scripts/shared.sh rebuild-and-verify    (or: shared.sh rebuild --all ; shared.sh reconcile --full)"
	log "  the owner's feed head: deploy/scripts/stack.sh <stack> bench execute nxerp.cutover.feed_head"
}

# ---- options ----
cmd="${1:-}"
[ -n "$cmd" ] || { sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
shift
yes=0 since='' rp_final='' label=rp0 restore_email=0 queue_timeout=600 arg1=''
while [ $# -gt 0 ]; do
	case "$1" in
		--yes) yes=1 ;;
		--since) since="${2:?--since needs a timestamp}"; shift ;;
		--rp-final) rp_final="${2:?--rp-final needs a path}"; shift ;;
		--label) label="${2:?--label needs a name}"; shift ;;
		--restore-email) restore_email=1 ;;
		--queue-timeout) queue_timeout="${2:?--queue-timeout needs seconds}"; shift ;;
		-*) die "unknown option $1" ;;
		*) arg1="$1" ;;
	esac
	shift
done

# ---------------------------------------------------------------------------------------------------------------------------------
cmd_preflight() {
	local cid ok=1 running code
	cid="$(stack_cid hd)"
	if [ -n "$cid" ]; then
		# 200 = up; 503 = up and in maintenance mode (the freeze does that): both prove the site name resolves and the network path works
		code="$(docker exec "$cid" curl -s -o /dev/null -w '%{http_code}' --max-time 10 -H "X-Frappe-Site-Name: ${SRC_SITE:-unset}" http://erp-backend:8000/api/method/ping || true)"
		if [ "$code" = 200 ] || [ "$code" = 503 ]; then
			log "OK   the owner site answers as erp-backend on the sync network (HTTP $code)"
		else
			log "FAIL the owner site (erp-backend:8000) does not answer from the hd backend; attach the old backend: docker compose -p $SRC_PROJECT -f $SRC_COMPOSE -f deploy/docker/compose/isolated/legacy-erp.override.yaml up -d backend"
			ok=0
		fi
	else
		log "FAIL the hd backend is not running"
		ok=0
	fi
	running="$(docker ps -q --filter "label=com.docker.compose.project=${SHARED_COMPOSE_PROJECT:-nxerp-shared}" --filter "label=com.docker.compose.service=shared-projector" --filter status=running)"
	if [ -z "$running" ]; then
		log "OK   the projector is paused (or the shared layer is not running)"
	elif [ "${NXERP_CUTOVER_PROJECTOR_REPOINTED:-0}" = 1 ]; then
		log "OK   the projector runs, and you said it is re-pointed (NXERP_CUTOVER_PROJECTOR_REPOINTED=1)"
	else
		log "FAIL the projector is running against the old source: pause it with  deploy/scripts/shared.sh stop projector  (or re-point it and set NXERP_CUTOVER_PROJECTOR_REPOINTED=1)"
		ok=0
	fi
	[ "$ok" = 1 ]
}

cmd_status() {
	if [ -f "$STATE" ]; then sed 's/^/  /' "$STATE" >&2; else log "no state recorded yet ($STATE)"; fi
	log "undo, by step:  clone-hd -> deploy/scripts/stack.sh hd drop-site (rehearsal only)  |  freeze -> cutover.sh unfreeze --yes [--restore-email]"
}

cmd_freeze() {
	need_source
	if [ "$yes" != 1 ]; then
		plan "would set nxerp_cutover_allowed 1 and maintenance_mode 1 on $SRC_SITE, record and disable its incoming Email Accounts, drain the outgoing queue (up to ${queue_timeout}s), print T0"
		plan "re-run with --yes to apply"
		return 0
	fi
	[ -z "$(state_get FROZEN)" ] || die "already frozen (T0 $(state_get T0)); unfreeze first or continue with the next step"
	mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR" 2>/dev/null || true
	erp_counts source >"$STATE_DIR/erp-counts-before.txt"
	src_bench set-config nxerp_cutover_allowed 1 >/dev/null
	src_bench set-config maintenance_mode 1 >/dev/null
	local t0 name
	t0="$(date -u +%FT%TZ)"
	state_set T0 "$t0"
	state_set FROZEN 1
	: >"$STATE_DIR/email_accounts.txt"
	chmod 600 "$STATE_DIR/email_accounts.txt" 2>/dev/null || true
	while IFS= read -r name; do
		[ -n "$name" ] || continue
		printf '%s\n' "$name" >>"$STATE_DIR/email_accounts.txt"
		set_incoming source "$name" 0
	done < <(incoming_accounts source)
	log "incoming Email Accounts disabled: $(grep -c . "$STATE_DIR/email_accounts.txt" || true) (names are in $STATE_DIR/email_accounts.txt)"
	if [ "$queue_timeout" -gt 0 ]; then
		local waited=0 left
		while :; do
			src_bench execute frappe.email.queue.flush >/dev/null 2>&1 || true
			left="$(exec_fn source frappe.db.count '{"dt":"Email Queue","filters":{"status":["in",["Not Sent","Sending"]]}}' | tail -n 1 | tr -d '\r')"
			left="${left:-0}" # bench execute prints nothing for a zero
			[ "$left" = 0 ] && break
			[ "$waited" -lt "$queue_timeout" ] || { log "WARN the Email Queue still holds $left message(s) after ${queue_timeout}s (outgoing mail muted?). Decide whether to continue."; break; }
			sleep 10
			waited=$((waited + 10))
		done
		[ "${left:-1}" != 0 ] || log "the Email Queue is empty"
	fi
	step_done freeze
	log "FROZEN. T0 = $t0   (write it down: delta-export --since uses it)"
	undo "deploy/scripts/cutover.sh unfreeze --yes --restore-email"
}

cmd_unfreeze() {
	need_source
	if [ "$yes" != 1 ]; then
		plan "would set maintenance_mode 0 and remove nxerp_cutover_allowed on $SRC_SITE$([ "$restore_email" = 1 ] && printf "; with --restore-email also re-enable the recorded incoming accounts")"
		plan "re-run with --yes to apply"
		return 0
	fi
	src_bench set-config maintenance_mode 0 >/dev/null
	src_bench set-config nxerp_cutover_allowed 0 >/dev/null
	if [ "$restore_email" = 1 ]; then
		local name
		while IFS= read -r name; do
			[ -n "$name" ] || continue
			set_incoming source "$name" 1
		done <"$STATE_DIR/email_accounts.txt"
		log "incoming Email Accounts re-enabled on the source"
	else
		log "incoming Email Accounts on the source were left disabled; with the Helpdesk site NOT polling the same mailbox run: cutover.sh unfreeze --yes --restore-email"
	fi
	state_set FROZEN ''
	step_done unfreeze
	log "unfrozen: users can use the source site again"
	undo "deploy/scripts/cutover.sh freeze --yes"
}

cmd_backup_source() {
	need_source
	if [ "$yes" != 1 ]; then
		plan "would back up $SRC_SITE (database and files, verified; encrypted when NXERP_BACKUP_AGE_RECIPIENT is set) as $label"
		plan "re-run with --yes to apply"
		return 0
	fi
	[ -n "${NXERP_DB_ROOT_PASSWORD:-}" ] || die "NXERP_DB_ROOT_PASSWORD (the source database root password) is not set"
	local out last
	out="$(src_script backup.sh)"
	last="$(printf '%s\n' "$out" | tail -n 1)"
	[ -e "$last" ] || die "backup.sh did not print an existing path"
	state_set "RP_$(printf '%s' "$label" | tr 'a-z-' 'A-Z_')" "$last"
	step_done "backup_$label"
	log "backup ($label): $last   (copy it off the host and keep it encrypted)"
	printf '%s\n' "$last"
	undo "nothing to undo: a backup only adds files. Remove $last yourself when it is no longer needed."
}

cmd_clone_hd() {
	[ -n "$arg1" ] || die "usage: cutover.sh clone-hd [--yes] <backup-dir>"
	[ -d "$arg1" ] || die "$arg1 is not a backup directory (unpack an encrypted backup first, or restore it with restore.sh)"
	if [ "$yes" != 1 ]; then
		plan "would OVERWRITE the Helpdesk site ($(stack_site hd)) with $arg1: restore, copy the encryption key, uninstall erpnext and payments, prune_helpdesk_site, reserve ticket numbers (+${NXERP_CUTOVER_TICKET_GAP:-100000}), migrate, disable the scheduler and incoming email"
		plan "re-run with --yes (and the typed phrase) to apply"
		return 0
	fi
	need_source
	cmd_preflight || die "pre-flight failed: fix the lines marked FAIL, then run again"
	require_allowed hd
	confirm "OVERWRITE HD SITE"
	local hd_site
	hd_site="$(stack_site hd)"
	# the clone's scheduler is disabled on purpose (an earlier run, or the next steps, switch it off): do not let the health check fail on that
	NXERP_REQUIRE_SCHEDULER=0 stk hd restore --yes --no-safety-backup "$arg1"
	copy_encryption_key "$arg1" hd || die "the encryption key could not be copied: encrypted values (mail account passwords) would not open. Stopped."
	local app
	# Nothing may write behind the tools while they work: the scheduler is off and the worker and scheduler containers are stopped.
	# Uninstalling an app queues one job per deleted document (hundreds, and Frappe refuses new work above max_queued_jobs), and a worker
	# running them while `migrate` runs makes the database refuse updates (error 1020). The clone has no use for those jobs: they are purged.
	stk hd bench disable-scheduler
	docker compose -p nxerp-hd stop queue-worker scheduler
	stk hd bench set-config max_queued_jobs 1000000
	for app in erpnext payments; do
		if stk hd bench list-apps | awk '{print $1}' | grep -qx "$app"; then
			stk hd bench uninstall-app "$app" --yes --no-backup || die "uninstall-app $app failed on $hd_site (see the output; nothing was pruned). Undo: NXERP_ALLOW_DESTROY=1 deploy/scripts/stack.sh hd drop-site, then create-site and run clone-hd again."
		fi
	done
	exec_fn hd nxerp.cutover.prune_helpdesk_site '{"dry_run":0}'
	exec_fn hd nxerp.cutover.reserve_naming_series_offset "{\"gap\":${NXERP_CUTOVER_TICKET_GAP:-100000}}"
	stk hd bench purge-jobs
	stk hd bench set-config max_queued_jobs 500
	stk hd bench migrate
	# after_migrate queues the search index rebuild (helpdesk.hooks); the worker starts again now, the scheduler stays off by its site flag
	docker compose -p nxerp-hd start queue-worker scheduler
	local name
	while IFS= read -r name; do
		[ -n "$name" ] || continue
		set_incoming hd "$name" 0
	done < <(incoming_accounts hd)
	step_done clone_hd
	log "Helpdesk site $hd_site holds the clone; scheduler and inbound email are DISABLED until a person enables them (step 8.6)"
	undo "deploy/scripts/cutover.sh unfreeze --yes   (users return to the source; the clone is simply not used). Rehearsal reset: NXERP_ALLOW_DESTROY=1 deploy/scripts/stack.sh hd drop-site"
	post_rebuild_hint
}

cmd_build_id() {
	if [ "$yes" != 1 ]; then
		plan "would export the identity data from the Helpdesk clone and import it into the identity site ($(stack_site id)); the encryption key travels by pipe, not in the file or on a command line"
		plan "re-run with --yes to apply"
		return 0
	fi
	require_allowed hd
	require_allowed id
	local hd_cid id_cid hd_site id_site file="/tmp/nxerp-identity-$$.json" admin_mode='keep'
	hd_cid="$(stack_cid hd)"
	id_cid="$(stack_cid id)"
	hd_site="$(stack_site hd)"
	id_site="$(stack_site id)"
	exec_fn hd nxerp.cutover.identity_export "{\"path\":\"$file\"}"
	docker exec "$hd_cid" cat "$file" | docker exec -i "$id_cid" bash -lc "umask 077; cat >$file"
	docker exec "$hd_cid" bash -lc "cd $BENCH_DIR && env/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1]))[\"encryption_key\"])' sites/$hd_site/site_config.json" |
		docker exec -i "$id_cid" bash -lc "read -r K; export NXERP_CUTOVER_SOURCE_ENCRYPTION_KEY=\$K; cd $BENCH_DIR && bench --site $id_site execute nxerp.cutover.identity_import --kwargs '{\"path\":\"$file\",\"admin_password\":\"$admin_mode\"}'"
	docker exec "$hd_cid" rm -f "$file"
	docker exec "$id_cid" rm -f "$file"
	step_done build_id
	log "identity data copied (counts above); the Administrator password of the identity site was left as it is"
	undo "the import is an upsert and changes only identity rows; to start over rehearse on a fresh id site (stack.sh id drop-site + create-site)"
	post_rebuild_hint
}

cmd_reconcile() {
	need_source
	require_allowed source
	require_allowed hd
	local ts dir hd_cid src_cid_v hd_site
	ts="$(date -u +%Y%m%dT%H%M%SZ)"
	dir="$STATE_DIR/reports/$ts"
	mkdir -p "$dir" && chmod 700 "$dir" 2>/dev/null || true
	hd_cid="$(stack_cid hd)"
	src_cid_v="$(src_cid)"
	hd_site="$(stack_site hd)"
	exec_fn source nxerp.cutover.reconcile "{\"snapshot_path\":\"/tmp/nxerp-snap-source.json\"}" >/dev/null
	exec_fn hd nxerp.cutover.reconcile "{\"snapshot_path\":\"/tmp/nxerp-snap-hd.json\"}" >/dev/null
	# files travel through stdin and stdout, never `docker cp`: that leaves root-owned files the tools' user cannot remove
	docker exec "$src_cid_v" cat /tmp/nxerp-snap-source.json >"$dir/source.json"
	docker exec -i "$hd_cid" sh -c 'cat >/tmp/nxerp-snap-source.json' <"$dir/source.json"
	exec_fn hd nxerp.cutover.reconcile '{"snapshot_path":"/tmp/nxerp-snap-source.json","mode":"compare","other":"/tmp/nxerp-snap-hd.json","report":"/tmp/nxerp-reconcile-report.md"}' >/dev/null || true
	docker exec "$hd_cid" cat /tmp/nxerp-reconcile-report.md >"$dir/report.md"
	docker exec "$hd_cid" rm -f /tmp/nxerp-snap-source.json /tmp/nxerp-snap-hd.json /tmp/nxerp-reconcile-report.md
	docker exec "$src_cid_v" rm -f /tmp/nxerp-snap-source.json
	# the ERP side of the source must be unchanged since the freeze
	if [ -f "$STATE_DIR/erp-counts-before.txt" ]; then
		erp_counts source >"$dir/erp-counts-after.txt"
		if diff -q "$STATE_DIR/erp-counts-before.txt" "$dir/erp-counts-after.txt" >/dev/null; then
			printf '\nERP counts on the source: unchanged since the freeze\n' >>"$dir/report.md"
		else
			printf '\nERP counts on the source: CHANGED since the freeze\nRESULT: FAIL\n' >>"$dir/report.md"
		fi
	fi
	grep -E '^RESULT:' "$dir/report.md" | tee /dev/stderr >/dev/null
	log "report: $dir/report.md   (hd site: $hd_site; no names or values inside, only counts and hashes)"
	step_done reconcile
	! grep -q '^RESULT: FAIL' "$dir/report.md"
}

cmd_delta_export() {
	[ -n "$since" ] || die "usage: cutover.sh delta-export --since <T0 as printed by freeze, e.g. 2026-11-20T10:00:00Z (converted to the site's timezone)> [--yes]"
	if [ "$yes" != 1 ]; then
		plan "would export everything created or changed on the Helpdesk site since $since into a bundle under $STATE_DIR/bundles"
		plan "re-run with --yes to apply"
		return 0
	fi
	require_allowed hd
	local ts dir hd_cid remote
	ts="$(date -u +%Y%m%dT%H%M%SZ)"
	dir="$STATE_DIR/bundles/delta-$ts"
	remote="/tmp/nxerp-delta-$ts"
	hd_cid="$(stack_cid hd)"
	mkdir -p "$STATE_DIR/bundles" && chmod 700 "$STATE_DIR/bundles" 2>/dev/null || true
	exec_fn hd nxerp.cutover.delta_export "{\"since\":\"$since\",\"path\":\"$remote\"}"
	docker exec "$hd_cid" tar -C /tmp -cf - "nxerp-delta-$ts" | tar -C "$STATE_DIR/bundles" -xf -
	mv "$STATE_DIR/bundles/nxerp-delta-$ts" "$dir"
	docker exec "$hd_cid" rm -rf "$remote"
	step_done delta_export
	log "bundle: $dir"
	printf '%s\n' "$dir"
	undo "nothing to undo: a bundle only adds files. Replay it with: deploy/scripts/cutover.sh delta-import --yes $dir"
}

cmd_delta_import() {
	[ -n "$arg1" ] || die "usage: cutover.sh delta-import [--yes] <bundle>"
	[ -f "$arg1/bundle.json" ] || die "$arg1 is not a bundle (no bundle.json)"
	if [ "$yes" != 1 ]; then
		plan "would replay $arg1 into $SRC_SITE: add what is missing, skip what is identical, report what differs (never overwrite)"
		plan "re-run with --yes (and the typed phrase) to apply"
		return 0
	fi
	need_source
	require_allowed source
	confirm "REPLAY INTO SOURCE"
	local cid remote out
	cid="$(src_cid)"
	remote="/tmp/$(basename "$arg1")"
	tar -C "$(dirname "$arg1")" -cf - "$(basename "$arg1")" | docker exec -i "$cid" tar -C /tmp -xf -
	out="$(exec_fn source nxerp.cutover.delta_import "{\"path\":\"$remote\"}")"
	printf '%s\n' "$out"
	docker exec "$cid" rm -rf "$remote"
	step_done delta_import
	if printf '%s' "$out" | grep -q '"conflicts": [1-9]'; then
		log "CONFLICTS were reported: a person decides each one; nothing was overwritten"
		exit 3
	fi
	undo "the replay only ADDS documents. To remove them, restore RP0 on the source (docs/runbooks/isolation-rollback.md)."
}

cmd_finalize_erp() {
	[ -n "$rp_final" ] || die "usage: cutover.sh finalize-erp [--yes] --rp-final <RP-final path>"
	[ -e "$rp_final" ] || die "--rp-final path does not exist: $rp_final"
	if [ -d "$rp_final" ]; then
		[ -f "$rp_final/SHA256SUMS" ] || die "no SHA256SUMS in $rp_final: refusing an unverified restore point"
		(cd "$rp_final" && sha256sum -c --quiet SHA256SUMS) || die "checksums of $rp_final do not verify"
	else
		[ -f "$rp_final.sha256" ] || die "$rp_final.sha256 is missing: refusing an unverified restore point"
		(cd "$(dirname "$rp_final")" && sha256sum -c --quiet "$(basename "$rp_final").sha256") || die "checksum of $rp_final does not verify"
	fi
	log "OK   RP-final checksums verify"
	if [ "$yes" != 1 ]; then
		plan "would uninstall helpdesk and telephony from $SRC_SITE (DESTRUCTIVE; there is no rollback after this)"
		plan "re-run with --yes, NXERP_CUTOVER_DECISION_D=GO and the typed phrase"
		return 0
	fi
	need_source
	[ "${NXERP_CUTOVER_DECISION_D:-}" = GO ] || die "decision point D is not recorded: set NXERP_CUTOVER_DECISION_D=GO only after the human replied DECISION D: GO"
	confirm "REMOVE HELPDESK FROM OLD SITE"
	local app
	for app in helpdesk telephony; do
		if src_bench list-apps | awk '{print $1}' | grep -qx "$app"; then
			src_bench uninstall-app "$app" --yes --no-backup || die "uninstall-app $app failed; the site may be half-changed. Restore RP-final: deploy/scripts/restore.sh --yes $rp_final"
		fi
	done
	step_done finalize_erp
	log "Helpdesk and telephony removed from $SRC_SITE"
	undo "none after decision D. Disaster recovery only: restore RP-final ($rp_final) with deploy/scripts/restore.sh --yes."
}

cmd_move_erp() {
	[ -n "$arg1" ] || die "usage: cutover.sh move-erp [--yes] <backup-dir>"
	[ -d "$arg1" ] || die "$arg1 is not a backup directory"
	if [ "$yes" != 1 ]; then
		plan "would restore $arg1 into the erp stack ($(stack_site erp)), copy the encryption key, migrate, and compare finance counts with the source"
		plan "re-run with --yes (and the typed phrase) to apply"
		return 0
	fi
	need_source
	cmd_preflight || die "pre-flight failed: fix the lines marked FAIL, then run again"
	confirm "MOVE ERP"
	stk erp restore --yes --no-safety-backup "$arg1"
	copy_encryption_key "$arg1" erp || die "the encryption key could not be copied; stopped"
	stk erp bench migrate
	local after before="$STATE_DIR/erp-counts-before.txt"
	after="$STATE_DIR/erp-counts-after-move.txt"
	erp_counts erp >"$after"
	if [ -f "$before" ] && diff -q "$before" "$after" >/dev/null; then
		log "OK   finance counts on the erp stack equal the source's counts at the freeze"
	else
		die "finance counts differ (or no counts were recorded at the freeze): compare $before with $after before going on"
	fi
	step_done move_erp
	log "the erp site holds the finance data. Next: trial balance and ten invoices (accountant), then point erp.<domain> at the new stack"
	undo "docker compose -p $SRC_PROJECT start   (the old stack is kept for 30 days); point erp.<domain> back; re-enter finance records made on the new site by hand"
	post_rebuild_hint
}

case "$cmd" in
	status) cmd_status ;;
	preflight) need_source; cmd_preflight ;;
	freeze) cmd_freeze ;;
	unfreeze) cmd_unfreeze ;;
	backup-source) cmd_backup_source ;;
	clone-hd) cmd_clone_hd ;;
	build-id) cmd_build_id ;;
	reconcile) cmd_reconcile ;;
	delta-export) cmd_delta_export ;;
	delta-import) cmd_delta_import ;;
	finalize-erp) cmd_finalize_erp ;;
	move-erp) cmd_move_erp ;;
	*) die "unknown subcommand '$cmd' (run without arguments for the list)" ;;
esac
