(function(){
  try {
    document.addEventListener("DOMContentLoaded", function () {
      const jdSelect = document.getElementById("jdSelect");
      const jobInput = document.getElementById("selectedJobInput");
      const form = document.getElementById("dropdownAiForm");
      if (!form || !jdSelect || !jobInput) return;
      // on submit, ensure job selected and set hidden input, then show AI overlay before submitting
      form.addEventListener("submit", function(e) {
        if (!jdSelect.value) {
          e.preventDefault();
          alert("Please select a Job first.");
          return;
        }
        jobInput.value = jdSelect.value;

        // Show AI progress overlay before submit
        e.preventDefault();
        try {
          if (typeof showAiProgress === 'function') {
            showAiProgress({
              title: "AI Evaluation",
              subtitle: "Analyzing JD and matching candidates — this may take a few moments."
            });
          } else {
            const overlay = document.getElementById('aiProgressOverlay');
            if (overlay) {
              const titleEl = document.getElementById('aiProgressTitle');
              const subEl = document.getElementById('aiProgressSubtitle');
              if (titleEl) titleEl.textContent = "AI Evaluation";
              if (subEl) subEl.textContent = "Analyzing JD and matching candidates — this may take a few moments.";
              overlay.style.display = 'flex';
              try { document.body.style.overflow = 'hidden'; } catch(e){}
            }
          }
        } catch (err) {
          console.warn('showAiProgress error', err);
        }

        // Ensure browser repaints overlay before navigation by waiting two animation frames
        requestAnimationFrame(function(){
          requestAnimationFrame(function(){
            form.submit();
          });
        });
      });
    });
  } catch (e) { console.warn('dropdownAiForm init failed', e); }
})();

/* Replaced JS — robust dropdown persistence, reset, pageshow handling, delegation, modal, pagination.
   IMPORTANT: This script keeps every backend endpoint, form action and UI markup EXACTLY the same.
   Only behavior changed: when returning to page we now force server fetch to repopulate vendor/job
   lists when a saved client exists (fixes vanish on navigation/back).
*/

document.addEventListener('DOMContentLoaded', function () {
  // Element refs
  const clientSelectEl = () => document.getElementById('clientSelect');
  const vendorSelectEl = () => document.getElementById('vendorSelect');
  const jdSelectEl = () => document.getElementById('jdSelect');
  const tbody = () => document.getElementById('search-results-body');
  const recordsPerEl = document.getElementById('records-per-page');
  const prevBtn = document.getElementById('prev-page');
  const nextBtn = document.getElementById('next-page');
  const pageInfo = document.getElementById('page-info');
  const recentlyLinkedBtn = document.getElementById('recentlyLinkedBtn');
  const aiProgressOverlay = document.getElementById('aiProgressOverlay');
  const advancedForm = document.getElementById('advancedSearchForm');
  const searchForm = document.getElementById('searchForm');

  // Keys
  const STORAGE_KEY = 'nxg_search_snapshot_v1';
  const DD_STATE_KEY = 'nxg_dropdown_state_v1';
  const LINKED_IDS_KEY = 'nxg_linked_candidate_ids_v1';
  const RECENTLY_KEY = 'recently_linked';
  const RESET_FLAG = 'nxg_reset_flag_v1';

  // --- UI helpers ---
  function showAiProgress(opts = {}) {
    try {
      if (opts.title) document.getElementById('aiProgressTitle').textContent = opts.title;
      if (opts.subtitle) document.getElementById('aiProgressSubtitle').textContent = opts.subtitle;
      if (aiProgressOverlay) aiProgressOverlay.style.display = 'flex';
      document.body.style.overflow = 'hidden';
    } catch(e){}
  }
  function hideAiProgress() {
    try { if (aiProgressOverlay) aiProgressOverlay.style.display = 'none'; } catch(e){}
    document.body.style.overflow = '';
  }
  function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, function(m){ return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]); });
  }
  
  /* add this right after escapeHtml(s) */
  function decodeHtmlEntities(str) {
    if (!str) return '';
    const ta = document.createElement('textarea');
    ta.innerHTML = str;
    return ta.value;
  }
