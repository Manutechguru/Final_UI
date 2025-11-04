// static/js/gmail_compose.js
document.addEventListener("DOMContentLoaded", () => {
  const init = window.__GMAIL_INIT || {};
  const toEl = document.getElementById('to');
  const ccEl = document.getElementById('cc');
  const bccEl = document.getElementById('bcc');
  const subjectEl = document.getElementById('subject');
  const wysiwyg = document.getElementById('wysiwyg');
  const bodyTextarea = document.getElementById('bodyTextarea');
  const sendBtn = document.getElementById('sendBtn');
  const authorizeBtn = document.getElementById('authorizeBtn');
  const attachBtn = document.getElementById('attachBtn');
  const fileInput = document.getElementById('fileInput');
  const attachList = document.getElementById('attachList');
  const toggleCcBtn = document.getElementById('toggleCcBtn');
  const toggleBccBtn = document.getElementById('toggleBccBtn');
  const ccBccArea = document.getElementById('ccBccArea');
  const emojiBtn = document.getElementById('emojiBtn');
  let emojiPicker = document.getElementById('emojiPicker'); // we may move this to body
  const fontSelect = document.getElementById('fontSelect');
  const fontSizeSelect = document.getElementById('fontSizeSelect');
  const templateSelect = document.getElementById('templateSelect');
  const previewGrid = document.getElementById('previewGrid');
  const draftTimeEl = document.getElementById('draftTime');
  const discardBtn = document.getElementById('discardBtn');

  // optionally set initial values
  if (init.from_email) {
    const f = document.getElementById('from_email');
    if (f) f.value = init.from_email;
  }
  if (init.to_emails && toEl && !toEl.value) toEl.value = init.to_emails;
  if (init.jd_id) {
    const hid = document.getElementById('init_jd_id');
    if (hid) hid.value = init.jd_id;
  }
  if (init.candidate_ids) {
    const hid2 = document.getElementById('init_candidate_ids');
    if (hid2) hid2.value = init.candidate_ids;
  }

  // ---- Preview rendering ----
  function renderPreviews() {
    if (!previewGrid) return;
    previewGrid.innerHTML = "";

    // JD should be shown only for candidates mode (explicitly requested)
    const mode = (document.getElementById('init_mode') && document.getElementById('init_mode').value) || init.mode || 'candidates';
    const jdLink = (init.jd_link || "").trim();
    const previewLinks = (init.preview_links || []);

    // show JD only when mode === 'candidates' and jdLink exists
    if (mode === 'candidates' && jdLink) {
      const card = document.createElement('div');
      card.className = 'preview-card';
      card.innerHTML = `<div style="font-weight:700;margin-bottom:6px">Job Description</div>
        <iframe src="${escapeAttr(makePreviewUrl(jdLink))}" sandbox="allow-scripts allow-same-origin allow-popups" loading="lazy"></iframe>`;
      previewGrid.appendChild(card);
    }

    // Resumes / preview links shown for clients or candidates as provided
    if (Array.isArray(previewLinks) && previewLinks.length) {
      previewLinks.forEach((l, i) => {
        if (!l) return;
        const card = document.createElement('div');
        card.className = 'preview-card';
        card.innerHTML = `<div style="font-weight:700;margin-bottom:6px">Resume ${i+1}</div>
          <iframe src="${escapeAttr(makePreviewUrl(l))}" sandbox="allow-scripts allow-same-origin allow-popups" loading="lazy"></iframe>`;
        previewGrid.appendChild(card);
      });
    }
  }

  function makePreviewUrl(url) {
    if (!url) return '';
    try {
      const m = url.match(/\/d\/([^/]+)\//);
      if (m && m[1]) return `https://drive.google.com/file/d/${m[1]}/preview`;
      const m2 = url.match(/document\/d\/([^/]+)\//);
      if (m2 && m2[1]) return `https://docs.google.com/document/d/${m2[1]}/preview`;
      const m3 = url.match(/spreadsheets\/d\/([^/]+)\//);
      if (m3 && m3[1]) return `https://docs.google.com/spreadsheets/d/${m3[1]}/preview`;
      const m4 = url.match(/presentation\/d\/([^/]+)\//);
      if (m4 && m4[1]) return `https://docs.google.com/presentation/d/${m4[1]}/preview`;
      return url;
    } catch (e) {
      return url;
    }
  }

  function escapeAttr(s) {
    if (!s) return '';
    return s.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  renderPreviews();

  // ---- toolbar delegation ----
  document.addEventListener('click', (ev) => {
    const btn = ev.target.closest && ev.target.closest('button[data-cmd]');
    if (!btn) return;
    ev.preventDefault();
    const cmd = btn.getAttribute('data-cmd');
    if (cmd === 'link') {
      const url = prompt('Enter URL', 'https://');
      if (url) execCommand('createLink', url);
    } else if (cmd === 'bold') execCommand('bold');
    else if (cmd === 'italic') execCommand('italic');
    else if (cmd === 'underline') execCommand('underline');
    else if (cmd === 'ul') execCommand('insertUnorderedList');
    else if (cmd === 'ol') execCommand('insertOrderedList');
  }, true);

  function execCommand(cmd, val=null) {
    try {
      restoreSelection();
      document.execCommand(cmd, false, val);
      if (wysiwyg) wysiwyg.focus();
      saveSelection();
    } catch (e) { console.warn('execCommand failed', cmd, e); }
  }

  // ---- font controls ----
  if (fontSelect) fontSelect.addEventListener('change', () => { if (wysiwyg) wysiwyg.style.fontFamily = fontSelect.value; });
  if (fontSizeSelect) fontSizeSelect.addEventListener('change', () => { if (wysiwyg) wysiwyg.style.fontSize = fontSizeSelect.value; });

  // ---- emoji picker: build + controlled show/hide ----
  const EMOJIS = ["😀","😁","😂","🤣","😊","😉","😍","😘","😎","🤝","👍","👎","🙏","💪","🎉","🔥","✨","💡","📎","📩","📝","🚀","🔒","💼","📅","✅","❌","🔔","🕒","📊"];

  // If emojiPicker exists in DOM, move it to body to avoid clipping by parent overflow
  if (emojiPicker) {
    try {
      // move node to body to avoid clipping inside overflow-hidden flex containers
      document.body.appendChild(emojiPicker);
    } catch (e) {
      // ignore if fail; remain in place
    }
  }

  if (emojiPicker) {
    // build picker content (idempotent)
    emojiPicker.innerHTML = '';
    EMOJIS.forEach(e => {
      const b = document.createElement('button');
      b.type='button';
      b.className='emoji-btn';
      b.textContent = e;
      b.title = e;
      b.addEventListener('click', (ev) => {
        ev.preventDefault();
        // restore selection (if saved) then insert then hide
        restoreSelection();
        insertAtCaret(e);
        hideEmoji();
      });
      emojiPicker.appendChild(b);
    });

    // ensure it's hidden on load (force to avoid CSS collisions)
    emojiPicker.classList.remove('show');
    emojiPicker.setAttribute('aria-hidden','true');
    emojiPicker.style.display = 'none';
    emojiPicker.style.position = 'absolute';
    emojiPicker.style.zIndex = '9999';
    // small safety defaults (these will be overridden by CSS but ensure visible styled)
    emojiPicker.style.background = '#fff';
    emojiPicker.style.border = '1px solid #e2e8f0';
    emojiPicker.style.padding = '8px';
    emojiPicker.style.borderRadius = '8px';
    emojiPicker.style.boxShadow = '0 6px 20px rgba(2,6,23,0.08)';
  }

  // saved selection range for insertion & execCommand
  let savedRange = null;
  function saveSelection() {
    try {
      const sel = window.getSelection();
      if (!sel) return;
      if (sel.rangeCount > 0) savedRange = sel.getRangeAt(0).cloneRange();
    } catch (e) { /* ignore */ }
  }
  function restoreSelection() {
    try {
      if (!savedRange) return;
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(savedRange);
    } catch (e) { /* ignore */ }
  }

  // position the emoji picker near the emoji button (keeps within viewport)
  function positionEmoji() {
    if (!emojiBtn || !emojiPicker) return;
    const rect = emojiBtn.getBoundingClientRect();
    const picker = emojiPicker;
    const pw = picker.offsetWidth || 260;
    const ph = picker.offsetHeight || 220;

    // compute top (below button)
    const top = rect.bottom + window.scrollY + 8;

    // try to right-align the picker to the button's right edge, fall back to left edge
    let left = rect.right + window.scrollX - pw;
    if (left < 8) left = rect.left + window.scrollX;
    // ensure it doesn't overflow viewport on the right
    const maxLeft = window.scrollX + window.innerWidth - pw - 8;
    if (left > maxLeft) left = Math.max(8 + window.scrollX, maxLeft);

    picker.style.top = top + 'px';
    picker.style.left = left + 'px';
  }

  function showEmoji() {
    if (!emojiPicker) return;
    positionEmoji();
    emojiPicker.classList.add('show');
    emojiPicker.setAttribute('aria-hidden','false');
    emojiPicker.style.display = 'grid';
    // ensure grid layout if CSS uses grid
    emojiPicker.style.gridTemplateColumns = emojiPicker.style.gridTemplateColumns || 'repeat(8, 1fr)';
  }
  function hideEmoji() {
    if (!emojiPicker) return;
    emojiPicker.classList.remove('show');
    emojiPicker.setAttribute('aria-hidden','true');
    emojiPicker.style.display = 'none';
  }

  // emoji button toggling: show on click, hide on second click
  if (emojiBtn) {
    emojiBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      // Save caret/selection for insertion after picker click
      saveSelection();
      if (emojiPicker && emojiPicker.classList.contains('show')) {
        hideEmoji();
      } else {
        showEmoji();
      }
    });
  }

  // hide when clicking outside or esc
  document.addEventListener('click', (ev) => {
    if (!emojiPicker) return;
    // if the click is not inside picker and not the emoji icon, hide
    if (!emojiPicker.contains(ev.target) && ev.target !== emojiBtn && !ev.target.closest('#emojiBtn')) {
      hideEmoji();
    }
  });
  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') hideEmoji(); });

  // insertion helper
  function insertAtCaret(text) {
    try {
      restoreSelection();
      if (!wysiwyg) return;
      wysiwyg.focus();
      const sel = window.getSelection();
      if (!sel || !sel.rangeCount) {
        // append at end if no selection
        wysiwyg.innerHTML += text;
        // update saved selection to end
        const range = document.createRange();
        range.selectNodeContents(wysiwyg);
        range.collapse(false);
        savedRange = range.cloneRange();
        saveSelection();
        return;
      }
      const range = sel.getRangeAt(0);
      range.deleteContents();
      const node = document.createTextNode(text);
      range.insertNode(node);
      // move caret after inserted node
      range.setStartAfter(node);
      range.setEndAfter(node);
      sel.removeAllRanges();
      sel.addRange(range);
      // save current selection for future commands
      savedRange = range.cloneRange();
      saveSelection();
    } catch (e) { console.warn('insertAtCaret', e); }
  }

  // wire up wysiwyg selection saving so commands work reliably
  if (wysiwyg) ['mouseup','keyup','keydown','focus','click','input'].forEach(evt => { wysiwyg.addEventListener(evt, saveSelection); });

  // ---- attachments UI ----
  if (attachBtn && fileInput) {
    attachBtn.addEventListener('click', (e) => { e.preventDefault(); fileInput.click(); });
    fileInput.addEventListener('change', (ev) => {
      attachList.innerHTML = '';
      const files = Array.from(fileInput.files || []);
      files.forEach(f => {
        const pill = document.createElement('span');
        pill.className = 'attachment-pill';
        pill.innerHTML = `<i class="fas fa-file"></i>&nbsp;${escapeHtml(f.name)}`;
        attachList.appendChild(pill);
      });
    });
  }

  function escapeHtml(s) {
    if (!s) return '';
    return s.replace(/[&<>"']/g, function(m) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]; });
  }

  // ---- cc/bcc toggles ----
  if (toggleCcBtn) toggleCcBtn.addEventListener('click', () => { if (ccBccArea) ccBccArea.style.display = ccBccArea.style.display === 'flex' ? 'none' : 'flex'; });
  if (toggleBccBtn) toggleBccBtn.addEventListener('click', () => { if (ccBccArea) ccBccArea.style.display = ccBccArea.style.display === 'flex' ? 'none' : 'flex'; });

  // ---- template insertion ----
  if (templateSelect) templateSelect.addEventListener('change', function(){
    const v = this.value;
    if (!v) return;

    const templates = {
  // ---- Default ----
  logout_update: {
    subject: "Logout Update",
    body: `<p>Dear Team,</p>
           <p>Today’s update:</p>
           <ul><li>Item 1</li><li>Item 2</li></ul>
           <p>Regards,<br>HR Team</p>`
  },

  // ---- Candidate Templates ----
  application_received: {
    subject: "Application Received - [Job Title]",
    body: `<p>Dear [Candidate Name],</p>
           <p>We’ve received your application for the <strong>[Job Title]</strong> position at <strong>[Company Name]</strong>. Our recruitment team will review your profile and get back to you soon.</p>
           <p>Thank you for your interest in joining us!</p>
           <p>Best regards,<br>[Your Name]<br>[Your Company]</p>`
  },

  interview_scheduled: {
    subject: "Interview Scheduled - [Job Title]",
    body: `<p>Dear [Candidate Name],</p>
           <p>We’re pleased to inform you that your interview for the <strong>[Job Title]</strong> position has been scheduled.</p>
           <ul>
             <li><strong>Date:</strong> [Interview Date]</li>
             <li><strong>Time:</strong> [Interview Time]</li>
             <li><strong>Mode:</strong> [Online/Offline]</li>
             <li><strong>Location:</strong> [Address or Google Meet link]</li>
           </ul>
           <p>Please confirm your availability.</p>
           <p>Regards,<br>[Your Name]<br>[Your Company]</p>`
  },

  shortlisted_notification: {
    subject: "Shortlisted for Next Round - [Job Title]",
    body: `<p>Dear [Candidate Name],</p>
           <p>Congratulations! You’ve been shortlisted for the next round of interviews for the <strong>[Job Title]</strong> role.</p>
           <p>We’ll reach out soon with the schedule.</p>
           <p>Best regards,<br>[Your Name]<br>[Your Company]</p>`
  },

  offer_letter: {
    subject: "Offer Letter - [Job Title]",
    body: `<p>Dear [Candidate Name],</p>
           <p>We’re delighted to offer you the position of <strong>[Job Title]</strong> at <strong>[Company Name]</strong>.</p>
           <p>Please find your offer letter attached for your review.</p>
           <p>Congratulations and welcome aboard!</p>
           <p>Warm regards,<br>[Your Name]<br>[Your Company]</p>`
  },

  rejection_mail: {
    subject: "Application Update - [Job Title]",
    body: `<p>Dear [Candidate Name],</p>
           <p>Thank you for taking the time to apply for the <strong>[Job Title]</strong> position.</p>
           <p>After careful consideration, we’ve decided to move forward with other candidates at this time.</p>
           <p>We appreciate your interest and encourage you to apply for future opportunities.</p>
           <p>Wishing you all the best,<br>[Your Name]<br>[Your Company]</p>`
  },

  follow_up: {
    subject: "Follow-Up on Interview Status",
    body: `<p>Dear [Candidate Name],</p>
           <p>Hope you’re doing well. This is a friendly reminder regarding your interview status for the <strong>[Job Title]</strong> role.</p>
           <p>Please share any updates from your end.</p>
           <p>Best regards,<br>[Your Name]<br>[Your Company]</p>`
  },

  // ---- Recruiter Templates ----
  new_requirement: {
    subject: "New Hiring Requirement - [Position Title]",
    body: `<p>Dear [Recruiter Name],</p>
           <p>We have a new opening for <strong>[Position Title]</strong> at <strong>[Company Name]</strong>.</p>
           <p><strong>Details:</strong></p>
           <ul>
             <li>Experience: [X Years]</li>
             <li>Location: [City]</li>
             <li>Budget: [CTC Range]</li>
           </ul>
           <p>Please start sourcing candidates accordingly.</p>
           <p>Regards,<br>[Your Name]<br>[Your Company]</p>`
  },

  candidate_update: {
    subject: "Candidate Status Update",
    body: `<p>Dear [Recruiter Name],</p>
           <p>Please find below the update on candidate submissions:</p>
           <ul>
             <li>Profiles Shared: [X]</li>
             <li>Shortlisted: [Y]</li>
             <li>Feedback Pending: [Z]</li>
           </ul>
           <p>Best,<br>[Your Name]</p>`
  },

  jd_clarification: {
    subject: "Clarification Required - Job Description",
    body: `<p>Dear [Recruiter Name],</p>
           <p>Kindly clarify the following details for the <strong>[Job Title]</strong> role:</p>
           <ul><li>[Query 1]</li><li>[Query 2]</li></ul>
           <p>Once received, we can proceed with accurate sourcing.</p>
           <p>Regards,<br>[Your Name]<br>[Your Company]</p>`
  },

  joining_confirmation: {
    subject: "Joining Confirmation - [Candidate Name]",
    body: `<p>Dear [Recruiter Name],</p>
           <p>This is to confirm that <strong>[Candidate Name]</strong> has accepted the offer for <strong>[Job Title]</strong> and will be joining on <strong>[Joining Date]</strong>.</p>
           <p>Best regards,<br>[Your Name]<br>[Your Company]</p>`
  },

  thank_you_recruiter: {
    subject: "Thank You for Your Support",
    body: `<p>Dear [Recruiter Name],</p>
           <p>Thank you for your assistance and continuous support throughout the recruitment process.</p>
           <p>Looking forward to future collaboration!</p>
           <p>Best regards,<br>[Your Name]<br>[Your Company]</p>`
  }
};
    
  const selectedTemplate = templates[v];
  if (!selectedTemplate) return;

  console.log('Template applied:', v, selectedTemplate.body.slice(0,50));

  // Autofill subject & body
  if (subjectEl) subjectEl.value = selectedTemplate.subject;
  if (wysiwyg) wysiwyg.innerHTML = selectedTemplate.body;
  else if (bodyTextarea) bodyTextarea.value = selectedTemplate.body;

  
  saveSelection();
 });

  // ---- discard ----
  if (discardBtn) discardBtn.addEventListener('click', () => {
    if (toEl) toEl.value = "";
    if (ccEl) ccEl.value = "";
    if (bccEl) bccEl.value = "";
    if (subjectEl) subjectEl.value = "";
    if (wysiwyg) wysiwyg.innerHTML = "";
    if (attachList) attachList.innerHTML = "";
    if (fileInput) fileInput.value = null;
    // reset preview area
    if (previewGrid) previewGrid.innerHTML = '';
    // hide emoji if visible
    hideEmoji();
  });

  // ---- draft time ----
  if (draftTimeEl) draftTimeEl.textContent = (new Date()).toLocaleTimeString();

  // ---- send handler (includes cc/bcc) ----
  if (sendBtn) sendBtn.addEventListener('click', async () => {
    const to = (toEl && toEl.value || "").trim();
    const cc = (ccEl && ccEl.value || "").trim();
    const bcc = (bccEl && bccEl.value || "").trim();
    if (!to && !cc && !bcc) { alert('Please enter at least one recipient (To, Cc or Bcc)'); return; }
    const subject = subjectEl ? subjectEl.value.trim() : '';
    const body_html = wysiwyg ? wysiwyg.innerHTML : '';
    const modeEl = document.getElementById('init_mode');
    const mode = (modeEl && modeEl.value) || init.mode || 'candidates';
    const jd_id = (document.getElementById('init_jd_id') && document.getElementById('init_jd_id').value) || '';
    const candidate_ids = (document.getElementById('init_candidate_ids') && document.getElementById('init_candidate_ids').value) || init.candidate_ids || '';

    sendBtn.disabled = true;
    sendBtn.style.opacity = '0.6';
    const spinner = document.createElement('span'); spinner.id = 'sendSpinner'; spinner.style.marginLeft='8px'; spinner.innerHTML='<i class="fas fa-spinner fa-spin"></i>'; sendBtn.appendChild(spinner);

    try {
      const res = await fetch('/candidates/gmail/send', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          to,
          cc,
          bcc,
          subject,
          body_html,
          mode,
          jd_id,
          candidate_ids
        }),
        credentials: 'same-origin'
      });
      if (!res.ok) {
        const err = await res.json().catch(()=>({detail:'Send failed'}));
        throw new Error(err.detail||err.error||'Send failed');
      }
      const data = await res.json();

      // show sent modal and wire buttons
      const sentModal = document.getElementById('sentModal');
      const sentModalMsg = document.getElementById('sentModalMsg');
      if (sentModal) {
        if (sentModalMsg) sentModalMsg.textContent = (data && data.message) ? data.message : 'Message sent';
        sentModal.setAttribute('aria-hidden','false');
        try { document.body.style.overflow = 'hidden'; } catch(e){}
      }

      // clear inputs (but don't touch authorize state)
      if (toEl) toEl.value = "";
      if (ccEl) ccEl.value = "";
      if (bccEl) bccEl.value = "";
      if (subjectEl) subjectEl.value = "";
      if (wysiwyg) wysiwyg.innerHTML = "";
      if (attachList) attachList.innerHTML = '';
      if (fileInput) fileInput.value = null;
      // also clear previews (iframes)
      if (previewGrid) previewGrid.innerHTML = '';

      // wire modal buttons (compose another / go home)
      const composeAnotherBtn = document.getElementById('composeAnotherBtn');
      const goHomeBtn = document.getElementById('goHomeBtn');
      if (composeAnotherBtn) {
        composeAnotherBtn.onclick = (ev) => {
          ev.preventDefault();
          try {
            if (sentModal) sentModal.setAttribute('aria-hidden','true');
            document.body.style.overflow = '';
          } catch (e){}
          try {
            if (toEl) toEl.value = "";
            if (ccEl) ccEl.value = "";
            if (bccEl) bccEl.value = "";
            if (subjectEl) subjectEl.value = "";
            if (wysiwyg) wysiwyg.innerHTML = "";
            if (fileInput) fileInput.value = null;
            if (attachList) attachList.innerHTML = "";
            if (previewGrid) previewGrid.innerHTML = '';
            if (templateSelect) templateSelect.value = "";
            if (ccBccArea) ccBccArea.style.display = 'none';
            if (draftTimeEl) draftTimeEl.textContent = (new Date()).toLocaleTimeString();
            hideEmoji();
          } catch (err) { console.warn('composeAnother reset error', err); }
          if (wysiwyg) wysiwyg.focus();
        };
      }
      if (goHomeBtn) {
        goHomeBtn.onclick = (ev) => {
          ev.preventDefault();
          try { window.location.href = '/templates'; } catch(e) { window.location.reload(); }
        };
      }
    } catch (e) {
      console.error('Send error', e);
      alert('Send failed: ' + (e.message || e));
    } finally {
      sendBtn.disabled = false;
      sendBtn.style.opacity = '';
      const sp = document.getElementById('sendSpinner'); if (sp) sp.remove();
    }
  });

  // helper: allow Ctrl+Enter to send
  if (wysiwyg) wysiwyg.addEventListener('keydown', (e) => { if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); sendBtn.click(); } });

  // fill previews from hidden fallback field if needed
  (function fillPreviewsFromHidden() {
    const hidden = document.getElementById('init_preview_links');
    if (hidden && hidden.value && previewGrid && previewGrid.children.length===0) {
      const arr = hidden.value.split(',').map(s=>s.trim()).filter(Boolean);
      if (arr.length) {
        arr.forEach((l,i) => {
          const card = document.createElement('div');
          card.className='preview-card';
          card.innerHTML = `<div style="font-weight:700;margin-bottom:6px">Resume ${i+1}</div>
            <iframe src="${escapeAttr(makePreviewUrl(l))}" sandbox="allow-scripts allow-same-origin allow-popups" loading="lazy"></iframe>`;
          previewGrid.appendChild(card);
        });
      }
    }
  })();

});
