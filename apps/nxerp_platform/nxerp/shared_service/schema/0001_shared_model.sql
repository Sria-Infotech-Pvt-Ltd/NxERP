-- NXDESK shared read database, migration 0001. MariaDB 11.8.
--
-- DERIVED data only. Nothing here is authoritative: every row names its owner (source_app) and the owner's
-- version stamp, and the whole database can be dropped and rebuilt from the owners (snapshot, then replay).
-- Only the projector writes the entity tables (Phase 4); apps never read them by SQL, only through the Read API.
--
-- The entity tables below are generated from the ownership contracts by schema/generate_columns.py
-- (python generate_columns.py --ddl). Do not edit them by hand: change the contract, regenerate, and
-- tests/test_schema_matches_contracts.py checks the two agree.
--
-- Rules this file keeps:
--   * key (source_app, entity_id): the owner's id is never rewritten;
--   * version stamp (source_modified, last_seq): an incoming event is applied only when it is newer;
--   * tombstones: a delete sets deleted_at; views hide them; they are purged after 90 days;
--   * no foreign keys between entities (the owners' databases are separate, a child may arrive before its parent);
--   * no secret, password, token or class S3 column anywhere;
--   * this file creates no account and grants nothing (accounts and grants are Phase 4).
--
-- Idempotent upsert, as the projector will run it inside one transaction together with the cursor update
-- (shown for entity_customer; every entity table has the same system columns). MariaDB syntax: VALUES(col),
-- not the MySQL 8 "AS new" row alias. The business columns and the other stamps are assigned FIRST, each guarded by
-- the comparison on the OLD stamps; source_modified and last_seq are assigned LAST, because a column assigned
-- earlier in ON DUPLICATE KEY UPDATE is already changed when a later assignment reads it.
--   INSERT INTO entity_customer (source_app, entity_id, tenant_id, <fields>, source_modified, last_seq,
--                                contract_version, deleted_at, synced_at)
--   VALUES (...)
--   ON DUPLICATE KEY UPDATE
--     <field> = IF((VALUES(source_modified), VALUES(last_seq)) > (source_modified, last_seq), VALUES(<field>), <field>),
--     (deleted_at, synced_at, contract_version likewise),
--     source_modified = GREATEST(source_modified, VALUES(source_modified)),
--     last_seq = IF(VALUES(source_modified) > source_modified
--                   OR (VALUES(source_modified) = source_modified AND VALUES(last_seq) > last_seq),
--                   VALUES(last_seq), last_seq);
--   INSERT INTO sync_cursor ... ON DUPLICATE KEY UPDATE last_seq = VALUES(last_seq), updated_at = VALUES(updated_at);
--   COMMIT;
-- Verified on MariaDB 11.8.9 by scripts/check_shared_ddl.sh (2026-11-19): the file runs twice, an older event is
-- ignored, a replay is a no-op, a newer event wins, a tombstone sticks and a late older event cannot resurrect it.

-- ---------------------------------------------------------------------------------------------------------
-- Entity tables (generated)
-- ---------------------------------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS entity_contact (
	source_app VARCHAR(64) NOT NULL,
	entity_id VARCHAR(140) NOT NULL,
	tenant_id VARCHAR(64) NOT NULL,
	customer_id VARCHAR(140) NULL DEFAULT NULL,
	full_name VARCHAR(140) NULL DEFAULT NULL,
	email VARCHAR(140) NULL DEFAULT NULL,
	phone VARCHAR(140) NULL DEFAULT NULL,
	is_primary TINYINT(1) NULL DEFAULT NULL,
	source_modified DATETIME(6) NOT NULL,
	last_seq BIGINT NOT NULL,
	contract_version INT NOT NULL,
	deleted_at DATETIME(6) NULL DEFAULT NULL,
	synced_at DATETIME(6) NOT NULL,
	PRIMARY KEY (source_app, entity_id),
	KEY idx_live (tenant_id, deleted_at),
	KEY idx_customer_id (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS entity_customer (
	source_app VARCHAR(64) NOT NULL,
	entity_id VARCHAR(140) NOT NULL,
	tenant_id VARCHAR(64) NOT NULL,
	display_name VARCHAR(140) NULL DEFAULT NULL,
	customer_type VARCHAR(140) NULL DEFAULT NULL,
	customer_group VARCHAR(140) NULL DEFAULT NULL,
	territory VARCHAR(140) NULL DEFAULT NULL,
	disabled TINYINT(1) NULL DEFAULT NULL,
	primary_contact_id VARCHAR(140) NULL DEFAULT NULL,
	source_modified DATETIME(6) NOT NULL,
	last_seq BIGINT NOT NULL,
	contract_version INT NOT NULL,
	deleted_at DATETIME(6) NULL DEFAULT NULL,
	synced_at DATETIME(6) NOT NULL,
	PRIMARY KEY (source_app, entity_id),
	KEY idx_live (tenant_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS entity_employee_ref (
	source_app VARCHAR(64) NOT NULL,
	entity_id VARCHAR(140) NOT NULL,
	tenant_id VARCHAR(64) NOT NULL,
	display_name VARCHAR(140) NULL DEFAULT NULL,
	department VARCHAR(140) NULL DEFAULT NULL,
	designation VARCHAR(140) NULL DEFAULT NULL,
	manager_employee_id VARCHAR(140) NULL DEFAULT NULL,
	active TINYINT(1) NULL DEFAULT NULL,
	source_modified DATETIME(6) NOT NULL,
	last_seq BIGINT NOT NULL,
	contract_version INT NOT NULL,
	deleted_at DATETIME(6) NULL DEFAULT NULL,
	synced_at DATETIME(6) NOT NULL,
	PRIMARY KEY (source_app, entity_id),
	KEY idx_live (tenant_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS entity_org_unit (
	source_app VARCHAR(64) NOT NULL,
	entity_id VARCHAR(140) NOT NULL,
	tenant_id VARCHAR(64) NOT NULL,
	name VARCHAR(140) NULL DEFAULT NULL,
	parent_id VARCHAR(140) NULL DEFAULT NULL,
	disabled TINYINT(1) NULL DEFAULT NULL,
	source_modified DATETIME(6) NOT NULL,
	last_seq BIGINT NOT NULL,
	contract_version INT NOT NULL,
	deleted_at DATETIME(6) NULL DEFAULT NULL,
	synced_at DATETIME(6) NOT NULL,
	PRIMARY KEY (source_app, entity_id),
	KEY idx_live (tenant_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS entity_project_ref (
	source_app VARCHAR(64) NOT NULL,
	entity_id VARCHAR(140) NOT NULL,
	tenant_id VARCHAR(64) NOT NULL,
	name VARCHAR(140) NULL DEFAULT NULL,
	status VARCHAR(140) NULL DEFAULT NULL,
	owner_user_id VARCHAR(140) NULL DEFAULT NULL,
	source_modified DATETIME(6) NOT NULL,
	last_seq BIGINT NOT NULL,
	contract_version INT NOT NULL,
	deleted_at DATETIME(6) NULL DEFAULT NULL,
	synced_at DATETIME(6) NOT NULL,
	PRIMARY KEY (source_app, entity_id),
	KEY idx_live (tenant_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS entity_ticket_summary (
	source_app VARCHAR(64) NOT NULL,
	entity_id VARCHAR(140) NOT NULL,
	tenant_id VARCHAR(64) NOT NULL,
	customer_id VARCHAR(140) NULL DEFAULT NULL,
	status VARCHAR(140) NULL DEFAULT NULL,
	priority VARCHAR(140) NULL DEFAULT NULL,
	opened_at DATETIME(6) NULL DEFAULT NULL,
	resolved_at DATETIME(6) NULL DEFAULT NULL,
	assignee_user_id VARCHAR(140) NULL DEFAULT NULL,
	source_modified DATETIME(6) NOT NULL,
	last_seq BIGINT NOT NULL,
	contract_version INT NOT NULL,
	deleted_at DATETIME(6) NULL DEFAULT NULL,
	synced_at DATETIME(6) NOT NULL,
	PRIMARY KEY (source_app, entity_id),
	KEY idx_live (tenant_id, deleted_at),
	KEY idx_customer_id (customer_id),
	KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS entity_user_ref (
	source_app VARCHAR(64) NOT NULL,
	entity_id VARCHAR(140) NOT NULL,
	tenant_id VARCHAR(64) NOT NULL,
	display_name VARCHAR(140) NULL DEFAULT NULL,
	enabled TINYINT(1) NULL DEFAULT NULL,
	user_type VARCHAR(140) NULL DEFAULT NULL,
	apps_granted VARCHAR(300) NULL DEFAULT NULL,
	source_modified DATETIME(6) NOT NULL,
	last_seq BIGINT NOT NULL,
	contract_version INT NOT NULL,
	deleted_at DATETIME(6) NULL DEFAULT NULL,
	synced_at DATETIME(6) NOT NULL,
	PRIMARY KEY (source_app, entity_id),
	KEY idx_live (tenant_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------------------------------------
-- Control tables
-- ---------------------------------------------------------------------------------------------------------

-- One cursor per owner feed. It lives in this database so it moves in the same transaction as the applied rows.
CREATE TABLE IF NOT EXISTS sync_cursor (
	source_app VARCHAR(64) NOT NULL,
	last_seq BIGINT NOT NULL DEFAULT 0,
	last_event_id VARCHAR(64) NULL DEFAULT NULL,
	snapshot_seq BIGINT NULL DEFAULT NULL,
	state VARCHAR(16) NOT NULL DEFAULT 'live',
	updated_at DATETIME(6) NOT NULL,
	PRIMARY KEY (source_app)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Events the projector could not apply. Kept until resolved, then 30 days.
CREATE TABLE IF NOT EXISTS sync_dead_letter (
	id BIGINT NOT NULL AUTO_INCREMENT,
	event_id VARCHAR(64) NOT NULL,
	source_app VARCHAR(64) NOT NULL,
	entity_type VARCHAR(40) NOT NULL,
	entity_id VARCHAR(140) NOT NULL,
	seq BIGINT NULL DEFAULT NULL,
	event_json JSON NOT NULL,
	error_text TEXT NOT NULL,
	attempts INT NOT NULL DEFAULT 1,
	created_at DATETIME(6) NOT NULL,
	resolved_at DATETIME(6) NULL DEFAULT NULL,
	PRIMARY KEY (id),
	UNIQUE KEY uq_event (source_app, event_id),
	KEY idx_unresolved (resolved_at, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Which fields of which entity an app may read through the Read API (generated from the contracts' consumers).
-- The per-app credential is checked by the Read API; where its hash is kept is decided in Phase 4, not here.
CREATE TABLE IF NOT EXISTS consumer_grant (
	consumer_app VARCHAR(64) NOT NULL,
	entity_type VARCHAR(40) NOT NULL,
	granted_fields JSON NOT NULL,
	contract_version INT NOT NULL,
	enabled TINYINT(1) NOT NULL DEFAULT 1,
	updated_at DATETIME(6) NOT NULL,
	PRIMARY KEY (consumer_app, entity_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Every Read API call (who read what). Kept 400 days (ASSUMPTION; a compliance owner decides).
CREATE TABLE IF NOT EXISTS read_audit (
	id BIGINT NOT NULL AUTO_INCREMENT,
	read_at DATETIME(6) NOT NULL,
	consumer_app VARCHAR(64) NOT NULL,
	entity_type VARCHAR(40) NOT NULL,
	entity_id VARCHAR(140) NULL DEFAULT NULL,
	tenant_id VARCHAR(64) NULL DEFAULT NULL,
	fields_returned JSON NULL DEFAULT NULL,
	row_count INT NOT NULL DEFAULT 0,
	request_id VARCHAR(64) NULL DEFAULT NULL,
	outcome VARCHAR(16) NOT NULL,
	PRIMARY KEY (id),
	KEY idx_read_at (read_at),
	KEY idx_consumer (consumer_app, read_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The contracts the shared layer was last built from (a hash of each contract file), so drift is visible.
CREATE TABLE IF NOT EXISTS contract_registry (
	entity_type VARCHAR(40) NOT NULL,
	contract_version INT NOT NULL,
	owner_app VARCHAR(64) NOT NULL,
	status VARCHAR(16) NOT NULL,
	contract_sha256 CHAR(64) NOT NULL,
	loaded_at DATETIME(6) NOT NULL,
	PRIMARY KEY (entity_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
