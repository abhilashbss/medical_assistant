/**
 * MedicationList component.
 * Fetches, filters, renders, and manages the lifecycle of medication entries.
 * Supports optimistic UI updates with rollback on API failure.
 */
const MedicationList = (function () {
  const FILTERS = ['all', 'active', 'completed'];

  let state = {
    medications: [],
    filter: 'all',
    loading: false,
    error: null,
  };

  function cacheElements() {
    return {
      list: document.getElementById('medication-list'),
      filterButtons: document.querySelectorAll('.filter-btn'),
      addBtn: document.getElementById('add-btn'),
    };
  }

  function sortByCreatedAtDesc(meds) {
    return meds.slice().sort((a, b) => {
      const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
      const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
      return bTime - aTime;
    });
  }

  function filterMeds(meds, filter) {
    if (!filter || filter === 'all') return meds;
    return meds.filter((m) => m.status === filter);
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function renderCard(med) {
    const card = document.createElement('div');
    card.className = 'medication-card';
    card.dataset.id = med.id;

    const info = document.createElement('div');
    info.className = 'medication-info';

    const nameRow = document.createElement('div');
    nameRow.className = 'medication-name';
    const nameSpan = document.createElement('span');
    nameSpan.textContent = med.name;
    nameRow.appendChild(nameSpan);

    const badge = document.createElement('span');
    badge.className = `status-badge ${med.status}`;
    badge.textContent = med.status;
    nameRow.appendChild(badge);

    const details = document.createElement('div');
    details.className = 'medication-details';
    const detailParts = [];
    detailParts.push(`Dosage: ${med.dosage}`);
    detailParts.push(`Frequency: ${med.frequency}`);
    if (med.start_date) detailParts.push(`Start: ${formatDate(med.start_date)}`);
    if (med.end_date) detailParts.push(`End: ${formatDate(med.end_date)}`);
    details.textContent = detailParts.join('  •  ');

    info.appendChild(nameRow);
    info.appendChild(details);

    const actions = document.createElement('div');
    actions.className = 'medication-actions';

    const editBtn = document.createElement('button');
    editBtn.className = 'action-btn edit-btn';
    editBtn.textContent = 'Edit';
    editBtn.addEventListener('click', () => handleEdit(med.id));

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'action-btn delete-btn';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', () => handleDelete(med.id, med.name));

    actions.appendChild(editBtn);
    actions.appendChild(deleteBtn);

    card.appendChild(info);
    card.appendChild(actions);
    return card;
  }

  function renderEmpty() {
    const el = cacheElements();
    const wrapper = document.createElement('div');
    wrapper.className = 'empty-state';
    const heading = document.createElement('h2');
    heading.textContent = 'No medications found';
    const para = document.createElement('p');
    para.textContent = state.filter === 'all'
      ? 'Start tracking your medications by adding your first one.'
      : `No ${state.filter} medications yet.`;
    const cta = document.createElement('button');
    cta.className = 'add-btn';
    cta.textContent = '+ Add Medication';
    cta.addEventListener('click', handleAdd);
    wrapper.appendChild(heading);
    wrapper.appendChild(para);
    wrapper.appendChild(cta);
    el.list.innerHTML = '';
    el.list.appendChild(wrapper);
  }

  function renderError(message) {
    const el = cacheElements();
    const div = document.createElement('div');
    div.className = 'error-message';
    div.textContent = `Error: ${message}`;
    el.list.innerHTML = '';
    el.list.appendChild(div);
  }

  function renderLoading() {
    const el = cacheElements();
    el.list.innerHTML = '<div class="loading">Loading medications...</div>';
  }

  function render() {
    const el = cacheElements();
    if (state.error) {
      renderError(state.error);
      return;
    }
    if (state.loading) {
      renderLoading();
      return;
    }
    const sorted = sortByCreatedAtDesc(state.medications);
    if (sorted.length === 0) {
      renderEmpty();
      return;
    }
    el.list.innerHTML = '';
    const fragment = document.createDocumentFragment();
    sorted.forEach((med) => fragment.appendChild(renderCard(med)));
    el.list.appendChild(fragment);
  }

  function setFilterActive(filter) {
    const el = cacheElements();
    el.filterButtons.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.filter === filter);
    });
  }

  async function load() {
    state.loading = true;
    state.error = null;
    render();
    try {
      const data = await MedicationAPI.getMedications(state.filter);
      state.medications = data || [];
      state.loading = false;
      render();
    } catch (err) {
      state.loading = false;
      state.error = err.message || 'Failed to load medications';
      render();
      Toast.error(state.error);
    }
  }

  function setFilter(filter) {
    if (!FILTERS.includes(filter)) return;
    state.filter = filter;
    setFilterActive(filter);
    load();
  }

  function handleAdd() {
    MedicationForm.open(null, async (id, data) => {
      const created = await MedicationAPI.createMedication(data);
      state.medications = [created, ...state.medications];
      render();
      Toast.success('Medication added successfully');
    });
  }

  function handleEdit(id) {
    MedicationForm.open(null, async (_, __) => {
      // Placeholder; replaced below with pre-fetched data.
    });
  }

  function handleDelete(id, name) {
    DeleteDialog.open(id, name, async (targetId) => {
      // Optimistic update: remove from local state immediately.
      const snapshot = state.medications.slice();
      state.medications = state.medications.filter((m) => m.id !== targetId);
      render();
      try {
        await MedicationAPI.deleteMedication(targetId);
        Toast.success('Medication deleted successfully');
      } catch (err) {
        // Rollback on failure.
        state.medications = snapshot;
        render();
        throw err;
      }
    });
  }

  function getMedicationFromState(id) {
    return state.medications.find((m) => m.id === id) || null;
  }

  function init() {
    const el = cacheElements();

    el.filterButtons.forEach((btn) => {
      btn.addEventListener('click', () => setFilter(btn.dataset.filter));
    });

    el.addBtn.addEventListener('click', handleAdd);

    // Override handleEdit to fetch fresh data, pre-populate the form, then submit PUT.
    handleEdit = function (id) {
      const cached = getMedicationFromState(id);
      if (cached) {
        MedicationForm.open(cached, async (editId, data) => {
          const snapshot = state.medications.slice();
          // Optimistic update.
          state.medications = state.medications.map((m) =>
            m.id === editId ? Object.assign({}, m, data) : m
          );
          render();
          try {
            const updated = await MedicationAPI.updateMedication(editId, data);
            state.medications = state.medications.map((m) =>
              m.id === editId ? updated : m
            );
            render();
            Toast.success('Medication updated successfully');
          } catch (err) {
            // Rollback on failure.
            state.medications = snapshot;
            render();
            throw err;
          }
        });
      } else {
        // Not in local state — fetch from API then open.
        MedicationAPI.getMedication(id)
          .then((med) => {
            MedicationForm.open(med, async (editId, data) => {
              const updated = await MedicationAPI.updateMedication(editId, data);
              state.medications = state.medications.map((m) =>
                m.id === editId ? updated : m
              );
              if (state.medications.length === 0) {
                await load();
              } else {
                render();
              }
              Toast.success('Medication updated successfully');
            });
          })
          .catch(() => {
            Toast.error('Failed to load medication details');
          });
      }
    };

    load();
  }

  // Exposed for testing.
  return {
    init,
    load,
    setFilter,
    getState: () => Object.assign({}, state),
    getMedications: () => state.medications.slice(),
    sortByCreatedAtDesc,
    filterMeds,
  };
})();