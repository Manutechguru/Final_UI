// jd_candidates.js - updated to correctly use #candidateDetailsModal from the template
// Only modification: candidate details popup wiring fixed to use existing modal IDs in HTML

// 🔥 FORCE preboarding modal to escape table/scroll containers
document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("preboardingModal");
  if (modal && modal.parentElement !== document.body) {
    document.body.appendChild(modal);
  }
});

let jdId = null;
let statusOptions = [];
let notesSaveTimers = {};
let editableSaveTimers = {};

// ================= ONBOARDING =================

const ONBOARDING_STEPS = [
  "JOINING_DETAILS",
  "PAYROLL",
  "IT_ACCESS",
  "POLICY",
  "FINAL"
];

// ================= PREBOARDING =================

const REQUIRED_DOCS = {
  ID: [
    "AADHAAR_OR_PASSPORT",
    "PAN_CARD",
    "ADDRESS_PROOF",
    "PASSPORT_PHOTO"
  ],
  EDUCATION: [
    "DEGREE_CERTIFICATE",
    "SEM_MARKSHEETS",
    "INTERMEDIATE_CERT",
    "SSC_CERT"
  ],
  EXPERIENCE: [
    "OFFER_LETTER",
    "RELIEVING_LETTER",
    "PAYSLIPS"
  ],
  REFERENCE: [
    "REF_1",
    "REF_2",
    "REF_CONTACT"
  ]
};

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
  // ================= STAGE ACTION ENTRY =================
  if (stage === "Preboarding" || stage === "Onboarding") {
    const wrapper = document.createElement("div");
    wrapper.style.marginTop = "16px";

    const isPreboarding = stage === "Preboarding";
    const candidateId = row.dataset.candidateId;

    wrapper.innerHTML = `
      <div style="border-top:1px solid var(--border); padding-top:12px;">
        <button class="btn small stage-action-btn">
          ${isPreboarding ? "Preboarding" : "Onboarding"}
        </button>
      </div>
    `;

    contentContainer
      .querySelector(".modal-body-content")
      .appendChild(wrapper);

    const btn = wrapper.querySelector(".stage-action-btn");

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation(); // 🔥 prevent row / modal conflicts

      closeCandidateDetailsModal(); // close candidate details first

      if (isPreboarding) {
        openPreboardingModal(candidateId, window.jdId);
      } else {
        openOnboardingModal(candidateId, window.jdId);
      }
    });
  }

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
// Modern white-card toast implementation (shortlisted / JD candidates)
function showToast(msg, type = 'success', time = 3000) {
  const c = document.getElementById('toastContainer');
  if (!c) return;

  // Build container piece
  const el = document.createElement('div');
  el.className = 'toast';
  // Map type to title (optional)
  const titleMap = { success: 'Success', error: 'Error', warning: 'Notice', info: 'Info', default: '' };
  const title = titleMap[type] || titleMap['default'];

  // icon selection
  let iconSvg = '';
  if (type === 'success') {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 13l4 4L19 7"></path></svg>`;
  } else if (type === 'error') {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6L6 18M6 6l12 12"></path></svg>`;
  } else if (type === 'warning') {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><path d="M12 9v4M12 17h.01"/></svg>`;
  } else {
    iconSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>`;
  }

  // Escape function to prevent accidental HTML injection
  function escapeHtml(str) {
    if (typeof str !== 'string') return String(str);
    return str.replace(/[&<>"'`=\/]/g, function(s){ return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','/':'&#x2F;','`':'&#x60;','=':'&#x3D;'})[s]; });
  }

  el.innerHTML = `
    <div class="toast-icon">${iconSvg}</div>
    <div class="toast-body">
      ${ title ? `<div class="toast-title">${escapeHtml(title)}</div>` : '' }
      <div class="toast-msg">${escapeHtml(msg)}</div>
    </div>
    <button class="toast-close" aria-label="Close">&times;</button>
  `;

  // close handler
  const closeBtn = el.querySelector('.toast-close');
  const remove = () => {
    el.style.opacity = '0';
    el.style.transform = 'translateX(18px)';
    setTimeout(() => { try { el.remove(); } catch(e){} }, 220);
  };
  closeBtn && closeBtn.addEventListener('click', remove);

  c.appendChild(el);
  // auto dismiss
  setTimeout(remove, time);
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

// ================= LOAD PREBOARDING INTO MODAL =================
async function loadPreboardingIntoModal(candidateId, jdId) {
  const container = document.getElementById("preboardingModalContent");
  if (!container) return;

  try {
    const res = await fetch(
      `/preboarding/case?candidate_id=${candidateId}&jd_id=${jdId}`
    );

    if (!res.ok) throw new Error(await res.text());

    const data = await res.json();

    // store case id globally for FINAL step
    window.currentPreboardingCaseId = data.case_id;

    // render chevron UI
    container.innerHTML = renderPreboardingChevron(data);

    // 🔥 AUTO-OPEN FIRST STEP (ID) IMMEDIATELY
    setTimeout(() => {
      const firstStepBtn = container.querySelector(".preboarding-step-btn");
      if (!firstStepBtn) return;

      const stepId = firstStepBtn.dataset.stepId;
      const stepType = firstStepBtn.dataset.stepType;
      const stepStatus = firstStepBtn.dataset.stepStatus;

      expandPreboardingStep(stepId, stepType, stepStatus);

      // optional: mark as active (pure UI, no logic impact)
      firstStepBtn.classList.add("active");
    }, 0);

  } catch (err) {
    console.error(err);
    container.innerHTML =
      `<div style="color:red;">Failed to load preboarding</div>`;
  }
}

// ================= PREBOARDING CHEVRON UI (EXPANDABLE) =================
function renderPreboardingChevron(data) {
  const steps = data.steps || [];

  return `
    <div class="preboarding-wrapper" style="position:relative;">

      <!-- ✅ REAL CLOSE BUTTON (THIS WILL FINALLY EXIST) -->
      <button
        type="button"
        class="preboarding-close-btn"
        onclick="closePreboardingModal()"
        aria-label="Close"
        style="
          position:absolute;
          top:10px;
          right:12px;
          font-size:30px;
          line-height:1;
          background:none;
          border:none;
          cursor:pointer;
          color:#374151;
          z-index:10000;
        ">
        &times;
      </button>

      <!-- STEP CHEVRONS -->
      <div class="preboarding-steps" style="margin-bottom:12px;">
        ${steps.map((s, idx) => {
          const prevSteps = steps.slice(0, idx);
          const isLocked = prevSteps.some(ps => ps.status === "FAILED");

          return `
            <button
              class="preboarding-step-btn"
              data-step-id="${s.id}"
              data-step-type="${s.step_type}"
              data-step-status="${s.status}"
              ${isLocked ? "disabled" : ""}
              style="
                position:relative;
                padding:10px 34px;
                margin-right:2px;
                font-size:0.8rem;
                font-weight:700;
                border:none;
                cursor:${isLocked ? "not-allowed" : "pointer"};
                opacity:${isLocked ? "0.45" : "1"};
                background:${
                  s.status === "CLEARED" ? "#d1fae5" :
                  s.status === "FAILED" ? "#fee2e2" :
                 "#fef3c7"
                };
                color:${
                  s.status === "CLEARED" ? "#065f46" :
                  s.status === "FAILED" ? "#991b1b" :
                  "#92400e"
                };
                clip-path: polygon(
                  0 0,
                  calc(100% - 18px) 0,
                  100% 50%,
                  calc(100% - 18px) 100%,
                  0 100%,
                  18px 50%
                );
              ">
              ${s.step_type}
            </button>
          `;
        }).join("")}
      </div>

      <!-- EXPANDABLE CONTENT -->
      <div
        id="preboardingStepContent"
        style="
          border-top:1px solid var(--border);
          padding-top:12px;
          flex:1;
          display:flex;
          flex-direction:column;
        "
      >

        <div style="color:#6b7280; font-size:0.9rem;">
          Select a step to verify
        </div>
      </div>
    </div>
  `;
}


// Handle step click → expand content
document.addEventListener("click", function (e) {
  const btn = e.target.closest(".preboarding-step-btn");
  if (!btn) return;

  const stepId = btn.dataset.stepId;
  const stepType = btn.dataset.stepType;
  const stepStatus = btn.dataset.stepStatus;

  expandPreboardingStep(stepId, stepType, stepStatus);
});

function expandPreboardingStep(stepId, stepType, stepStatus) {
  const container = document.getElementById("preboardingStepContent");
  if (!container) return;

  // Initial skeleton
  container.innerHTML = `
    <div style="font-weight:700; margin-bottom:8px;">
      ${stepType} Verification
    </div>

    <div id="stepFormArea" style="margin-top:10px;">
      Loading verification details...
    </div>
  `;

  // 🔥 LOAD DOCS FIRST, THEN RENDER FORM (THIS IS THE FIX)
  loadDocumentsForStep(stepId).then(docs => {
    const formArea = document.getElementById("stepFormArea");
    if (!formArea) return;

    formArea.innerHTML = renderStepForm(
      stepType,
      stepId,
      stepStatus,
      docs
    );

    // 🔐 Enable / disable "Mark Cleared" based on docs
    evaluateStepClearEligibility(docs, stepId);
  });
}

async function loadDocumentsForStep(stepId) {
  try {
    const [docsRes, metaRes] = await Promise.all([
      fetch(`/preboarding/documents/${stepId}`),
      fetch(`/preboarding/step/meta/${stepId}`)
    ]);

    if (!docsRes.ok || !metaRes.ok) {
      throw new Error("Failed to load step data");
    }

    const docs = await docsRes.json();
    const meta = await metaRes.json();

    // 🔐 SINGLE SOURCE OF TRUTH (PER STEP)
    window.stepEditPermissions = window.stepEditPermissions || {};
    window.stepEditPermissions[stepId] = meta.allow_user_edit === true;

    return docs;

  } catch (err) {
    console.error("loadDocumentsForStep failed:", err);

    // fail-safe
    window.stepEditPermissions = window.stepEditPermissions || {};
    window.stepEditPermissions[stepId] = false;

    return [];
  }
}


function renderDocumentsList(docs, stepId) {
  return `
    <div style="font-size:0.85rem;">
      <strong>Uploaded Documents</strong>
      <ul style="margin-top:6px;">
        ${docs.map(d => `
          <li style="
            margin-bottom:6px;
            display:flex;
            align-items:center;
            gap:8px;
          ">
            <a href="${d.file_url}" target="_blank">
              ${d.doc_type}
            </a>

            ${renderDocStatus(d)}

            <button class="btn small"
              onclick="verifyDocument(${d.id}, 'VERIFIED', ${stepId})"
              ${d.verified === "VERIFIED" ? "disabled" : ""}>
              ✔
            </button>

            <button class="btn small btn-danger"
              onclick="verifyDocument(${d.id}, 'REJECTED', ${stepId})"
              ${d.verified === "REJECTED" ? "disabled" : ""}>
              ✖
            </button>
          </li>
        `).join("")}
      </ul>
    </div>
  `;
}

function renderDocStatus(doc) {
  if (doc.verified === "VERIFIED") {
    return `<span style="color:green;font-weight:700;">✔ VERIFIED</span>`;
  }
  if (doc.verified === "REJECTED") {
    return `<span style="color:red;font-weight:700;">✖ REJECTED</span>`;
  }
  return `<span style="color:#92400e;">⏳ PENDING</span>`;
}

/* ================= STEP CLEAR ELIGIBILITY ================= */
/* 🔥 ADD EXACTLY HERE 🔥 */

function evaluateStepClearEligibility(docs, stepId) {
  const clearBtn = document.querySelector(
    `button[onclick="handleStepAction('${stepId}', 'CLEARED')"]`
  );

  if (!clearBtn) return;

  // 🔥 Mark Cleared must ALWAYS be clickable
  clearBtn.disabled = false;
  clearBtn.style.opacity = "1";

  // Optional: helpful tooltip (NOT enforcement)
  if (!docs || docs.length === 0) {
    clearBtn.title = "Upload all required documents before marking Cleared";
  } else {
    clearBtn.title = "Click to mark this step as Cleared";
  }
}


async function verifyDocument(docId, status, stepId) {
  await fetch("/preboarding/document/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_id: docId,
      status: status
    })
  });

  // Reload documents + reevaluate step
  loadDocumentsForStep(stepId);
}


