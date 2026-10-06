"""Flask API for prescription tracker CRUD and lifecycle endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from flask import Flask, jsonify, request

from .database import Database
from .models import DoseLog, DoseStatus, Prescription
from .repository import PrescriptionRepository
from .service import ConflictError, PrescriptionService


def create_app(db_path: str = None):
    """Create and configure the Flask application.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Configured Flask application.
    """
    app = Flask(__name__)

    database = Database(db_path)
    database.init_schema()
    service = PrescriptionService(database)
    repository = PrescriptionRepository(database)

    def _parse_uuid(value: str, field: str = "id"):
        try:
            return UUID(value)
        except (ValueError, TypeError):
            return None

    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "healthy"})

    @app.route("/prescriptions", methods=["POST"])
    def create_prescription():
        """Create a new prescription.

        Required body fields: patient_id, doctor_id, medicine_name, dosage_amount,
        dosage_unit, frequency, start_date (ISO 8601 with timezone).
        Optional: end_date, status.
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        try:
            prescription = Prescription.from_dict(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        try:
            result = service.create_prescription(prescription)
            return jsonify(result.to_dict()), 201
        except ConflictError as exc:
            return jsonify({"error": str(exc)}), 409

    @app.route("/prescriptions/<prescription_id>", methods=["GET"])
    def get_prescription(prescription_id):
        rx_id = _parse_uuid(prescription_id)
        if rx_id is None:
            return jsonify({"error": "Invalid prescription ID format"}), 400

        prescription = service.get_prescription(rx_id)
        if prescription is None:
            return jsonify({"error": "Prescription not found"}), 404
        return jsonify(prescription.to_dict())

    @app.route("/patients/<patient_id>/prescriptions", methods=["GET"])
    def get_patient_prescriptions(patient_id):
        pid = _parse_uuid(patient_id, "patient_id")
        if pid is None:
            return jsonify({"error": "Invalid patient ID format"}), 400

        history = service.get_patient_history(pid)
        return jsonify({
            "active": [rx.to_dict() for rx in history["active"]],
            "historical": [rx.to_dict() for rx in history["historical"]],
        })

    @app.route("/prescriptions/<prescription_id>/complete", methods=["PATCH"])
    def complete_prescription(prescription_id):
        rx_id = _parse_uuid(prescription_id)
        if rx_id is None:
            return jsonify({"error": "Invalid prescription ID format"}), 400

        try:
            result = service.complete_prescription(rx_id)
            return jsonify(result.to_dict())
        except ValueError as exc:
            message = str(exc)
            if "not found" in message:
                return jsonify({"error": message}), 404
            return jsonify({"error": message}), 400

    @app.route("/prescriptions/<prescription_id>/discontinue", methods=["PATCH"])
    def discontinue_prescription(prescription_id):
        rx_id = _parse_uuid(prescription_id)
        if rx_id is None:
            return jsonify({"error": "Invalid prescription ID format"}), 400

        data = request.get_json() or {}
        reason = data.get("reason")
        if not reason or not isinstance(reason, str) or not reason.strip():
            return jsonify({"error": "a non-empty reason is required to discontinue a prescription"}), 400

        try:
            result = service.discontinue_prescription(rx_id, reason)
            return jsonify(result.to_dict())
        except ValueError as exc:
            message = str(exc)
            if "not found" in message:
                return jsonify({"error": message}), 404
            return jsonify({"error": message}), 400

    @app.route("/prescriptions/<prescription_id>/doses", methods=["POST"])
    def log_dose(prescription_id):
        rx_id = _parse_uuid(prescription_id)
        if rx_id is None:
            return jsonify({"error": "Invalid prescription ID format"}), 400

        prescription = service.get_prescription(rx_id)
        if prescription is None:
            return jsonify({"error": "Prescription not found"}), 404

        data = request.get_json() or {}
        taken_at = data.get("taken_at")
        if not taken_at:
            taken_at = datetime.now(timezone.utc).isoformat()
        status_value = data.get("status", DoseStatus.TAKEN.value)

        try:
            dose = DoseLog(
                prescription_id=rx_id,
                taken_at=taken_at,
                status=status_value,
            )
            result = service.log_dose(dose)
            return jsonify(result.to_dict()), 201
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/prescriptions/<prescription_id>/doses", methods=["GET"])
    def get_dose_logs(prescription_id):
        rx_id = _parse_uuid(prescription_id)
        if rx_id is None:
            return jsonify({"error": "Invalid prescription ID format"}), 400

        logs = service.get_dose_logs(rx_id)
        return jsonify([log.to_dict() for log in logs])

    @app.route("/prescriptions/<prescription_id>/transitions", methods=["GET"])
    def get_transitions(prescription_id):
        rx_id = _parse_uuid(prescription_id)
        if rx_id is None:
            return jsonify({"error": "Invalid prescription ID format"}), 400

        transitions = service.get_transitions(rx_id)
        return jsonify([t.to_dict() for t in transitions])

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5001)