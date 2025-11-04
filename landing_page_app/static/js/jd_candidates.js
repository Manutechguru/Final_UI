// jd_candidates.js - updated to correctly use #candidateDetailsModal from the template
// Only modification: candidate details popup wiring fixed to use existing modal IDs in HTML

let jdId = null;
let statusOptions = [];
let notesSaveTimers = {};
let editableSaveTimers = {};

// Initialize
function initJDCandidatesPage(data) {
  jdId = data.jdId;
  statusOptions = data.statusOptions || [];
  setupEventListeners();
  setupNotesEditing();
  setupEditableFields();
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

  // modal close (generic)
  document.querySelectorAll('.modal-close').forEach(btn => {
    btn.addEventListener('click', () => {
      const modal = btn.closest('.modal') || btn.closest('.custom-modal');
      if (modal) modal.classList.remove('open');
      if (modal) modal.setAttribute('aria-hidden', 'true');
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

// Editable fields (Notice Period & CTC)
function setupEditableFields() {
  document.querySelectorAll('.editable-field').forEach(container => {
    const display = container.querySelector('.editable-display');
    const edit = container.querySelector('.editable-edit');
    const cid = container.dataset.candidateId;
    const fieldType = container.dataset.fieldType;
    
    container.dataset.originalValue = (display?.textContent || '').trim();

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

    edit.addEventListener('blur', () => saveEditableField(cid, fieldType, edit.value));
    edit.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        edit.blur();
      } else if (e.key === 'Escape') {
        edit.value = container.dataset.originalValue || '';
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

// Save editable fields (Notice Period & CTC)
function saveEditableField(candidateId, fieldType, value) {
  if (!candidateId || !fieldType) return;
  
  const container = document.querySelector(`.editable-field[data-candidate-id="${candidateId}"][data-field-type="${fieldType}"]`);
  if (!container) return;
  
  const display = container.querySelector('.editable-display');
  const edit = container.querySelector('.editable-edit');

  if (display) display.textContent = 'Saving...';
  if (edit) { edit.style.display = 'none'; display.style.display = 'block'; }

  clearTimeout(editableSaveTimers[`${candidateId}-${fieldType}`]);
  editableSaveTimers[`${candidateId}-${fieldType}`] = setTimeout(async () => {
    try {
      let endpoint, payload;
      
      if (fieldType === 'notice_period') {
        endpoint = '/candidates/update-notice-period';
        payload = { candidate_id: candidateId, notice_period: value };
      } else if (fieldType === 'ctc') {
        endpoint = '/candidates/update-ctc';
        payload = { candidate_id: candidateId, ctc: value };
      } else {
        throw new Error('Unknown field type');
      }

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) throw new Error(await res.text());
      
      container.dataset.originalValue = value || '';
      display.textContent = value || 'Click to edit';
      showToast(`${fieldType === 'ctc' ? 'CTC' : 'Notice period'} updated`, 'success');
    } catch (err) {
      display.textContent = container.dataset.originalValue || 'Click to edit';
      edit.value = container.dataset.originalValue || '';
      showToast(`Failed to save ${fieldType === 'ctc' ? 'CTC' : 'notice period'}: ` + err.message, 'error', 3000);
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
      modal?.setAttribute('aria-hidden', 'false');
      modal?.addEventListener('click', (ev) => { if (ev.target === modal) modal.classList.remove('open'); }, { once: true });
    });
  });
}

// Row expansion and row click -> open details modal
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
      if (t.closest('.editable-field')) return; // notice period & ctc
      if (t.closest('.ai-score-container') || t.closest('.ai-score')) return; // AI score

      // fallback check by column header
      const td = t.closest('td');
      if (td) {
        const th = row.closest('table')?.querySelector(`thead tr th:nth-child(${td.cellIndex + 1})`);
        const heading = (th?.textContent || '').trim().toLowerCase();
        if (heading.includes('recruiter notes') || heading.includes('ai score') || 
            heading.includes('notice') || heading.includes('ctc')) return;
      }

      openCandidateDetailsModal(row);
    });
  });

  const modal = document.getElementById('candidateDetailsModal');
  modal?.addEventListener('click', (ev) => { if (ev.target === modal) closeCandidateDetailsModal(); });
  document.getElementById('candidateDetailsClose')?.addEventListener('click', closeCandidateDetailsModal);
}

// Replace existing openCandidateDetailsModal with this tighter version
function openCandidateDetailsModal(row) {
  const modal = document.getElementById('candidateDetailsModal');
  const contentContainer = document.getElementById('candidateDetailsContent');
  if (!modal || !contentContainer || !row) return;

  // Collect headers and cells (prefer expanded row values when present)
  const table = row.closest('table');
  const headers = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
  const cells = [...row.querySelectorAll('td')];
  const expandedRow = (row.nextElementSibling && row.nextElementSibling.classList.contains('expanded-row')) ? row.nextElementSibling : null;
  const expandedCells = expandedRow ? [...expandedRow.querySelectorAll('td')] : [];

  const getByHeader = (cands) => {
    for (const cand of cands) {
      const idx = headers.findIndex(h => h.toLowerCase() === cand.toLowerCase());
      if (idx >= 0) {
        const prefer = (expandedCells[idx] && expandedCells[idx].innerText.trim()) ? expandedCells[idx] : cells[idx];
        return (prefer?.innerText || '').trim() || 'N/A';
      }
    }
    return 'N/A';
  };

  // Gather fields
  const name = getByHeader(['Name']) || 'N/A';
  const skills = getByHeader(['Skills','Skillset']) || 'N/A';
  const relExp = getByHeader(['Rel Exp','Relevant Experience','Relevant']) || 'N/A';
  const location = getByHeader(['Location']) || 'N/A';
  const contact = getByHeader(['Contact','Phone']) || 'N/A';
  const email = getByHeader(['Email']) || 'N/A';
  const itExp = getByHeader(['IT Exp','IT Experience']) || 'N/A';
  const education = getByHeader(['Education']) || 'N/A';
  const company = getByHeader(['Company']) || 'N/A';
  const clients = getByHeader(['Clients']) || 'N/A';
  const notice = getByHeader(['Notice','Notice Period']) || 'N/A';
  const ctc = getByHeader(['CTC']) || 'N/A';
  const comment = getByHeader(['Comment']) || 'N/A';
  const recruiterNotes = getByHeader(['Recruiter Notes','Recruitment Notes']) || 'N/A';
  const stage = getByHeader(['Stage']) || 'N/A';
  const aiScoreRaw = getByHeader(['AI Score','AI']) || 'N/A';

  // resume link detection
  let resumeHref = '#';
  const resumeIdx = headers.findIndex(h => /resume/i.test(h));
  if (resumeIdx >= 0) {
    const targetCell = (expandedCells[resumeIdx] && expandedCells[resumeIdx].querySelector('a')) ? expandedCells[resumeIdx] : cells[resumeIdx];
    resumeHref = targetCell?.querySelector?.('a')?.href || '#';
  } else {
    const a = row.querySelector('a[href*="resume"], a[title*="resume"], a[aria-label*="resume"]');
    resumeHref = a?.href || '#';
  }

  // Build header (NO "Candidate Details" title, compact)
  const headerHtml = `
    <div class="custom-modal-header-strip" role="banner" aria-hidden="false">
      <div class="modal-header-left" style="padding-right:12px;">
        <div class="candidate-title" style="margin:0; font-weight:800; font-size:1rem;">${escapeHtml(name)}</div>
        <div style="margin-top:8px; display:flex; flex-direction:column; gap:6px;">
          ${resumeHref && resumeHref !== '#' ? `<a class="resume-action" href="${resumeHref}" target="_blank" rel="noopener noreferrer">View Resume <i class="bi bi-box-arrow-up-right"></i></a>` : ''}
          <div class="candidate-meta" style="font-size:0.9rem; opacity:0.95;">${escapeHtml(location)}${contact && contact !== 'N/A' ? ' • ' + escapeHtml(contact) : ''}</div>
        </div>
      </div>

      <div class="modal-header-right" style="display:flex; align-items:center; gap:10px;">
        <div class="ai-badge" aria-hidden="true">AI Score: ${escapeHtml(aiScoreRaw)}</div>
        <button class="custom-modal-close header-close" id="candidateDetailsCloseInner" aria-label="Close">&times;</button>
      </div>
    </div>
  `;

  // Details grid (two columns)
  const detailsGrid = `
    <div class="candidate-details-grid" style="margin-top:6px;">
      <div class="label">Email</div><div class="value">${escapeHtml(email)}</div>
      <div class="label">Company</div><div class="value">${escapeHtml(company)}</div>
      <div class="label">IT Exp</div><div class="value">${escapeHtml(itExp)}</div>
      <div class="label">Education</div><div class="value">${escapeHtml(education)}</div>
      <div class="label">Notice</div><div class="value">${escapeHtml(notice)}</div>
      <div class="label">Clients</div><div class="value">${escapeHtml(clients)}</div>
      <div class="label">CTC</div><div class="value">${escapeHtml(ctc)}</div>
      <div class="label">Stage</div><div class="value">${escapeHtml(stage)}</div>
    </div>
  `;

  const skillsHtml = `
    <div class="section" style="padding:14px 0 6px 0;">
      <div style="font-weight:700; margin-bottom:10px;">Skills & Experience</div>
      <div style="font-size:0.92rem; color:#374151;">
        <div style="font-weight:700; text-transform:uppercase; color:var(--muted,#6b7280); font-size:0.78rem;">SKILLS</div>
        <div style="margin:6px 0 10px 0;">${escapeHtml(skills)}</div>
        <div style="font-weight:700; text-transform:uppercase; color:var(--muted,#6b7280); font-size:0.78rem; margin-top:8px;">RELEVANT EXPERIENCE</div>
        <div style="margin:6px 0 0 0;">${escapeHtml(relExp)}</div>
      </div>
    </div>
  `;

  const commentHtml = `
    <div class="section" style="padding-top:12px;">
      <div style="font-weight:700; margin-bottom:8px;">Comment</div>
      <div style="color:#374151;">${escapeHtml(comment)}</div>
    </div>
    <div class="section" style="padding-top:12px;">
      <div style="font-weight:700; margin-bottom:8px;">Recruitment Notes</div>
      <div style="color:#374151;">${escapeHtml(recruiterNotes)}</div>
    </div>
  `;

  // Compose final HTML (into existing .custom-modal-body container)
  contentContainer.innerHTML = `
    ${headerHtml}
    <div class="modal-body-content" role="document">
      ${skillsHtml}
      <div style="border-top:1px solid var(--border,#eef2f7); padding-top:12px;">
        <div style="font-weight:700; margin-bottom:10px;">Details</div>
        ${detailsGrid}
      </div>
      ${commentHtml}
    </div>
  `;

  // Show overlay and center it
  modal.classList.add('open');
  modal.setAttribute('aria-hidden','false');

  document.body.style.overflow = 'hidden';                          // prevent background scroll
  // reset inner content scroll to top if exists
  const inner = contentContainer.querySelector('.modal-body-content');
  if (inner) inner.scrollTop = 0;


  // Bind inner close (header)
  const innerClose = document.getElementById('candidateDetailsCloseInner');
  if (innerClose) innerClose.addEventListener('click', closeCandidateDetailsModal);

  // Accessibility focus
  const closeBtn = modal.querySelector('.header-close');
  if (closeBtn) closeBtn.focus();

  // Small helper to escape HTML
  function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"'`=\/]/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','/':'&#x2F;','`':'&#x60;','=':'&#x3D;'}[c];
    });
  }
}