function showToast(msg, type='default', time=3200) {
    try {
      const c = document.getElementById('richToastContainer') || document.body;
      const el = document.createElement('div');
      el.className = 'rich-toast' + (type==='success' ? ' success' : '');
      el.innerHTML = `<div class="rt-left">${type==='success' ? '✔' : ''}</div><div style="flex:1;"><div class="rt-main">${escapeHtml(msg)}</div></div><button class="rt-close" aria-label="Close">&times;</button>`;
      c.appendChild(el);
      el.querySelector('.rt-close').addEventListener('click', ()=>el.remove());
      setTimeout(()=>{ el.style.opacity='0'; setTimeout(()=>el.remove(),300); }, time);
    } catch(e){}
  }

  // --- dropdown persistence ---
  function saveDropdownState() {
    try {
      const clientSelect = clientSelectEl();
      const vendorSelect = vendorSelectEl();
      const jdSelect = jdSelectEl();
      const state = {
        client: clientSelect ? clientSelect.value : '',
        vendor: vendorSelect ? vendorSelect.value : '',
        job: jdSelect ? jdSelect.value : '',
        vendors: vendorSelect ? Array.from(vendorSelect.options).map(o=>({value:o.value, text:o.textContent})) : [],
        jobs: jdSelect ? Array.from(jdSelect.options).map(o=>({value:o.value, text:o.textContent})) : []
      };
      localStorage.setItem(DD_STATE_KEY, JSON.stringify(state));
    } catch(e){}
  }

  function clearDropdownState() {
    try { localStorage.removeItem(DD_STATE_KEY); } catch(e){}
  }

  // --- fetching helpers (unchanged endpoints) ---
  async function fetchVendorsForClient(clientId) {
    const vendorSelect = vendorSelectEl();
    const jdSelect = jdSelectEl();
    if (!vendorSelect || !jdSelect) return;
    vendorSelect.innerHTML = '<option value="">Select Manager</option>';
    jdSelect.innerHTML = '<option value="">Select Job</option>';
    if (!clientId) { saveDropdownState(); applyLinkedIds(); return; }
    try {
      const res = await fetch(`/candidates/get-vendors/${encodeURIComponent(clientId)}`);
      const data = await res.json().catch(()=>[]);
      (data || []).forEach(v => {
        const o = document.createElement('option'); o.value = v.vendor_id; o.textContent = v.vendor_name; vendorSelect.appendChild(o);
      });
      saveDropdownState();
    } catch(e){ console.warn('fetchVendorsForClient', e); }
  }

  async function fetchJobsForVendor(vendorId) {
    const jdSelect = jdSelectEl();
    if (!jdSelect) return;
    jdSelect.innerHTML = '<option value="">Select Job</option>';
    if (!vendorId) { saveDropdownState(); return; }
    try {
      const res = await fetch(`/candidates/get-jobs/${encodeURIComponent(vendorId)}`);
      const data = await res.json().catch(()=>[]);
      (data || []).forEach(j => {
        const o = document.createElement('option'); o.value = j.job_id; o.textContent = j.job_title; jdSelect.appendChild(o);
      });
      saveDropdownState();
    } catch(e){ console.warn('fetchJobsForVendor', e); }
  }

  // safe-binding: avoid duplicate event listeners using dataset flags
  function bindCascadingOnce() {
    try {
      const clientSelect = clientSelectEl();
      const vendorSelect = vendorSelectEl();
      const jdSelect = jdSelectEl();
      if (clientSelect && clientSelect.dataset.bound !== '1') {
        clientSelect.addEventListener('change', function(){ fetchVendorsForClient(this.value); });
        clientSelect.dataset.bound = '1';
      }
      if (vendorSelect && vendorSelect.dataset.bound !== '1') {
        vendorSelect.addEventListener('change', function(){ fetchJobsForVendor(this.value); });
        vendorSelect.dataset.bound = '1';
      }
      if (jdSelect && jdSelect.dataset.bound !== '1') {
        jdSelect.addEventListener('change', function(){ saveDropdownState(); if (this.value) refreshMappingsForJob(this.value); });
        jdSelect.dataset.bound = '1';
      }
    } catch(e){}
  }
  bindCascadingOnce();

  // --- reset interceptors ---
  function bindResetInterceptors() {
    try {
      const resetEls = Array.from(document.querySelectorAll('a[href="/candidates/search"], .reset-btn, button[type="reset"]'));
      resetEls.forEach(el => {
        if (el.dataset.resetBound === '1') return;
        el.dataset.resetBound = '1';
        el.addEventListener('click', function () {
          try {
            localStorage.removeItem(STORAGE_KEY);
            localStorage.removeItem(LINKED_IDS_KEY);
            localStorage.removeItem(RECENTLY_KEY);
            clearDropdownState();
            const c = clientSelectEl(); const v = vendorSelectEl(); const j = jdSelectEl();
            if (c) c.value = '';
            if (v) v.innerHTML = '<option value="">Select Manager</option>';
            if (j) j.innerHTML = '<option value="">Select Job</option>';
            sessionStorage.setItem(RESET_FLAG, Date.now().toString());
          } catch(e){}
        });
      });
    } catch(e){}
  }
  bindResetInterceptors();

  // --- linked ids helpers ---
  function getLinkedIds() {
    try {
      const raw = localStorage.getItem(LINKED_IDS_KEY); if (!raw) return new Set();
      const arr = JSON.parse(raw || '[]'); return new Set((arr||[]).map(x=>String(x)));
    } catch(e){ return new Set(); }
  }
  function saveLinkedIds(set) { try { localStorage.setItem(LINKED_IDS_KEY, JSON.stringify(Array.from(set))); } catch(e){} }
  function addLinkedId(id) { try { const s = getLinkedIds(); s.add(String(id)); saveLinkedIds(s); } catch(e){} }
  function removeLinkedId(id) { try { const s = getLinkedIds(); s.delete(String(id)); saveLinkedIds(s); } catch(e){} }

  // --- pagination ---
  let currentPage = 1;
  // preserve existing default (30) to avoid changing UX
  let recordsPerPage = recordsPerEl ? parseInt(recordsPerEl.value, 10) || 30 : 30;

  function getRows() {
    return Array.from(document.querySelectorAll('tr.candidate-row')).filter(r => r.dataset.hidden !== 'true');
  }

  function renderPagination() {
    try {
      const visibleRows = getRows();
      const total = visibleRows.length;
      const per = recordsPerPage || 30;
      const maxPages = Math.max(1, Math.ceil(total / per));

      // clamp currentPage
      if (currentPage > maxPages) currentPage = maxPages;
      if (currentPage < 1) currentPage = 1;

      const start = (currentPage - 1) * per;
      const end = Math.min(start + per, total);

      // hide/show only the visibleRows slice (preserve rows filtered/hidden by other logic)
      // First hide all candidate rows
      Array.from(document.querySelectorAll('tr.candidate-row')).forEach(r => { r.style.display = 'none'; });

      visibleRows.forEach((r, idx) => {
        r.style.display = (idx >= start && idx < end) ? '' : 'none';
      });

      // update page info UI
      const from = total === 0 ? 0 : (start + 1);
      const to = total === 0 ? 0 : end;
      if (pageInfo) pageInfo.textContent = `Showing ${from}–${to} of ${total}`;
      const visibleCountEl = document.getElementById('visibleCountLabel');
      if (visibleCountEl) visibleCountEl.textContent = String(total);

      // enable/disable prev/next
      if (prevBtn) prevBtn.disabled = currentPage <= 1;
      if (nextBtn) nextBtn.disabled = currentPage >= maxPages;
    } catch (e) {
      console.warn('renderPagination error', e);
    }
  }

  // hook up records-per-page change
  if (recordsPerEl && !recordsPerEl.dataset.boundForPagination) {
    recordsPerEl.dataset.boundForPagination = '1';
    recordsPerEl.addEventListener('change', function () {
      recordsPerPage = parseInt(this.value, 10) || 30;
      currentPage = 1;
      try { serializeSnapshot(); } catch(e){}
      renderPagination();
    });
  }

  // prev / next buttons
  if (prevBtn && !prevBtn.dataset.boundForPagination) {
    prevBtn.dataset.boundForPagination = '1';
    prevBtn.addEventListener('click', function (e) {
      e.preventDefault();
      if (currentPage > 1) {
        currentPage--;
        renderPagination();
      }
    });
  }
  if (nextBtn && !nextBtn.dataset.boundForPagination) {
    nextBtn.dataset.boundForPagination = '1';
    nextBtn.addEventListener('click', function (e) {
      e.preventDefault();
      const visibleCount = getRows().length;
      const maxPages = Math.max(1, Math.ceil(visibleCount / (recordsPerPage || 30)));
      if (currentPage < maxPages) {
        currentPage++;
        renderPagination();
      }
    });
  }

  // Ensure initial pagination run after hydration
  try { renderPagination(); } catch(e) {}
