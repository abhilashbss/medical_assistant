/**
 * API client for medication tracker backend.
 * Thin wrapper over fetch with consistent error handling.
 */
const MedicationAPI = (function () {
  const API_BASE = '';

  async function handleResponse(response) {
    if (response.status === 204) {
      return null;
    }
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;
    if (!response.ok) {
      const message = (data && data.error) || `Request failed (${response.status})`;
      const err = new Error(message);
      err.status = response.status;
      err.body = data;
      throw err;
    }
    return data;
  }

  async function getMedications(filter) {
    const status = filter || 'all';
    const url = status === 'all'
      ? `${API_BASE}/medications`
      : `${API_BASE}/medications?status=${encodeURIComponent(status)}`;
    const response = await fetch(url);
    return handleResponse(response);
  }

  async function getMedication(id) {
    const response = await fetch(`${API_BASE}/medications/${id}`);
    return handleResponse(response);
  }

  async function createMedication(data) {
    const response = await fetch(`${API_BASE}/medications`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return handleResponse(response);
  }

  async function updateMedication(id, data) {
    const response = await fetch(`${API_BASE}/medications/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return handleResponse(response);
  }

  async function deleteMedication(id) {
    const response = await fetch(`${API_BASE}/medications/${id}`, {
      method: 'DELETE',
    });
    return handleResponse(response);
  }

  return {
    getMedications,
    getMedication,
    createMedication,
    updateMedication,
    deleteMedication,
  };
})();