function closeCandidateDetailsModal() {
  const modal = document.getElementById('candidateDetailsModal');
  if (!modal) return;
  modal.classList.remove('open');
  modal.setAttribute('aria-hidden', 'true');
}

document.body.style.overflow = '';  // restore background scroll

// Close button handler (bind once)
document.addEventListener("DOMContentLoaded", () => {
  const closeBtn = document.getElementById("closePopup");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => closeCandidateDetailsModal());
  }
});


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


// ✅ UPDATED: Excel Export (handles both ALL + SELECTED candidates)
function handleDownloadXlsx() {
  const selected = getCheckboxes().filter(c => c.checked).map(c => c.value);

  if (selected.length) {
    // 👉 Export only selected candidates
    showConfirmation(
      'Export Selected Candidates',
      `Do you want to export ${selected.length} selected candidates?`,
      async () => {
        showProgress('Exporting', 'Preparing Excel for selected candidates...');
        try {
          const response = await fetch("/candidates/export/xlsx", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ candidate_ids: selected })
          });

          if (!response.ok) throw new Error("Failed to export selected candidates");
          
          // Convert response to a downloadable file
          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "selected_candidates.xlsx";
          document.body.appendChild(a);
          a.click();
          a.remove();
          window.URL.revokeObjectURL(url);

          hideProgress();
          showToast('Exported selected candidates', 'success');
        } catch (err) {
          hideProgress();
          showToast('Error exporting candidates', 'error');
          console.error(err);
        }
      }
    );
  } else {
    // 👉 Export all candidates (existing flow)
    showConfirmation('Export Excel', 'Export all candidate data?', () => {
      showProgress('Exporting', 'Preparing Excel...');
      setTimeout(() => { 
        window.location.href = `/candidates/export/xlsx?jd_id=${jdId}`; 
        hideProgress(); 
        showToast('Export started', 'success'); 
      }, 800);
    });
  }
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