// --- apply linked ids (hide rows) ---
  function applyLinkedIds() {
try {
    const linked = getLinkedIds();
    const all = Array.from(document.querySelectorAll('tr.candidate-row'));
    all.forEach(row => {
      const cid = String(row.dataset.candidateId || row.getAttribute('data-candidate-id') || '');
      const cb = row.querySelector('.candidate-link-checkbox');
      if (cid && linked.has(cid)) {
        row.dataset.linked = 'true';
        if (cb) cb.checked = true;
      } else {
        if (row.dataset.linked !== 'true') {
          row.dataset.linked = 'false';
          if (cb) cb.checked = false;
        }
      }
    });
    currentPage = 1; renderPagination();
  } catch(e){}
}

  // --- serialize/hydrate for back navigation ---
  function serializeSnapshot() {
    try {
      const tbodyEl = document.getElementById('search-results-body');
      if (!tbodyEl) return;
      const trs = Array.from(tbodyEl.querySelectorAll('tr.candidate-row'));
      if (!trs.length) { localStorage.removeItem(STORAGE_KEY); return; }
      const results = trs.map(tr => {
        const cid = tr.getAttribute('data-candidate-id') || '';
        const name = (tr.querySelector('td:nth-child(2)')?.innerText || '').trim();
        const skillElems = Array.from(tr.querySelectorAll('td:nth-child(3) span')).map(s=>s.innerText.trim());
        const skillset = skillElems.join(',');
        const email = (tr.querySelector('td:nth-child(4)')?.innerText || '').trim();
        const contact = (tr.querySelector('td:nth-child(5)')?.innerText || '').trim();
        const it_experience = (tr.querySelector('td:nth-child(6)')?.innerText || '').trim();
        const score = (tr.querySelector('.ai-score-cell')?.innerText || '').trim();
        const resumelink = tr.querySelector('td:nth-child(8) a') ? tr.querySelector('td:nth-child(8) a').href : '';
        const location = (tr.querySelector('td:nth-child(9)')?.innerText || '').trim();
        const cb = tr.querySelector('.candidate-link-checkbox');
        const is_linked = !!((cb && cb.checked) || String(tr.dataset.linked) === 'true');
        const existing_jd_ids = tr.dataset.existingJdIds || tr.getAttribute('data-existing-jd-ids') || '';
        const mapping_display = tr.dataset.mappingDisplay || tr.getAttribute('data-mapping-display') || '';
        return { candidates_id: cid, candidate_name: name, skillset, email, contact, it_experience, score, resumelinks: resumelink, location, is_linked: !!is_linked, existing_jd_ids: existing_jd_ids, mapping_display: mapping_display };
      });
      const clientSelect = clientSelectEl(); const vendorSelect = vendorSelectEl(); const jdSelect = jdSelectEl();
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ ts: Date.now(), results, clientId: clientSelect ? clientSelect.value : '', vendorId: vendorSelect ? vendorSelect.value : '', jobId: jdSelect ? jdSelect.value : '' }));
    } catch(e){ console.warn('serializeSnapshot', e); }
  }

  async function hydrateIfNeeded() {
    try {
      const tbodyEl = document.getElementById('search-results-body');
      if (!tbodyEl) return false;
      const serverRows = Array.from(tbodyEl.querySelectorAll('tr.candidate-row'));
      if (serverRows.length > 0) { serializeSnapshot(); applyLinkedIds(); renderPagination(); return false; }
      // avoid overwriting if user typed filters
      const skillsIn = document.querySelector('input[name="skills"]');
      const locIn = document.querySelector('input[name="location"]');
      const expIn = document.querySelector('input[name="experience"]');
      const inputsEmpty = (!skillsIn || !skillsIn.value.trim()) && (!locIn || !locIn.value.trim()) && (!expIn || !expIn.value.trim());
      if (!inputsEmpty) return false;

      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      const store = JSON.parse(raw);
      if (!store || !Array.isArray(store.results) || store.results.length === 0) return false;

      tbodyEl.innerHTML = store.results.map(buildRowHtml).join('');
      // restore selects using server lists where possible
      try {
        if (store.clientId) {
          const clientSelect = clientSelectEl(); const vendorSelect = vendorSelectEl(); const jdSelect = jdSelectEl();
          clientSelect.value = store.clientId;
          const rv = await fetch(`/candidates/get-vendors/${encodeURIComponent(store.clientId)}`).catch(()=>null);
          if (rv && rv.ok) {
            const vendors = await rv.json().catch(()=>[]);
            vendorSelect.innerHTML = '<option value="">Select Manager</option>';
            vendors.forEach(v => { const o = document.createElement('option'); o.value = v.vendor_id; o.textContent = v.vendor_name; vendorSelect.appendChild(o); });
            if (store.vendorId) {
              vendorSelect.value = store.vendorId;
              const rj = await fetch(`/candidates/get-jobs/${encodeURIComponent(store.vendorId)}`).catch(()=>null);
              if (rj && rj.ok) {
                const jobs = await rj.json().catch(()=>[]);
                jdSelect.innerHTML = '<option value="">Select Job</option>';
                jobs.forEach(j => { const o = document.createElement('option'); o.value = j.job_id; o.textContent = j.job_title; jdSelect.appendChild(o); });
                if (store.jobId) jdSelect.value = store.jobId;
              }
            }
          }
        } else {
          // if no server-side client, restore local snapshot
          restoreDropdownStateIfSafe();
        }
      } catch(e){ console.warn('hydrate restore', e); }

      attachDelegation();
      applyLinkedIds();
      renderPagination();
      return true;
    } catch(e){ console.warn('hydrateIfNeeded', e); return false; }
  }

  function buildRowHtml(candidate) {
    const cid = candidate.candidates_id || candidate.id || '';
    const name = candidate.candidate_name || candidate.name || 'N/A';
    const skillList = (candidate.skillset || '').split(',').map(s=>s.trim()).filter(Boolean);
    const showSkills = skillList.slice(0,3).map(s => `<span style="font-size:0.78rem; padding:5px 8px; background:#eef2ff; color:#1e3a8a; border-radius:999px; font-weight:700;">${escapeHtml(s)}</span>`).join('');
    const extra = skillList.length>3 ? `<span style="font-size:0.78rem; padding:5px 8px; background:#eef2ff; color:#1e3a8a; border-radius:999px;">+${skillList.length-3}</span>` : '';
    const email = candidate.email || 'N/A';
    const contact = candidate.contact || 'N/A';
    const itExp = candidate.it_experience || candidate.it_exp || 'N/A';
    const score = candidate.score || candidate.ai_score || '';
    const resume = candidate.resumelinks ? `<a href="${escapeHtml(candidate.resumelinks)}" target="_blank" style="color:#2563eb; text-decoration:none;"><i class="bi bi-paperclip"></i></a>` : '<span style="color:#6b7280;">N/A</span>';
    const loc = candidate.location || 'N/A';
    return `
      <tr class="candidate-row" data-candidate-id="${escapeHtml(cid)}" data-linked="${candidate.is_linked ? 'true' : 'false'}" data-existing-jd-ids="${escapeHtml(candidate.existing_jd_ids || '')}" data-mapping-display="${escapeHtml(candidate.mapping_display || '')}">
        <td style="padding:8px 12px; text-align:center; vertical-align:middle;">
          <input type="checkbox" id="link_cb_${escapeHtml(cid)}" class="candidate-link-checkbox" data-candidate="${escapeHtml(cid)}" style="position:absolute; left:-9999px;" ${candidate.is_linked ? 'checked' : ''}>
          <label for="link_cb_${escapeHtml(cid)}" class="link-btn" style="display:inline-block; width:36px; height:36px; border-radius:10px; border:1px solid #d1d5db; background:#fff; text-align:center; line-height:36px; cursor:pointer;">🔗</label>
        </td>
        <td style="padding:12px;"><div style="font-weight:700; color:#111827;">${escapeHtml(name)}</div></td>
        <td style="padding:12px;"><div style="display:flex; gap:6px; flex-wrap:wrap;">${showSkills}${extra}</div></td>
        <td style="padding:12px; color:#374151;">${escapeHtml(email)}</td>
        <td style="padding:12px; color:#374151;">${escapeHtml(contact)}</td>
        <td style="padding:12px; color:#374151;">${escapeHtml(itExp)}</td>
        <td style="padding:12px; text-align:center;"><div style="display:flex; gap:8px; align-items:center; justify-content:center;"><span class="ai-score-cell" data-id="${escapeHtml(cid)}" style="font-weight:800;">${escapeHtml(score)}</span>
        <td style="padding:12px; color:#374151;">${escapeHtml(loc)}</td>
      </tr>
    `;
  }

  // --- event delegation for table (single binding) ---
  function attachDelegation() {
    const tbodyEl = tbody();
    if (!tbodyEl) return;
    if (tbodyEl._nxgBound === '1') return;
    tbodyEl._nxgBound = '1';

  // --- capture-phase click interception on label.link-btn to show mapping-warning immediately (prevents checkbox flicker) ---
  tbodyEl.addEventListener('click', function (e) {
    try {
      const label = e.target.closest && e.target.closest('label.link-btn');
      if (!label) return;
      // derive checkbox
      let checkbox = null;
      const forAttr = label.getAttribute && label.getAttribute('for');
      if (forAttr) checkbox = document.getElementById(forAttr);
      if (!checkbox) checkbox = label.closest('td') ? label.closest('td').querySelector('.candidate-link-checkbox') : null;
      if (!checkbox) return;

      const row = checkbox.closest('tr.candidate-row');
      const candidateId = Number(checkbox.dataset && checkbox.dataset.candidate);
      const jd = jdSelectEl && jdSelectEl();
      const jobId = jd && jd.value ? String(jd.value) : null;
      if (!jobId) return; // require JD selected for mapping checks

      const existingIdsRaw = (row && row.dataset && row.dataset.existingJdIds) ? (row.dataset.existingJdIds || '') : '';
      const existingIds = existingIdsRaw.split(',').map(s=>s.trim()).filter(Boolean);
      // If candidate already mapped elsewhere (one or more ids exist) AND selected job is different -> intercept
      if (existingIds.length > 0 && !existingIds.includes(String(jobId))) {
        // prevent default label toggle and further handlers
        try { e.preventDefault(); e.stopImmediatePropagation(); } catch(err) {}
        // Build and display mapping modal (reuse same DOM nodes as handleToggleLink)
        try {
          const mappingDisplayRaw = (row && row.dataset && row.dataset.mappingDisplay) ? row.dataset.mappingDisplay : '';
          const mappingDisplayDecoded = (typeof decodeHtmlEntities === 'function') ? decodeHtmlEntities(mappingDisplayRaw || '') : mappingDisplayRaw;
          const titleEl = document.getElementById('mappingWarningTitle');
          const bodyEl = document.getElementById('mappingWarningBody');
          const modal = document.getElementById('mappingWarningModal');
          if (titleEl && bodyEl && modal) {
            let mappingItems = [];
            if (mappingDisplayDecoded && mappingDisplayDecoded.trim()) {
              mappingItems = mappingDisplayDecoded.split(/\s*\|\s*/).map(s => s.trim()).filter(Boolean);
            } else if (existingIds.length) {
              mappingItems = existingIds.map(id => `Job ID: ${id}`);
            }
            // Build HTML lines
            let linesHtml = '';
            try {
              if (mappingItems.length && existingIds.length && mappingItems.length === existingIds.length) {
                linesHtml = mappingItems.map((item, idx) => {
                  const jid = existingIds[idx];
                  if (jid) {
                    const href = `/candidates/jd/${encodeURIComponent(jid)}?highlight=${encodeURIComponent(candidateId)}`;
                    return `<div style="margin-top:8px; font-weight:700;"><a href="${escapeHtml(href)}" style="color:#1d4ed8; text-decoration:underline;">${escapeHtml(item)}</a></div>`;
                  }
                  return `<div style="margin-top:8px; font-weight:700;">${escapeHtml(item)}</div>`;
                }).join('');
              } else if (existingIds.length) {
                linesHtml = existingIds.map(jid => {
                  const href = `/candidates/jd/${encodeURIComponent(jid)}?highlight=${encodeURIComponent(candidateId)}`;
                  return `<div style="margin-top:8px; font-weight:700;"><a href="${escapeHtml(href)}" style="color:#1d4ed8; text-decoration:underline;">Job ID: ${escapeHtml(String(jid))}</a></div>`;
                }).join('');
              } else {
                linesHtml = mappingItems.map(item => `<div style="margin-top:8px; font-weight:700;">${escapeHtml(item)}</div>`).join('');
              }
            } catch (e) {
              linesHtml = mappingItems.map(item => `<div style="margin-top:8px; font-weight:700;">${escapeHtml(item)}</div>`).join('');
            }
            titleEl.textContent = 'Candidate already linked';
            bodyEl.innerHTML = `<div>This candidate is already linked under:</div>${linesHtml}<div style="margin-top:12px;">Do you want to also link the candidate to the selected job?</div>`;
            // set pending toggle with prevChecked recorded (current visual state)
            window._nxg_pending_toggle = { checkbox, candidateId, jobId: Number(jobId), linked: true, row, prevChecked: !!checkbox.checked };
            try {
              // === EDITED: ensure modal.dataset.pending explicitly includes linked:true ===
              modal.dataset.pending = JSON.stringify({ candidateId: Number(candidateId), jobId: Number(jobId), linked: true, prevChecked: !!checkbox.checked });
            } catch(e) {}
            modal.style.display = 'flex';
            try { document.body.style.overflow = 'hidden'; } catch (e) {}
            return;
          }
        } catch (err) {
          // fallback to default behavior if modal build fails
        }
      }
    } catch (err) { /* ignore */ }
  }, true);

    // click: open modal or explain/reset
    tbodyEl.addEventListener('click', async function (e) {
      const explainBtn = e.target.closest('.ai-explain-btn');
      if (explainBtn) {
        e.preventDefault();
        const cid = explainBtn.dataset.id;
        if (!cid) return;
        try {
          showAiProgress({ title:'Fetching explanation', subtitle:'Please wait.' });
          const res = await fetch(`/candidates/ai-explanation/${encodeURIComponent(cid)}`);
          const data = await res.json().catch(()=>null);
          hideAiProgress();
          if (!res.ok) throw new Error(data?.message || 'Explanation failed');
          const body = document.getElementById('aiExplanationModalBody');
          const score = data && (data.ai_score !== undefined && data.ai_score !== null) ? data.ai_score : (data.score !== undefined ? data.score : '');
          const expl = data && (data.explanation || data.ai_explanation) ? (data.explanation || data.ai_explanation) : 'No explanation available.';
          body.innerText = `Score: ${score}\n\nExplanation:\n${expl}`;
          document.getElementById('aiExplanationModal').style.display = 'flex';
          document.body.style.overflow = 'hidden';
        } catch(err){ hideAiProgress(); alert('Failed to fetch explanation'); }
        return;
      }

      

      // ignore clicks on inputs/labels/buttons/anchors
      if (e.target.closest('input, label, a, button, textarea, select')) return;
      const row = e.target.closest('tr.candidate-row');
      if (!row) return;
      const cid = row.dataset.candidateId;
      if (!cid) return;
      openCandidateModal(cid);
    });

    // change: checkbox toggle
    tbodyEl.addEventListener('change', function (e) {
      if (e.target && e.target.matches('.candidate-link-checkbox')) {
        handleToggleLink(e.target);
      }
    });
  }

  attachDelegation();

  // --- toggle link ---
  