// ================= PREBOARDING STEP FORMS =================
function renderStepForm(stepType, stepId, stepStatus, docs) {

  // 🔑 build docsMap so UI knows which document already exists
  const docsMap = {};
  (docs || []).forEach(d => {
    docsMap[d.doc_type] = d;
  });

  const statusBadge = `
    <div style="margin-bottom:8px; font-size:0.85rem;">
      Status:
      <strong>${stepStatus}</strong>
    </div>
  `;

  const actionButtons = `
    <div
      style="
        margin-top:auto;
        padding-top:90px;
        border-top:1px solid #e5e7eb;
        display:flex;
        justify-content:flex-end;
        gap:16px;
      "
    >
      <button
        class="btn small"
        style="
          min-width:150px;
          display:flex;
          align-items:center;
          justify-content:center;
        "
        onclick="handleStepAction('${stepId}', 'CLEARED')"
      >
        Mark Cleared
      </button>

      <button
        class="btn small btn-danger"
        style="
          min-width:150px;
          display:flex;
          align-items:center;
          justify-content:center;
        "
        onclick="handleStepAction('${stepId}', 'FAILED')"
      >
        Mark Failed
      </button>
    </div>
  `;

  const adminControls =
    window.currentUserRole?.includes("ADMIN")
      ? `
        <div
          style="
            margin-top:12px;
            padding-bottom:12px;
            border-bottom:1px dashed #e5e7eb;
            display:flex;
            gap:8px;
            justify-content:flex-end;
          "
        >
          <button class="btn small btn-warning"
            onclick="toggleUserEdit('${stepId}', true)">
            Allow User Edit
          </button>

          <button class="btn small"
            onclick="toggleUserEdit('${stepId}', false)">
            Lock User Edit
          </button>

          <!-- ✅ EXISTING OVERRIDE BUTTON MOVED HERE -->
          <button class="btn small btn-warning">
            Override
          </button>
        </div>
      `
      : "";


  // ---------------- ID VERIFICATION ----------------
  if (stepType === "ID") {
    return `
      ${statusBadge}
      <strong>ID Documents</strong>

      ${renderUploadRow(
        stepId,
        "AADHAAR_OR_PASSPORT",
        "Aadhaar / Passport",
        docsMap["AADHAAR_OR_PASSPORT"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "PAN_CARD",
        "PAN Card",
        docsMap["PAN_CARD"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "ADDRESS_PROOF",
        "Address Proof",
        docsMap["ADDRESS_PROOF"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "PASSPORT_PHOTO",
        "Passport Size Photo",
        docsMap["PASSPORT_PHOTO"],
        stepStatus
      )}

      ${adminControls}
      ${actionButtons}
    `;
  }

  // ---------------- EDUCATION VERIFICATION ----------------
  if (stepType === "EDUCATION") {
    return `
      ${statusBadge}
      <strong>Education Documents</strong>

      ${renderUploadRow(
        stepId,
        "DEGREE_CERTIFICATE",
        "Degree / Provisional Certificate",
        docsMap["DEGREE_CERTIFICATE"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "SEM_MARKSHEETS",
        "All Semester Marksheets",
        docsMap["SEM_MARKSHEETS"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "INTERMEDIATE_CERT",
        "Intermediate Certificate",
        docsMap["INTERMEDIATE_CERT"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "SSC_CERT",
        "10th SSC Certificate",
        docsMap["SSC_CERT"],
        stepStatus
      )}

      ${adminControls}
      ${actionButtons}
    `;
  }

  // ---------------- EXPERIENCE VERIFICATION ----------------
  if (stepType === "EXPERIENCE") {
    return `
      ${statusBadge}
      <strong>Experience Documents</strong>

      ${renderUploadRow(
        stepId,
        "OFFER_LETTER",
        "Offer Letter",
        docsMap["OFFER_LETTER"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "RELIEVING_LETTER",
        "Relieving / Experience Letter",
        docsMap["RELIEVING_LETTER"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "PAYSLIPS",
        "Last 3–6 Payslips",
        docsMap["PAYSLIPS"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "PF_UAN",
        "PF UAN Proof",
        docsMap["PF_UAN"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "GAP_EXPLANATION",
        "Employment Gap Explanation (if any)",
        docsMap["GAP_EXPLANATION"],
        stepStatus
      )}

      ${adminControls}
      ${actionButtons}
    `;
  }

  // ---------------- REFERENCE VERIFICATION ----------------
  if (stepType === "REFERENCE") {
    return `
      ${statusBadge}
      <strong>Reference Verification</strong>

      ${renderUploadRow(
        stepId,
        "REF_1",
        "Reference 1 (Manager / HR)",
        docsMap["REF_1"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "REF_2",
        "Reference 2 (Client / Manager)",
        docsMap["REF_2"],
        stepStatus
      )}

      ${renderUploadRow(
        stepId,
        "REF_CONTACT",
        "Official Email / Contact Proof",
        docsMap["REF_CONTACT"],
        stepStatus
      )}

      ${adminControls}
      ${actionButtons}
    `;
  }

  // ---------------- FINAL VERIFICATION ----------------
  if (stepType === "FINAL") {
    setTimeout(renderFinalSummary, 0);

    return `
      <!-- FINAL HEADER -->
      <div
        style="
          font-size:1.05rem;
          font-weight:700;
          margin-bottom:14px;
          color:#111827;
        "
      >
        Final Verification Summary
      </div>

      <!-- SUMMARY CONTAINER -->
      <div
        id="finalSummaryContainer"
        style="
          border:1px solid #e5e7eb;
          border-radius:12px;
          padding:16px;
          background:#fafafa;
          margin-bottom:20px;
        "
      >
        Loading verification summary...
      </div>

      <!-- CONFIRMATION NOTE -->
      <div
        style="
          padding:14px 16px;
          border-radius:10px;
          background:#ecfeff;
          border:1px solid #67e8f9;
          color:#155e75;
          font-size:0.85rem;
          margin-bottom:24px;
        "
      >
        Please ensure all required verification steps are reviewed.
        Completing preboarding will lock further edits unless overridden by admin.
      </div>

      <!-- FINAL ACTION -->
      <div
        style="
          display:flex;
          justify-content:flex-end;
          border-top:2px solid #e5e7eb;
          padding-top:20px;
        "
      >
        <button
          class="btn"
          style="
            min-width:200px;
            height:42px;
            font-weight:600;
            display:flex;
            align-items:center;
            justify-content:center;
          "
          onclick="completePreboarding()"
        >
          ✔ Preboarding Completed
        </button>
      </div>
    `;
  }

  return `<div style="color:red;">Unknown verification step</div>`;
}