// Hide specific columns completely
function hideColumns(cols) {
  const table = document.querySelector('table.candidates');
  if (!table) return;

  table.querySelectorAll('tr').forEach(row => {
    cols.forEach(c => {
      const cell = row.children[c - 1]; // columns are 1-indexed
      if (cell) cell.style.display = 'none';
    });
  });
}

// call it
hideColumns([1, 4, 7, 9, 10, 11, 13, 16]);

// --- Gmail icon dropdown logic ---
document.addEventListener("DOMContentLoaded", () => {
  const gmailBtn = document.getElementById("gmailActionBtn");
  const dropdown = document.getElementById("gmailActionDropdown");
  const toCandidatesBtn = document.getElementById("gmailToCandidates");
  const toClientsBtn = document.getElementById("gmailToClients");

  if (!gmailBtn || !dropdown) return;

  // Toggle dropdown visibility
  gmailBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    dropdown.classList.toggle("show");
  });

  // Close dropdown on outside click
  document.addEventListener("click", (e) => {
    if (!gmailBtn.contains(e.target)) {
      dropdown.classList.remove("show");
    }
  });

  function getSelectedCandidateIds() {
    const checkboxes = document.querySelectorAll(".candidateCheckbox:checked");
    return Array.from(checkboxes).map(cb => cb.value);
  }

  // Redirect to compose (to candidates)
  toCandidatesBtn.addEventListener("click", () => {
    const ids = getSelectedCandidateIds();
    if (!ids.length) {
      alert("Please select at least one candidate.");
      return;
    }
    const jdId = window.jdId || "{{ jd_id }}";
    window.location.href = `/candidates/gmail/compose?mode=candidates&candidate_ids=${ids.join(',')}&jd_id=${jdId}`;
  });

  // Redirect to compose (to clients/recruiters)
  toClientsBtn.addEventListener("click", () => {
    const ids = getSelectedCandidateIds();
    if (!ids.length) {
      alert("Please select at least one candidate.");
      return;
    }
    const jdId = window.jdId;
    window.location.href = `/candidates/gmail/compose?mode=clients&candidate_ids=${ids.join(',')}&jd_id=${jdId}`;
  });
});

