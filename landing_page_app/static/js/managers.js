// static/js/managers.js
document.addEventListener("DOMContentLoaded", () => {
  // Vendor scoped namespace
  const vendorScope = {
    grid: document.getElementById('vendorScopedGrid'),
    filterButtons: document.querySelectorAll('.vendor-scoped-filter-btn'),
    toast: document.getElementById('vendorScopedToast'),
    toastMessage: document.getElementById('vendorScopedToastMessage'),
    toastClose: document.querySelector('.vendor-scoped-toast-close'),
    confirmationDialog: document.getElementById('vendorScopedDialog'),
    dialogTitle: document.getElementById('vendorScopedDialogTitle'),
    dialogMessage: document.getElementById('vendorScopedDialogMessage'),
    dialogCancel: document.getElementById('vendorScopedDialogCancel'),
    dialogConfirm: document.getElementById('vendorScopedDialogConfirm'),
    addVendorForm: document.getElementById('vendorScopedAddForm'),
    pendingDelete: null
  };

  // Vendor Creation Dialog Elements
  const vendorCreationDialog = document.getElementById('vendorCreationDialog');
  const openVendorDialogBtn = document.getElementById('openVendorDialog');
  const closeVendorDialogBtn = document.getElementById('closeVendorDialog');
  const cancelVendorCreationBtn = document.getElementById('cancelVendorCreation');
  const vendorCreationForm = document.getElementById('vendorCreationForm');
  const jobsContainer = document.getElementById('jobsContainer');
  const addAnotherJobBtn = document.getElementById('addAnotherJob');
  let jobIndex = 0;

  // Initialize vendor creation functionality
  function initVendorCreationDialog() {
    if (!vendorCreationDialog) return;
    
    // Open dialog
    openVendorDialogBtn.addEventListener('click', () => {
      vendorCreationDialog.classList.add('active');
      // Reset form and job fields
      vendorCreationForm.reset();
      resetJobFields();
      // Focus on vendor name field
      document.getElementById('manager_name').focus();
    });
    
    // Close dialog
    function closeVendorDialog() {
      vendorCreationDialog.classList.remove('active');
    }
    
    closeVendorDialogBtn.addEventListener('click', closeVendorDialog);
    cancelVendorCreationBtn.addEventListener('click', closeVendorDialog);
    
    // Close when clicking outside the dialog
    vendorCreationDialog.addEventListener('click', (e) => {
      if (e.target === vendorCreationDialog) {
        closeVendorDialog();
      }
    });
    
    // Add job field
    addAnotherJobBtn.addEventListener('click', addJobField);
    
    // Handle form submission
    vendorCreationForm.addEventListener('submit', handleVendorCreation);
  }
  
  // Reset job fields to initial state (one job field)
  function resetJobFields() {
    jobsContainer.innerHTML = '';
    jobIndex = 0;
    addJobField(); // Add the first job field
  }
  
  // Add a new job field
  function addJobField() {
    const jobEntry = document.createElement('div');
    jobEntry.className = 'vendor-scoped-job-entry';
    jobEntry.setAttribute('data-job-index', jobIndex);
    
    jobEntry.innerHTML = `
      <div class="vendor-scoped-form-group">
        <label for="job_title_${jobIndex}">Job Title *</label>
        <input type="text" name="job_title" id="job_title_${jobIndex}" placeholder="Enter Job Title" required>
      </div>
      <div class="vendor-scoped-form-group">
        <label for="job_description_${jobIndex}">Job Description</label>
        <textarea name="job_description" id="job_description_${jobIndex}" placeholder="Enter Job Description (Optional)"></textarea>
      </div>
      ${jobIndex > 0 ? '<button type="button" class="vendor-scoped-remove-job">Remove</button>' : ''}
    `;
    
    jobsContainer.appendChild(jobEntry);
    
    // Add remove functionality for this job field (except the first one)
    if (jobIndex > 0) {
      const removeBtn = jobEntry.querySelector('.vendor-scoped-remove-job');
      removeBtn.addEventListener('click', () => {
        jobEntry.remove();
        updateRemoveButtons();
      });
    }
    
    jobIndex++;
    updateRemoveButtons();
  }
  
  // Update remove buttons visibility (hide on first job field)
  function updateRemoveButtons() {
    const jobEntries = document.querySelectorAll('.vendor-scoped-job-entry');
    jobEntries.forEach((entry, index) => {
      const removeBtn = entry.querySelector('.vendor-scoped-remove-job');
      if (removeBtn) {
        removeBtn.style.display = index === 0 ? 'none' : 'block';
      }
    });
  }
  
  // Handle vendor creation form submission
  async function handleVendorCreation(e) {
    e.preventDefault();
    
    const formData = new FormData(vendorCreationForm);
    const vendorName = formData.get('manager_name');
    
    // Validate at least one job title is provided
    const jobTitles = formData.getAll('job_title').filter(title => title.trim() !== '');
    if (jobTitles.length === 0) {
      showToast('At least one job title is required!', true);
      return;
    }
    
    try {
      const response = await fetch(vendorCreationForm.action, {
        method: 'POST',
        body: formData,
        credentials: 'same-origin'
      });
      
      if (response.ok) {
        showToast(`Vendor "${vendorName}" created successfully with ${jobTitles.length} job(s)`);
        // Close the dialog
        vendorCreationDialog.classList.remove('active');
        // Reload the page to show the new vendor
        setTimeout(() => {
          window.location.reload();
        }, 1500);
      } else {
        const error = await response.text();
        showToast('Failed to add vendor: ' + error, true);
      }
    } catch (err) {
      showToast('Network error adding vendor: ' + err.message, true);
    }
  }

  // Show toast notification
  function showToast(message, isError = false) {
    vendorScope.toastMessage.textContent = message;
    vendorScope.toast.className = isError ? 'vendor-scoped-toast error' : 'vendor-scoped-toast';
    vendorScope.toast.style.display = 'flex';
    
    // Auto hide after 4 seconds
    setTimeout(() => {
      hideToast();
    }, 4000);
  }

  // Hide toast
  function hideToast() {
    vendorScope.toast.style.display = 'none';
  }

  // Show confirmation dialog
  function showConfirmationDialog(title, message, confirmCallback) {
    vendorScope.dialogTitle.textContent = title;
    vendorScope.dialogMessage.textContent = message;
    vendorScope.confirmationDialog.classList.add('active');
    
    // Set up event listeners
    const confirmHandler = () => {
      vendorScope.confirmationDialog.classList.remove('active');
      confirmCallback();
      vendorScope.dialogConfirm.removeEventListener('click', confirmHandler);
      vendorScope.dialogCancel.removeEventListener('click', cancelHandler);
    };
    
    const cancelHandler = () => {
      vendorScope.confirmationDialog.classList.remove('active');
      vendorScope.dialogConfirm.removeEventListener('click', confirmHandler);
      vendorScope.dialogCancel.removeEventListener('click', cancelHandler);
    };
    
    vendorScope.dialogConfirm.addEventListener('click', confirmHandler);
    vendorScope.dialogCancel.addEventListener('click', cancelHandler);
  }

  // Close toast when clicked
  vendorScope.toastClose.addEventListener('click', hideToast);

  // Filter functionality
  vendorScope.filterButtons.forEach(button => {
    button.addEventListener('click', () => {
      const status = button.dataset.status;
      
      // Update active button
      vendorScope.filterButtons.forEach(btn => btn.classList.remove('active'));
      button.classList.add('active');
      
      // Filter cards
      const cards = document.querySelectorAll('.vendor-scoped-card');
      cards.forEach(card => {
        if (status === 'all') {
          card.style.display = 'flex';
        } else {
          card.style.display = card.dataset.status === status ? 'flex' : 'none';
        }
      });
    });
  });

  // close dropdowns helper
  function closeAllDropdowns() {
    document.querySelectorAll('.vendor-scoped-menu-content').forEach(m => m.classList.remove('show'));
    document.querySelectorAll('.vendor-scoped-menu-btn').forEach(b => b.setAttribute('aria-expanded', 'false'));
  }

  // attach dropdown handlers
  document.querySelectorAll('.vendor-scoped-menu-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      closeAllDropdowns();
      const parent = btn.closest('.vendor-scoped-menu');
      const menu = parent.querySelector('.vendor-scoped-menu-content');
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
  vendorScope.grid.addEventListener('change', async (e) => {
    const el = e.target;
    if (!el.classList.contains('vendor-scoped-toggle-input')) return;

    const toggleUrl = el.dataset.toggleUrl;
    const vendorName = el.dataset.name;
    const managerCard = el.closest('.vendor-scoped-card');
    const statusBadge = managerCard ? managerCard.querySelector('.vendor-scoped-status') : null;

    if (!toggleUrl) {
      console.error('Toggle URL missing', el);
      el.checked = !el.checked;
      return;
    }

    const desired = el.checked ? 'active' : 'inactive';

    try {
      const res = await fetch(toggleUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'application/json'
        },
        body: JSON.stringify({ status: desired })
      });

      const parsed = await parseResponseSafely(res);

      if (!parsed.ok) {
        const msg = parsed.json?.detail || parsed.json?.message || parsed.text || `Status ${parsed.status}`;
        showToast('Failed to toggle vendor status: ' + msg, true);
        el.checked = !el.checked;
        return;
      }

      const data = parsed.json || {};
      const newStatus = data.new_status || desired;
      
      // Update card status for filtering
      managerCard.dataset.status = newStatus;
      
      if (statusBadge) {
        statusBadge.textContent = newStatus.charAt(0).toUpperCase() + newStatus.slice(1);
        statusBadge.className = 'vendor-scoped-status ' + (newStatus === 'active' ? 'active' : 'inactive');
      }
      
      showToast(`${vendorName} is now ${newStatus}`);
    } catch (err) {
      console.error('Network/error toggling status', err);
      showToast('Network error toggling status: ' + err.message, true);
      el.checked = !el.checked;
    }
  });

  // Delegated click for menu actions (delete/edit)
  vendorScope.grid.addEventListener('click', async (e) => {
    const del = e.target.closest('.vendor-scoped-menu-delete');
    if (del) {
      e.preventDefault();
      const url = del.dataset.deleteUrl;
      const vendorName = del.dataset.name;
      
      if (!url) { 
        showToast('Delete URL missing', true);
        return; 
      }
      
      // Show confirmation dialog instead of using confirm()
      showConfirmationDialog(
        'Confirm Deletion', 
        `Are you sure you want to delete "${vendorName}" and all its jobs? This action cannot be undone.`,
        async () => {
          try {
            const res = await fetch(url, { 
              method: 'POST', 
              credentials: 'same-origin', 
              headers: { 
                'X-Requested-With': 'XMLHttpRequest', 
                'Accept': 'application/json' 
              }
            });
            
            const parsed = await parseResponseSafely(res);
            if (!parsed.ok) { 
              showToast(parsed.json?.detail || parsed.text || 'Failed to delete vendor', true); 
              return; 
            }
            
            const card = del.closest('.vendor-scoped-card'); 
            if (card) {
              card.style.opacity = '0';
              card.style.transition = 'opacity 0.3s';
              setTimeout(() => card.remove(), 300);
            }
            
            showToast(`${vendorName} has been deleted successfully`);
          } catch (err) { 
            showToast('Error deleting vendor: ' + err.message, true); 
          }
        }
      );
      
      return;
    }

    const edt = e.target.closest('.vendor-scoped-menu-edit');
    if (edt) {
      e.preventDefault();
      const editUrl = edt.dataset.editUrl;
      const currentName = edt.dataset.name || edt.closest('.vendor-scoped-card').querySelector('.vendor-scoped-card-title').textContent;
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
        if (!parsed.ok) { 
          showToast(parsed.json?.detail || parsed.text || 'Failed to update vendor', true); 
          return; 
        }
        
        const data = parsed.json || {};
        const card = edt.closest('.vendor-scoped-card');
        if (card) {
          const title = card.querySelector('.vendor-scoped-card-title');
          if (title) title.textContent = data.manager_name || newName.trim();
          // Update the data-name attribute for future operations
          edt.dataset.name = data.manager_name || newName.trim();
          
          // Also update the toggle switch data-name
          const toggleSwitch = card.querySelector('.vendor-scoped-toggle-input');
          if (toggleSwitch) toggleSwitch.dataset.name = data.manager_name || newName.trim();
        }
        
        showToast(`Vendor name updated to "${data.manager_name || newName.trim()}"`);
      } catch (err) { 
        showToast('Error updating vendor: ' + err.message, true); 
      }
      return;
    }
  });

  // Initialize vendor creation dialog
  initVendorCreationDialog();
});