// --- toggle link ---
// Replaces old handleToggleLink / confirm() flow with a dialog-style modal.
// Event binding elsewhere already calls handleToggleLink(e.target)
let _nxg_pending_toggle = null;


async function handleToggleLink(checkbox) {
  try {
    if (!checkbox) return;
    const candidateId = Number(checkbox.dataset.candidate);
    const jdSelect = jdSelectEl();
    const jobId = jdSelect && jdSelect.value ? Number(jdSelect.value) : null;
    if (!jobId) {
      alert('Please select a Job before linking/unlinking.');
      try { checkbox.checked = !checkbox.checked; } catch(e){}
      return;
    }
    const linked = !!checkbox.checked;
    const row = checkbox.closest('tr.candidate-row');

    // Prefer mapping_display attribute if present
    const existingIds = (row && row.dataset && row.dataset.existingJdIds) ? (row.dataset.existingJdIds || '').split(',').map(s=>s.trim()).filter(Boolean) : [];
    const mappingDisplayRaw = (row && row.dataset && row.dataset.mappingDisplay) ? row.dataset.mappingDisplay : '';

    // decode server-escaped entities (Jinja often writes &gt; etc.)
    const mappingDisplayDecoded = decodeHtmlEntities(mappingDisplayRaw);

    // Convert mappingDisplay into array of readable lines (or fallback to job ids)
    let mappingItems = [];
    if (mappingDisplayDecoded && mappingDisplayDecoded.trim()) {
      // mappingDisplay uses " | " separators server-side
      mappingItems = mappingDisplayDecoded.split(/\s*\|\s*/).map(s => s.trim()).filter(Boolean);
    } else if (existingIds.length) {
      // fallback: show Job ID list so user still sees where it's linked
      mappingItems = existingIds.map(id => `Job ID: ${id}`);
    }
// Decide if we must warn:
    const isLinkingToDifferent = linked && existingIds.length > 0 && !existingIds.includes(String(jobId));
    const isUnlinkingPresent = !linked && existingIds.length > 0 && existingIds.includes(String(jobId));

    if (isLinkingToDifferent || isUnlinkingPresent) {
      try {
        const titleEl = document.getElementById('mappingWarningTitle');
        const bodyEl = document.getElementById('mappingWarningBody');
        const modal = document.getElementById('mappingWarningModal');
        if (titleEl && bodyEl && modal) {
          // Build HTML: one bold line per mapping item
          let linesHtml = '';
try {
  // If mapping text items and JD ids align, render each item as a link to its JD page
  if (mappingItems.length && existingIds.length && mappingItems.length === existingIds.length) {
    linesHtml = mappingItems.map((item, idx) => {
      const jid = existingIds[idx];
      if (jid) {
        const href = `/candidates/jd/${encodeURIComponent(jid)}?highlight=${encodeURIComponent(candidateId)}`;
        return `<div style="margin-top:8px; font-weight:700;">
                  <a href="${escapeHtml(href)}" class="mapping-link" data-candidate="${escapeHtml(String(candidateId))}" data-job="${escapeHtml(String(jid))}" style="color:#1d4ed8; text-decoration:underline;">
                    ${escapeHtml(item)}
                  </a>
                </div>`;
      }
      return `<div style="margin-top:8px; font-weight:700;">${escapeHtml(item)}</div>`;
    }).join('');
  } else if (existingIds.length) {
    // If we only have job ids, show Job ID links
    linesHtml = existingIds.map(jid => {
      const href = `/candidates/jd/${encodeURIComponent(jid)}?highlight=${encodeURIComponent(candidateId)}`;
      return `<div style="margin-top:8px; font-weight:700;">
                <a href="${escapeHtml(href)}" style="color:#1d4ed8; text-decoration:underline;">Job ID: ${escapeHtml(String(jid))}</a>
              </div>`;
    }).join('');
  } else {
    // Fallback: plain text mapping items
    linesHtml = mappingItems.map(item => `<div style="margin-top:8px; font-weight:700;">${escapeHtml(item)}</div>`).join('');
  }
} catch (e) {
  // safe fallback in case of unexpected data
  linesHtml = mappingItems.map(item => `<div style="margin-top:8px; font-weight:700;">${escapeHtml(item)}</div>`).join('');
}
if (isLinkingToDifferent) {
            titleEl.textContent = 'Candidate already linked';
            bodyEl.innerHTML = `<div>This candidate is already linked under:</div>
                                ${linesHtml}
                                <div style="margin-top:12px;">Do you want to also link the candidate to the selected job?</div>`;
          } else {
            titleEl.textContent = 'Confirm unlink';
            bodyEl.innerHTML = `<div>You are about to unlink this candidate from the selected job.</div>
                                ${linesHtml}
                                <div style="margin-top:12px;">Proceed to unlink?</div>`;
          }
          // set pending with the actual checkbox/row reference (so confirm handler can use them)
          _nxg_pending_toggle = { checkbox, candidateId, jobId, linked, row, prevChecked: !linked };
          // also persist pending on the modal dataset so confirm handler can rebuild if the global var is lost
          try {
            // === EDITED: write explicit linked boolean into modal.dataset.pending ===
            modal.dataset.pending = JSON.stringify({ candidateId: Number(candidateId), jobId: Number(jobId), linked: !!linked, prevChecked: !!(!linked) ? true : !!linked });
          } catch(e) {}
          modal.style.display = 'flex';
          try { document.body.style.overflow = 'hidden'; } catch(e){}
          return; // wait for modal confirm/cancel
        }
      } catch(e) {
        // fallback to classic confirm if modal fails
        const fallbackMsg = mappingItems.length ? `This candidate is already linked under:\n${mappingItems.join('\n')}` : `This candidate is already linked under another job.`;
        if (!confirm(fallbackMsg + '\n\nProceed?')) {
          try { checkbox.checked = !linked; } catch(e){}
          return;
        }
      }
    }

    // no warning required — perform toggle directly
    await _nxg_perform_toggle({ checkbox, candidateId, jobId, linked, row });
  } catch (err) {
    console.warn('handleToggleLink error', err);
    try { checkbox.checked = !checkbox.checked; } catch(e){}
  }
}


