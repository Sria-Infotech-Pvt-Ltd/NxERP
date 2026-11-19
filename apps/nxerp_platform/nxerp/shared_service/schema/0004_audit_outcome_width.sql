-- Outcome names such as "denied_unauthorized" (19 characters) did not fit VARCHAR(16): widen the column.
ALTER TABLE read_audit MODIFY COLUMN outcome VARCHAR(32) NOT NULL;
