"""Command line of the shared service: `python -m nxerp.shared_service <command>`. No frappe.

	create-accounts            root, one-shot: the database and the accounts (passwords from the environment, never printed)
	migrate                    shared_migrate: apply schema/*.sql, then refresh the per-object grants
	grants sync | show         consumer_grant from the contracts
	views                      generate the per-consumer views, then refresh the per-object grants
	tokens create|rotate|revoke|list   per-app Read API tokens (the token is shown once)
	status                     counts only: rows per entity table, cursors, dead letters, metrics
	projector [--once]         pull the owners' feeds and apply them (the only writer of the entity tables)
	reconcile --recent|--full  compare with the owners and repair drift (owner to shared, never the reverse)
	reconcile-loop             the reconciler process: recent scan hourly, full compare nightly
	rebuild --source X|--all   snapshot every entity, replay the events since, and report the drift left

Output is JSON, one object per line, with counts and names only: never a password, a token or a payload value.
"""

import argparse
import json
import logging
import signal
import sys

from nxerp.shared_service import accounts, config, credentials, db, grants, migrate, sqlutil, views


def emit(**values) -> None:
	print(json.dumps(values, default=str, sort_keys=True))


def cmd_create_accounts(args) -> int:
	conn = db.connect(db.settings_from_env("root"), database=None)
	try:
		created = accounts.create_accounts(conn)
	finally:
		conn.close()
	emit(command="create-accounts", accounts=created)
	return 0


def cmd_migrate(args) -> int:
	conn = db.connect(db.settings_from_env("migrate"))
	try:
		applied = migrate.apply_migrations(conn)
		summary = accounts.apply_object_grants(conn)
	finally:
		conn.close()
	emit(command="migrate", applied=applied, grants=summary)
	return 0


def cmd_grants(args) -> int:
	conn = db.connect(db.settings_from_env("migrate"))
	try:
		if args.action == "sync":
			emit(command="grants sync", **grants.sync(conn))
		else:
			for row in grants.read_grants(conn, enabled_only=False):
				emit(**row)
	finally:
		conn.close()
	return 0


def cmd_views(args) -> int:
	settings = db.settings_from_env("migrate")
	conn = db.connect(settings)
	try:
		desired = views.render_all(grants.read_grants(conn))
		result = views.apply_views(conn, desired, settings.name, accounts.all_accounts())
		summary = accounts.apply_object_grants(conn)
	finally:
		conn.close()
	emit(command="views", **result, grants=summary)
	return 0


def cmd_status(args) -> int:
	from nxerp.shared import registry
	from nxerp.shared_service.schema.generate_columns import table_name

	conn = db.connect(db.settings_from_env("projector"))
	try:
		with conn.cursor() as cur:
			counts = {}
			for entity_type in registry.load_contracts():
				table = table_name(entity_type)
				cur.execute(sqlutil.count_rows(table))
				row = cur.fetchone()
				counts[table] = {"rows": int(row["n"]), "tombstones": int(row["tombstones"])}
			cur.execute("SELECT source_app, last_seq, state, updated_at FROM sync_cursor ORDER BY source_app")
			cursors = cur.fetchall()
			cur.execute("SELECT COUNT(*) AS n FROM sync_dead_letter WHERE resolved_at IS NULL")
			dead = int(cur.fetchone()["n"])
			cur.execute("SELECT source, name, value FROM sync_metric ORDER BY source, name")
			metrics = {f"{r['source']}.{r['name']}": r["value"] for r in cur.fetchall()}
		conn.commit()
	finally:
		conn.close()
	emit(command="status", tables=counts, cursors=cursors, unresolved_dead_letters=dead, metrics=metrics)
	return 0


def cmd_tokens(args) -> int:
	"""Manage the Read API tokens (the migrate account). A token is shown once, when it is issued or rotated, and cannot be shown again."""
	conn = db.connect(db.settings_from_env("migrate"))
	try:
		if args.action == "create":
			emit(
				command="tokens create",
				app=args.app,
				**credentials.issue(conn, _need(args.app, "--app"), args.expires_days),
			)
		elif args.action == "rotate":
			emit(
				command="tokens rotate",
				app=args.app,
				**credentials.rotate(conn, _need(args.app, "--app"), args.grace_hours),
			)
		elif args.action == "revoke":
			emit(
				command="tokens revoke",
				revoked=credentials.revoke(conn, app=args.app, credential_id=args.credential_id),
			)
		else:
			for row in credentials.list_credentials(conn):
				emit(**row)
	finally:
		conn.close()
	return 0


def _need(value, flag: str):
	if not value:
		raise ValueError(f"{flag} is required")
	return value


def cmd_projector(args) -> int:
	"""Run the projector until stopped (SIGTERM or SIGINT), or one pass with --once."""
	from nxerp.shared_service.projector import Projector

	logging.basicConfig(
		level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s %(message)s"
	)
	settings = db.settings_from_env("projector")
	projector = Projector(lambda: db.connect(settings), config.load_sources())
	if args.once:
		emit(command="projector", **{"passes": projector.run_once()})
		return 0

	def stop(signum, frame):
		projector.stopping = True

	signal.signal(signal.SIGTERM, stop)
	signal.signal(signal.SIGINT, stop)
	projector.run_forever()
	return 0


