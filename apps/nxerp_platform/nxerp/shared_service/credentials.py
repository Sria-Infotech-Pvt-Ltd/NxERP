"""Per-app tokens for the Read API: issue, verify, rotate, revoke. No frappe. Standard library (`hashlib.scrypt`, `hmac`, `secrets`).

A token is `<credential_id>.<secret>`: a 12-hex-digit public id that finds the row and a random 256-bit secret (64 hex digits). The
database holds only a scrypt hash of the secret (with its own salt and parameters), never the token: a leak of the database does not
leak a usable token. Verification is constant-time (`hmac.compare_digest`), and an unknown id costs the same scrypt work as a wrong
secret, so ids cannot be probed by timing. A token is printed once, when it is issued.
"""

import hashlib
import hmac
import re
import secrets

SCRYPT_N, SCRYPT_R, SCRYPT_P, DKLEN = 2**14, 8, 1, 64
MAXMEM = 64 * 1024 * 1024
TOKEN_PATTERN = re.compile(r"^([0-9a-f]{12})\.([0-9a-f]{64})$")
_DUMMY_SALT = bytes(16)


def hash_secret(secret: str, salt: bytes, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> str:
	return hashlib.scrypt(secret.encode("ascii"), salt=salt, n=n, r=r, p=p, dklen=DKLEN, maxmem=MAXMEM).hex()


def split_token(token) -> tuple | None:
	"""(credential_id, secret) for a well-formed token, otherwise None."""
	match = TOKEN_PATTERN.match(token) if isinstance(token, str) else None
	return (match.group(1), match.group(2)) if match else None


def verify_secret(secret: str, row: dict | None) -> bool:
	"""Constant-time check of a secret against a credential row. `row` None (unknown id) still does the same work and answers False."""
	if row is None:
		hash_secret(secret, _DUMMY_SALT)
		return False
	expected = hash_secret(
		secret, bytes.fromhex(row["salt"]), row["scrypt_n"], row["scrypt_r"], row["scrypt_p"]
	)
	return hmac.compare_digest(expected, row["secret_hash"])


class CredentialError(ValueError):
	"""A token operation that cannot be done (unknown app, nothing to revoke)."""


def _require_consumer(conn, app: str) -> None:
	with conn.cursor() as cur:
		cur.execute(
			"SELECT 1 AS found FROM consumer_grant WHERE consumer_app = %s AND enabled = 1 LIMIT 1", (app,)
		)
		if cur.fetchone() is None:
			raise CredentialError(f"{app} is not a consumer in any enabled grant (run grants sync first)")


def issue(conn, app: str, expires_days: int | None = None) -> dict:
	"""Create a token for an app. Returns {credential_id, token}; the token is not stored and cannot be shown again."""
	_require_consumer(conn, app)
	credential_id = secrets.token_hex(6)
	secret = secrets.token_hex(32)
	salt = secrets.token_bytes(16)
	values = (credential_id, app, salt.hex(), hash_secret(secret, salt), SCRYPT_N, SCRYPT_R, SCRYPT_P)
	with conn.cursor() as cur:
		if expires_days:
			cur.execute(
				"INSERT INTO consumer_credential (credential_id, consumer_app, salt, secret_hash, scrypt_n, scrypt_r, scrypt_p, created_at, expires_at) "
				"VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(6), NOW(6) + INTERVAL %s DAY)",
				(*values, int(expires_days)),
			)
		else:
			cur.execute(
				"INSERT INTO consumer_credential (credential_id, consumer_app, salt, secret_hash, scrypt_n, scrypt_r, scrypt_p, created_at, expires_at) "
				"VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(6), NULL)",
				values,
			)
	conn.commit()
	return {"credential_id": credential_id, "token": f"{credential_id}.{secret}"}


def revoke(conn, app: str | None = None, credential_id: str | None = None) -> int:
	"""Revoke one credential, or every live credential of an app. Returns how many were revoked."""
	if not app and not credential_id:
		raise CredentialError("give an app or a credential id")
	with conn.cursor() as cur:
		if credential_id:
			cur.execute(
				"UPDATE consumer_credential SET revoked_at = NOW(6) WHERE credential_id = %s AND revoked_at IS NULL",
				(credential_id,),
			)
		else:
			cur.execute(
				"UPDATE consumer_credential SET revoked_at = NOW(6) WHERE consumer_app = %s AND revoked_at IS NULL",
				(app,),
			)
		count = cur.rowcount
	conn.commit()
	return count


def rotate(conn, app: str, grace_hours: int = 0) -> dict:
	"""Issue a new token and retire the old ones: at once, or after `grace_hours` so a consumer can switch over."""
	new = issue(conn, app)
	with conn.cursor() as cur:
		if grace_hours > 0:
			cur.execute(
				"UPDATE consumer_credential SET expires_at = NOW(6) + INTERVAL %s HOUR "
				"WHERE consumer_app = %s AND credential_id <> %s AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > NOW(6) + INTERVAL %s HOUR)",
				(int(grace_hours), app, new["credential_id"], int(grace_hours)),
			)
		else:
			cur.execute(
				"UPDATE consumer_credential SET revoked_at = NOW(6) WHERE consumer_app = %s AND credential_id <> %s AND revoked_at IS NULL",
				(app, new["credential_id"]),
			)
	conn.commit()
	return new


def list_credentials(conn) -> list:
	"""Ids, apps and dates only: never a hash."""
	with conn.cursor() as cur:
		cur.execute(
			"SELECT credential_id, consumer_app, created_at, expires_at, revoked_at FROM consumer_credential ORDER BY consumer_app, created_at"
		)
		rows = list(cur.fetchall())
	conn.commit()
	return rows
