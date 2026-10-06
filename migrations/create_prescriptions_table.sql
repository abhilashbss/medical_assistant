-- Migration: Create prescription tracker tables
-- Description: Defines patients, doctors, prescriptions, status_transitions, and dose_logs
-- Created: 2026-10-01

CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS doctors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS prescriptions (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    doctor_id TEXT NOT NULL,
    medicine_name TEXT NOT NULL,
    dosage_amount TEXT NOT NULL,
    dosage_unit TEXT NOT NULL,
    frequency TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(id),
    CONSTRAINT chk_rx_status CHECK (status IN ('active', 'completed', 'discontinued')),
    CONSTRAINT chk_rx_end_date CHECK (end_date IS NULL OR end_date >= start_date),
    CONSTRAINT chk_rx_medicine CHECK (medicine_name <> ''),
    CONSTRAINT chk_rx_dosage_amount CHECK (dosage_amount <> ''),
    CONSTRAINT chk_rx_dosage_unit CHECK (dosage_unit <> ''),
    CONSTRAINT chk_rx_frequency CHECK (frequency <> '')
);

CREATE TABLE IF NOT EXISTS status_transitions (
    id TEXT PRIMARY KEY,
    prescription_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    reason TEXT,
    transitioned_at TEXT,
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS dose_logs (
    id TEXT PRIMARY KEY,
    prescription_id TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    status TEXT,
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE,
    CONSTRAINT chk_dose_status CHECK (status IN ('taken', 'skipped', 'missed'))
);

-- Partial unique index enforcing one active prescription per medicine per patient.
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_per_medicine
    ON prescriptions(patient_id, medicine_name)
    WHERE status = 'active';

-- Index supporting history queries sorted by start date descending.
CREATE INDEX IF NOT EXISTS idx_prescriptions_patient_start
    ON prescriptions(patient_id, start_date DESC);

CREATE INDEX IF NOT EXISTS idx_prescriptions_status
    ON prescriptions(status);

CREATE INDEX IF NOT EXISTS idx_rx_patient_status
    ON prescriptions(patient_id, status);

CREATE INDEX IF NOT EXISTS idx_status_transitions_rx
    ON status_transitions(prescription_id);

CREATE INDEX IF NOT EXISTS idx_dose_logs_rx_taken
    ON dose_logs(prescription_id, taken_at);