async function renderFinalSummary() {
  const container = document.getElementById("finalSummaryContainer");
  if (!container) return;

  container.innerHTML = "Loading summary...";

  const steps = document.querySelectorAll(".preboarding-step-btn");

  let html = "";

  for (const btn of steps) {
    const stepType = btn.dataset.stepType;
    const stepId = btn.dataset.stepId;

    if (stepType === "FINAL") continue;

    const docs = await fetch(`/preboarding/documents/${stepId}`)
      .then(r => r.json());

    html += `
      <div style="margin-bottom:16px;">
        <h4 style="font-weight:700; margin-bottom:6px;">
          ${stepType} Verification
        </h4>

        ${
          docs.length === 0
            ? `<div style="color:#6b7280;">No documents</div>`
            : `
              <ul style="font-size:0.85rem;">
                ${docs.map(d => `
                  <li style="margin-bottom:4px;">
                    ${d.doc_type}
                    –
                    <a href="${d.file_url}" target="_blank">View</a>
                    <span style="
                      margin-left:6px;
                      color:${d.verified === "VERIFIED" ? "green" : "orange"};
                      font-weight:600;
                    ">
                      ${d.verified}
                    </span>
                  </li>
                `).join("")}
              </ul>
            `
        }
      </div>
    `;
  }

  container.innerHTML = html;
}

function renderUploadRow(stepId, docType, label, existingDoc, stepStatus) {
  const inputId = `file-${stepId}-${docType}`;

  const isAdmin = window.currentUserRole === "UserRole.ADMIN";
  const allowUserEdit = window.stepEditPermissions?.[stepId] === true;

  const isLocked =
    stepStatus === "CLEARED" &&
    !isAdmin &&
    !allowUserEdit;

  const hasFile = !!existingDoc;

  return `
    <div
      style="
        display:flex;
        align-items:center;
        justify-content:space-between;
        padding:14px 16px;
        margin-bottom:12px;
        border-radius:10px;
        background:${hasFile ? "#f9fafb" : "#ffffff"};
        border:1px solid ${hasFile ? "#e5e7eb" : "#d1d5db"};
        transition:background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
        opacity:${isLocked ? "0.55" : "1"};
      "
      onmouseenter="this.style.background='${isLocked ? (hasFile ? "#f9fafb" : "#ffffff") : "#f1f5f9"}'; this.style.borderColor='#cbd5e1';"
      onmouseleave="this.style.background='${hasFile ? "#f9fafb" : "#ffffff"}'; this.style.borderColor='${hasFile ? "#e5e7eb" : "#d1d5db"}';"
    >

      <!-- LEFT -->
      <div style="display:flex; gap:12px; align-items:flex-start;">

        <!-- ICON -->
        <div
          style="
            width:36px;
            height:36px;
            border-radius:8px;
            background:${hasFile ? "#e0f2fe" : "#f3f4f6"};
            color:${hasFile ? "#0369a1" : "#6b7280"};
            display:flex;
            align-items:center;
            justify-content:center;
            font-size:16px;
            flex-shrink:0;
          "
        >
          📄
        </div>

        <!-- TEXT -->
        <div>
          <div style="font-weight:600; font-size:0.9rem; color:#111827;">
            ${label}
          </div>

          ${
            hasFile
              ? `
                <div style="font-size:0.8rem; color:#2563eb; margin-top:2px;">
                  <a href="${existingDoc.file_url}" target="_blank" style="text-decoration:none;">
                    View uploaded file
                  </a>
                </div>
              `
              : `
                <div style="font-size:0.8rem; color:#6b7280; margin-top:2px;">
                  No file uploaded
                </div>
              `
          }
        </div>
      </div>

      <!-- RIGHT ACTION -->
      <div>
        <input
          type="file"
          id="${inputId}"
          style="display:none"
          ${isLocked ? "disabled" : ""}
          onchange="handleFileSelected(event, '${stepId}', '${docType}')"
        />

        <button
          class="btn small"
          style="
            min-width:110px;
            display:flex;
            align-items:center;
            justify-content:center;
            ${isLocked ? "opacity:0.5; cursor:not-allowed;" : ""}
          "
          ${isLocked ? "disabled" : ""}
          onclick="document.getElementById('${inputId}').click()"
        >
          ${hasFile ? "Replace" : "Upload"}
        </button>
      </div>
    </div>
  `;
}


async function handleFileSelected(event, stepId, docType) {
  const file = event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("step_id", stepId);
  formData.append("doc_type", docType);
  formData.append("file", file);

  try {
    const res = await fetch("/preboarding/document/upload", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || "Upload failed", "error");
      return;
    }

    showToast("Document uploaded", "success");

    // 🔥 1️⃣ Reload docs (MUST await)
    const docs = await loadDocumentsForStep(stepId);

    // 🔥 2️⃣ Re-render step form (THIS WAS MISSING)
    const stepBtn = document.querySelector(
      `.preboarding-step-btn[data-step-id="${stepId}"]`
    );

    if (stepBtn) {
      const stepType = stepBtn.dataset.stepType;
      const stepStatus = stepBtn.dataset.stepStatus;

      const formArea = document.getElementById("stepFormArea");
      if (formArea) {
        formArea.innerHTML = renderStepForm(
          stepType,
          stepId,
          stepStatus,
          docs
        );
      }
    }

    // 🔥 3️⃣ Re-evaluate clear eligibility
    evaluateStepClearEligibility(docs, stepId);

  } catch (e) {
    console.error(e);
    showToast("Upload error", "error");
  }

  // Reset input so same file can be selected again
  event.target.value = "";
}


// ================= PREBOARDING MODAL CONTROL =================

