/**
 * App entry point. Initializes all UI components on DOMContentLoaded.
 */
document.addEventListener('DOMContentLoaded', () => {
  MedicationForm.init();
  DeleteDialog.init();
  MedicationList.init();
});