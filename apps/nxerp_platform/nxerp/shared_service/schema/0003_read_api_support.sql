-- NXDESK shared read database, migration 0003. MariaDB 11.8.
--
-- What the Read API and the projector's metrics need on top of 0001:
--   * consumer_credential: one row per issued app token, holding only a scrypt hash (never the token);
--   * a tenant on each consumer grant, more detail on each audit row, and projector metrics;
--   * ctl_* views: the only control data the Read API account may touch. It has no privilege on any base table, so a flaw in
--     the Read API cannot read or write the entity tables or the control tables behind these views. The views run with the
--     definer's rights (the migrate account); the Read API account is granted SELECT (and INSERT on ctl_read_audit) per view.
--
-- Column names avoid the contract deny-list fragments on purpose (credential_id, not a name containing "token").

ALTER TABLE consumer_grant ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NULL DEFAULT NULL AFTER granted_fields;

ALTER TABLE read_audit ADD COLUMN IF NOT EXISTS acting_user VARCHAR(140) NULL DEFAULT NULL;

ALTER TABLE read_audit ADD COLUMN IF NOT EXISTS ids_hash CHAR(64) NULL DEFAULT NULL;

-- A token is "<credential_id>.<secret>": the id is public and finds the row, the secret is checked against secret_hash.
CREATE TABLE IF NOT EXISTS consumer_credential (
	credential_id CHAR(12) NOT NULL,
	consumer_app VARCHAR(64) NOT NULL,
	salt CHAR(32) NOT NULL,
	secret_hash CHAR(128) NOT NULL,
	scrypt_n INT NOT NULL,
	scrypt_r INT NOT NULL,
	scrypt_p INT NOT NULL,
	created_at DATETIME(6) NOT NULL,
	expires_at DATETIME(6) NULL DEFAULT NULL,
	revoked_at DATETIME(6) NULL DEFAULT NULL,
	PRIMARY KEY (credential_id),
	KEY idx_app (consumer_app, revoked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Projector counters and gauges (applied, skipped_old, dead_letters, lag_seconds, last_success, ...), one row per source and name.
CREATE TABLE IF NOT EXISTS sync_metric (
	source VARCHAR(64) NOT NULL,
	name VARCHAR(64) NOT NULL,
	value DOUBLE NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	PRIMARY KEY (source, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE OR REPLACE SQL SECURITY DEFINER VIEW ctl_consumer_grant AS
SELECT consumer_app, entity_type, granted_fields, tenant_id, contract_version
FROM consumer_grant
WHERE enabled = 1;

CREATE OR REPLACE SQL SECURITY DEFINER VIEW ctl_consumer_credential AS
SELECT credential_id, consumer_app, salt, secret_hash, scrypt_n, scrypt_r, scrypt_p, expires_at
FROM consumer_credential
WHERE revoked_at IS NULL;

CREATE OR REPLACE SQL SECURITY DEFINER VIEW ctl_sync_metric AS
SELECT source, name, value, updated_at
FROM sync_metric;

-- insertable: the Read API writes its audit rows through this view
CREATE OR REPLACE SQL SECURITY DEFINER VIEW ctl_read_audit AS
SELECT read_at, consumer_app, entity_type, entity_id, tenant_id, fields_returned, row_count, request_id, outcome, acting_user, ids_hash
FROM read_audit;
