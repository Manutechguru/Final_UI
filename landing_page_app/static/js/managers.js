// static/js/managers.js
document.addEventListener("DOMContentLoaded", () => {
  const managers = {
    table: document.getElementById('managersTable'),
    filterButtons: document.querySelectorAll('.managers-filter-btn'),
    toast: document.getElementById('managersToast'),
    toastMessage: document.getElementById('managersToastMessage'),
    toastClose: document.querySelector('.managers-toast-close'),
    confirmationDialog: document.getElementById('managersConfirmationDialog'),
    dialogTitle: document.getElementById('managersDialogTitle'),
    dialogMessage: document.getElementById('managersDialogMessage'),
    dialogCancel: document.getElementById('managersDialogCancel'),
    dialogConfirm: document.getElementById('managersDialogConfirm'),
    pendingDelete: null
  };

  // Manager Creation Dialog Elements
  const managerCreationDialog = document.getElementById('managerCreationDialog');
  const openManagerDialogBtn = document.getElementById('openManagerDialog');
  const closeManagerDialogBtn = document.getElementById('closeManagerDialog');
  const cancelManagerCreationBtn = document.getElementById('cancelManagerCreation');
  const managerCreationForm = document.getElementById('managerCreationForm');
  const jobsContainer = document.getElementById('jobsContainer');
  const addAnotherJobBtn = document.getElementById('addAnotherJob');
  let jobIndex = 0;

  // Initialize manager creation functionality
  function initManagerCreationDialog() {
    if (!managerCreationDialog) return;
    
    openManagerDialogBtn.addEventListener('click', () => {
      managerCreationDialog.classList.add('active');
      managerCreationForm.reset();
      resetJobFields();
      document.getElementById('manager_name').focus();
    });
    
    function closeManagerDialog() {
      managerCreationDialog.classList.remove('active');
    }
    
    closeManagerDialogBtn.addEventListener('click', closeManagerDialog);
    cancelManagerCreationBtn.addEventListener('click', closeManagerDialog);
    
    managerCreationDialog.addEventListener('click', (e) => {
      if (e.target === managerCreationDialog) {
        closeManagerDialog();
      }
    });
    
    addAnotherJobBtn.addEventListener('click', addJobField);
    managerCreationForm.addEventListener('submit', handleManagerCreation);
  }
  
  function resetJobFields() {
    jobsContainer.innerHTML = '';
    jobIndex = 0;
    addJobField();
  }
  
  function addJobField() {
    const jobEntry = document.createElement('div');
    jobEntry.className = 'managers-job-entry';
    jobEntry.setAttribute('data-job-index', jobIndex);
    
    jobEntry.innerHTML = `
      <div class="managers-form-group">
        <label for="job_title_${jobIndex}">Job Title *</label>
        <input type="text" name="job_title" id="job_title_${jobIndex}" placeholder="Enter Job Title" required>
      </div>
      <div class="managers-form-group">
        <label for="job_description_${jobIndex}">Job Description</label>
        <textarea name="job_description" id="job_description_${jobIndex}" placeholder="Enter Job Description (Optional)"></textarea>
      </div>
      ${jobIndex > 0 ? '<button type="button" class="managers-remove-job">Remove</button>' : ''}
    `;
    
    jobsContainer.appendChild(jobEntry);
    
    if (jobIndex > 0) {
      const removeBtn = jobEntry.querySelector('.managers-remove-job');
      removeBtn.addEventListener('click', () => {
        jobEntry.remove();
        updateRemoveButtons();
      });
    }
    
    jobIndex++;
    updateRemoveButtons();
  }
  
  function updateRemoveButtons() {
    const jobEntries = document.querySelectorAll('.managers-job-entry');
    jobEntries.forEach((entry, index) => {
      const removeBtn = entry.querySelector('.managers-remove-job');
      if (removeBtn) {
        removeBtn.style.display = index === 0 ? 'none' : 'block';
      }
    });
  }
  
  async function handleManagerCreation(e) {
    e.preventDefault();
    
    const formData = new FormData(managerCreationForm);
    const managerName = formData.get('manager_name');
    
    const jobTitles = formData.getAll('job_title').filter(title => title.trim() !== '');
    if (jobTitles.length === 0) {
      showToast('At least one job title is required!', true);
      return;
    }
    
    try {
      const response = await fetch(managerCreationForm.action, {
        method: 'POST',
        body: formData,
        credentials: 'same-origin'
      });
      
      if (response.ok) {
        showToast(`Manager "${managerName}" created successfully with ${jobTitles.length} job(s)`);
        managerCreationDialog.classList.remove('active');
        setTimeout(() => {
          window.location.reload();
        }, 1500);
      } else {
        const error = await response.text();
        showToast('Failed to add manager: ' + error, true);
      }
    } catch (err) {
      showToast('Network error adding manager: ' + err.message, true);
    }
  }

  // Show toast notification
  function showToast(message, isError = false) {
    managers.toastMessage.textContent = message;
    managers.toast.className = isError ? 'managers-toast error' : 'managers-toast';
    managers.toast.style.display = 'flex';
    
    setTimeout(() => {
      hideToast();
    }, 4000);
  }

  function hideToast() {
    managers.toast.style.display = 'none';
  }

  // Show confirmation dialog
  function showConfirmationDialog(title, message, confirmCallback) {
    managers.dialogTitle.textContent = title;
    managers.dialogMessage.textContent = message;
    managers.confirmationDialog.classList.add('active');
    
    const confirmHandler = () => {
      managers.confirmationDialog.classList.remove('active');
      confirmCallback();
      managers.dialogConfirm.removeEventListener('click', confirmHandler);
      managers.dialogCancel.removeEventListener('click', cancelHandler);
    };
    
    const cancelHandler = () => {
      managers.confirmationDialog.classList.remove('active');
      managers.dialogConfirm.removeEventListener('click', confirmHandler);
      managers.dialogCancel.removeEventListener('click', cancelHandler);
    };
    
    managers.dialogConfirm.addEventListener('click', confirmHandler);
    managers.dialogCancel.addEventListener('click', cancelHandler);
  }

  managers.toastClose.addEventListener('click', hideToast);

  // Filter functionality
  managers.filterButtons.forEach(button => {
    button.addEventListener('click', () => {
      const status = button.dataset.status;
      
      managers.filterButtons.forEach(btn => btn.classList.remove('active'));
      button.classList.add('active');
      
      const rows = document.querySelectorAll('.manager-row');
      rows.forEach(row => {
        if (status === 'all') {
          row.style.display = '';
        } else {
          row.style.display = row.dataset.status === status ? '' : 'none';
        }
      });
    });
  });

  // Dropdown functionality
  function closeAllDropdowns() {
    document.querySelectorAll('.manager-dropdown-content').forEach(m => m.classList.remove('show'));
  }

  document.querySelectorAll('.manager-dropdown-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      closeAllDropdowns();
      const dropdown = btn.nextElementSibling;
      dropdown.classList.toggle('show');
    });
  });

  document.addEventListener('click', closeAllDropdowns);
  document.addEventListener('keydown', (e) => { 
    if (e.key === 'Escape') closeAllDropdowns(); 
  });

  async function parseResponseSafely(res) {
    const text = await res.text();
    try {
      return { ok: res.ok, status: res.status, json: JSON.parse(text), text };
    } catch {
      return { ok: res.ok, status: res.status, json: null, text };
    }
  }

  // Toggle switches
  managers.table.addEventListener('change', async (e) => {
    const el = e.target;
    if (!el.classList.contains('manager-toggle-input')) return;

    const toggleUrl = el.dataset.toggleUrl;
    const managerName = el.dataset.name;
    const managerRow = el.closest('.manager-row');
    const statusBadge = managerRow ? managerRow.querySelector('.manager-status-badge') : null;

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
        showToast('Failed to toggle manager status: ' + msg, true);
        el.checked = !el.checked;
        return;
      }

      const data = parsed.json || {};
      const newStatus = data.new_status || desired;
      
      managerRow.dataset.status = newStatus;
      
      if (statusBadge) {
        statusBadge.textContent = newStatus.charAt(0).toUpperCase() + newStatus.slice(1);
        statusBadge.className = 'manager-status-badge ' + (newStatus === 'active' ? 'active' : 'inactive');
      }
      
      showToast(`${managerName} is now ${newStatus}`);
    } catch (err) {
      console.error('Network/error toggling status', err);
      showToast('Network error toggling status: ' + err.message, true);
      el.checked = !el.checked;
    }
  });

  // Delegated click for menu actions
  managers.table.addEventListener('click', async (e) => {
    const del = e.target.closest('.manager-delete');
    if (del) {
      e.preventDefault();
      const url = del.dataset.deleteUrl;
      const managerName = del.dataset.name;
      
      if (!url) { 
        showToast('Delete URL missing', true);
        return; 
      }
      
      showConfirmationDialog(
        'Confirm Deletion', 
        `Are you sure you want to delete "${managerName}" and all its jobs? This action cannot be undone.`,
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
              showToast(parsed.json?.detail || parsed.text || 'Failed to delete manager', true); 
              return; 
            }
            
            const row = del.closest('.manager-row'); 
            if (row) {
              row.style.opacity = '0';
              row.style.transition = 'opacity 0.3s';
              setTimeout(() => row.remove(), 300);
            }
            
            showToast(`${managerName} has been deleted successfully`);
          } catch (err) { 
            showToast('Error deleting manager: ' + err.message, true); 
          }
        }
      );
      
      return;
    }

    const edt = e.target.closest('.manager-edit');
    if (edt) {
      e.preventDefault();
      const editUrl = edt.dataset.editUrl;
      const currentName = edt.dataset.name || edt.closest('.manager-row').querySelector('.manager-name-text').textContent;
      const newName = prompt('Edit manager name:', currentName);
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
          showToast(parsed.json?.detail || parsed.text || 'Failed to update manager', true); 
          return; 
        }
        
        const data = parsed.json || {};
        const row = edt.closest('.manager-row');
        if (row) {
          const nameCell = row.querySelector('.manager-name-text');
          if (nameCell) {
            nameCell.textContent = newName.trim();
          }
          
          // Update the data-name attribute on the edit button
          edt.dataset.name = newName.trim();
          
          // Update the data-name attribute on the delete button if it exists
          const deleteBtn = row.querySelector('.manager-delete');
          if (deleteBtn) {
            deleteBtn.dataset.name = newName.trim();
          }
        }
        
        showToast(`Manager name updated to "${newName.trim()}"`);
      } catch (err) {
        showToast('Error updating manager: ' + err.message, true);
      }
      
      return;
    }

    // Handle view jobs action
    const viewJobs = e.target.closest('.manager-view-jobs');
    if (viewJobs) {
      e.preventDefault();
      const jobsUrl = viewJobs.dataset.jobsUrl;
      if (jobsUrl) {
        window.location.href = jobsUrl;
      }
      return;
    }
  });

  // Initialize the manager creation dialog
  initManagerCreationDialog();

  // Auto-hide toast on click outside
  document.addEventListener('click', (e) => {
    if (managers.toast.style.display === 'flex' && !e.target.closest('.managers-toast')) {
      hideToast();
    }
  });

  // Keyboard navigation for dropdowns
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      const dropdowns = document.querySelectorAll('.manager-dropdown-content.show');
      if (dropdowns.length > 0) {
        const firstItem = dropdowns[0].querySelector('a, button');
        if (firstItem) {
          firstItem.focus();
          e.preventDefault();
        }
      }
    }
  });

  // Enhanced error handling for fetch requests
  function handleFetchError(error, defaultMessage = 'An error occurred') {
    console.error('Fetch error:', error);
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      showToast('Network error: Please check your connection', true);
    } else {
      showToast(defaultMessage + ': ' + error.message, true);
    }
  }

  // Utility function to debounce rapid clicks
  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  // Debounce the toggle switch to prevent rapid clicks
  managers.table.addEventListener('change', debounce(async (e) => {
    const el = e.target;
    if (!el.classList.contains('manager-toggle-input')) return;

    // The actual toggle logic is handled above, this just prevents rapid firing
  }, 300));

  console.log('Managers JS loaded successfully');
});