function openPreboardingModal(candidateId, jdId) {
  const modal = document.getElementById("preboardingModal");
  const content = document.getElementById("preboardingModalContent");

  if (!modal || !content) {
    console.error("Preboarding modal elements missing");
    return;
  }

  modal.classList.add("open");      // show modal
  document.body.style.overflow = "hidden"; // lock background scroll

  content.innerHTML = "Loading preboarding...";
  loadPreboardingIntoModal(candidateId, jdId);
}

function closePreboardingModal() {
  const modal = document.getElementById("preboardingModal");
  if (!modal) return;

  modal.classList.remove("open");   // hide modal
  document.body.style.overflow = ""; // restore scroll
}


function openOnboardingModal(candidateId, jdId) {
  const modal = document.getElementById("onboardingModal");
  const content = document.getElementById("onboardingModalContent");

  if (!modal || !content) {
    console.error("❌ Onboarding modal or content container not found");
    return;
  }

  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  content.innerHTML = "<div style='padding:16px;'>Loading onboarding…</div>";

  fetch(`/onboarding/case?candidate_id=${candidateId}&jd_id=${jdId}`)
    .then(res => {
      if (!res.ok) throw new Error("Failed to load onboarding case");
      return res.json();
    })
    .then(data => {
      console.log("✅ Onboarding payload:", data);

      // 🔥 SAFE CASE ID RESOLUTION
      const caseId =
        data?.case?.id ??
        data?.case_id ??
        data?.id;

      if (!caseId) {
        throw new Error("Onboarding case ID missing in payload");
      }

      window.currentOnboardingCaseId = caseId;

      renderOnboardingFlow(data, candidateId, jdId);
      populateJoiningDetailsMeta(jdId);
    })
    .catch(err => {
      console.error("❌ Onboarding load failed:", err);
      content.innerHTML =
        "<div style='padding:16px;color:red;'>Failed to load onboarding data</div>";
    });
}



// ================= ONBOARDING MODAL CLOSE (STRICT FIX) =================
function closeOnboardingModal() {
  const modal = document.getElementById("onboardingModal");
  if (!modal) return;

  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");

  // 🔥 restore background scroll
  document.body.style.overflow = "";
}

// 🔐 Backdrop click closes onboarding
document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("onboardingModal");
  if (!modal) return;

  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      closeOnboardingModal();
    }
  });

  // 🔐 ESC key closes onboarding
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("open")) {
      closeOnboardingModal();
    }
  });
});


function hydrateJoiningDetails(stepData) {
  if (!stepData) return;

  document.getElementById("jd-doj").value =
    stepData.date_of_joining || "";

  document.getElementById("jd-work-location").value =
    stepData.work_location || "";

  document.querySelectorAll('input[name="jd-employment"]').forEach(radio => {
    radio.checked = radio.value === stepData.employment_type;
  });

  document.getElementById("jd-shift").value =
    stepData.shift_timings || "";

  document.getElementById("jd-confirm").checked =
    stepData.candidate_confirmed === true;
}

function hydratePayrollDetails(data, status, documents = []) {
  if (!data) return;

  // TEXT FIELDS
  document.getElementById("pr-holder").value =
    data.bank_account_holder ?? "";

  document.getElementById("pr-bank").value =
    data.bank_name ?? "";

  document.getElementById("pr-ifsc").value =
    data.ifsc_code ?? "";

  document.getElementById("pr-account").value =
    data.account_number ?? "";

  // RADIO: PF OPTION
  if (data.pf_option) {
    const pf = document.querySelector(
      `input[name="pr-pf"][value="${data.pf_option}"]`
    );
    if (pf) pf.checked = true;
  }

  // RADIO: ESIC
  if (typeof data.esic_applicable === "boolean") {
    const esic = document.querySelector(
      `input[name="pr-esic"][value="${data.esic_applicable ? "yes" : "no"}"]`
    );
    if (esic) esic.checked = true;
  }

  // ================= BANK PROOF (FROM PAYLOAD) =================
  const fileInput = document.getElementById("pr-bank-proof");
  if (!fileInput) return;

  const bankProof = documents.find(d => d.doc_type === "BANK_PROOF");

  if (bankProof) {
    fileInput.style.display = "none";

    fileInput.insertAdjacentHTML(
      "afterend",
      `
      <div class="uploaded-file-info" style="margin-top:8px;">
        <span style="font-size:13px;color:#16a34a;font-weight:600;">
          ✔ Bank proof uploaded (${bankProof.verified})
        </span>

        <a
          href="${bankProof.file_url}"
          target="_blank"
          rel="noopener"
          style="
            margin-left:12px;
            font-size:13px;
            color:#2563eb;
            font-weight:600;
            text-decoration:underline;
          ">
          View File
        </a>

        <button
          type="button"
          class="btn small danger outline"
          style="margin-left:6px;"
          onclick="enableBankProofReplace()">
          Replace File
        </button>
      </div>
      `
    );
  }



  // 🔒 LOCK IF CLEARED
  if (status === "CLEARED") {
    document
      .querySelectorAll(
        "#pr-holder, #pr-bank, #pr-ifsc, #pr-account, #pr-bank-proof"
      )
      .forEach(el => (el.disabled = true));

    document
      .querySelectorAll(
        'input[name="pr-pf"], input[name="pr-esic"], #pr-salary-ack'
      )
      .forEach(el => (el.disabled = true));

    const btn = document.querySelector(
      'button[onclick^="savePayrollDetails"]'
    );
    if (btn) btn.style.display = "none";
  }
}

function enableBankProofReplace() {
  const fileInput = document.getElementById("pr-bank-proof");
  if (!fileInput) return;

  // Remove old status UI
  document
    .querySelectorAll(".uploaded-file-info")
    .forEach(el => el.remove());

  // Show file input again
  fileInput.style.display = "block";
  fileInput.disabled = false;

  // Optional visual cue
  fileInput.style.border = "1px dashed #ef4444";
}


function renderBankProofView(doc) {
  const fileInput = document.getElementById("pr-bank-proof");
  if (!fileInput) return;

  // Hide native file input (cannot prefill anyway)
  fileInput.style.display = "none";

  // Prevent duplicate rendering
  if (document.getElementById("bank-proof-view")) return;

  fileInput.insertAdjacentHTML(
    "afterend",
    `
    <div id="bank-proof-view"
         style="margin-top:6px;display:flex;align-items:center;gap:12px;">
      <span style="font-size:13px;color:#16a34a;font-weight:600;">
        ✔ Bank proof uploaded (${doc.verified})
      </span>

      <a href="${doc.file_url}"
         target="_blank"
         rel="noopener"
         class="btn small"
         style="padding:4px 10px;">
        View File
      </a>
    </div>
    `
  );
}


function hydrateITAccess(data) {
  if (!data) return;

  // Email
  const emailInput = document.getElementById("it-email");
  if (emailInput) emailInput.value = data.official_email || "";

  // Asset required
  if (typeof data.asset_required === "boolean") {
    const assetYes = document.querySelector(
      'input[name="it-asset-required"][value="yes"]'
    );
    const assetNo = document.querySelector(
      'input[name="it-asset-required"][value="no"]'
    );

    if (data.asset_required && assetYes) assetYes.checked = true;
    if (!data.asset_required && assetNo) assetNo.checked = true;
  }

  // Asset ID
  const assetIdInput = document.getElementById("it-asset-id");
  if (assetIdInput) assetIdInput.value = data.asset_id || "";

  // Access checklist
  if (document.getElementById("it-email-created"))
    document.getElementById("it-email-created").checked = !!data.email_created;

  if (document.getElementById("it-laptop-assigned"))
    document.getElementById("it-laptop-assigned").checked = !!data.laptop_assigned;

  if (document.getElementById("it-vpn-enabled"))
    document.getElementById("it-vpn-enabled").checked = !!data.vpn_enabled;

  if (document.getElementById("it-client-tools"))
    document.getElementById("it-client-tools").checked =
      !!data.client_tools_access;
}