// Modal handlers: confirm / cancel / close
(function () {
  const modal = document.getElementById('mappingWarningModal');
  const confirmBtn = document.getElementById('mappingWarningConfirm');
  const cancelBtn = document.getElementById('mappingWarningCancel');
  const closeBtn = document.getElementById('mappingWarningClose');

  function closeModalAndRestore(revertCheckbox = true) {
    if (!modal) return;
    modal.style.display = 'none';
    try { document.body.style.overflow = ''; } catch(e){}
    if (_nxg_pending_toggle && revertCheckbox && _nxg_pending_toggle.checkbox) {
      try {
        if (typeof _nxg_pending_toggle.prevChecked !== 'undefined') {
          _nxg_pending_toggle.checkbox.checked = !!_nxg_pending_toggle.prevChecked;
        } else {
          _nxg_pending_toggle.checkbox.checked = !_nxg_pending_toggle.linked;
        }
      } catch(e){}
    }
    _nxg_pending_toggle = null;
  }

  if (confirmBtn) {
    confirmBtn.addEventListener('click', async function () {
    // Try to use the global pending toggle if present
    let pending = window._nxg_pending_toggle;

    // 🔧 If pending data got lost (typical when user intercepted modal)
    if (!pending || !pending.candidateId || !pending.jobId) {
      try {
        const modal = document.getElementById('mappingWarningModal');
        const raw = modal && modal.dataset && modal.dataset.pending
          ? JSON.parse(modal.dataset.pending)
          : null;
        if (raw && raw.candidateId && raw.jobId) {
          // === EDITED: robustly parse the linked flag. Ensure boolean and fall back to title inference ===
          let parsedLinked;
          if (typeof raw.linked === 'boolean') {
            parsedLinked = raw.linked;
          } else if (raw.linked === 'true' || raw.linked === 'false') {
            parsedLinked = (raw.linked === 'true');
          } else {
            // fallback: infer from modal title (Confirm unlink => unlink)
            const titleEl = document.getElementById('mappingWarningTitle');
            const titleText = titleEl ? (titleEl.textContent || '') : '';
            parsedLinked = !(/unlink/i.test(titleText)); // if title contains 'unlink' => parsedLinked=false
          }

          pending = {
            candidateId: raw.candidateId,
            jobId: raw.jobId,
            // respect the original pending.linked value if provided, otherwise parsedLinked
            linked: (typeof raw.linked === 'boolean') ? raw.linked : !!parsedLinked,
            row: null,
            prevChecked: !!raw.prevChecked
          };
        }
      } catch (e) {
        console.warn('Modal pending parse failed', e);
      }
    }

    if (!pending || !pending.candidateId || !pending.jobId) {
      closeModalAndRestore(true);
      return;
    }

    // ✅ Actually perform the toggle/link/unlink
    try {
      closeModalAndRestore(false);
      await _nxg_perform_toggle(pending);
    } catch (err) {
      console.error('Toggle link/unlink failed', err);
    }
  });
  }

  if (cancelBtn) {
    cancelBtn.addEventListener('click', function () { closeModalAndRestore(true); });
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', function () { closeModalAndRestore(true); });
  }
})();

