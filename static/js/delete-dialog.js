/**
 * DeleteDialog component.
 * Confirmation modal before deleting a medication. Calls onConfirm
 * only when the user explicitly confirms; cancel is a no-op.
 */
const DeleteDialog = (function () {
  let pendingId = null;
  let pendingName = null;
  let onConfirmCallback = null;

  function cacheElements() {
    return {
      overlay: document.getElementById('delete-modal'),
      message: document.getElementById('delete-message'),
      confirmBtn: document.getElementById('delete-confirm-btn'),
    };
  }

  function open(id, name, onConfirm) {
    const el = cacheElements();
    pendingId = id;
    pendingName = name;
    onConfirmCallback = onConfirm || null;
    el.message.textContent = `Are you sure you want to delete "${name}"? This action cannot be undone.`;
    el.overlay.classList.add('active');
  }

  function close() {
    const el = cacheElements();
    el.overlay.classList.remove('active');
    pendingId = null;
    pendingName = null;
    onConfirmCallback = null;
  }

  function isOpen() {
    const el = cacheElements();
    return el.overlay.classList.contains('active');
  }

  function getPendingId() {
    return pendingId;
  }

  async function handleConfirm() {
    if (!pendingId || !onConfirmCallback) return;
    const id = pendingId;
    const name = pendingName;
    const el = cacheElements();
    el.confirmBtn.disabled = true;
    el.confirmBtn.textContent = 'Deleting...';
    try {
      await onConfirmCallback(id, name);
      close();
    } catch (err) {
      Toast.error(err.message || 'Failed to delete medication');
    } finally {
      el.confirmBtn.disabled = false;
      el.confirmBtn.textContent = 'Delete';
    }
  }

  function init() {
    const el = cacheElements();
    el.confirmBtn.addEventListener('click', handleConfirm);
    el.overlay.addEventListener('click', (e) => {
      if (e.target === el.overlay) close();
    });
    document.querySelectorAll('[data-close-delete]').forEach((btn) => {
      btn.addEventListener('click', close);
    });
  }

  return { init, open, close, isOpen, getPendingId };
})();