function hydratePolicyAck(data, status) {
  if (!data) return;

  document.getElementById("pl-offer").checked =
    !!data.offer_letter_accepted;

  document.getElementById("pl-nda").checked =
    !!data.nda_signed;

  document.getElementById("pl-employment").checked =
    !!data.employment_agreement_signed;

  document.getElementById("pl-client-policy").checked =
    !!data.client_policy_accepted;

  // 🔒 If CLEARED → lock the form
  if (status === "CLEARED") {
    [
      "pl-offer",
      "pl-nda",
      "pl-employment",
      "pl-client-policy"
    ].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.disabled = true;
    });

    const btn = document.querySelector(
      ".policy-ack-form button"
    );
    if (btn) btn.style.display = "none";
  }
}

function buildFullOnboardingSummary(steps) {
  const get = type =>
    steps.find(s => s.step_type === type)?.data || {};

  return {
    joining: get("JOINING_DETAILS"),
    payroll: get("PAYROLL"),
    it: get("IT_ACCESS"),
    policy: get("POLICY")
  };
}

function renderOnboardingFlow(payload, candidateId, jdId) {
  const container = document.getElementById("onboardingModalContent");

  /* ===============================
     HARD GUARDS (DO NOT TOUCH)
     =============================== */
  if (!container) {
    console.error("❌ onboardingModalContent not found");
    return;
  }

  if (!payload || !Array.isArray(payload.steps)) {
    container.innerHTML =
      "<div style='padding:16px;color:red;'>Invalid onboarding data</div>";
    console.error("❌ Invalid onboarding payload:", payload);
    return;
  }

  if (payload.steps.length === 0) {
    container.innerHTML =
      "<div style='padding:16px;color:#64748b;'>No onboarding steps found</div>";
    return;
  }

  /* ===============================
     SORT STEPS (CANONICAL ORDER)
     =============================== */
  const sortedSteps = payload.steps.sort(
    (a, b) =>
      ONBOARDING_STEPS.indexOf(a.step_type) -
      ONBOARDING_STEPS.indexOf(b.step_type)
  );

  /* ===============================
     RESET UI
     =============================== */
  container.innerHTML = "";

  /* ===============================
     CHEVRON BAR
     =============================== */
  const chevronBar = document.createElement("div");
  chevronBar.className = "chevron-bar";
  chevronBar.style.marginBottom = "16px";

  /* ===============================
     STEP CONTENT AREA
     =============================== */
  const stepContent = document.createElement("div");

  container.appendChild(chevronBar);
  container.appendChild(stepContent);

  let opened = false;

  /* ===============================
     RENDER CHEVRONS
     =============================== */
  sortedSteps.forEach((step, index) => {
    const chevron = document.createElement("button");
    chevron.className = "chevron";
    chevron.textContent = formatOnboardingStepTitle(step.step_type);

    if (step.status === "CLEARED") chevron.classList.add("cleared");
    if (step.status === "FAILED") chevron.classList.add("failed");

    // 🔒 LOCK RULE (SAME AS PREBOARDING)
    if (
      index > 0 &&
      sortedSteps[index - 1].status !== "CLEARED"
    ) {
      chevron.classList.add("locked");
      chevron.disabled = true;
    }

    chevron.onclick = () => {
      chevronBar
        .querySelectorAll(".chevron")
        .forEach(c => c.classList.remove("active"));

      chevron.classList.add("active");
      // 🔥 FINAL STEP SUMMARY (BUILD ONCE PER CLICK)
      let finalSummary = null;
      if (step.step_type === "FINAL") {
        finalSummary = buildFullOnboardingSummary(sortedSteps);
      }

      /* ===============================
         RENDER SINGLE STEP
         =============================== */
      stepContent.innerHTML = `
        <div class="onboarding-step">

          <div class="onboarding-step-header">
            <div class="onboarding-step-title">
              ${formatOnboardingStepTitle(step.step_type)}
            </div>
            <span class="onboarding-status ${step.status.toLowerCase()}">
              ${step.status}
            </span>
          </div>

          <div class="form-section">
            ${renderOnboardingStepStub(step, finalSummary)}
          </div>
        </div>
      `;


      /* ===============================
         🔥 STEP-SPECIFIC HYDRATION
         =============================== */
      if (step.step_type === "JOINING_DETAILS") {
        // 1️⃣ Populate manager & client (JD-based)
        populateJoiningDetailsMeta(jdId);

        // 2️⃣ Populate form fields (step data)
        if (step.data) {
          hydrateJoiningDetails(step.data);
        }
      }


      if (step.step_type === "PAYROLL") {
        fetchPanFromPreboarding(candidateId, jdId);

        hydratePayrollDetails(
          step.data || {},
          step.status,
          step.documents || []   // 🔥 THIS IS THE FIX
        );
      }


      if (step.step_type === "IT_ACCESS" && step.data) {
        hydrateITAccess(step.data);
      }

      if (step.step_type === "POLICY" && step.data) {
        hydratePolicyAck(step.data, step.status);
      }
    };

    chevronBar.appendChild(chevron);

    /* ===============================
       AUTO-OPEN FIRST VALID STEP
       =============================== */
    if (!opened) {
      if (
        (index === 0 && step.status !== "CLEARED") ||
        (index > 0 &&
          sortedSteps[index - 1].status === "CLEARED" &&
          step.status !== "CLEARED")
      ) {
        chevron.click();
        opened = true;
      }
    }
  });
}

/* =========================================
   ONBOARDING STEP UPDATE (REQUIRED)
   ========================================= */
async function updateOnboardingStep(caseId, stepType) {
  await fetch("/onboarding/step/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      case_id: caseId,
      step_type: stepType,
      status: "CLEARED",
      data: {} // existing form data already handled
    })
  });

  showToast("Step cleared", "success");

  // close modal to force refresh + unlock next step
  document
    .querySelector("#onboardingModal .custom-modal-close")
    .click();
}

function formatOnboardingStepTitle(stepType) {
  return {
    JOINING_DETAILS: "Joining Details",
    PAYROLL: "Compliance & Payroll",
    IT_ACCESS: "IT & Access",
    POLICY: "Policy Acknowledgement",
    FINAL: "Joining Confirmation"
  }[stepType] || stepType;
}

