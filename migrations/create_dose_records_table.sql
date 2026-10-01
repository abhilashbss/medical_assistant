-- Migration: Create dose_records table
-- Description: Defines the schema for tracking medication dose adherence
<<<<<<< HEAD
-- Created: 2026-09-24

-- Create dose_records table with all required fields
CREATE TABLE IF NOT EXISTS dose_records (
    -- Primary key: unique identifier for each dose record
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' || '4' || substr(lower(hex(randomblob(2))), 2) || '-' || substr('89ab', abs(random()) % 4 + 1, 1) || substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6)))),

    -- Reference to the medication this dose belongs to (required)
    medication_id UUID NOT NULL,

    -- Date the dose was taken/scheduled (required)
    date TEXT NOT NULL,

    -- Exact timestamp when dose was recorded (auto-set if not provided)
    timestamp TEXT,

    -- Dose status: 'taken' for completed doses, 'skipped' for intentionally skipped, 'missed' for forgotten doses
    status TEXT DEFAULT 'taken' NOT NULL,

    -- Foreign key constraint linking to medications table
    FOREIGN KEY (medication_id) REFERENCES medications(id) ON DELETE CASCADE,

    -- Constraint: status must be one of the valid values
    CONSTRAINT chk_dose_status CHECK (status IN ('taken', 'skipped', 'missed')),

    -- Unique constraint: prevent duplicate dose records for same medication on same date
=======

CREATE TABLE IF NOT EXISTS dose_records (
    id TEXT PRIMARY KEY,
    medication_id TEXT NOT NULL,
    date TEXT NOT NULL,
    timestamp TEXT,
    status TEXT DEFAULT 'taken' NOT NULL,
    FOREIGN KEY (medication_id) REFERENCES medications(id) ON DELETE CASCADE,
    CONSTRAINT chk_dose_status CHECK (status IN ('taken', 'skipped', 'missed')),
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
    CONSTRAINT unique_medication_date UNIQUE (medication_id, date)
);

-- Index on medication_id for efficient lookup of dose history by medication
CREATE INDEX IF NOT EXISTS idx_dose_records_medication_id ON dose_records(medication_id);

-- Index on date for efficient date-range queries
CREATE INDEX IF NOT EXISTS idx_dose_records_date ON dose_records(date);

-- Composite index for common query pattern: medication + date range
<<<<<<< HEAD
CREATE INDEX IF NOT EXISTS idx_dose_records_medication_date ON dose_records(medication_id, date DESC);

-- Comment on table
COMMENT ON TABLE dose_records IS 'Stores medication dose adherence records with timestamps and status tracking';

-- Comments on columns
COMMENT ON COLUMN dose_records.id IS 'Unique identifier for the dose record';
COMMENT ON COLUMN dose_records.medication_id IS 'Reference to the medication this dose belongs to';
COMMENT ON COLUMN dose_records.date IS 'Date the dose was taken or scheduled';
COMMENT ON COLUMN dose_records.timestamp IS 'Exact timestamp when dose was recorded (ISO format)';
COMMENT ON COLUMN dose_records.status IS 'Dose status: taken, skipped, or missed';
=======
CREATE INDEX IF NOT EXISTS idx_dose_records_medication_date ON dose_records(medication_id, date DESC);
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
