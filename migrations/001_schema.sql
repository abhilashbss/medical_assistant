-- Prescription tracker schema (SQLite)
-- Foundation for the medication_tracker package. Defines reference tables
-- (patients, doctors), the prescriptions table with structured dosage and a
-- partial unique index enforcing one active prescription per medicine per
-- patient, plus status_transitions and dose_logs audit tables.
--
-- All datetime columns are stored as ISO 8601 text with a timezone offset.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doctors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prescriptions (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    doctor_id TEXT NOT NULL,
    medicine_name TEXT NOT NULL CHECK (medicine_name <> ''),
    dosage_amount REAL NOT NULL CHECK (dosage_amount > 0),
    dosage_unit TEXT NOT NULL CHECK (dosage_unit <> ''),
    frequency TEXT NOT NULL CHECK (frequency <> ''),
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'discontinued')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT,
    FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE RESTRICT,
    CHECK (end_date IS NULL OR end_date > start_date)
);

-- One active prescription per medicine per patient; historical duplicates allowed.
CREATE UNIQUE INDEX IF NOT EXISTS idx_rx_active_unique
    ON prescriptions(patient_id, medicine_name)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_rx_patient_status
    ON prescriptions(patient_id, status);

CREATE INDEX IF NOT EXISTS idx_rx_patient_start
    ON prescriptions(patient_id, start_date DESC);

CREATE TABLE IF NOT EXISTS status_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prescription_id TEXT NOT NULL,
    from_status TEXT NOT NULL CHECK (from_status IN ('active', 'completed', 'discontinued')),
    to_status TEXT NOT NULL CHECK (to_status IN ('active', 'completed', 'discontinued')),
    reason TEXT,
    transitioned_at TEXT NOT NULL,
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_transitions_rx
    ON status_transitions(prescription_id, transitioned_at);

CREATE TABLE IF NOT EXISTS dose_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prescription_id TEXT NOT NULL,
    event TEXT NOT NULL CHECK (event IN ('taken', 'skipped')),
    logged_at TEXT NOT NULL,
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_dose_logs_rx_time
    ON dose_logs(prescription_id, logged_at);