function renderOnboardingStepStub(step, finalSummary = null) {
  switch (step.step_type) {

    case "JOINING_DETAILS":
      return `
        <div class="form-vertical joining-details-form">

          <div class="form-field-block">
            <label>Date of Joining *</label>
            <input type="date" id="jd-doj" />
          </div>

          <div class="form-field-block">
            <label>Work Location *</label>
            <select id="jd-work-location" required>
              <option value="Client Site">Client Site</option>
              <option value="Remote">Remote</option>
              <option value="Hybrid">Hybrid</option>
            </select>
          </div>

          <div class="form-field-block">
            <label>Employment Type *</label>
            <div class="form-field-inline">
              <label>
                <input type="radio" name="jd-employment" value="Full-time">
                Full-time
              </label>
              <label>
                <input type="radio" name="jd-employment" value="Contract">
                Contract
              </label>
              <label>
                <input type="radio" name="jd-employment" value="C2H">
                C2H
              </label>
            </div>
          </div>

          <div class="form-field-block">
            <label>Shift Timings *</label>
            <input type="text" id="jd-shift" placeholder="e.g. 9 AM - 6 PM" />
          </div>

          <div class="form-field-block">
            <label>Reporting Manager *</label>
            <select id="jd-manager" disabled>
              <option value="">Loading...</option>
            </select>
          </div>

          <div class="form-field-block">
            <label>Client Name *</label>
            <input type="text" id="jd-client" disabled />
          </div>

          <div class="form-field-block">
            <label class="form-field-inline">
              <input type="checkbox" id="jd-confirm" />
              Candidate confirms availability to join on DOJ
            </label>
          </div>

          <div class="form-action">
            <button class="btn small" onclick="saveJoiningDetails()">
              Save Joining Details
            </button>
          </div>

        </div>
      `;

    case "PAYROLL":
      return `
      <div class="form-vertical payroll-form">

        <!-- ================= PAN ================= -->
        <div class="form-field-block">
          <label>PAN (from Preboarding)</label>
          <span id="pb-pan" style="font-weight:600;">
            Loading PAN...
          </span>
        </div>

        <!-- ================= Bank Details ================= -->
        <div class="form-field-block">
          <label>Bank Account Holder Name *</label>
          <input type="text" id="pr-holder" />
        </div>

        <div class="form-field-block">
          <label>Bank Name *</label>
          <input type="text" id="pr-bank" />
        </div>

        <div class="form-field-block">
          <label>IFSC Code *</label>
          <input type="text" id="pr-ifsc" />
        </div>

        <div class="form-field-block">
          <label>Account Number *</label>
          <input type="text" id="pr-account" />
        </div>

        <!-- ================= PF Option ================= -->
        <div class="form-field-block">
          <label>PF Option *</label>
          <div class="form-field-inline">
            <label>
              <input type="radio" name="pr-pf" value="OPT_IN">
              Opt-in
            </label>
            <label>
              <input type="radio" name="pr-pf" value="OPT_OUT">
              Opt-out
            </label>
          </div>
        </div>

        <!-- ================= ESIC ================= -->
        <div class="form-field-block">
          <label>ESIC Applicable *</label>
          <div class="form-field-inline">
            <label>
              <input type="radio" name="pr-esic" value="yes">
              Yes
            </label>
            <label>
              <input type="radio" name="pr-esic" value="no">
              No
            </label>
          </div>
        </div>

        <!-- ================= Salary ================= -->
        <div class="form-field-block">
          <label>Salary Structure</label>
          <span id="pr-ctc" style="font-weight:600;">
            CTC: Read-only
          </span>
          <label class="form-field-inline" style="margin-top:6px;">
            <input type="checkbox" id="pr-salary-ack" />
            I acknowledge the salary structure
          </label>
        </div>

        <!-- ================= Bank Proof ================= -->
        <div class="form-field-block">
          <label>Upload Bank Proof *</label>
          <input type="file" id="pr-bank-proof" />
        </div>

        <!-- ================= Action ================= -->
        <div class="form-action">
          <button
            class="btn small"
            onclick="savePayrollDetails()">
            Save Compliance & Payroll
          </button>
        </div>
      </div>
    `;

    case "IT_ACCESS":
      return `
        <div class="form-vertical it-access-form">

          <!-- ================= Official Email ================= -->
          <div class="form-field-block">
            <label>Official Email ID *</label>
            <input
              type="email"
              id="it-email"
              placeholder="auto-generated / assigned"
            />
          </div>

          <!-- ================= Asset Requirement ================= -->
          <div class="form-field-block">
            <label>Asset Required *</label>
            <div class="form-field-inline">
              <label>
                <input
                  type="radio"
                  name="it-asset-required"
                  value="yes">
                Yes
              </label>
              <label>
                <input
                  type="radio"
                  name="it-asset-required"
                  value="no">
                No
              </label>
            </div>
          </div>

          <!-- ================= Asset ID ================= -->
          <div class="form-field-block">
            <label>Asset ID (Laptop)</label>
            <input
              type="text"
              id="it-asset-id"
              placeholder="Required if asset = Yes"
            />
          </div>

          <!-- ================= Access Checklist ================= -->
          <div class="form-field-block">
            <label>Access Checklist *</label>

            <div class="form-field-inline">
              <label>
                <input type="checkbox" id="it-email-created" />
                Official email created
              </label>
            </div>

            <div class="form-field-inline">
              <label>
                <input type="checkbox" id="it-laptop-assigned" />
                Laptop assigned
              </label>
            </div>

            <div class="form-field-inline">
              <label>
                <input type="checkbox" id="it-vpn-enabled" />
                VPN enabled (if required)
              </label>
            </div>

            <div class="form-field-inline">
              <label>
                <input type="checkbox" id="it-client-tools" />
                Client tools access granted
              </label>
            </div>
          </div>

          <!-- ================= Action ================= -->
          <div class="form-action">
            <button
              class="btn small"
              onclick="saveITAccess()">
              Save IT & Access
            </button>
          </div>
        </div>
      `;


    case "POLICY":
      return `
        <div class="form-vertical policy-ack-form">

        <!-- ================= Instructions ================= -->
          <div class="form-field-block">
            <p style="color:#475569;font-size:0.85rem;">
              Please review and accept the following agreements to proceed
              with onboarding. Your acceptance is mandatory.
            </p>
          </div>

        <!-- ================= Offer Letter ================= -->
          <div class="form-field-block">
            <label class="form-field-inline">
              <input type="checkbox" id="pl-offer" />
              I accept the <strong>Final Offer Letter</strong>
            </label>
          </div>

        <!-- ================= NDA ================= -->
          <div class="form-field-block">
            <label class="form-field-inline">
              <input type="checkbox" id="pl-nda" />
              I have read and signed the <strong>NDA</strong>
            </label>
          </div>

        <!-- ================= Employment Agreement ================= -->
          <div class="form-field-block">
            <label class="form-field-inline">
              <input type="checkbox" id="pl-employment" />
              I agree to the <strong>Employment Agreement</strong>
            </label>
          </div>

        <!-- ================= Client Policy ================= -->
          <div class="form-field-block">
            <label class="form-field-inline">
              <input type="checkbox" id="pl-client-policy" />
              I accept the <strong>Client Policy</strong> (if applicable)
            </label>
          </div>

        <!-- ================= Action ================= -->
          <div class="form-action">
            <button
              class="btn small"
              onclick="savePolicyAck(window.currentOnboardingCaseId)">
              Accept & Continue
            </button>
          </div>

        <!-- ================= Legal Note ================= -->
          <div class="form-field-block">
            <p style="font-size:12px;color:#64748b;">
              Acceptance is legally binding and logged with timestamp
              and IP address for audit purposes.
            </p>
          </div>
        </div>
      `;


    case "FINAL": {
      const s = finalSummary || {};
      const j = s.joining || {};
      const p = s.payroll || {};
      const it = s.it || {};
      const pol = s.policy || {};

      const field = (label, value) => `
        <div class="summary-field">
          <div class="summary-label">${label}</div>
          <div class="summary-value">${value ?? "—"}</div>
        </div>
      `;

      return `
        <div class="final-summary-container">

          <!-- HEADER -->
          <div class="final-summary-header">
            <h3>✅ Final Onboarding Review</h3>
            <p>Please verify all onboarding details before confirming joining.</p>
          </div>

          <!-- JOINING DETAILS -->
          <div class="summary-card">
            <h4>Joining Details</h4>
            <div class="summary-grid">
              ${field("Date of Joining", j.date_of_joining)}
              ${field("Work Location", j.work_location)}
              ${field("Employment Type", j.employment_type)}
              ${field("Shift Timings", j.shift_timings)}
              ${field("Reporting Manager", j.reporting_manager)}
              ${field("Client Name", j.client_name)}
              ${field("Candidate Confirmed DOJ", j.confirm_availability ? "Yes" : "No")}
            </div>
          </div>

          <!-- COMPLIANCE & PAYROLL -->
          <div class="summary-card">
            <h4>Compliance & Payroll</h4>
            <div class="summary-grid">
              ${field("PAN Verified", p.pan_verified ? "Yes" : "No")}
              ${field("Bank Holder Name", p.account_holder)}
              ${field("Bank Name", p.bank_name)}
              ${field("Account Number", p.account_number)}
              ${field("IFSC Code", p.ifsc)}
              ${field("PF Option", p.pf_option)}
              ${field("ESIC Applicable", p.esic_applicable ? "Yes" : "No")}
              ${field("CTC", p.ctc)}
              ${field("Salary Acknowledged", p.salary_ack ? "Yes" : "No")}
            </div>
          </div>

          <!-- IT & ACCESS -->
          <div class="summary-card">
            <h4>IT & Access</h4>
            <div class="summary-grid">
              ${field("Official Email", it.official_email)}
              ${field("Asset Required", it.asset_required ? "Yes" : "No")}
              ${field("Asset ID", it.asset_id)}
              ${field("Email Created", it.email_created ? "Yes" : "No")}
              ${field("Laptop Assigned", it.laptop_assigned ? "Yes" : "No")}
              ${field("VPN Enabled", it.vpn_enabled ? "Yes" : "No")}
              ${field("Client Tools Access", it.client_tools_access ? "Yes" : "No")}
            </div>
          </div>

          <!-- POLICY -->
          <div class="summary-card">
            <h4>Policy Acknowledgement</h4>
            <div class="summary-grid">
              ${field("Offer Letter Accepted", pol.offer_letter_accepted ? "Yes" : "No")}
              ${field("NDA Signed", pol.nda_signed ? "Yes" : "No")}
              ${field("Employment Agreement", pol.employment_agreement_signed ? "Yes" : "No")}
              ${field("Client Policy Accepted", pol.client_policy_accepted ? "Yes" : "No")}
            </div>
          </div>

          <!-- ACTIONS -->
          <div class="final-summary-actions">
            <button class="btn success"
              onclick="confirmJoining(window.currentOnboardingCaseId)">
              Confirm Joining
            </button>

            <button class="btn danger"
              onclick="markNoShow(window.currentOnboardingCaseId)">
              Mark No-Show
            </button>
          </div>
        </div>
      `;
    }


    default:
      return `<div style="color:#64748b;">Unknown onboarding step</div>`;
  }
}

