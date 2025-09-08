// jd_candidates.js - full
// Only modification: prevent candidate details popup when clicking Recruiter Notes or AI Score columns

let jdId = null;
let statusOptions = [];
let notesSaveTimers = {};

// Initialize
function initJDCandidatesPage(data) {
  jdId = data.jdId;
  statusOptions = data.statusOptions || [];
  setupEventListeners();
  setupNotesEditing();
  setupAIExplanation();
  updateKPI();
  ensureCheckboxIds();
  applyStageFilter();
  highlightRowsFromURL();
}

// Event listeners
function setupEventListeners() {
  const selectAll = document.getElementById('selectAll');
  const removeBtn = document.getElementById('removeSelectedBtn');
  const stageFilter = document.getElementById('stageFilter');
  const actionMenuBtn = document.getElementById('actionMenuBtn');
  const actionMenuDropdown = document.getElementById('actionMenuDropdown');
  const downloadZipBtn = document.getElementById('downloadZipBtn');
  const downloadXlsxBtn = document.getElementById('downloadXlsxBtn');
  const confirmationCancel = document.getElementById('confirmationCancel');
  const confirmationConfirm = document.getElementById('confirmationConfirm');

  // three-dot menu
  actionMenuBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    actionMenuDropdown.classList.toggle('show');
  });
  document.addEventListener('click', (e) => {
    if (!actionMenuBtn?.contains(e.target) && !actionMenuDropdown?.contains(e.target)) {
      actionMenuDropdown?.classList.remove('show');
    }
  });

  // select all
  selectAll?.addEventListener('change', () => {
    const checked = selectAll.checked;
    getCheckboxes().forEach(cb => cb.checked = checked);
    updateKPI();
  });
  getCheckboxes().forEach(cb => cb.addEventListener('change', () => {
    selectAll.checked = getCheckboxes().every(c => c.checked);
    updateKPI();
  }));

  // toolbar
  removeBtn?.addEventListener('click', handleRemoveSelected);
  downloadZipBtn?.addEventListener('click', handleDownloadZip);
  downloadXlsxBtn?.addEventListener('click', handleDownloadXlsx);
  stageFilter?.addEventListener('change', applyStageFilter);

  confirmationCancel?.addEventListener('click', closeConfirmationDialog);
  confirmationConfirm?.addEventListener('click', executeConfirmedAction);

  // modal close
  document.querySelectorAll('.modal-close').forEach(btn => {
    btn.addEventListener('click', () => {
      const modal = btn.closest('.modal');
      if (modal) modal.classList.remove('open');
    });
  });

  // row popup
  setupRowExpansion();
}

// Notes editing
function setupNotesEditing() {
  document.querySelectorAll('.notes-editable').forEach(container => {
    const display = container.querySelector('.notes-display');
    const edit = container.querySelector('.notes-edit');
    const cid = container.dataset.candidateId;
    container.dataset.originalNotes = (display?.textContent || '').trim();

    if (display) {
      display.addEventListener('click', (e) => {
        e.stopPropagation(); // block row modal
        if (!edit) return;
        display.style.display = 'none';
        edit.style.display = 'block';
        edit.focus();
        try { edit.select(); } catch {}
      });
    }

    if (!edit) return;

    edit.addEventListener('blur', () => saveNotes(cid, edit.value));
    edit.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        edit.blur();
      } else if (e.key === 'Escape') {
        edit.value = container.dataset.originalNotes || '';
        edit.style.display = 'none';
        display.style.display = 'block';
      }
    });
  });
}

// Save notes
function saveNotes(candidateId, notes) {
  if (!candidateId) return;
  const container = document.querySelector(`.notes-editable[data-candidate-id="${candidateId}"]`);
  if (!container) return;
  const display = container.querySelector('.notes-display');
  const edit = container.querySelector('.notes-edit');

  if (display) display.textContent = 'Saving...';
  if (edit) { edit.style.display = 'none'; display.style.display = 'block'; }

  clearTimeout(notesSaveTimers[candidateId]);
  notesSaveTimers[candidateId] = setTimeout(async () => {
    try {
      const res = await fetch('/candidates/update-recruiter-notes', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ candidate_id: candidateId, notes })
      });
      if (!res.ok) throw new Error(await res.text());
      container.dataset.originalNotes = notes || '';
      display.textContent = notes || 'Click to add notes';
      showToast('Notes saved', 'success');
    } catch (err) {
      display.textContent = container.dataset.originalNotes || 'Click to add notes';
      edit.value = container.dataset.originalNotes || '';
      showToast('Failed to save notes: ' + err.message, 'error', 3000);
    }
  }, 700);
}

