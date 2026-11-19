"""Small SQL helpers for the shared service: identifier validation and quoting, and statement splitting. No frappe.

Every table, view and column name that reaches a query is checked against a strict pattern and, by the caller, against a
whitelist built from the ownership contracts: a name never comes from a request or a payload. Values are always bound
parameters. This is the one place that builds SQL text from identifiers, so the bandit B608 suppressions live here.
"""

import re

IDENTIFIER = re.compile(r"^[A-Za-z0-9_]{1,64}$")
# values written into a view definition (a tenant literal): letters, digits and a few separators, never a quote
SAFE_LITERAL = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")


def ident(name: str) -> str:
	"""A validated identifier, quoted with backticks."""
	if not isinstance(name, str) or not IDENTIFIER.fullmatch(name):
		raise ValueError(f"not a safe SQL identifier: {name!r}")
	return f"`{name}`"


def literal(value: str) -> str:
	"""A validated string literal for a generated view (never taken from a request)."""
	if not isinstance(value, str) or not SAFE_LITERAL.fullmatch(value):
		raise ValueError(f"not a safe SQL literal: {value!r}")
	return f"'{value}'"


def select(view: str, columns: list, where: str = "", order_by: str = "", limit: bool = False) -> str:
	"""`SELECT <columns> FROM <view> [WHERE ...] [ORDER BY ...] [LIMIT %s]`; `where` and `order_by` are fixed text from the caller."""
	if not columns:
		raise ValueError("a select needs at least one column")
	text = "SELECT " + ", ".join(ident(c) for c in columns) + " FROM " + ident(view)  # nosec B608 - identifiers validated above
	if where:
		text += " WHERE " + where
	if order_by:
		text += " ORDER BY " + order_by
	if limit:
		text += " LIMIT %s"
	return text


def create_view(view: str, columns: list, table: str, where: str) -> str:
	"""`CREATE OR REPLACE ... VIEW` over one table; `where` is fixed text built by the caller from validated parts."""
	parts = [
		"CREATE OR REPLACE SQL SECURITY DEFINER VIEW ",
		ident(view),
		" AS\nSELECT ",
		", ".join(ident(c) for c in columns),
		"\nFROM ",
		ident(table),
		"\nWHERE ",
		where,
	]
	return "".join(parts)  # every identifier above passed ident()


def count_rows(table: str) -> str:
	"""`SELECT COUNT(*) AS n, <tombstones> FROM <table>` for an entity table (name checked)."""
	return "SELECT COUNT(*) AS n, COALESCE(SUM(deleted_at IS NOT NULL), 0) AS tombstones FROM " + ident(table)  # nosec B608


def split_statements(sql: str) -> list:
	"""Split a SQL script into statements: comments removed, `;` inside quotes and backticks respected."""
	statements, current = [], []
	quote = None
	index = 0
	length = len(sql)
	while index < length:
		char = sql[index]
		nxt = sql[index + 1] if index + 1 < length else ""
		if quote:
			current.append(char)
			if char == "\\" and quote != "`" and nxt:
				current.append(nxt)
				index += 1
			elif char == quote:
				if nxt == quote:  # doubled quote inside a string
					current.append(nxt)
					index += 1
				else:
					quote = None
		elif char in ("'", '"', "`"):
			quote = char
			current.append(char)
		elif char == "-" and nxt == "-" and (index + 2 >= length or sql[index + 2] in " \t\r\n"):
			while index < length and sql[index] != "\n":
				index += 1
			continue
		elif char == "/" and nxt == "*":
			end = sql.find("*/", index + 2)
			index = length if end == -1 else end + 1
		elif char == ";":
			text = "".join(current).strip()
			if text:
				statements.append(text)
			current = []
		else:
			current.append(char)
		index += 1
	tail = "".join(current).strip()
	if tail:
		statements.append(tail)
	return statements