function saveJoiningDetails() {
  const caseId = window.currentOnboardingCaseId;
  if (!caseId) {
    alert("Onboarding case not initialized");
    return;
  }

  const payload = {
    date_of_joining: document.getElementById("jd-doj").value,
    work_location: document.getElementById("jd-work-location").value,
    employment_type: document.querySelector('input[name="jd-employment"]:checked')?.value,
    shift_timings: document.getElementById("jd-shift").value,
    reporting_manager_id: Number(document.getElementById("jd-manager").value),
    client_id: Number(document.getElementById("jd-client").dataset.clientId),
    candidate_confirmed: document.getElementById("jd-confirm").checked
  };

  console.log("🚀 FINAL Joining payload", payload);

  // HARD VALIDATION
  for (const [k, v] of Object.entries(payload)) {
    if (v === undefined || v === null || v === "" || (k === "candidate_confirmed" && v !== true)) {
      console.error("❌ Invalid field:", k, v);
      alert("Please complete all required fields");
      return;
    }
  }

  fetch(`/onboarding/step/update?case_id=${caseId}&step_type=JOINING_DETAILS&status=CLEARED`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)   // 🔥 NO WRAPPER
  })
  .then(res => {
    if (!res.ok) return res.text().then(t => { throw new Error(t); });
    return res.json();
  })
  .then(() => {
    alert("Joining Details saved successfully");
    closeOnboardingModal();
  })
  .catch(err => {
    console.error("❌ BACKEND ERROR:", err);
    alert("Cannot clear Joining Details. Check all fields.");
  });
}

function savePayrollDetails() {
  const caseId = window.currentOnboardingCaseId;
  if (!caseId) {
    alert("Onboarding case not initialized");
    return;
  }

  const fileInput = document.getElementById("pr-bank-proof");
  if (!fileInput.files.length) {
    alert("Bank proof is mandatory");
    return;
  }

  const payload = {
    bank_account_holder: document.getElementById("pr-holder").value,
    bank_name: document.getElementById("pr-bank").value,
    ifsc_code: document.getElementById("pr-ifsc").value,
    account_number: document.getElementById("pr-account").value,
    pf_option: document.querySelector('input[name="pr-pf"]:checked')?.value,
    esic_applicable:
      document.querySelector('input[name="pr-esic"]:checked')?.value === "yes",
    salary_acknowledged: document.getElementById("pr-salary-ack").checked
  };

  for (const [k, v] of Object.entries(payload)) {
    if (v === undefined || v === null || v === "") {
      alert("Please complete all payroll fields");
      return;
    }
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  fetch(
    `/onboarding/document/upload?case_id=${caseId}&step_type=PAYROLL&doc_type=BANK_PROOF`,
    { method: "POST", body: formData }
  )
    .then(res => {
      if (!res.ok) throw new Error("Bank proof upload failed");
      return res.json();
    })
    .then(() => {
      return fetch(
        `/onboarding/step/update?case_id=${caseId}&step_type=PAYROLL&status=CLEARED`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        }
      );
    })
    .then(res => {
      if (!res.ok) throw new Error("Payroll validation failed");
      return res.json();
    })
    .then(() => {
      alert("Compliance & Payroll saved successfully");
    })
    .catch(err => {
      console.error("❌ Payroll save failed:", err);
      alert("Payroll step cannot be cleared. Check all fields.");
    });
}

function saveITAccess() {
  const caseId = window.currentOnboardingCaseId;

  if (!caseId) {
    alert("Onboarding case not initialized");
    return;
  }

  const assetRequired =
    document.querySelector('input[name="it-asset-required"]:checked')?.value;

  const data = {
    official_email: document.getElementById("it-email").value,
    asset_required: assetRequired === "yes",
    asset_id: document.getElementById("it-asset-id").value || null,
    email_created: document.getElementById("it-email-created").checked,
    laptop_assigned: document.getElementById("it-laptop-assigned").checked,
    vpn_enabled: document.getElementById("it-vpn-enabled").checked,
    client_tools_access: document.getElementById("it-client-tools").checked
  };

  // 🔒 HARD FRONTEND GUARDS
  if (!data.official_email) {
    alert("Official email is mandatory");
    return;
  }

  if (data.asset_required && !data.asset_id) {
    alert("Asset ID is mandatory when asset is required");
    return;
  }

  if (
    !data.email_created ||
    !data.client_tools_access ||
    (data.asset_required && !data.laptop_assigned)
  ) {
    alert("All required access must be completed");
    return;
  }

  fetch(
    `/onboarding/step/update?case_id=${caseId}&step_type=IT_ACCESS&status=CLEARED`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    }
  )
    .then(res => {
      if (!res.ok) throw new Error("IT access validation failed");
      alert("IT & Access provisioned");
      closeOnboardingModal();
    })
    .catch(err => {
      console.error(err);
      alert("Cannot clear IT & Access step");
    });
}

function savePolicyAck() {
  // ✅ SINGLE SOURCE OF TRUTH (same as other steps)
  const caseId = window.currentOnboardingCaseId;

  if (!caseId) {
    console.error("❌ Policy Ack failed: caseId missing");
    alert("Internal error: onboarding case not loaded. Please reopen onboarding.");
    return;
  }

  const data = {
    offer_letter_accepted: document.getElementById("pl-offer")?.checked,
    nda_signed: document.getElementById("pl-nda")?.checked,
    employment_agreement_signed:
      document.getElementById("pl-employment")?.checked,
    client_policy_accepted:
      document.getElementById("pl-client-policy")?.checked,
    acceptance_meta: {
      timestamp: new Date().toISOString()
    }
  };

  // 🔒 HARD FRONTEND VALIDATION
  if (
    !data.offer_letter_accepted ||
    !data.nda_signed ||
    !data.employment_agreement_signed ||
    !data.client_policy_accepted
  ) {
    alert("All agreements must be accepted");
    return;
  }

  fetch(
    `/onboarding/step/update?case_id=${caseId}&step_type=POLICY&status=CLEARED`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    }
  )
    .then(res => {
      if (!res.ok) throw new Error("Policy validation failed");
      alert("Policy accepted successfully");
      closeOnboardingModal();
    })
    .catch(err => {
      console.error(err);
      alert("Cannot complete policy acknowledgement");
    });
}

function buildOnboardingSummary(steps) {
  const get = type =>
    steps.find(s => s.step_type === type)?.data || {};

  const joining = get("JOINING_DETAILS");
  const payroll = get("PAYROLL");
  const it = get("IT_ACCESS");
  const policy = get("POLICY");

  return {
    preboarding_status: "CLEARED", // already enforced earlier

    doj: joining.date_of_joining || "—",
    work_location: joining.work_location || "—",
    employment_type: joining.employment_type || "—",

    salary: payroll.ctc || "—",
    bank_verified: !!payroll.account_number,

    asset_assigned:
      it.asset_required === "yes" && !!it.asset_id,

    policy_accepted:
      !!policy.offer_letter_accepted &&
      !!policy.nda_signed &&
      !!policy.employment_agreement_signed &&
      !!policy.client_policy_accepted
  };
}

function confirmJoining(caseId) {
  if (!confirm("Confirm candidate has joined? This cannot be undone.")) return;

  fetch(`/onboarding/finalize?case_id=${caseId}&action=CONFIRM`, {
    method: "POST"
  })
    .then(res => {
      if (!res.ok) throw new Error("Finalize failed");
      alert("Candidate marked as HIRED");
      closeOnboardingModal();
      location.reload();
    })
    .catch(err => {
      console.error(err);
      alert("Cannot confirm joining. Ensure all steps are CLEARED.");
    });
}

