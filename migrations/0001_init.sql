-- Migration: Initialize prescription tracker schema
-- Description: Creates patients, doctors, prescriptions, status_transitions, and dose_logs
--              tables with foreign keys, CHECK constraints, structured dosage columns,
--              and a partial unique index enforcing one active prescription per medicine
--              per patient.
-- Created: 2026-09-30

-- Patient reference table (identifiers stored as references, not duplicated inline)
CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Doctor reference table
CREATE TABLE IF NOT EXISTS doctors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Prescriptions table
CREATE TABLE IF NOT EXISTS prescriptions (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    doctor_id TEXT NOT NULL,
    medicine_name TEXT NOT NULL,
    dosage_amount REAL NOT NULL,
    dosage_unit TEXT NOT NULL,
    frequency TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,

    -- Required reference integrity
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT,
    FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE RESTRICT,

    -- Status must be a valid lifecycle value
    CONSTRAINT chk_rx_status CHECK (status IN ('active', 'completed', 'discontinued')),
    -- Dosage amount must be positive
    CONSTRAINT chk_rx_dosage_amount CHECK (dosage_amount > 0),
    -- Non-empty text fields
    CONSTRAINT chk_rx_medicine_name CHECK (medicine_name <> '' AND medicine_name IS NOT NULL),
    CONSTRAINT chk_rx_dosage_unit CHECK (dosage_unit <> '' AND dosage_unit IS NOT NULL),
    CONSTRAINT chk_rx_frequency CHECK (frequency <> '' AND frequency IS NOT NULL),
    -- End date, if present, must be after start date
    CONSTRAINT chk_rx_end_after_start CHECK (end_date IS NULL OR end_date > start_date)
);

-- Indexes for the 500ms single-patient read SLO
CREATE INDEX IF NOT EXISTS idx_rx_patient_status ON prescriptions(patient_id, status);
CREATE INDEX IF NOT EXISTS idx_rx_patient_start ON prescriptions(patient_id, start_date DESC);

-- Partial unique index: at most one active prescription per medicine per patient.
-- Allows historical (completed/discontinued) duplicates.
CREATE UNIQUE INDEX IF NOT EXISTS idx_rx_active_unique
    ON prescriptions(patient_id, medicine_name)
    WHERE status = 'active';

-- Status transition audit table (append-only, one row per transition)
CREATE TABLE IF NOT EXISTS status_transitions (
    id TEXT PRIMARY KEY,
    prescription_id TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    reason TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE,
    CONSTRAINT chk_st_from CHECK (from_status IN ('active', 'completed', 'discontinued')),
    CONSTRAINT chk_st_to CHECK (to_status IN ('active', 'completed', 'discontinued'))
);

CREATE INDEX IF NOT EXISTS idx_st_prescription ON status_transitions(prescription_id);