// AI explanation
function setupAIExplanation() {
  document.querySelectorAll('.ai-score-container').forEach(container => {
    container.addEventListener('click', (e) => {
      e.stopPropagation(); // block row modal
      const explanation = container.dataset.explanation || 'No explanation available';
      const modal = document.getElementById('aiExplanationModal');
      const content = document.getElementById('aiExplanationContent');
      if (content) content.textContent = explanation;
      modal?.classList.add('open');
      modal?.addEventListener('click', (ev) => { if (ev.target === modal) modal.classList.remove('open'); }, { once: true });
    });
  });
}

// Row expansion
function setupRowExpansion() {
  document.querySelectorAll('.expander-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const row = btn.closest('tr.main-row');
      if (row) openCandidateDetailsModal(row);
    });
  });

  document.querySelectorAll('table.candidates tbody tr.main-row').forEach(row => {
    row.addEventListener('click', (e) => {
      const t = e.target;
      if (!t) return;

      // block interactive areas
      if (t.closest('input, select, button, a')) return;
      if (t.closest('.notes-editable')) return; // recruiter notes
      if (t.closest('.ai-score-container') || t.closest('.ai-score')) return; // AI score

      // fallback check by column header
      const td = t.closest('td');
      if (td) {
        const th = row.closest('table')?.querySelector(`thead tr th:nth-child(${td.cellIndex + 1})`);
        const heading = (th?.textContent || '').trim().toLowerCase();
        if (heading.includes('recruiter notes') || heading.includes('ai score')) return;
      }

      openCandidateDetailsModal(row);
    });
  });

  const modal = document.getElementById('candidateDetailsModal');
  modal?.addEventListener('click', (ev) => { if (ev.target === modal) closeCandidateDetailsModal(); });
  document.getElementById('candidateDetailsClose')?.addEventListener('click', closeCandidateDetailsModal);
}

// Candidate modal
function openCandidateDetailsModal(row) {
  const modal = document.getElementById('candidateDetailsModal');
  const titleEl = document.getElementById('candidateDetailsTitle');
  const contentEl = document.getElementById('candidateDetailsContent');
  if (!modal || !titleEl || !contentEl) return;

  const expanded = row.nextElementSibling?.classList.contains('expanded-row') ? row.nextElementSibling : null;
  const headers = [...row.closest('table').querySelectorAll('thead th')].slice(2).map(h => h.textContent.trim());
  const mainCells = [...row.querySelectorAll('td')].slice(2);
  const expandedCells = expanded ? [...expanded.querySelectorAll('td')].slice(2) : [];

  const nameCell = expandedCells[0] || mainCells[0];
  titleEl.textContent = (nameCell?.textContent || '').trim() || 'Candidate Details';

  let html = '<div class="candidate-details-grid">';
  headers.forEach((label, i) => {
    const cell = expandedCells[i] || mainCells[i];
    let valueHTML = 'N/A';
    if (cell) {
      if (label.toLowerCase().includes('recruiter notes')) {
        const nd = cell.querySelector('.notes-display');
        valueHTML = nd ? escapeHTML(nd.textContent.trim()) : escapeHTML(cell.textContent.trim());
      } else {
        valueHTML = cell.innerHTML.trim() || escapeHTML(cell.textContent.trim());
      }
    }
    html += `<div class="label">${escapeHTML(label)}</div><div class="value">${valueHTML}</div>`;
  });
  html += '</div>';

  contentEl.innerHTML = html;
  modal.classList.add('open');
  const onKey = (ev) => { if (ev.key === 'Escape') { closeCandidateDetailsModal(); document.removeEventListener('keydown', onKey); } };
  document.addEventListener('keydown', onKey);
}
function closeCandidateDetailsModal() {
  document.getElementById('candidateDetailsModal')?.classList.remove('open');
}
function escapeHTML(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}

