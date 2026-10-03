-- Prescription Tracker schema: patients, doctors, prescriptions, dose_logs, status_transitions
-- Idempotent: uses IF NOT EXISTS so it can be re-run on an existing database.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS patients (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS doctors (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS prescriptions (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL,
    doctor_id       TEXT NOT NULL,
    medicine_name   TEXT NOT NULL,
    dosage_amount   REAL NOT NULL CHECK (dosage_amount > 0),
    dosage_unit     TEXT NOT NULL CHECK (length(dosage_unit) > 0),
    frequency       TEXT NOT NULL,
    start_date      TEXT NOT NULL,
    end_date        TEXT,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'completed', 'discontinued')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    -- end_date, when present, must be after start_date
    CHECK (end_date IS NULL OR end_date > start_date),
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT,
    FOREIGN KEY (doctor_id)  REFERENCES doctors(id)  ON DELETE RESTRICT
);

-- One active prescription per medicine per patient.
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_per_medicine
    ON prescriptions(patient_id, medicine_name) WHERE status = 'active';

-- Single-patient read paths: filter by patient+status, history by start_date DESC.
CREATE INDEX IF NOT EXISTS idx_prescriptions_patient_status
    ON prescriptions(patient_id, status);

CREATE INDEX IF NOT EXISTS idx_prescriptions_patient_startdate
    ON prescriptions(patient_id, start_date DESC);

CREATE TABLE IF NOT EXISTS status_transitions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prescription_id TEXT NOT NULL,
    from_status     TEXT NOT NULL CHECK (from_status IN ('active', 'completed', 'discontinued')),
    to_status       TEXT NOT NULL CHECK (to_status   IN ('active', 'completed', 'discontinued')),
    reason          TEXT,
    transitioned_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE RESTRICT
);

-- Dose adherence log: append-only by design (no UPDATE/DELETE path in code).
CREATE TABLE IF NOT EXISTS dose_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prescription_id TEXT NOT NULL,
    event           TEXT NOT NULL CHECK (event IN ('taken', 'skipped')),
    timestamp       TEXT NOT NULL,
    notes           TEXT,
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_dose_logs_rx_time
    ON dose_logs(prescription_id, timestamp DESC);