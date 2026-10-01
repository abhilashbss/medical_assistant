/**
 * MedicationForm component.
 * Modal form for creating and editing medications. When an existing medication
 * is provided, all fields are pre-populated and the form submits a PUT; otherwise
 * it submits a POST to create a new entry.
 */
const MedicationForm = (function () {
  let onSaveCallback = null;
  let isEditing = false;

  function cacheElements() {
    return {
      overlay: document.getElementById('medication-modal'),
      title: document.getElementById('modal-title'),
      form: document.getElementById('medication-form'),
      idInput: document.getElementById('medication-id'),
      name: document.getElementById('medication-name'),
      dosage: document.getElementById('medication-dosage'),
      frequency: document.getElementById('medication-frequency'),
      startDate: document.getElementById('medication-start-date'),
      endDate: document.getElementById('medication-end-date'),
      status: document.getElementById('medication-status'),
      saveBtn: document.querySelector('#medication-form .save-btn'),
    };
  }

  function open(medication, onSave) {
    const el = cacheElements();
    isEditing = !!medication;
    onSaveCallback = onSave || null;

    el.title.textContent = isEditing ? 'Edit Medication' : 'Add Medication';
    el.idInput.value = isEditing ? medication.id : '';
    el.form.reset();
    el.status.value = 'active';

    if (isEditing) {
      el.name.value = medication.name;
      el.dosage.value = medication.dosage;
      el.frequency.value = medication.frequency;
      el.startDate.value = medication.start_date || '';
      el.endDate.value = medication.end_date || '';
      el.status.value = medication.status;
    }

    el.overlay.classList.add('active');
    el.name.focus();
  }

  function close() {
    const el = cacheElements();
    el.overlay.classList.remove('active');
    onSaveCallback = null;
  }

  function isOpen() {
    const el = cacheElements();
    return el.overlay.classList.contains('active');
  }

  function validate(data) {
    if (!data.name) return 'Medication name is required';
    if (!data.dosage) return 'Dosage is required';
    if (!data.frequency) return 'Frequency is required';
    return null;
  }

  function collectFormData() {
    const el = cacheElements();
    return {
      name: el.name.value.trim(),
      dosage: el.dosage.value.trim(),
      frequency: el.frequency.value.trim(),
      start_date: el.startDate.value || null,
      end_date: el.endDate.value || null,
      status: el.status.value,
    };
  }

  function setSubmitting(submitting) {
    const el = cacheElements();
    el.saveBtn.disabled = submitting;
    el.saveBtn.textContent = submitting ? 'Saving...' : 'Save Changes';
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!onSaveCallback) return;

    const el = cacheElements();
    const id = el.idInput.value;
    const data = collectFormData();

    const validationError = validate(data);
    if (validationError) {
      Toast.error(validationError);
      return;
    }

    setSubmitting(true);
    try {
      await onSaveCallback(id, data);
      close();
    } catch (err) {
      Toast.error(err.message || 'Failed to save medication');
    } finally {
      setSubmitting(false);
    }
  }

  function init() {
    const el = cacheElements();
    el.form.addEventListener('submit', handleSubmit);
    el.overlay.addEventListener('click', (e) => {
      if (e.target === el.overlay) close();
    });
    document.querySelectorAll('[data-close-modal]').forEach((btn) => {
      btn.addEventListener('click', close);
    });
  }

  return { init, open, close, isOpen, isEditing: () => isEditing };
})();