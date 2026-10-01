-- Migration: Create medications table
-- Description: Defines the schema for tracking prescribed medications
-- Created: 2026-09-24

-- Create medications table with all required fields
CREATE TABLE IF NOT EXISTS medications (
    -- Primary key: unique identifier for each medication
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Medication name (required, non-empty)
    name TEXT NOT NULL,

    -- Dosage information (required, non-empty) e.g., "500mg", "10ml"
    dosage TEXT NOT NULL,

    -- Frequency of administration (required, non-empty) e.g., "twice daily", "every 8 hours"
    frequency TEXT NOT NULL,

    -- Optional: treatment start date
    start_date DATE,

    -- Optional: treatment end date
    end_date DATE,

    -- Status tracking: 'active' for current medications, 'completed' for finished/discontinued
    status TEXT DEFAULT 'active' NOT NULL,

    -- Record creation timestamp
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Record last update timestamp
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Constraint: status must be either 'active' or 'completed'
    CONSTRAINT chk_status CHECK (status IN ('active', 'completed')),

    -- Constraint: name must be non-empty string
    CONSTRAINT chk_name_not_empty CHECK (name <> '' AND name IS NOT NULL),

    -- Constraint: dosage must be non-empty string
    CONSTRAINT chk_dosage_not_empty CHECK (dosage <> '' AND dosage IS NOT NULL),

    -- Constraint: frequency must be non-empty string
    CONSTRAINT chk_frequency_not_empty CHECK (frequency <> '' AND frequency IS NOT NULL)
);

-- Index on status for efficient filtering by active/completed medications
CREATE INDEX IF NOT EXISTS idx_medications_status ON medications(status);

-- Index on created_at for sorting by most recently added
CREATE INDEX IF NOT EXISTS idx_medications_created_at ON medications(created_at DESC);

-- Comment on table
COMMENT ON TABLE medications IS 'Stores prescribed medication records with dosage and schedule information';

-- Comments on columns
COMMENT ON COLUMN medications.id IS 'Unique identifier for the medication record';
COMMENT ON COLUMN medications.name IS 'Name of the medication (required)';
COMMENT ON COLUMN medications.dosage IS 'Dosage amount and unit e.g., 500mg, 10ml (required)';
COMMENT ON COLUMN medications.frequency IS 'How often to take the medication e.g., twice daily (required)';
COMMENT ON COLUMN medications.start_date IS 'Date when medication treatment started (optional)';
COMMENT ON COLUMN medications.end_date IS 'Date when medication treatment ended or should end (optional)';
COMMENT ON COLUMN medications.status IS 'Current status: active or completed';
COMMENT ON COLUMN medications.created_at IS 'Timestamp when record was created';
COMMENT ON COLUMN medications.updated_at IS 'Timestamp when record was last updated';