def _ops_setup():
	logging.basicConfig(
		level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s %(message)s"
	)
	settings = db.settings_from_env("projector")
	return (lambda: db.connect(settings)), config.load_sources()


def cmd_reconcile(args) -> int:
	from nxerp.shared_service.reconcile import HashFunctionMismatch, Reconciler

	connect, sources = _ops_setup()
	try:
		report = Reconciler(connect, sources).run("recent" if args.recent else "full", only=args.source)
	except HashFunctionMismatch as exc:
		emit(command="reconcile", status="failed", error=str(exc))
		return 2
	emit(command="reconcile", **report)
	return 0 if report["refused"] == 0 and all(s["status"] == "ok" for s in report["sources"].values()) else 1


def cmd_reconcile_loop(args) -> int:
	"""The reconciler process: a recent scan every hour, a full compare nightly (SHARED_RECONCILE_FULL_HOUR, UTC, default 3)."""
	import os

	from nxerp.shared_service.reconcile import Reconciler, Schedule, run_schedule

	connect, sources = _ops_setup()
	state = {"stop": False}

	def stop(signum, frame):
		state["stop"] = True

	signal.signal(signal.SIGTERM, stop)
	signal.signal(signal.SIGINT, stop)
	schedule = Schedule(full_hour=int(os.environ.get("SHARED_RECONCILE_FULL_HOUR", "3")))
	run_schedule(Reconciler(connect, sources), schedule, stop=lambda: state["stop"])
	return 0


def cmd_rebuild(args) -> int:
	from nxerp.shared_service.rebuild import RebuildError, rebuild

	connect, sources = _ops_setup()
	try:
		report = rebuild(connect, sources, only=None if args.all else args.source, relay_wait=args.relay_wait)
	except RebuildError as exc:
		emit(command="rebuild", **exc.report, error=str(exc))
		return 1
	emit(command="rebuild", **report)
	return 0 if all(s["drift_after"] == 0 for s in report["sources"].values()) else 1


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(prog="python -m nxerp.shared_service", description=__doc__)
	sub = parser.add_subparsers(dest="command", required=True)
	sub.add_parser("create-accounts")
	sub.add_parser("migrate")
	grants_parser = sub.add_parser("grants")
	grants_parser.add_argument("action", choices=["sync", "show"])
	sub.add_parser("views")
	tokens_parser = sub.add_parser("tokens")
	tokens_parser.add_argument("action", choices=["create", "rotate", "revoke", "list"])
	tokens_parser.add_argument("--app", help="the consuming app (a consumer in an enabled grant)")
	tokens_parser.add_argument("--credential-id", help="revoke just this credential")
	tokens_parser.add_argument(
		"--expires-days", type=int, help="create: the token expires after this many days"
	)
	tokens_parser.add_argument(
		"--grace-hours", type=int, default=0, help="rotate: keep the old token valid for this many hours"
	)
	sub.add_parser("status")
	reconcile_parser = sub.add_parser("reconcile")
	mode = reconcile_parser.add_mutually_exclusive_group(required=True)
	mode.add_argument("--recent", action="store_true", help="documents modified since the last scan (hourly)")
	mode.add_argument("--full", action="store_true", help="every id and payload hash (nightly)")
	reconcile_parser.add_argument("--source", help="only this source")
	sub.add_parser("reconcile-loop")
	rebuild_parser = sub.add_parser("rebuild")
	target = rebuild_parser.add_mutually_exclusive_group(required=True)
	target.add_argument("--source", help="rebuild this source")
	target.add_argument("--all", action="store_true", help="rebuild every source")
	rebuild_parser.add_argument(
		"--relay-wait", type=float, default=90.0, help="seconds to wait for the owner's relay (default 90)"
	)
	projector_parser = sub.add_parser("projector")
	projector_parser.add_argument("--once", action="store_true", help="one pass over every source, then exit")
	return parser


HANDLERS = {
	"create-accounts": cmd_create_accounts,
	"migrate": cmd_migrate,
	"grants": cmd_grants,
	"views": cmd_views,
	"tokens": cmd_tokens,
	"status": cmd_status,
	"projector": cmd_projector,
	"reconcile": cmd_reconcile,
	"reconcile-loop": cmd_reconcile_loop,
	"rebuild": cmd_rebuild,
}


def main(argv=None) -> int:
	args = build_parser().parse_args(argv)
	try:
		return HANDLERS[args.command](args)
	except (
		db.SettingsError,
		config.ConfigError,
		migrate.MigrationError,
		views.ViewError,
		credentials.CredentialError,
		ValueError,
	) as exc:
		print(f"{args.command}: {type(exc).__name__}: {exc}", file=sys.stderr)
		return 1


if __name__ == "__main__":
	sys.exit(main())
