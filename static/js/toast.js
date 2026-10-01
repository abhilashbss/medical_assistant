/**
 * Toast notification component.
 * Shows transient success/error messages at the bottom-right of the screen.
 */
const Toast = (function () {
  const DURATION_MS = 3000;

  function show(message, type) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast ${type || 'success'}`;
    toast.textContent = message;
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    document.body.appendChild(toast);

    setTimeout(() => {
      if (toast.parentNode) toast.remove();
    }, DURATION_MS);
  }

  function success(message) {
    show(message, 'success');
  }

  function error(message) {
    show(message, 'error');
  }

  return { show, success, error };
})();