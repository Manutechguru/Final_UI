document.addEventListener("DOMContentLoaded", function() {

  // Row expand
  document.querySelectorAll(".main-row").forEach(row => {
    row.addEventListener("click", function(e){
      if(e.target.tagName.toLowerCase() === 'input' || e.target.tagName.toLowerCase() === 'a') return;
      this.classList.toggle("expanded");
    });
  });

  // Advanced Search toggle
  const advToggle = document.getElementById('advToggle');
  const advBody = document.getElementById('advBody');
  const advIcon = document.getElementById('advIcon');
  if(advToggle && advBody && advIcon){
    advToggle.addEventListener('click', ()=>{
      advBody.classList.toggle('show');
      advIcon.classList.toggle('bi-caret-down-fill');
      advIcon.classList.toggle('bi-caret-up-fill');
    });
  }

  // Checkbox logic
  const selectAll = document.getElementById('selectAll');
  const linkBtn = document.getElementById('linkCandidatesBtn');
  const toggleAllBtn = document.getElementById('toggleAllBtn');
  const clientSelect = document.getElementById('clientSelect');
  const jdSelect = document.getElementById('jdSelect');
  const kpiSelected = document.getElementById('kpiSelected');
  const kpiJobs = document.getElementById('kpiJobs');

  const getBoxes = () => Array.from(document.querySelectorAll('.candidateCheckbox'));

  function updateKPIs(){
    if(kpiSelected) kpiSelected.textContent = getBoxes().filter(b=>b.checked).length;
    if(kpiJobs) kpiJobs.textContent = Math.max(0,(jdSelect? jdSelect.options.length:0)-1);
    const ok = (clientSelect && clientSelect.value) && (jdSelect && jdSelect.value) && getBoxes().some(b=>b.checked);
    if(linkBtn) linkBtn.disabled = !ok;
  }

  function syncRowVisuals(){
    getBoxes().forEach(cb=>{
      const tr = cb.closest('tr');
      if(tr) tr.classList.toggle('selected', !!cb.checked);
    });
    updateKPIs();
  }

  if(selectAll){
    selectAll.addEventListener('change', ()=> {
      const checked = selectAll.checked;
      getBoxes().forEach(b=>b.checked=checked);
      syncRowVisuals();
    });
  }

  document.addEventListener('change', (e)=>{
    if(e.target.classList.contains('candidateCheckbox')){
      const boxes = getBoxes();
      selectAll && (selectAll.checked = boxes.every(b=>b.checked));
      syncRowVisuals();
    }
  });

  if(toggleAllBtn){
    toggleAllBtn.addEventListener('click', ()=>{
      const boxes = getBoxes();
      const allChecked = boxes.every(b=>b.checked);
      boxes.forEach(b=>b.checked=!allChecked);
      selectAll && (selectAll.checked = !allChecked);
      syncRowVisuals();
    });
  }

  // Fetch jobs for client
  if(clientSelect){
    clientSelect.addEventListener('change', ()=>{
      const clientId = clientSelect.value;
      jdSelect.innerHTML = '<option value="">Loading...</option>';
      updateKPIs();
      if(!clientId){ jdSelect.innerHTML = '<option value="">Select Job</option>'; updateKPIs(); return; }
      fetch(`/candidates/jobs/${clientId}`)
        .then(r=>r.json())
        .then(list=>{
          jdSelect.innerHTML='<option value="">Select Job</option>';
          list.forEach(j=>{
            const opt=document.createElement('option');
            opt.value=j.jd_id;
            opt.textContent=j.title;
            jdSelect.appendChild(opt);
          });
          updateKPIs();
        }).catch(err=>{ console.error(err); jdSelect.innerHTML='<option value="">Select Job</option>'; updateKPIs(); });
    });
  }

  // Link candidates button
  if(linkBtn){
    linkBtn.addEventListener('click', ()=>{
      const selected = getBoxes().filter(b=>b.checked).map(b=>parseInt(b.value)).filter(Boolean);
      const clientId = parseInt(clientSelect.value);
      const jdId = parseInt(jdSelect.value);
      if(!clientId||!jdId||!selected.length){ alert('Select client, job, and candidates.'); return; }
      const prev = linkBtn.innerHTML;
      linkBtn.disabled = true;
      linkBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Linking...';
      fetch('/candidates/link-to-job',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ client_id: clientId, jd_id: jdId, candidate_ids:selected })
      }).then(r=>r.json())
        .then(resp=>{ alert(resp.message||'Linked successfully'); window.location.reload(); })
        .catch(err=>{ console.error(err); alert('Failed to link candidates'); })
        .finally(()=>{ linkBtn.disabled=false; linkBtn.innerHTML=prev; });
    });
  }

  updateKPIs();
});
