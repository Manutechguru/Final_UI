// static/js/new_arrivals.js
// Clients page JavaScript (complete). Handles filters, search, create/edit/delete, toggles.
// IMPORTANT: This file updates UI only; no backend wiring changes are made.

(function () {
  'use strict';

  // ---------- DOM Elements ----------
  const filterSidebar = document.getElementById('filterSidebar');
  const sidebarOverlay = document.getElementById('sidebarOverlay');
  const filterToggle = document.getElementById('filterToggle');
  const closeFilters = document.getElementById('closeFilters');

  const searchBox = document.getElementById('searchBox');
  const statusFilter = document.getElementById('statusFilter');
  const sortFilter = document.getElementById('sortFilter');
  const clearFilters = document.getElementById('clearFilters');
  const clearFiltersEmpty = document.getElementById('clearFiltersEmpty');

  const clientsTableBody = document.getElementById('clientsTableBody');
  const activeFilters = document.getElementById('activeFilters');
  const loadingState = document.getElementById('loadingState');
  const emptyState = document.getElementById('emptyState');

  const createModal = document.getElementById('createModal');
  const closeCreateModal = document.getElementById('closeCreateModal');
  const cancelCreate = document.getElementById('cancelCreate');
  const createClientBtn = document.getElementById('createClientBtn');
  const addJobFieldBtn = document.getElementById('addJobField');
  const jobsContainer = document.getElementById('jobsContainer');

  const editModal = document.getElementById('editModal');
  const editClientForm = document.getElementById('editClientForm');
  const modalClientId = document.getElementById('modalClientId');
  const modalClientName = document.getElementById('modalClientName');

  const deleteModal = document.getElementById('deleteModal');
  const confirmDeleteBtn = document.getElementById('confirmDelete');

  const mainContentEl = document.querySelector('.main-content'); // used to expand/shrink table area

  // ---------- In-memory cache ----------
  let originalRows = []; // clones of table rows (dom nodes)
  let desktopHidden = false;

  // ---------- Helpers ----------
  function debounce(fn, ms = 150) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), ms);
    };
  }

  async function safeText(res) {
    try { return await res.text(); } catch (e) { return ''; }
  }

  // Generic sequential endpoint tester (tries each URL with optionsFactory(url))
  async function tryEndpointsSequentially(urls, optionsFactory) {
    let lastError = null;
    for (const url of urls) {
      const opts = optionsFactory ? optionsFactory(url) : {};
      try {
        const res = await fetch(url, opts);
        if (res && (res.ok || res.status === 204)) return { ok: true, url, res };
        const text = await safeText(res);
        lastError = { url, status: res.status, statusText: res.statusText, text };
      } catch (err) {
        lastError = { url, message: err.message };
      }
    }
    return { ok: false, lastError };
  }

  // ---------- Build cache from initial server-rendered rows ----------
  function buildOriginalRowsCache() {
    originalRows = [];
    if (!clientsTableBody) return;
    const trs = Array.from(clientsTableBody.querySelectorAll('tr'));
    trs.forEach(tr => {
      const clone = tr.cloneNode(true);
      // ensure dataset entries exist
      if (!clone.dataset.clientId) {
        const idCell = clone.querySelectorAll('td')[1];
        if (idCell) clone.dataset.clientId = idCell.textContent.trim();
      }
      if (!clone.dataset.status) {
        const st = clone.querySelector('.status-text');
        clone.dataset.status = st ? (st.textContent || '').trim().toLowerCase() : '';
      }
      originalRows.push(clone);
    });
  }

  function renderRows(rows) {
    if (!clientsTableBody) return;
    clientsTableBody.innerHTML = '';
    rows.forEach(r => clientsTableBody.appendChild(r.cloneNode(true)));
    attachRowActionListeners();
  }

  // ---------- Filtering / searching ----------
  function applyFilters() {
    if (!clientsTableBody) return;
    loadingState && loadingState.classList.remove('hidden');

    const q = (searchBox?.value || '').trim().toLowerCase();
    const status = (statusFilter?.value || '').toLowerCase();
    const sort = (sortFilter?.value || 'recent');

    let filtered = originalRows.filter(row => {
      const nameCell = row.querySelector('td');
      const name = (nameCell ? (nameCell.textContent || '') : '').toLowerCase();
      const rowStatus = (row.dataset.status || '').toString().toLowerCase();
      const okSearch = !q || name.includes(q);
      const okStatus = !status || (rowStatus === status);
      return okSearch && okStatus;
    });

    // sorting by data-created if present
    filtered.sort((a, b) => {
      const da = a.dataset.created || '';
      const db = b.dataset.created || '';
      if (!da && !db) return 0;
      if (!da) return sort === 'recent' ? 1 : -1;
      if (!db) return sort === 'recent' ? -1 : 1;
      const A = new Date(da), B = new Date(db);
      return sort === 'recent' ? (B - A) : (A - B);
    });

    if (filtered.length === 0) emptyState && emptyState.classList.remove('hidden');
    else emptyState && emptyState.classList.add('hidden');

    renderRows(filtered);
    updateActiveBadges();
    loadingState && loadingState.classList.add('hidden');
  }
  const debouncedApply = debounce(applyFilters, 160);

  function updateActiveBadges() {
    if (!activeFilters) return;
    activeFilters.innerHTML = '';
    if (searchBox && searchBox.value) addBadge('Search', searchBox.value, 'search');
    if (statusFilter && statusFilter.value) addBadge('Status', statusFilter.options[statusFilter.selectedIndex].text, 'status');
  }

  function addBadge(label, value, type) {
    const badge = document.createElement('div');
    badge.className = 'bg-indigo-100 text-indigo-800 px-3 py-1 rounded-full text-sm flex items-center';
    badge.innerHTML = `<span class="font-medium">${label}:</span><span class="ml-1">${value}</span><button type="button" class="ml-2 text-indigo-600" data-filter-type="${type}">&times;</button>`;
    activeFilters.appendChild(badge);
    badge.querySelector('button').addEventListener('click', (e) => {
      const t = e.currentTarget.dataset.filterType;
      if (t === 'search') searchBox.value = '';
      if (t === 'status') statusFilter.value = '';
      if (t === 'sort') sortFilter.value = 'recent';
      applyFilters();
    });
  }

  function attachFilterControls() {
    searchBox?.addEventListener('input', debouncedApply);
    statusFilter?.addEventListener('change', applyFilters);
    sortFilter?.addEventListener('change', applyFilters);
    clearFilters?.addEventListener('click', () => { if (searchBox) searchBox.value = ''; if (statusFilter) statusFilter.value = ''; if (sortFilter) sortFilter.value = 'recent'; applyFilters(); });
    clearFiltersEmpty?.addEventListener('click', () => { if (searchBox) searchBox.value = ''; if (statusFilter) statusFilter.value = ''; if (sortFilter) sortFilter.value = 'recent'; applyFilters(); });
  }

  // ---------- Row actions: dropdowns, edit, delete ----------
  function attachRowActionListeners() {
    document.querySelectorAll('.dropdown-toggle').forEach(btn => {
      btn.onclick = null;
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        const menu = btn.parentElement.querySelector('.dropdown-menu');
        document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
        document.querySelectorAll('.dropdown-toggle').forEach(b => b.setAttribute('aria-expanded', 'false'));
        if (menu) {
          const isShown = menu.classList.contains('show');
          if (!isShown) { menu.classList.add('show'); btn.setAttribute('aria-expanded', 'true'); }
          else { menu.classList.remove('show'); btn.setAttribute('aria-expanded', 'false'); }
        }
      });
    });

    window.addEventListener('click', () => {
      document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
      document.querySelectorAll('.dropdown-toggle').forEach(b => b.setAttribute('aria-expanded', 'false'));
    });

    // edit actions
    document.querySelectorAll('.edit-action').forEach(el => {
      el.onclick = null;
      el.addEventListener('click', (e) => {
        e.preventDefault();
        const id = el.dataset.clientId;
        const row = el.closest('tr');
        const name = row ? (row.querySelector('td')?.textContent || '') : '';
        if (modalClientId) modalClientId.value = id;
        if (modalClientName) modalClientName.value = name;
        if (editClientForm) editClientForm.action = `/clients/edit/${id}`;
        editModal && editModal.classList.remove('hidden');
      });
    });

    // delete actions
    document.querySelectorAll('.delete-action').forEach(el => {
      el.onclick = null;
      el.addEventListener('click', (e) => {
        e.preventDefault();
        const id = el.dataset.clientId;
        deleteModal.dataset.pendingId = id;
        deleteModal && deleteModal.classList.remove('hidden');
      });
    });

    // status toggles: note - template uses inline onchange="toggleActive('{id}', this)" so we don't rely on data attr
    // but we still ensure any dynamically-rendered checkboxes behave if they were added without inline handler.
    document.querySelectorAll('input[type="checkbox"]').forEach(chk => {
      // only attach if checkbox appears to be a status toggle (has a .status-text sibling) to avoid interfering with other checkboxes
      const statusText = chk.closest('td')?.querySelector('.status-text');
      if (!statusText) return;
      // ensure an onchange exists
      if (!chk.getAttribute('data-toggle-bound')) {
        chk.setAttribute('data-toggle-bound', '1');
        chk.addEventListener('change', function () {
          // prefer inline handler if present, otherwise call our toggle
          const clientIdInline = chk.getAttribute('data-toggle-client-id');
          if (clientIdInline) {
            window.toggleActive(clientIdInline, chk);
          } else {
            // try to retrieve id from row data
            const row = chk.closest('tr');
            const idFromRow = row ? (row.dataset.clientId || (row.querySelectorAll('td')[1] || {}).textContent || '').toString().trim() : '';
            if (idFromRow) window.toggleActive(idFromRow, chk);
          }
        });
      }
    });
  }

  // ---------- Edit (match backend: POST /clients/edit/{id} with form field new_name) ----------
  if (editClientForm) {
    editClientForm.addEventListener('submit', async function (ev) {
      ev.preventDefault();

      const id = modalClientId.value;
      const newName = (modalClientName.value || '').trim();
      if (!id) { alert('No client selected to edit'); return; }
      if (!newName) { alert('Client name cannot be empty'); return; }

      const editUrlPrimary = `/clients/edit/${id}`;
      let form = new FormData();
      form.append('new_name', newName);

      try {
        const res = await fetch(editUrlPrimary, { method: 'POST', body: form });
        if (res.ok) {
          editModal && editModal.classList.add('hidden');
          updateClientNameInCache(id, newName);
          applyFilters();
          // alert('Client updated successfully.');
          return;
        } else {
          const text = await safeText(res);
          console.warn(`POST ${editUrlPrimary} returned ${res.status}`, text);
        }
      } catch (err) {
        console.warn('Error calling POST', editUrlPrimary, err);
      }

      // Fallbacks — try PUT/POST/PATCH on likely endpoints
      const candidateUrls = [
        `/clients/${id}`,
        `/clients/all_clients/${id}`,
        `/clients/${id}/edit`,
        `/clients/update/${id}`
      ];
      const payload = { client_name: newName };

      let result = await tryEndpointsSequentially(candidateUrls, (url) => ({
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }));

      if (!result.ok) {
        result = await tryEndpointsSequentially(candidateUrls, (url) => ({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }));
      }

      if (!result.ok) {
        result = await tryEndpointsSequentially(candidateUrls, (url) => ({
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }));
      }

      if (result.ok) {
        editModal && editModal.classList.add('hidden');
        updateClientNameInCache(id, newName);
        applyFilters();
        alert('Client updated successfully (via fallback).');
      } else {
        const le = result.lastError || {};
        let msg = '';
        if (le.url) msg += `Tried: ${le.url}\n`;
        if (le.status) msg += `Status: ${le.status} ${le.statusText || ''}\n`;
        if (le.text) msg += `Response: ${le.text}\n`;
        if (le.message) msg += `Error: ${le.message}\n`;
        console.error('Edit failed details:', le);
        alert('Update failed. See console for details. Server response:\n\n' + (msg || 'No details available.'));
      }
    });
  }

  function updateClientNameInCache(clientId, newName) {
    for (let i = 0; i < originalRows.length; i++) {
      const or = originalRows[i];
      const cid = (or.dataset.clientId || (or.querySelectorAll('td')[1] || {}).textContent || '').toString().trim();
      if (cid == clientId) {
        const firstTd = or.querySelectorAll('td')[0];
        if (firstTd) firstTd.textContent = newName;
      }
    }
  }

  // ---------- Delete (use POST /clients/delete/{id} as primary) ----------
  confirmDeleteBtn?.addEventListener('click', async function () {
    const pending = deleteModal?.dataset?.pendingId;
    if (!pending) { alert('No client selected'); return; }
    this.disabled = true;
    this.textContent = 'Deleting...';

    const primary = `/clients/delete/${pending}`;
    try {
      const res = await fetch(primary, { method: 'POST' });
      if (res.ok) {
        deleteModal && deleteModal.classList.add('hidden');
        originalRows = originalRows.filter(or => {
          const cid = (or.dataset.clientId || (or.querySelectorAll('td')[1] || {}).textContent || '').toString().trim();
          return cid !== pending;
        });
        applyFilters();
        //alert('Client deleted successfully.');
        this.disabled = false;
        this.textContent = 'Delete';
        return;
      } else {
        const text = await safeText(res);
        console.warn(`POST ${primary} returned ${res.status}`, text);
      }
    } catch (err) {
      console.warn('Error calling POST', primary, err);
    }

    const candidateUrls = [
      `/clients/${pending}`,
      `/clients/all_clients/${pending}`,
      `/clients/remove/${pending}`
    ];

    let result = await tryEndpointsSequentially(candidateUrls, (url) => ({ method: 'DELETE' }));
    if (!result.ok) {
      const postDeleteUrls = candidateUrls.concat(candidateUrls.map(u => u + '/delete'));
      result = await tryEndpointsSequentially(postDeleteUrls, (url) => ({ method: 'POST' }));
    }

    if (result.ok) {
      deleteModal && deleteModal.classList.add('hidden');
      originalRows = originalRows.filter(or => {
        const cid = (or.dataset.clientId || (or.querySelectorAll('td')[1] || {}).textContent || '').toString().trim();
        return cid !== pending;
      });
      applyFilters();
      alert('Client deleted successfully (via fallback).');
    } else {
      const le = result.lastError || {};
      let msg = '';
      if (le.url) msg += `Tried: ${le.url}\n`;
      if (le.status) msg += `Status: ${le.status} ${le.statusText || ''}\n`;
      if (le.text) msg += `Response: ${le.text}\n`;
      if (le.message) msg += `Error: ${le.message}\n`;
      console.error('Delete failed details:', le);
      alert('Delete failed. See console for details. Server response:\n\n' + (msg || 'No details available.'));
    }

    this.disabled = false;
    this.textContent = 'Delete';
  });

  // ---------- Toggle active/inactive (primary endpoint POST /clients/toggle/{id}) ----------
  // Optimistic UI update: update immediately and persist the state into originalRows (checkbox + label) so future re-renders keep it.
  window.toggleActive = window.toggleActive || async function (clientId, checkboxEl) {
    if (!clientId || !checkboxEl) return;

    const newChecked = !!checkboxEl.checked; // current desired state
    // optimistic update: immediately update label text in DOM
    const statusTextEl = checkboxEl.closest('td')?.querySelector('.status-text');
    if (statusTextEl) statusTextEl.textContent = newChecked ? 'Active' : 'Inactive';

    // *** Update the cached originalRows FULLY (dataset + internal checkbox + status text)
    originalRows.forEach(or => {
      const cid = (or.dataset.clientId || (or.querySelectorAll('td')[1] || {}).textContent || '').toString().trim();
      if (cid == clientId) {
        // update dataset status
        or.dataset.status = newChecked ? 'active' : 'inactive';
        // update any status-text element inside cached row
        const st = or.querySelector('.status-text');
        if (st) st.textContent = newChecked ? 'Active' : 'Inactive';
        // update checkbox inside cached row if present
        const chk = or.querySelector('input[type="checkbox"]');
        if (chk) {
          // set attribute & property
          if (newChecked) chk.setAttribute('checked', 'checked');
          else chk.removeAttribute('checked');
          chk.checked = newChecked;
        }
      }
    });

    // disable while the request runs
    checkboxEl.disabled = true;

    // Attempt primary endpoint first
    const primary = `/clients/toggle/${clientId}`;
    try {
      const res = await fetch(primary, { method: 'POST' });
      if (res && res.ok) {
        checkboxEl.disabled = false;
        return;
      }
    } catch (err) {
      console.warn('toggleActive POST failed:', err);
    }

    // fallback: try POST to likely endpoints with JSON body
    const fallbackUrls = [`/clients/${clientId}`, `/clients/all_clients/${clientId}`];
    const body = JSON.stringify({ status: newChecked ? 'active' : 'inactive' });
    const res2 = await tryEndpointsSequentially(fallbackUrls, (url) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body }));
    if (res2.ok) {
      checkboxEl.disabled = false;
      return;
    }

    // second fallback: PATCH attempts
    const res3 = await tryEndpointsSequentially(fallbackUrls, (url) => ({ method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body }));
    if (res3.ok) {
      checkboxEl.disabled = false;
      return;
    }

    // If we reach here: all attempts failed to return ok.
    // We keep the optimistic UI change (prevent immediate flick-back) but inform the user.
    checkboxEl.disabled = false;
    console.warn(`toggleActive: couldn't confirm server update for client ${clientId}. UI kept optimistic state.`);
    setTimeout(() => {
      alert('Status change could not be confirmed by the server right now. UI updated optimistically — refresh later to confirm.');
    }, 50);
  };

  // ---------- Create modal and add-job dynamic fields ----------
  createClientBtn?.addEventListener('click', () => createModal && createModal.classList.remove('hidden'));
  // ---------- Edit modal close handlers ----------
