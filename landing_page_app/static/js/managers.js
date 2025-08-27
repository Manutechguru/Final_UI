// static/js/managers.js
document.addEventListener("DOMContentLoaded", () => {
  const grid = document.getElementById('managersGrid');

  // close dropdowns helper
  function closeAllDropdowns() {
    document.querySelectorAll('.dropdown-content').forEach(m => m.classList.remove('show'));
    document.querySelectorAll('.three-dots-btn').forEach(b => b.setAttribute('aria-expanded', 'false'));
  }

  // attach dropdown handlers
  document.querySelectorAll('.three-dots-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      closeAllDropdowns();
      const parent = btn.closest('.three-dots');
      const menu = parent.querySelector('.dropdown-content');
      const show = menu.classList.toggle('show');
      btn.setAttribute('aria-expanded', show ? 'true' : 'false');
    });
  });

  document.addEventListener('click', () => closeAllDropdowns());
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeAllDropdowns(); });

  async function parseResponseSafely(res) {
    const text = await res.text();
    try {
      return { ok: res.ok, status: res.status, json: JSON.parse(text), text };
    } catch {
      return { ok: res.ok, status: res.status, json: null, text };
    }
  }

  // Delegated - toggle switches
  grid.addEventListener('change', async (e) => {
    const el = e.target;
    if (!el.classList.contains('toggle-switch')) return;

    const toggleUrl = el.dataset.toggleUrl;
    const managerCard = el.closest('.manager-card');
    const statusBadge = managerCard ? managerCard.querySelector('.status-badge') : null;

    if (!toggleUrl) {
      console.error('Toggle URL missing', el);
      el.checked = !el.checked;
      return;
    }

    const desired = el.checked ? 'active' : 'inactive';
    console.log('[MANAGERS] Toggle request ->', toggleUrl, 'desired=', desired);

    try {
      const res = await fetch(toggleUrl, {
        method: 'POST',
        credentials: 'same-origin',   // send session cookie
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ status: desired })
      });

      const parsed = await parseResponseSafely(res);
      console.log('[MANAGERS] toggle response', parsed);

      if (!parsed.ok) {
        const msg = parsed.json?.detail || parsed.json?.message || parsed.text || 'Status ${parsed.status}';
        alert('Failed to toggle: ' + msg);
        el.checked = !el.checked;
        return;
      }

      const data = parsed.json || {};
      const newStatus = data.new_status || desired;
      if (statusBadge) {
        statusBadge.textContent = newStatus.charAt(0).toUpperCase() + newStatus.slice(1);
        statusBadge.className = 'status-badge ' + (newStatus === 'active' ? 'active' : 'inactive');
      }

      // update updated-by/time if provided
      if (data.updated_by_name || data.updated_at) {
        if (managerCard) {
          const metaRows = managerCard.querySelectorAll('.card-meta .meta-row');
          if (metaRows[1]) {
            const val = metaRows[1].querySelector('.meta-value');
            const ts = metaRows[1].querySelector('.meta-ts');
            if (val && data.updated_by_name) val.textContent = data.updated_by_name;
            if (ts && data.updated_at) ts.textContent = (data.updated_at.length ? data.updated_at.replace('T',' ').split('.')[0] : data.updated_at);
          }
        }
      }
    } catch (err) {
      console.error('Network/error toggling status', err);
      alert('Network error toggling status: ' + err.message);
      el.checked = !el.checked;
    }
  });

  // Delegated click for menu actions (delete/edit)
  grid.addEventListener('click', async (e) => {
    const del = e.target.closest('.menu-delete');
    if (del) {
      e.preventDefault();
      const url = del.dataset.deleteUrl;
      if (!url) { alert('Delete URL missing'); return; }
      if (!confirm('Delete this vendor and all its jobs?')) return;
      try {
        const res = await fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' }});
        const parsed = await parseResponseSafely(res);
        if (!parsed.ok) { alert(parsed.json?.detail || parsed.text || 'Failed to delete'); return; }
        const card = del.closest('.manager-card'); if (card) card.remove();
      } catch (err) { alert('Error deleting vendor: ' + err.message); }
      return;
    }

    const edt = e.target.closest('.menu-edit');
    if (edt) {
      e.preventDefault();
      const editUrl = edt.dataset.editUrl;
      const currentName = edt.dataset.name || edt.closest('.manager-card').querySelector('.card-title').textContent;
      const newName = prompt('Edit vendor name:', currentName);
      if (!newName || newName.trim() === '' || newName.trim() === currentName.trim()) return;
      try {
        const body = new URLSearchParams({ manager_name: newName.trim() });
        const res = await fetch(editUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
          },
          body: body.toString()
        });
        const parsed = await parseResponseSafely(res);
        if (!parsed.ok) { alert(parsed.json?.detail || parsed.text || 'Failed to update vendor'); return; }
        const data = parsed.json || {};
        const card = edt.closest('.manager-card');
        if (card) {
          const title = card.querySelector('.card-title');
          if (title) title.textContent = data.manager_name || newName.trim();
          const metaRows = card.querySelectorAll('.card-meta .meta-row');
          if (data.updated_by_name && metaRows[1]) {
            const val = metaRows[1].querySelector('.meta-value');
            const ts = metaRows[1].querySelector('.meta-ts');
            if (val) val.textContent = data.updated_by_name;
            if (ts && data.updated_at) ts.textContent = (data.updated_at.length ? data.updated_at.replace('T',' ').split('.')[0] : data.updated_at);
          }
        }
        alert('Vendor updated');
      } catch (err) { alert('Error updating vendor: ' + err.message); }
      return;
    }
  });

});