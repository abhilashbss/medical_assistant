"""Flask API for medication tracker CRUD operations."""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from datetime import datetime, date
from uuid import uuid4
import os

from .database import Database
from .models import Medication, MedicationStatus, DoseRecord
from .repository import MedicationRepository
from .dose_service import DoseService, ConflictError


def create_app(db_path: str = None, static_folder: str = None):
    """Create and configure Flask application.

    Args:
        db_path: Path to SQLite database file. Defaults to medications.db in current directory.
        static_folder: Path to static files folder. Defaults to 'static' in parent directory.

    Returns:
        Configured Flask application
    """
    app = Flask(__name__, static_folder=static_folder or 'static')
    CORS(app)

    # Initialize database
    if db_path is None:
        db_path = "medications.db"
    database = Database(db_path)
    database.init_schema()
    repository = MedicationRepository(database)
    dose_service = DoseService(database)

    @app.route('/medications', methods=['GET'])
    def get_medications():
        """Get all medications, optionally filtered by status.

        Query params:
            status: 'active', 'completed', or 'all' (default: 'all')

        Returns:
            JSON array of medications sorted by created_at descending
        """
        status_param = request.args.get('status', 'all')

        if status_param == 'all':
            medications = repository.get_all()
        elif status_param in ('active', 'completed'):
            try:
                status = MedicationStatus(status_param)
                medications = repository.get_all(status=status)
            except ValueError:
                return jsonify({"error": "Invalid status value. Must be 'active', 'completed', or 'all'"}), 400
        else:
            return jsonify({"error": "Invalid status value. Must be 'active', 'completed', or 'all'"}), 400

        return jsonify([med.to_dict() for med in medications])

    @app.route('/medications', methods=['POST'])
    def create_medication():
        """Create a new medication.

        Request body:
            name: string (required, non-empty)
            dosage: string (required, non-empty)
            frequency: string (required, non-empty)
            start_date: string (optional, ISO date format)
            end_date: string (optional, ISO date format)
            status: string (optional, default: 'active')

        Returns:
            Created medication with ID and timestamps
        """
        data = request.get_json()

        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        try:
            medication = Medication.from_dict(data)
        except (KeyError, ValueError) as e:
            return jsonify({"error": str(e)}), 400

        try:
            result = repository.create(medication)
            return jsonify(result.to_dict()), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route('/medications/<medication_id>', methods=['GET'])
    def get_medication(medication_id):
        """Get a specific medication by ID.

        Args:
            medication_id: UUID of medication to retrieve

        Returns:
            Medication object or 404 if not found
        """
        try:
            from uuid import UUID
            med_uuid = UUID(medication_id)
        except ValueError:
            return jsonify({"error": "Invalid medication ID format"}), 400

        medication = repository.get_by_id(med_uuid)
        if medication is None:
            return jsonify({"error": "Medication not found"}), 404

        return jsonify(medication.to_dict())

    @app.route('/medications/<medication_id>', methods=['PUT'])
    def update_medication(medication_id):
        """Update an existing medication.

        Args:
            medication_id: UUID of medication to update

        Request body:
            name: string (optional)
            dosage: string (optional)
            frequency: string (optional)
            start_date: string (optional)
            end_date: string (optional)
            status: string (optional)

        Returns:
            Updated medication or 404 if not found
        """
        try:
            from uuid import UUID
            med_uuid = UUID(medication_id)
        except ValueError:
            return jsonify({"error": "Invalid medication ID format"}), 400

        existing = repository.get_by_id(med_uuid)
        if existing is None:
            return jsonify({"error": "Medication not found"}), 404

        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        # Update fields from request, keeping existing values
        try:
            existing.name = data.get('name', existing.name)
            existing.dosage = data.get('dosage', existing.dosage)
            existing.frequency = data.get('frequency', existing.frequency)

            if 'start_date' in data:
                existing.start_date = date.fromisoformat(data['start_date']) if data['start_date'] else None
            if 'end_date' in data:
                existing.end_date = date.fromisoformat(data['end_date']) if data['end_date'] else None
            if 'status' in data:
                existing.status = MedicationStatus(data['status'])

            result = repository.update(existing)
            return jsonify(result.to_dict())
        except (KeyError, ValueError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route('/medications/<medication_id>', methods=['DELETE'])
    def delete_medication(medication_id):
        """Delete a medication.

        Args:
            medication_id: UUID of medication to delete

        Returns:
            204 No Content on success, 404 if not found
        """
        try:
            from uuid import UUID
            med_uuid = UUID(medication_id)
        except ValueError:
            return jsonify({"error": "Invalid medication ID format"}), 400

        deleted = repository.delete(med_uuid)
        if not deleted:
            return jsonify({"error": "Medication not found"}), 404

        return '', 204

    @app.route('/medications/<medication_id>/doses', methods=['POST'])
    def mark_as_taken(medication_id):
        """Mark a medication dose as taken.

        Args:
            medication_id: UUID of medication

        Request body (optional):
            date: string (ISO date format, defaults to today)

        Returns:
            Created dose record
        """
        try:
            from uuid import UUID
            med_uuid = UUID(medication_id)
        except ValueError:
            return jsonify({"error": "Invalid medication ID format"}), 400

        existing = repository.get_by_id(med_uuid)
        if existing is None:
            return jsonify({"error": "Medication not found"}), 404

        data = request.get_json() or {}

        dose_date = data.get('date')
        if dose_date:
            try:
                dose_date = date.fromisoformat(dose_date)
            except ValueError:
                return jsonify({"error": "Invalid date format. Use ISO format (YYYY-MM-DD)"}), 400
        else:
            dose_date = date.today()

        # Check for future date
        if dose_date > date.today():
            return jsonify({"error": "Cannot mark dose for a future date"}), 400

        dose_service = DoseService(database)

        try:
            dose_record = dose_service.mark_dose_taken(med_uuid, dose_date)
            return jsonify(dose_record.to_dict()), 201
        except Exception as e:
            error_msg = str(e)
            if "UNIQUE constraint failed" in error_msg or "already recorded" in error_msg.lower():
                return jsonify({"error": "Dose already recorded for this medication on this date"}), 409
            return jsonify({"error": error_msg}), 400

    @app.route('/medications/<medication_id>/doses', methods=['GET'])
    def get_dose_records(medication_id):
        """Get dose records for a medication.

        Args:
            medication_id: UUID of medication

        Query params:
            start: string (optional, ISO date format YYYY-MM-DD)
            end: string (optional, ISO date format YYYY-MM-DD)

        Returns:
            JSON array of dose records
        """
        try:
            from uuid import UUID
            med_uuid = UUID(medication_id)
        except ValueError:
            return jsonify({"error": "Invalid medication ID format"}), 400

        # Support both 'start'/'end' and 'start_date'/'end_date' query params
        start_param = request.args.get('start') or request.args.get('start_date')
        end_param = request.args.get('end') or request.args.get('end_date')

        # Convert string params to date objects
        start_date = None
        end_date = None

        if start_param:
            try:
                start_date = date.fromisoformat(start_param)
            except ValueError:
                return jsonify({"error": "Invalid start date format. Use ISO format (YYYY-MM-DD)"}), 400

        if end_param:
            try:
                end_date = date.fromisoformat(end_param)
            except ValueError:
                return jsonify({"error": "Invalid end date format. Use ISO format (YYYY-MM-DD)"}), 400

        records = dose_service.get_dose_history(med_uuid, start_date, end_date)
        return jsonify([record.to_dict() for record in records])

    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint."""
        return jsonify({"status": "healthy"})

    @app.route('/')
    def serve_index():
        """Serve the main HTML page."""
        return send_from_directory(app.static_folder, 'index.html')

    return app


# For running standalone
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