const closeEditModal = document.getElementById('closeEditModal');
const cancelEdit = document.getElementById('cancelEdit');
closeEditModal?.addEventListener('click', () => editModal && editModal.classList.add('hidden'));
cancelEdit?.addEventListener('click', () => editModal && editModal.classList.add('hidden'));

// ---------- Delete modal close handlers ----------
const closeDeleteModal = document.getElementById('closeDeleteModal');
const cancelDelete = document.getElementById('cancelDelete');
closeDeleteModal?.addEventListener('click', () => deleteModal && deleteModal.classList.add('hidden'));
cancelDelete?.addEventListener('click', () => deleteModal && deleteModal.classList.add('hidden'));


  addJobFieldBtn?.addEventListener('click', () => {
    if (!jobsContainer) return;
    const block = document.createElement('div');
    block.className = 'job-item grid grid-cols-1 gap-2';
    block.innerHTML = `
      <hr>
      <div>
        <label class="block text-sm font-medium text-gray-700">Job Title *</label>
        <input type="text" name="job_titles" class="mt-1 block w-full border rounded px-3 py-2" required />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700">Job Description</label>
        <textarea name="job_descriptions" rows="3" class="mt-1 block w-full border rounded px-3 py-2"></textarea>
      </div>
      <div>
        <button type="button" class="remove-job inline-flex items-center gap-2 px-3 py-2 bg-red-50 text-red-700 rounded hover:bg-red-100">Remove</button>
      </div>
    `;
    jobsContainer.appendChild(block);
    block.querySelector('.remove-job')?.addEventListener('click', () => block.remove());
  });

  // ---------- Sidebar toggle & layout expand/shrink ----------
  function setSidebarHiddenState(hidden) {
    if (!filterSidebar || !mainContentEl) return;
    if (hidden) {
      filterSidebar.classList.add('hidden-desktop');
      mainContentEl.classList.add('expanded-by-sidebar');
      sidebarOverlay && sidebarOverlay.classList.add('hidden');
      filterToggle && filterToggle.setAttribute('aria-pressed', 'true');
    } else {
      filterSidebar.classList.remove('hidden-desktop');
      mainContentEl.classList.remove('expanded-by-sidebar');
      sidebarOverlay && sidebarOverlay.classList.add('hidden');
      filterToggle && filterToggle.setAttribute('aria-pressed', 'false');
    }
  }

  filterToggle?.addEventListener('click', () => {
    if (window.innerWidth >= 1024) {
      desktopHidden = !desktopHidden;
      setSidebarHiddenState(desktopHidden);
    } else {
      filterSidebar.classList.remove('-translate-x-full');
      sidebarOverlay && sidebarOverlay.classList.remove('hidden');
    }
  });

  closeFilters?.addEventListener('click', () => {
    if (window.innerWidth < 1024) {
      filterSidebar.classList.add('-translate-x-full');
      sidebarOverlay && sidebarOverlay.classList.add('hidden');
    } else {
      desktopHidden = false;
      setSidebarHiddenState(false);
    }
  });

  sidebarOverlay?.addEventListener('click', () => {
    filterSidebar.classList.add('-translate-x-full');
    sidebarOverlay.classList.add('hidden');
  });

  // ---------- Initialization ----------
  window.addEventListener('DOMContentLoaded', () => {
    buildOriginalRowsCache();
    attachFilterControls();
    attachRowActionListeners();
    applyFilters();
    if (window.innerWidth >= 1024) {
      if (desktopHidden) setSidebarHiddenState(true);
      else setSidebarHiddenState(false);
    } else {
      filterSidebar && filterSidebar.classList.add('-translate-x-full');
      sidebarOverlay && sidebarOverlay.classList.add('hidden');
    }
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth >= 1024) {
      sidebarOverlay && sidebarOverlay.classList.add('hidden');
      if (desktopHidden) setSidebarHiddenState(true); else setSidebarHiddenState(false);
    } else {
      filterSidebar && filterSidebar.classList.remove('show');
      filterSidebar && filterSidebar.classList.add('-translate-x-full');
    }
  });

  // allow external call to rebuild cache
  window.__rebuildClientsCache = function () { buildOriginalRowsCache(); applyFilters(); };

})();