// actual network + UI update logic (extracted from original code so behavior is preserved)
async function _nxg_perform_toggle({ checkbox, candidateId, jobId, linked, row }) {
  // NOTE: relaxed guard — perform the server call if we have identifiers even if DOM refs are missing.
  if (!candidateId || !jobId) return;
  try {
    showAiProgress({ title: linked ? 'Linking candidate' : 'Unlinking candidate', subtitle: 'Please wait...' });
    const resp = await fetch('/candidates/toggle-link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: candidateId, job_id: jobId, linked: linked })
    });
    const data = await resp.json().catch(() => null);
    if (!resp.ok) throw new Error(data?.message || 'Toggle failed');

    if (linked) {
      addLinkedId(candidateId);
      try {
        const raw = localStorage.getItem(RECENTLY_KEY);
        const arr = raw ? JSON.parse(raw) : [];
        if (!arr.includes(candidateId)) { arr.push(candidateId); localStorage.setItem(RECENTLY_KEY, JSON.stringify(arr)); }
      } catch(e){}
      // update row metadata but only if we have a row DOM reference
      if (row) row.classList.add('recently-linked-highlight');
      setTimeout(() => {
        if (row) {
          row.classList.remove('recently-linked-highlight');
          row.dataset.linked = 'true';
          // append jobId into existing_jd_ids if not present
          const existing = (row.dataset.existingJdIds || '').split(',').map(s => s.trim()).filter(Boolean);
          if (!existing.includes(String(jobId))) existing.push(String(jobId));
          row.dataset.existingJdIds = existing.join(',');
          // append human-readable display from selects (best-effort)
          try {
            const clientName = clientSelectEl() ? (clientSelectEl().selectedOptions[0]?.textContent || '') : '';
            const vendorName = vendorSelectEl() ? (vendorSelectEl().selectedOptions[0]?.textContent || '') : '';
            const jobName = jdSelectEl() ? (jdSelectEl().selectedOptions[0]?.textContent || '') : '';
            const newDisp = `${clientName} > ${vendorName} > ${jobName}`;
            row.dataset.mappingDisplay = row.dataset.mappingDisplay ? (row.dataset.mappingDisplay + ' | ' + newDisp) : newDisp;
          } catch(e){}
        }
        try { serializeSnapshot(); } catch(e){}
        try { renderPagination(); } catch(e){}
      }, 420);
      showToast('Candidate linked','success',3000);
    } else {
      // unlink
      removeLinkedId(candidateId);
      // remove jobId from existing_jd_ids only if row exists
      if (row) {
        const existing = (row.dataset.existingJdIds || '').split(',').map(s => s.trim()).filter(Boolean).filter(id => id !== String(jobId));
        row.dataset.existingJdIds = existing.join(',');
        if (existing.length === 0) row.dataset.linked = 'false';
        // ensure checkbox reflects unlink
        try {
          const cb = row.querySelector('.candidate-link-checkbox');
          if (cb) cb.checked = false;
        } catch(e){}
        // visual cue for unlink (short highlight)
        try {
          row.classList.add('recently-unlinked-highlight');
          setTimeout(()=>{ row.classList.remove('recently-unlinked-highlight'); }, 550);
        } catch(e){}
      }
      // ensure local storage/pagination reflect change immediately
      serializeSnapshot(); renderPagination();

      // show unlink toast (same style as link)
      showToast('Candidate unlinked','success',3000);
    }
  } catch (err) {
    alert('Failed to toggle link: ' + (err.message || err));
    // revert checkbox on failure (only if checkbox ref exists)
    try { if (checkbox) checkbox.checked = !checkbox.checked; } catch(e){}
  } finally {
    hideAiProgress();
  }
}


  // --- refresh mapping for selected job ---
  async function refreshMappingsForJob() {
if (!jobId) { applyLinkedIds(); return; }
  showAiProgress({ title:'Updating job mapping', subtitle:'Fetching mapped candidates.' });
  try {
    const res = await fetch(`/candidates/get-mapped-candidates/${encodeURIComponent(jobId)}`);
    const mappings = await res.json().catch(()=>[]);
    const map = {}; (mappings || []).forEach(m => { map[String(m.candidate_id)] = m; });
    try {
      const s = getLinkedIds();
      (mappings || []).forEach(m => s.add(String(m.candidate_id)));
      saveLinkedIds(s);
    } catch(e){}
    Array.from(document.querySelectorAll('tr.candidate-row')).forEach(row => {
      const cid = String(row.dataset.candidateId || row.getAttribute('data-candidate-id') || '');
      const cb = row.querySelector('.candidate-link-checkbox');
      const scoreCell = row.querySelector('.ai-score-cell');
      if (map[cid]) {
        // mark as linked for selected job (do NOT hide)
        row.dataset.linked = 'true';
        if (cb) cb.checked = true;
        // ensure selected jobId present in existing_jd_ids
        const existing = (row.dataset.existingJdIds || '').split(',').map(s=>s.trim()).filter(Boolean);
        if (!existing.includes(String(jobId))) existing.push(String(jobId));
        row.dataset.existingJdIds = existing.join(',');
        // update mapping_display best-effort using selected dropdowns
        try {
          const clientName = clientSelectEl() ? (clientSelectEl().selectedOptions[0]?.textContent||'') : '';
          const vendorName = vendorSelectEl() ? (vendorSelectEl().selectedOptions[0]?.textContent||'') : '';
          const jobName = jdSelectEl() ? (jdSelectEl().selectedOptions[0]?.textContent||'') : '';
          const disp = `${clientName} > ${vendorName} > ${jobName}`;
          row.dataset.mappingDisplay = row.dataset.mappingDisplay ? (row.dataset.mappingDisplay + ' | ' + disp) : disp;
        } catch(e){}
        if (scoreCell && map[cid] && (map[cid].ai_score !== undefined && map[cid].ai_score !== null)) scoreCell.innerText = map[cid].ai_score;
      } else {
        // leave other rows as-is (do not hide)
        if (row.dataset.linked !== 'true') {
          if (cb) cb.checked = false;
          row.dataset.linked = 'false';
        }
      }
    });
    currentPage = 1; renderPagination();
  } catch(e) {
    console.warn('refreshMappingsForJob', e);
  } finally { hideAiProgress(); }
}

  // initial mapping refresh if jd selected on first load
  try { const jdInit = jdSelectEl(); if (jdInit && jdInit.value) setTimeout(()=>refreshMappingsForJob(jdInit.value), 200); } catch(e){}

  // --- Candidate modal helpers ---
  function findCandidateObject(obj, depth=0) {
    if (!obj || typeof obj !== 'object' || depth>4) return null;
    const keys = Object.keys(obj); const markers = ['candidates_id','candidate_id','candidate_name','name','email','skillset','it_experience','ai_score','score'];
    if (keys.some(k=>markers.includes(k))) return obj;
    for (const k of keys) {
      try { const v = obj[k]; if (v && typeof v === 'object') { const f = findCandidateObject(v, depth+1); if (f) return f; } } catch(e){}
    }
    return null;
  }
  function normalizeCandidatePayload(payload) {
    if (!payload) return {};
    if (Array.isArray(payload) && payload.length) { for (const p of payload) { const f = findCandidateObject(p); if (f) return f; } return payload[0] || {}; }
    if (payload.candidate) return findCandidateObject(payload.candidate) || payload.candidate;
    const f = findCandidateObject(payload); return f || payload;
  }

  async function openCandidateModal(candidateId) {
    try {
      showAiProgress({ title:'Loading candidate', subtitle:'Please wait.' });
      const resp = await fetch(`/candidates/${encodeURIComponent(candidateId)}`);
      const payload = await resp.json().catch(()=>({}));
      hideAiProgress();
      if (!resp.ok) throw new Error('Failed to fetch candidate');

      const c = normalizeCandidatePayload(payload);
      const name = c.candidate_name || c.name || 'N/A';
      const skills = c.skillset || c.skills || 'N/A';
      const aiScore = (c.ai_score !== undefined && c.ai_score !== null) ? c.ai_score : (c.score !== undefined ? c.score : '');
      const email = c.email || c.email_address || 'N/A';
      const contact = c.contact || c.phone || 'N/A';
      const itExp = c.it_experience || c.it_exp || 'N/A';
      const location = c.location || 'N/A';
      const relExp = c.relevant_experience || 'N/A';
      const education = c.education || 'N/A';
      const company = c.company || 'N/A';
      const resume = c.resumelinks || c.resume || '';
      const notice = c.notice_period || c.notice || '';
      const comment = c.comment || '';
      const notes = c.recruitment_notes || c.recruiter_notes || '';
      const mapping_jd_id = c.mapping_jd_id || c.mapping || '';

      const body = document.getElementById('candidateModalBody');
body.innerHTML = `
  <div class="candidate-details-box">
    <div class="candidate-header">
      <div class="candidate-main-info">
        <h2 class="candidate-name">${escapeHtml(name)}</h2>
        <p class="candidate-meta">${escapeHtml(company)} • ${escapeHtml(location)}</p>
        <p class="candidate-ai">AI Score: <span>${escapeHtml(aiScore)}</span></p>
        ${resume ? `<a href="${escapeHtml(resume)}" target="_blank" class="resume-link">View Resume <i class="bi bi-paperclip"></i></a>` : '<span class="resume-missing">No resume</span>'}
      </div>
    </div>

    <div class="candidate-grid">
      <div><label>Skills</label><p>${escapeHtml(skills)}</p></div>
      <div><label>Relevant Exp</label><p>${escapeHtml(relExp)}</p></div>

      <div><label>Email</label><p>${escapeHtml(email)}</p></div>
      <div><label>Contact</label><p>${escapeHtml(contact)}</p></div>

      <div><label>IT Exp</label><p>${escapeHtml(itExp)}</p></div>
      <div><label>Education</label><p>${escapeHtml(education)}</p></div>

      <div><label>Clients</label><p>${escapeHtml(c.clients || '')}</p></div>
      <div><label>Notice</label><p>${escapeHtml(notice)}</p></div>

      <div class="full-width"><label>Comment</label><p>${escapeHtml(comment)}</p></div>
    </div>

    <div class="notes-box">
      <label>Recruitment Notes</label>
      <textarea id="modalRecruitmentNotes" rows="2">${escapeHtml(notes)}</textarea>
    </div>
  </div>
`;


      const backdrop = document.getElementById('candidateModalBackdrop');
      backdrop.dataset.candidateId = candidateId;
      backdrop.dataset.mappingJdId = mapping_jd_id || '';
      backdrop.style.display = 'flex';
      document.body.style.overflow = 'hidden';
    } catch(err) {
      hideAiProgress();
      alert('Failed to load candidate details: ' + (err.message || err));
    }
  }

  // modal open/close handlers
  document.getElementById('candidateModalClose').addEventListener('click', closeCandidateModal);
  document.getElementById('candidateModalCancel').addEventListener('click', closeCandidateModal);
  document.getElementById('candidateModalBackdrop').addEventListener('click', function(e){ if (e.target.id === 'candidateModalBackdrop' || e.target.id === 'candidateModalOverlay') closeCandidateModal(); });
  function closeCandidateModal() { const b = document.getElementById('candidateModalBackdrop'); if (!b) return; b.style.display='none'; b.dataset.candidateId=''; b.dataset.mappingJdId=''; document.body.style.overflow=''; }

  // save notes
  document.getElementById('saveNotesBtn').addEventListener('click', async function () {
    const backdrop = document.getElementById('candidateModalBackdrop');
    const candidateId = Number(backdrop.dataset.candidateId || 0);
    const mappingJd = backdrop.dataset.mappingJdId || '';
    let jobIdVal = mappingJd || (jdSelectEl() ? jdSelectEl().value : '') || '';
    const job_id = jobIdVal ? Number(jobIdVal) : 0;
    const notes = document.getElementById('modalRecruitmentNotes').value || '';
    try {
      showAiProgress({ title:'Saving notes', subtitle:'Please wait.' });
      const resp = await fetch('/candidates/update-note', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ candidate_id: Number(candidateId), job_id: job_id, note: notes })});
      const data = await resp.json().catch(()=>null);
      hideAiProgress();
      if (!resp.ok) throw new Error(data?.message || 'Save failed');
      showToast('Notes saved','success',2000);
      try {
        const row = document.querySelector(`tr[data-candidate-id="${candidateId}"]`);
        if (row) { serializeSnapshot(); }
      } catch(e){}
      closeCandidateModal();
    } catch(err) { hideAiProgress(); alert('Failed to save notes: ' + (err.message || err)); }
  });

  // recently linked button behavior (append query param highlight)
  if (recentlyLinkedBtn) {
    recentlyLinkedBtn.addEventListener('click', function (e) {
      try {
        const raw = localStorage.getItem(RECENTLY_KEY); const arr = raw ? JSON.parse(raw) : [];
        if (!arr || arr.length === 0) { e.preventDefault(); alert('No recently linked candidates in this session.'); return; }
        const url = new URL(this.href, window.location.origin); url.searchParams.set('highlight', arr.join(',')); this.href = url.pathname + url.search;
      } catch(e){}
    });
  }

  // aiExplanation modal close
  document.getElementById('aiExplanationModalClose').addEventListener('click', function(){ document.getElementById('aiExplanationModal').style.display = 'none'; document.body.style.overflow = ''; });

  // --- Advanced & Manual form overlay behavior (preserve AI overlay) ---
  if (advancedForm) {
    advancedForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      showAiProgress({ title:'AI is evaluating candidates', subtitle:'Analyzing JD and matching candidates — this may take a few moments.' });
      const submitBtn = advancedForm.querySelector('button[type="submit"], input[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;
      try {
        const formData = new FormData(advancedForm);
        const resp = await fetch(advancedForm.action, { method:'POST', body: formData, credentials: 'same-origin' });
        if (!resp.ok) {
          const txt = await resp.text().catch(()=>null); hideAiProgress(); if (submitBtn) submitBtn.disabled = false; alert('Advanced search failed: ' + (txt || (resp.status + ' ' + resp.statusText))); return;
        }
        const contentType = resp.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          const j = await resp.json().catch(()=>null);
          if (j && j.redirect) { window.location.href = j.redirect; return; }
          hideAiProgress(); window.location.reload(); return;
        }
        const html = await resp.text();
        try { document.open(); document.write(html); document.close(); } catch(e) { window.location.href = '/candidates/search'; }
      } catch(err) { hideAiProgress(); if (submitBtn) submitBtn.disabled = false; alert('Advanced search error: ' + (err.message || err)); }
    });
  }

  if (searchForm) {
    searchForm.addEventListener('submit', function () {
      try {
        const skillsEl = document.querySelector('input[name="skills"]');
        const expEl = document.querySelector('input[name="experience"]');
        const locEl = document.querySelector('input[name="location"]');
        const skillsVal = skillsEl && skillsEl.value ? skillsEl.value.trim() : '';
        const expVal = expEl && expEl.value ? expEl.value.trim() : '';
        const locVal = locEl && locEl.value ? locEl.value.trim() : '';
        if (skillsVal || expVal || locVal) showAiProgress({ title:'Searching', subtitle:'Preparing search results — please wait.' });
      } catch(e){}
    });
  }

  // --- improved restore: always try to repopulate vendor/job lists from server when a saved client exists ---
  async function restoreDropdownStateIfSafe() {
    try {
      // If user clicked Reset recently, do not restore (bfcache safety)
      if (sessionStorage.getItem(RESET_FLAG)) { sessionStorage.removeItem(RESET_FLAG); return; }
      const raw = localStorage.getItem(DD_STATE_KEY);
      if (!raw) return;
      const st = JSON.parse(raw || '{}');
      if (!st) return;

      const clientSelect = clientSelectEl();
      const vendorSelect = vendorSelectEl();
      const jdSelect = jdSelectEl();

      if (st.client) {
        // set client value (if available)
        try { if (clientSelect) clientSelect.value = st.client; } catch(e){}

        // Force server fetch for vendors to ensure fresh options after navigating back
        try {
          await fetchVendorsForClient(st.client);
        } catch(e){ /* ignore, fallback below */ }

        // ensure vendor option exists and select it
        try {
          if (vendorSelect && st.vendor) {
            const exists = Array.from(vendorSelect.options).some(opt => String(opt.value) === String(st.vendor));
            if (!exists && st.vendors && st.vendors.length) {
              st.vendors.forEach(v => {
                if (v && v.value !== undefined && String(v.value) === String(st.vendor)) {
                  const o = document.createElement('option'); o.value = v.value; o.textContent = v.text; vendorSelect.appendChild(o);
                }
              });
            }
            vendorSelect.value = st.vendor;
            // fetch jobs for vendor (server-first)
            await fetchJobsForVendor(st.vendor);
          }
        } catch(e){}

        // ensure job option exists and select it
        try {
          if (jdSelect && st.job) {
            const existsJ = Array.from(jdSelect.options).some(opt => String(opt.value) === String(st.job));
            if (!existsJ && st.jobs && st.jobs.length) {
              st.jobs.forEach(j => {
                if (j && j.value !== undefined && String(j.value) === String(st.job)) {
                  const o = document.createElement('option'); o.value = j.value; o.textContent = j.text; jdSelect.appendChild(o);
                }
              });
            }
            jdSelect.value = st.job;
          }
        } catch(e){}
        return;
      }

      // if no saved client, restore vendor/job option snapshots if selects empty (original fallback)
      if (vendorSelect && vendorSelect.options.length <= 1 && st.vendors && st.vendors.length) {
        vendorSelect.innerHTML = '<option value="">Select Manager</option>';
        st.vendors.forEach(v => {
          if (v && v.value && !Array.from(vendorSelect.options).some(opt => String(opt.value) === String(v.value))) {
            const o = document.createElement('option'); o.value = v.value; o.textContent = v.text; vendorSelect.appendChild(o);
          }
        });
        try { vendorSelect.value = st.vendor || ''; } catch(e){}
      }
      if (jdSelect && jdSelect.options.length <= 1 && st.jobs && st.jobs.length) {
        jdSelect.innerHTML = '<option value="">Select Job</option>';
        st.jobs.forEach(j => {
          if (j && j.value && !Array.from(jdSelect.options).some(opt => String(opt.value) === String(j.value))) {
            const o = document.createElement('option'); o.value = j.value; o.textContent = j.text; jdSelect.appendChild(o);
          }
        });
        try { jdSelect.value = st.job || ''; } catch(e){}
      }
    } catch(e){ console.warn('restoreDropdownStateIfSafe', e); }
  }

  // Save on change (captures selects)
  ['change','input'].forEach(ev => {
    document.addEventListener(ev, function(e){
      if (e.target && (e.target.id === 'clientSelect' || e.target.id === 'vendorSelect' || e.target.id === 'jdSelect')) {
        saveDropdownState();
      }
    }, {capture:true});
  });

  window.addEventListener('beforeunload', saveDropdownState);

  // --- pageshow handler (bfcache) ---
  window.addEventListener('pageshow', async function (e) {
    try {
      bindResetInterceptors();
      bindCascadingOnce();
      // Wait for restore so selects are repopulated before mapping refresh
      await restoreDropdownStateIfSafe();
      attachDelegation();
      applyLinkedIds();
      renderPagination();
      const jd = jdSelectEl(); if (jd && jd.value) refreshMappingsForJob(jd.value);
    } catch(err){ console.warn('pageshow handler', err); }
  });

  // --- initial hydration and state apply ---
  attachDelegation();
  try { if (document.getElementById('search-results-body') && document.getElementById('search-results-body').querySelectorAll('tr.candidate-row').length > 0) serializeSnapshot(); } catch(e){}
  hydrateIfNeeded();
  // Ensure dropdown restore on first load too (covers direct navigation)
  restoreDropdownStateIfSafe();
  applyLinkedIds();
  renderPagination();
});
