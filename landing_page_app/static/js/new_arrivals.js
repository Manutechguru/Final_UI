// static/js/new_arrivals.js
// Clients page JavaScript (complete). Handles filters, search, create/edit/delete, toggles.
// IMPORTANT: This file updates UI only; no backend wiring changes are made.

(function () {
  'use strict';

  // ---------- Simple toast/notification system ----------
  // A11y + small non-blocking toasts shown in bottom-right corner.
  const TOAST_CONTAINER_ID = 'appToastContainer';

  function ensureToastContainer() {
    let c = document.getElementById(TOAST_CONTAINER_ID);
    if (!c) {
      c = document.createElement('div');
      c.id = TOAST_CONTAINER_ID;
      c.setAttribute('aria-live', 'polite');
      c.setAttribute('aria-atomic', 'false');
      c.style.position = 'fixed';
      c.style.right = '20px';
      c.style.bottom = '20px';
      c.style.zIndex = '100000';
      c.style.display = 'flex';
      c.style.flexDirection = 'column';
      c.style.gap = '10px';
      document.body.appendChild(c);
    }
    return c;
  }

  // showToast(message, { type: 'success'|'error'|'info', duration: ms })
  function showToast(message, opts = {}) {
  const title = opts.title || "Success";
  const duration = typeof opts.duration === "number" ? opts.duration : 4000;

  const container = ensureToastContainer();

  const toast = document.createElement("div");
  toast.className = "app-toast";

  toast.innerHTML = `
    <div class="app-toast__icon">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M5 9l3 3L13 7"></path>
      </svg>
    </div>
    <div class="app-toast__content">
      <div class="app-toast__title">${title}</div>
      <div class="app-toast__message">${message}</div>
    </div>
    <button class="app-toast__close" aria-label="Close">&times;</button>
  `;

  const closeBtn = toast.querySelector(".app-toast__close");
  const dismiss = () => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(20px)";
    setTimeout(() => toast.remove(), 200);
  };
  closeBtn.addEventListener("click", dismiss);

  container.appendChild(toast);
  setTimeout(dismiss, duration);
}

  window.showServerMessage = function (message) {
    if (!message) return;
    // message may contain pipe separators if backend combined messages
    const parts = message.split('|').map(p => p.trim()).filter(Boolean);
    parts.forEach(p => {
      // If backend message already includes "Client 'name' ..." we show as-is.
      showToast(p, { type: 'success' });
    });
  };

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
  // Robustly discover clientId for each row (handles cases where id moved into dropdown/menu)
  function discoverClientIdFromRowElement(rowEl) {
    // 1) dataset on the row itself
    if (rowEl.dataset && rowEl.dataset.clientId) return rowEl.dataset.clientId.toString().trim();

    // 2) second <td> (legacy layout)
    const tds = rowEl.querySelectorAll('td');
    if (tds && tds.length >= 2) {
      const maybe = (tds[1].textContent || '').toString().trim();
      if (maybe) return maybe;
    }

    // 3) try to find an element with class view-details-action and use its data-client-id
    const vda = rowEl.querySelector('.view-details-action');
    if (vda && vda.dataset && vda.dataset.clientId) return vda.dataset.clientId.toString().trim();

    // 4) generic: find any element with data-client-id attribute
    const anyWithData = rowEl.querySelector('[data-client-id]');
    if (anyWithData && anyWithData.dataset && anyWithData.dataset.clientId) return anyWithData.dataset.clientId.toString().trim();

    // 5) last resort: attempt to parse an "ID:" like pattern from text (very lenient)
    const fullText = (rowEl.textContent || '').toString();
    const match = fullText.match(/\bID[:#\s]*([A-Za-z0-9\-_]+)\b/i);
    if (match && match[1]) return match[1].trim();

    return '';
  }

  function buildOriginalRowsCache() {
    originalRows = [];
    if (!clientsTableBody) return;
    const trs = Array.from(clientsTableBody.querySelectorAll('tr'));
    trs.forEach(tr => {
      const clone = tr.cloneNode(true);
      // ensure dataset entries exist
      if (!clone.dataset.clientId) {
        const discovered = discoverClientIdFromRowElement(clone);
        if (discovered) clone.dataset.clientId = discovered;
      }
      if (!clone.dataset.status) {
        const st = clone.querySelector('.status-text');
        clone.dataset.status = st ? (st.textContent || '').trim().toLowerCase() : '';
      }
      // keep existing created dataset if present (some templates set it on row)
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

        // find the menu related to this toggle
        const menu = btn.parentElement.querySelector('.dropdown-menu');

        // ===== Reorder menu items here BEFORE showing the menu =====
        if (menu) {
          try {
            // Desired order (case-insensitive match)
            const ORDER = ['View Details', 'Edit', 'Delete'];

            // find all actionable nodes in the menu (buttons and anchors)
            const nodes = Array.from(menu.querySelectorAll('button, a')).filter(Boolean);

            // map found label -> node (first match wins)
            const found = {};
            nodes.forEach(n => {
              const txt = (n.textContent || '').trim().replace(/\s+/g, ' ');
              ORDER.forEach(label => {
                if (!found[label] && txt.toLowerCase().includes(label.toLowerCase())) {
                  found[label] = n;
                }
              });
            });

            // append in desired order (moves nodes in DOM)
            ORDER.forEach(label => {
              if (found[label]) menu.appendChild(found[label]);
            });

            // append any remaining nodes preserving original order
            nodes.forEach(n => {
              if (!Object.values(found).includes(n)) menu.appendChild(n);
            });
          } catch (err) {
            // nonfatal — we still proceed to show the menu
            console.warn('Dropdown reorder failed', err);
          }
        }
        // ===== end reorder =====

        // hide other open menus
        document.querySelectorAll('.dropdown-menu').forEach(m => {
          if (m !== menu) m.classList.remove('show');
        });
        document.querySelectorAll('.dropdown-toggle').forEach(b => {
          if (b !== btn) b.setAttribute('aria-expanded', 'false');
        });

        // toggle this menu
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

    // view details actions
    document.querySelectorAll('.view-details-action').forEach(el => {
      el.onclick = null;
      el.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();

         // close all menus before opening modal
    document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
    document.querySelectorAll('.dropdown-toggle').forEach(b => b.setAttribute('aria-expanded', 'false'));

        // robust client id lookup: element dataset or fallback to closest row
        let id = (el.dataset && el.dataset.clientId) ? el.dataset.clientId : '';
        if (!id) {
          const row = el.closest('tr');
          if (row) id = discoverClientIdFromRowElement(row);
        }
        id = id || '';

        // if still empty, abort gracefully
        if (!id) {
          console.warn('view-details-action: no client id found for clicked element', el);
          alert('Client identifier not found for this row. See console for details.');
          return;
        }

        // call backend
        try {
          const resp = await fetch(`/clients/details/${encodeURIComponent(id)}`);
          if (!resp.ok) {
            const text = await safeText(resp);
            console.warn('Details fetch failed', resp.status, text);
            alert('Could not fetch client details. See console for details.');
            return;
          }
          const data = await resp.json();

          // fill modal fields
          const vdNameEl = document.getElementById("vdName");
          const vdCreatedByEl = document.getElementById("vdCreatedBy");
          const vdCreatedAtEl = document.getElementById("vdCreatedAt");
          const vdUpdatedByEl = document.getElementById("vdUpdatedBy");
          const vdUpdatedAtEl = document.getElementById("vdUpdatedAt");
          const vdClientIdEl = document.getElementById("vdClientId");

          if (vdNameEl) vdNameEl.textContent = data.client_name || "N/A";
          if (vdCreatedByEl) vdCreatedByEl.textContent = data.created_by || "N/A";
          if (vdCreatedAtEl) vdCreatedAtEl.textContent = data.created_at || "N/A";
          if (vdUpdatedByEl) vdUpdatedByEl.textContent = data.updated_by || "N/A";
          if (vdUpdatedAtEl) vdUpdatedAtEl.textContent = data.updated_at || "N/A";

          // set client id into modal if there is a placeholder for it (helps show moved ID)
          if (vdClientIdEl) vdClientIdEl.textContent = data.client_id || id || "N/A";

          // show modal
          const vModal = document.getElementById("viewDetailsModal");
          if (vModal) vModal.classList.remove("hidden");
        } catch (err) {
          console.warn('Error fetching client details', err);
          alert('Error fetching client details. See console for details.');
        }
      });
    });

    // status toggles — no need to rebind, HTML already calls toggleActive() inline
    // just ensure the checkboxes have correct dataset attributes if needed
    document.querySelectorAll('input[type="checkbox"]').forEach(chk => {
      if (chk.closest('td')?.querySelector('.status-text')) {
      // mark as handled so we don't double attach later
      chk.setAttribute('data-toggle-bound', '1');
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
          // show toast instead of alert
          showToast(`Client '${newName}' edited successfully.`);
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
        showToast(`Client '${newName}' edited successfully (via fallback).`);
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
      const cid = (or.dataset.clientId || discoverClientIdFromRowElement(or) || (or.querySelectorAll('td')[1] || {}).textContent || '').toString().trim();
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
        // derive client name for toast (try to find from cache)
        let clientName = pending;
        for (let i = 0; i < originalRows.length; i++) {
          const or = originalRows[i];
          const cid = (or.dataset.clientId || discoverClientIdFromRowElement(or) || (or.querySelectorAll('td')[1] || {}).textContent || '').toString().trim();
          if (cid === pending) {
            clientName = (or.querySelector('td')?.textContent || pending);
            break;
          }
        }
        originalRows = originalRows.filter(or => {
          const cid = (or.dataset.clientId || discoverClientIdFromRowElement(or) || (or.querySelectorAll('td')[1] || {}).textContent || '').toString().trim();
          return cid !== pending;
        });
        applyFilters();
        showToast(`Client '${clientName}' deleted successfully.`);
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
      // try to find name
      let clientName = pending;
      for (let i = 0; i < originalRows.length; i++) {
        const or = originalRows[i];
        const cid = (or.dataset.clientId || discoverClientIdFromRowElement(or) || (or.querySelectorAll('td')[1] || {}).textContent || '').toString().trim();
        if (cid === pending) {
          clientName = (or.querySelector('td')?.textContent || pending);
          break;
        }
      }
      originalRows = originalRows.filter(or => {
        const cid = (or.dataset.clientId || discoverClientIdFromElement(or) || discoverClientIdFromRowElement(or) || '').toString().trim();
        return cid !== pending;
      });
      applyFilters();
      showToast(`Client '${clientName}' deleted successfully (via fallback).`);
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
      const cid = (or.dataset.clientId || discoverClientIdFromRowElement(or) || (or.querySelectorAll('td')[1] || {}).textContent || '').toString().trim();
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
        // show toast for activation/deactivation
        // attempt to find client name
        let clientName = clientId;
        const row = checkboxEl.closest('tr');
        if (row) clientName = (row.querySelector('td')?.textContent || clientId);
        showToast(`Client '${clientName}' ${newChecked ? 'activated' : 'inactivated'} successfully.`);
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
      let clientName = clientId;
      const row = checkboxEl.closest('tr');
      if (row) clientName = (row.querySelector('td')?.textContent || clientId);
      showToast(`Client '${clientName}' ${newChecked ? 'activated' : 'inactivated'} successfully.`);
      checkboxEl.disabled = false;
      return;
    }

    // second fallback: PATCH attempts
    const res3 = await tryEndpointsSequentially(fallbackUrls, (url) => ({ method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body }));
    if (res3.ok) {
      let clientName = clientId;
      const row = checkboxEl.closest('tr');
      if (row) clientName = (row.querySelector('td')?.textContent || clientId);
      showToast(`Client '${clientName}' ${newChecked ? 'activated' : 'inactivated'} successfully.`);
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
  // ---------- Create modal close handlers ----------
closeCreateModal?.addEventListener('click', () => {
  createModal && createModal.classList.add('hidden');
});

cancelCreate?.addEventListener('click', () => {
  createModal && createModal.classList.add('hidden');
});

// close when clicking OUTSIDE modal box (optional safety)
createModal?.addEventListener('click', (e) => {
  if (e.target.id === 'createModal') {
    createModal.classList.add('hidden');
  }
});

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

  // ---------- View Details modal close handlers ----------
const closeViewDetailsModal = document.getElementById('closeViewDetailsModal'); // X icon top right
const closeViewDetailsBtn = document.getElementById('closeViewDetailsBtn');     // bottom big close btn
const viewDetailsModal = document.getElementById('viewDetailsModal');

closeViewDetailsModal?.addEventListener('click', () => viewDetailsModal?.classList.add('hidden'));
closeViewDetailsBtn?.addEventListener('click', () => viewDetailsModal?.classList.add('hidden'));

// close when clicking OUTSIDE modal box
viewDetailsModal?.addEventListener('click', (e) => {
  if (e.target.id === 'viewDetailsModal') {
    viewDetailsModal.classList.add('hidden');
  }
});


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

    // If server injected a message via global variable (set by template), show it.
    if (window.__SERVER_TOAST_MESSAGE) {
      try {
        window.showServerMessage(window.__SERVER_TOAST_MESSAGE);
        // clear it so repeated DOMContentLoaded won't re-show
        window.__SERVER_TOAST_MESSAGE = '';
      } catch (e) { /* ignore */ }
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

  // helper (small safe alias used above)
  function discoverClientIdFromElement(el) {
    const row = el.closest && el.closest('tr');
    return row ? discoverClientIdFromRowElement(row) : '';
  }

})();