// ======= Cleanup stray "AI Score Explanation" element and tidy header actions =======
document.addEventListener('DOMContentLoaded', () => {
  try {
    // 1) Remove any stray section that contains heading text "AI Score Explanation"
    // We search headings and plain text nodes to be robust against slight markup differences.
    const possibleSelectors = [
      '#aiScoreExplanation',            // if someone added an id
      '.ai-score-explanation',          // common classname
      '#aiExplanation',                 // alternate id
      '#aiExplanationModalTrigger'      // alternate
    ];
    for (const sel of possibleSelectors) {
      const el = document.querySelector(sel);
      if (el) { el.remove(); }
    }

    // If the stray markup is a heading text on the page (e.g. <h3>AI Score Explanation</h3>),
    // locate any heading containing that text and remove its container.
    const headings = [...document.querySelectorAll('h1,h2,h3,h4,div,section,p')];
    for (const h of headings) {
      const txt = (h.textContent || '').trim();
      if (/^ai score explanation$/i.test(txt)) {
        // remove nearest block container to avoid leaving a hanging '×' or small element
        const container = h.closest('section,div,article') || h.parentElement;
        if (container) container.remove();
      }
    }

    // Also remove any small lone "×" that appears directly after a short label like "AI Score Explanation"
    // (covers cases where the close button is left behind)
    [...document.querySelectorAll('button,span')].forEach(el => {
      if ((el.textContent || '').trim() === '×' || (el.textContent || '').trim() === 'x') {
        // only remove if it's adjacent to a removed/empty block or suspiciously near "AI Score"
        const prev = el.previousSibling;
        const next = el.nextSibling;
        const context = ((prev && prev.textContent) || '') + ' ' + ((next && next.textContent) || '');
        if (/ai score/i.test(context) || /ai score explanation/i.test(context) || !el.getAttribute('data-preserve')) {
          // remove the icon (safe fallback)
          el.remove();
        }
      }
    });
  } catch (e) {
    console.warn('cleanup AI explanation failed', e);
  }
});