// Highlight new rows
function highlightRowsFromURL() {
  try {
    const ids = (new URLSearchParams(window.location.search).get('highlight') || '').split(',').filter(Boolean);
    ids.forEach(id => {
      const row = document.querySelector(`tr[data-candidate-id="${id}"]`);
      if (row) {
        row.classList.add('highlight-row');
        row.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
    setTimeout(() => ids.forEach(id => document.querySelector(`tr[data-candidate-id="${id}"]`)?.classList.remove('highlight-row')), 6000);
  } catch {}
}

// Helpers
function getCheckboxes() { return [...document.querySelectorAll('.candidateCheckbox')]; }
function updateKPI() { document.getElementById('kpiSelected').textContent = getCheckboxes().filter(c => c.checked).length; }
function ensureCheckboxIds() {
  getCheckboxes().forEach(cb => {
    if (!cb.value || cb.value.toLowerCase() === 'none') {
      const id = cb.closest('tr')?.dataset.candidateId;
      if (id) cb.value = id;
    }
  });
}
function applyStageFilter() {
  const val = document.getElementById('stageFilter')?.value || '';
  document.querySelectorAll('.main-row').forEach(r => r.style.display = (!val || r.dataset.stage === val) ? '' : 'none');
}

// Remove
function handleRemoveSelected() {
  const selected = getCheckboxes().filter(c => c.checked).map(c => c.value);
  if (!selected.length) return showToast('Please select candidates to remove', 'warning', 2000);
  showConfirmation('Remove Candidates', `Are you sure to remove ${selected.length}?`, async () => {
    showProgress('Removing', 'Removing candidates...', `${selected.length} candidates`);
    try {
      const res = await fetch('/candidates/remove-from-jd', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ candidate_ids: selected, jd_id: jdId }) });
      if (!res.ok) throw new Error(await res.text());
      showToast(`Removed ${selected.length}`, 'success');
      setTimeout(() => location.reload(), 900);
    } catch (err) { showToast('Remove failed: ' + err.message, 'error', 3000); }
    finally { hideProgress(); }
  });
}

// Download
function handleDownloadZip() {
  const selected = getCheckboxes().filter(c => c.checked).map(c => c.value);
  if (!selected.length) return showToast('Please select candidates', 'warning', 2000);
  showConfirmation('Download Resumes', `Download ${selected.length} as ZIP?`, () => {
    showProgress('Preparing', 'Preparing resumes...', `${selected.length} files`);
    setTimeout(() => { window.location.href = `/candidates/download/resumes?candidate_ids=${selected.join(',')}&jd_id=${jdId}`; hideProgress(); showToast('Download started', 'success'); }, 800);
  });
}
function handleDownloadXlsx() {
  showConfirmation('Export Excel', 'Export all candidate data?', () => {
    showProgress('Exporting', 'Preparing Excel...');
    setTimeout(() => { window.location.href = `/candidates/export/xlsx?jd_id=${jdId}`; hideProgress(); showToast('Export started', 'success'); }, 800);
  });
}

// Toast + dialogs
function showToast(msg, type='default', time=3000) {
  const c = document.getElementById('toastContainer'); if (!c) return;
  const el = document.createElement('div'); el.className = `toast ${type !== 'default' ? 'toast-'+type : ''}`;
  el.innerHTML = `<span>${msg}</span><button class="toast-close">&times;</button>`;
  el.querySelector('.toast-close').onclick = () => el.remove();
  c.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, time);
}
let confirmCallback=null;
function showConfirmation(title,msg,cb){document.getElementById('confirmationTitle').textContent=title;document.getElementById('confirmationMessage').textContent=msg;confirmCallback=cb;document.getElementById('confirmationDialog').classList.add('open');}
function closeConfirmationDialog(){document.getElementById('confirmationDialog').classList.remove('open');confirmCallback=null;}
function executeConfirmedAction(){if(typeof confirmCallback==='function')confirmCallback();closeConfirmationDialog();}
function showProgress(t,m,c=''){document.getElementById('progressTitle').textContent=t;document.getElementById('progressMessage').textContent=m;document.getElementById('progressCount').textContent=c;document.getElementById('progressOverlay').style.display='flex';}
function hideProgress(){document.getElementById('progressOverlay').style.display='none';}

// Stage change
document.addEventListener('change', async (e) => {
  const t = e.target;
  if (t.classList.contains('stageDropdown')) {
    const cid = t.dataset.candidate;
    const stage = t.value;
    const row = document.querySelector(`.main-row[data-candidate-id="${cid}"]`);
    const prev = row?.dataset.stage;
    try {
      const res = await fetch(`/candidates/${encodeURIComponent(cid)}/stage`, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ stage, jd_id: jdId }) });
      if (!res.ok) throw new Error(await res.text());
      if (row) row.dataset.stage = stage;
      applyStageFilter();
      showToast('Stage updated', 'success');
    } catch (err) {
      showToast('Update failed: ' + err.message, 'error', 3000);
      t.value = prev;
    }
  }
});
