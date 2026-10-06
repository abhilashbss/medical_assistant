-- Migration: Create dose_logs table
-- Description: Append-only dose adherence log recording timestamped taken/skipped
--              events per prescription. One row per dose event; rows are never
--              updated or back-dated-edited.
-- Created: 2026-09-30

CREATE TABLE IF NOT EXISTS dose_logs (
    -- Primary key: unique identifier for each dose log event
    id TEXT PRIMARY KEY,

    -- Reference to the prescription this dose belongs to (required)
    prescription_id TEXT NOT NULL,

    -- Adherence event: 'taken' or 'skipped'
    event TEXT NOT NULL,

    -- ISO 8601 timestamp with timezone of the event (required)
    timestamp TEXT NOT NULL,

    -- Optional free-text notes
    notes TEXT,

    -- Foreign key constraint linking to prescriptions table
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE,

    -- Constraint: event must be one of the valid adherence values
    CONSTRAINT chk_dose_log_event CHECK (event IN ('taken', 'skipped'))
);

-- Index on prescription_id for efficient per-medication history lookups
CREATE INDEX IF NOT EXISTS idx_dose_logs_prescription ON dose_logs(prescription_id);

-- Index on timestamp descending for adherence history ordered by time
CREATE INDEX IF NOT EXISTS idx_dose_logs_timestamp ON dose_logs(timestamp DESC);