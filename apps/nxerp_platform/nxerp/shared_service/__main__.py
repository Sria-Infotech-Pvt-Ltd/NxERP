"""Command line of the shared service: `python -m nxerp.shared_service <command>`. No frappe.

	create-accounts            root, one-shot: the database and the accounts (passwords from the environment, never printed)
	migrate                    shared_migrate: apply schema/*.sql, then refresh the per-object grants
	grants sync | show         consumer_grant from the contracts
	views                      generate the per-consumer views, then refresh the per-object grants
	status                     counts only: rows per entity table, cursors, dead letters, metrics
	projector [--once]         pull the owners' feeds and apply them (the only writer of the entity tables)

Output is JSON, one object per line, with counts and names only: never a password, a token or a payload value.
"""

import argparse
import json
import logging
import signal
import sys

from nxerp.shared_service import accounts, config, db, grants, migrate, sqlutil, views


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


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(prog="python -m nxerp.shared_service", description=__doc__)
	sub = parser.add_subparsers(dest="command", required=True)
	sub.add_parser("create-accounts")
	sub.add_parser("migrate")
	grants_parser = sub.add_parser("grants")
	grants_parser.add_argument("action", choices=["sync", "show"])
	sub.add_parser("views")
	sub.add_parser("status")
	projector_parser = sub.add_parser("projector")
	projector_parser.add_argument("--once", action="store_true", help="one pass over every source, then exit")
	return parser


HANDLERS = {
	"create-accounts": cmd_create_accounts,
	"migrate": cmd_migrate,
	"grants": cmd_grants,
	"views": cmd_views,
	"status": cmd_status,
	"projector": cmd_projector,
}


def main(argv=None) -> int:
	args = build_parser().parse_args(argv)
	try:
		return HANDLERS[args.command](args)
	except (db.SettingsError, config.ConfigError, migrate.MigrationError, views.ViewError, ValueError) as exc:
		print(f"{args.command}: {type(exc).__name__}: {exc}", file=sys.stderr)
		return 1


if __name__ == "__main__":
	sys.exit(main())