function markNoShow(caseId) {
  if (!confirm("Mark candidate as NO-SHOW? This will reject the candidate.")) return;

  fetch(`/onboarding/finalize?case_id=${caseId}&action=NO_SHOW`, {
    method: "POST"
  })
    .then(res => {
      if (!res.ok) throw new Error("No-show failed");
      alert("Candidate marked as REJECTED");
      closeOnboardingModal();
      location.reload();
    })
    .catch(err => {
      console.error(err);
      alert("Cannot mark no-show.");
    });
}

function populateJoiningDetailsMeta(jdId) {
  fetch(`/onboarding/joining-details/meta?jd_id=${jdId}`)
    .then(res => res.json())
    .then(data => {
      // Client
      const clientInput = document.getElementById("jd-client");
      clientInput.value = data.client.name;
      clientInput.dataset.clientId = data.client.id;

      // Manager
      const managerSelect = document.getElementById("jd-manager");
      managerSelect.innerHTML = `
        <option value="${data.manager.id}">
          ${data.manager.name}
        </option>
      `;
      managerSelect.value = data.manager.id;
    })
    .catch(err => {
      console.error(err);
      alert("Unable to load client/manager details");
    });
}

function fetchPanFromPreboarding(candidateId, jdId) {
  fetch(`/onboarding/payroll/pan?candidate_id=${candidateId}&jd_id=${jdId}`)
    .then(res => {
      if (!res.ok) throw new Error("PAN not found");
      return res.json();
    })
    .then(data => {
      const el = document.getElementById("pb-pan");
      if (!el) return;

      el.innerHTML = `
        <a href="${data.file_url}" target="_blank"
           class="btn btn-sm btn-outline-primary">
          View PAN File
        </a>
      `;
    })
    .catch(() => {
      const el = document.getElementById("pb-pan");
      if (el) {
        el.innerHTML =
          "<span style='color:#64748b;'>PAN not available</span>";
      }
    });
}

async function fetchBankProof(caseId) {
  try {
    const res = await fetch(
      `/onboarding/documents?case_id=${caseId}&doc_type=BANK_PROOF`
    );

    if (!res.ok) return;

    const doc = await res.json();
    if (!doc?.file_url) return;

    renderBankProofView(doc);
  } catch (e) {
    console.error("Bank proof fetch failed", e);
  }
}


async function handleStepAction(stepId, newStatus) {
  try {
    // ================= VALIDATION FIRST =================
    if (newStatus === "CLEARED") {
      const docs = await fetch(`/preboarding/documents/${stepId}`)
        .then(r => r.json());

      const stepBtn = document.querySelector(
        `.preboarding-step-btn[data-step-id="${stepId}"]`
      );

      if (!stepBtn) {
        showToast("Step metadata not found", "error");
        return;
      }

      const stepType = stepBtn.dataset.stepType;
      const required = REQUIRED_DOCS[stepType] || [];
      const uploadedTypes = docs.map(d => d.doc_type);

      const missing = required.filter(
        r => !uploadedTypes.includes(r)
      );

      if (missing.length) {
        showToast(
          "Upload all required documents before marking Cleared",
          "warning",
          3000
        );
        return;
      }
    }

    // ================= BACKEND UPDATE =================
    const res = await fetch("/preboarding/step/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        step_id: stepId,
        status: newStatus
      })
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || "Step update failed", "error", 3000);
      return;
    }

    const data = await res.json();

    // ================= UI UPDATES =================

    // 1️⃣ Update dataset status
    const statusEl = document.querySelector(
      `.preboarding-step-btn[data-step-id="${stepId}"]`
    );
    if (statusEl) {
      statusEl.setAttribute("data-step-status", data.step_status);
    }

    // 2️⃣ Update chevron color
    updatePreboardingStepUI(stepId, data.step_status);

    // 3️⃣ Update final status text
    const finalEl = document.getElementById("preboardingFinalStatus");
    if (finalEl) {
      finalEl.innerText = data.final_status;
    }

    // 4️⃣ Re-lock / unlock chevrons
    refreshPreboardingChevronLocks();

    // 5️⃣ Success feedback
    showToast(`Step marked ${newStatus}`, "success");

    // ================= 🔥 AUTO-MOVE TO NEXT STEP =================
    if (newStatus === "CLEARED") {
      const steps = Array.from(
        document.querySelectorAll(".preboarding-step-btn")
      );

      const currentIndex = steps.findIndex(
        btn => btn.dataset.stepId === stepId
      );

      if (currentIndex !== -1 && currentIndex < steps.length - 1) {
        const nextBtn = steps[currentIndex + 1];

        if (!nextBtn.disabled) {
          const nextStepId = nextBtn.dataset.stepId;
          const nextStepType = nextBtn.dataset.stepType;
          const nextStepStatus = nextBtn.dataset.stepStatus;

          setTimeout(() => {
            expandPreboardingStep(
              nextStepId,
              nextStepType,
              nextStepStatus
            );

            // visual active state
            steps.forEach(b => b.classList.remove("active"));
            nextBtn.classList.add("active");

            // ensure visibility
            document
              .getElementById("preboardingStepContent")
              ?.scrollIntoView({ behavior: "smooth", block: "start" });
          }, 300);
        }
      }
    }

  } catch (err) {
    console.error(err);
    showToast("Something went wrong while updating step", "error");
  }
}

async function toggleUserEdit(stepId, allow) {
  try {
    const res = await fetch("/preboarding/step/allow-user-edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ step_id: stepId, allow })
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || "Failed to update user access", "error");
      return;
    }

    // 🔐 UPDATE SINGLE SOURCE OF TRUTH
    window.stepEditPermissions = window.stepEditPermissions || {};
    window.stepEditPermissions[stepId] = allow;

    // 🔥 FORCE FULL STEP RE-RENDER
    const stepBtn = document.querySelector(
      `.preboarding-step-btn[data-step-id="${stepId}"]`
    );

    if (stepBtn) {
      const stepType = stepBtn.dataset.stepType;
      const stepStatus = stepBtn.dataset.stepStatus;

      const docs = await loadDocumentsForStep(stepId);

      const formArea = document.getElementById("stepFormArea");
      if (formArea) {
        formArea.innerHTML = renderStepForm(
          stepType,
          stepId,
          stepStatus,
          docs
        );
      }
    }

    showToast(
      allow
        ? "User can now edit locked documents"
        : "User edit access revoked",
      "success"
    );

  } catch (err) {
    console.error(err);
    showToast("Admin override failed", "error");
  }
}


function updatePreboardingStepUI(stepId, status) {
  const btn = document.querySelector(
    `.preboarding-step-btn[data-step-id="${stepId}"]`
  );
  if (!btn) return;

  btn.setAttribute("data-step-status", status);

  if (status === "CLEARED") {
    btn.style.background = "#d1fae5";
    btn.style.color = "#065f46";
  } else if (status === "FAILED") {
    btn.style.background = "#fee2e2";
    btn.style.color = "#991b1b";
  } else {
    btn.style.background = "#fef3c7";
    btn.style.color = "#92400e";
  }

  // Also update the text inside step panel
  const statusText = document.querySelector(
    "#preboardingStepContent div:nth-child(2)"
  );
  if (statusText) {
    statusText.innerHTML = `<strong>Status:</strong> ${status}`;
  }
}

function refreshPreboardingChevronLocks() {
  const buttons = Array.from(
    document.querySelectorAll(".preboarding-step-btn")
  );

  let failedSeen = false;

  buttons.forEach(btn => {
    const status = btn.getAttribute("data-step-status");

    if (failedSeen) {
      btn.disabled = true;
      btn.style.opacity = "0.45";
      btn.style.cursor = "not-allowed";
      return;
    }

    btn.disabled = false;
    btn.style.opacity = "1";
    btn.style.cursor = "pointer";

    if (status === "FAILED") {
      failedSeen = true;
    }
  });
}


async function completePreboarding() {
  try {
    const res = await fetch("/preboarding/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        case_id: window.currentPreboardingCaseId,
      }),
    });

    if (!res.ok) {
      alert(await res.text());
      return;
    }

    alert("Preboarding completed successfully");
    window.location.reload();

  } catch (err) {
    console.error("Preboarding completion failed:", err);
  }
}
