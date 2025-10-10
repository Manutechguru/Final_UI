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

  // Add Job Dialog Elements
  const addJobDialog = document.getElementById('addJobDialog');
  const addJobForm = document.getElementById('addJobForm');
  const closeAddJobDialogBtn = document.getElementById('closeAddJobDialog');
  const cancelAddJobBtn = document.getElementById('cancelAddJob');
  let currentManagerId = null;
  let currentManagerName = null;

  // Track toggle states to prevent unwanted changes
  const toggleStates = new Map();

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

  // Initialize add job dialog functionality
  function initAddJobDialog() {
    if (!addJobDialog) return;

    function openAddJobDialog(managerId, managerName, addJobUrl) {
      currentManagerId = managerId;
      currentManagerName = managerName;
      addJobForm.reset();
      
      // ✅ FIXED: Use the provided URL from data attribute
      if (addJobUrl) {
        addJobForm.action = addJobUrl;
      } else {
        // Fallback to the correct URL pattern
        addJobForm.action = `/clients/vendors/vendors/${managerId}/add-job-from-list`;
      }
      
      addJobDialog.classList.add('active');
      document.getElementById('add_job_title').focus();
      
      // Update dialog title to show manager name
      const dialogTitle = addJobDialog.querySelector('h3');
      if (dialogTitle) {
        dialogTitle.textContent = `Add Job - ${managerName}`;
      }
    }

    function closeAddJobDialog() {
      addJobDialog.classList.remove('active');
      currentManagerId = null;
      currentManagerName = null;
    }

    closeAddJobDialogBtn.addEventListener('click', closeAddJobDialog);
    cancelAddJobBtn.addEventListener('click', closeAddJobDialog);

    addJobDialog.addEventListener('click', (e) => {
      if (e.target === addJobDialog) {
        closeAddJobDialog();
      }
    });

    addJobForm.addEventListener('submit', handleAddJob);

    // Add event listener for add job buttons
    if (managers.table) {
      managers.table.addEventListener('click', (e) => {
        const addJobBtn = e.target.closest('.manager-add-job');
        if (addJobBtn) {
          e.preventDefault();
          const managerId = addJobBtn.dataset.managerId;
          const managerName = addJobBtn.dataset.managerName;
          const addJobUrl = addJobBtn.dataset.addJobUrl;
          
          if (!managerId) {
            showToast('Manager ID is missing!', true);
            return;
          }
          
          openAddJobDialog(managerId, managerName, addJobUrl);
        }
      });
    }
  }

  async function handleAddJob(e) {
    e.preventDefault();
    
    const formData = new FormData(addJobForm);
    const jobTitle = formData.get('job_title')?.trim();
    const jobDescription = formData.get('job_description')?.trim() || '';

    if (!jobTitle) {
      showToast('Job title is required!', true);
      return;
    }

    if (!currentManagerId) {
      showToast('Manager ID is missing!', true);
      return;
    }

    try {
      const body = new URLSearchParams({
        job_title: jobTitle,
        job_description: jobDescription
      });

      const response = await fetch(addJobForm.action, {
        method: 'POST',
        body: body,
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-Requested-With': 'XMLHttpRequest'
        }
      });

      if (response.ok) {
        showToast(`Job "${jobTitle}" added successfully to ${currentManagerName}!`);
        addJobDialog.classList.remove('active');
        
        // ✅ FIXED: Don't reload the page, just update the UI
        // This prevents toggle state issues
        updateManagerRowAfterJobAdd(currentManagerId, jobTitle);
        
      } else {
        const errorText = await response.text();
        let errorMessage = 'Failed to add job';
        
        try {
          const errorData = JSON.parse(errorText);
          errorMessage = errorData.detail || errorData.message || errorMessage;
        } catch {
          errorMessage = errorText || errorMessage;
        }
        
        showToast(errorMessage, true);
      }
    } catch (err) {
      console.error('Error adding job:', err);
      showToast('Network error adding job: ' + err.message, true);
    }
  }

  // ✅ UPDATED: Properly update manager row with new job as active
  function updateManagerRowAfterJobAdd(managerId, jobTitle) {
    const managerRow = document.querySelector(`.manager-row[data-manager-id="${managerId}"]`);
    if (!managerRow) return;

    // Find the jobs container for this manager
    // Look for common job container selectors
    let jobsContainer = managerRow.querySelector('.jobs-list, .manager-jobs, .jobs-container, tbody');
    
    if (!jobsContainer) {
      // If no specific jobs container found, try to find a table or list structure
      jobsContainer = managerRow.querySelector('table, ul, ol, .job-entries');
      
      // If still not found, create a basic container
      if (!jobsContainer) {
        console.warn('No jobs container found for manager, creating one');
        jobsContainer = document.createElement('div');
        jobsContainer.className = 'jobs-list';
        managerRow.appendChild(jobsContainer);
      }
    }

    // Create a new job row with active status by default
    const jobRow = document.createElement('div');
    jobRow.className = 'job-row';
    jobRow.dataset.jobTitle = jobTitle;
    jobRow.dataset.status = 'active';

    // Create job row HTML - adjust based on your actual job row structure
    jobRow.innerHTML = `
      <div class="job-info">
        <span class="job-title">${jobTitle}</span>
        <span class="job-status-badge active">Active</span>
      </div>
      <div class="job-actions">
        <label class="manager-toggle">
          <input type="checkbox" class="job-toggle-input" data-status="active" checked>
          <span class="manager-toggle-slider"></span>
        </label>
      </div>
    `;

    // Append the new job row
    jobsContainer.appendChild(jobRow);

    // ✅ Track toggle state for the new job
    const jobToggle = jobRow.querySelector('.job-toggle-input');
    if (jobToggle) {
      const jobId = `job-${Date.now()}`; // Generate a temporary ID
      jobRow.dataset.jobId = jobId;
      toggleStates.set(jobId, true);
      
      // Add toggle event listener for the new job
      jobToggle.addEventListener('change', handleJobToggleChange);
    }

    console.log(`Job "${jobTitle}" added to manager ${managerId} with active status`);
  }

  // ✅ NEW: Handle job toggle changes
  function handleJobToggleChange(e) {
    const jobToggle = e.target;
    const jobRow = jobToggle.closest('.job-row');
    const jobTitle = jobRow?.querySelector('.job-title')?.textContent;
    const statusBadge = jobRow?.querySelector('.job-status-badge');
    
    if (jobRow && statusBadge) {
      const newStatus = jobToggle.checked ? 'active' : 'inactive';
      
      // Update UI
      jobRow.dataset.status = newStatus;
      statusBadge.textContent = newStatus.charAt(0).toUpperCase() + newStatus.slice(1);
      statusBadge.className = 'job-status-badge ' + newStatus;
      
      // Update toggle state
      const jobId = jobRow.dataset.jobId;
      if (jobId) {
        toggleStates.set(jobId, jobToggle.checked);
      }
      
      console.log(`Job "${jobTitle}" status changed to ${newStatus}`);
      
      // Here you can add API call to update job status on backend if needed
      // await updateJobStatus(jobId, newStatus);
    }
  }
  
  function resetJobFields() {
    if (jobsContainer) {
      jobsContainer.innerHTML = '';
      jobIndex = 0;
      addJobField();
    }
  }
  
  function addJobField() {
    if (!jobsContainer) return;
    
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
        
        // ✅ FIXED: Only reload if necessary, otherwise update UI directly
        setTimeout(() => {
          window.location.reload();
        }, 1500);
      } else {
        const errorText = await response.text();
        let errorMessage = 'Failed to add manager';
        
        try {
          const errorData = JSON.parse(errorText);
          errorMessage = errorData.detail || errorData.message || errorMessage;
        } catch {
          errorMessage = errorText || errorMessage;
        }
        
        showToast(errorMessage, true);
      }
    } catch (err) {
      console.error('Error creating manager:', err);
      showToast('Network error adding manager: ' + err.message, true);
    }
  }

  
  // Show toast notification
  function showToast(message, isError = false) {
    if (!managers.toastMessage || !managers.toast) return;
    
    managers.toastMessage.textContent = message;
    managers.toast.className = isError ? 'managers-toast error' : 'managers-toast';
    managers.toast.style.display = 'flex';
    
    setTimeout(() => {
      hideToast();
    }, 4000);
  }

  function hideToast() {
    if (managers.toast) {
      managers.toast.style.display = 'none';
    }
  }

  // Show confirmation dialog
  function showConfirmationDialog(title, message, confirmCallback) {
    if (!managers.dialogTitle || !managers.dialogMessage || !managers.confirmationDialog) return;
    
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

  if (managers.toastClose) {
    managers.toastClose.addEventListener('click', hideToast);
  }

  // ✅ FIXED: Initialize toggle states from current DOM
  function initializeToggleStates() {
    const toggleInputs = document.querySelectorAll('.manager-toggle-input, .job-toggle-input');
    toggleInputs.forEach(toggle => {
      const managerId = toggle.dataset.managerId || toggle.closest('.manager-row')?.dataset.managerId;
      const jobId = toggle.dataset.jobId || toggle.closest('.job-row')?.dataset.jobId;
      
      if (managerId) {
        toggleStates.set(managerId, toggle.checked);
      }
      if (jobId) {
        toggleStates.set(jobId, toggle.checked);
      }
    });
  }

  // Filter functionality
  if (managers.filterButtons) {
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
  }

  // Dropdown functionality
  function closeAllDropdowns() {
    document.querySelectorAll('.manager-dropdown-content').forEach(m => m.classList.remove('show'));
  }

  document.querySelectorAll('.manager-dropdown-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      closeAllDropdowns();
      const dropdown = btn.nextElementSibling;
      if (dropdown) {
        dropdown.classList.toggle('show');
      }
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

  // ✅ FIXED: Enhanced toggle functionality with state tracking
  if (managers.table) {
    managers.table.addEventListener('change', async (e) => {
      const el = e.target;
      if (!el.classList.contains('manager-toggle-input')) return;

      const toggleUrl = el.dataset.toggleUrl;
      const managerName = el.dataset.name;
      const managerId = el.dataset.managerId || el.closest('.manager-row')?.dataset.managerId;
      const managerRow = el.closest('.manager-row');
      const statusBadge = managerRow ? managerRow.querySelector('.manager-status-badge') : null;

      if (!toggleUrl) {
        console.error('Toggle URL missing', el);
        el.checked = !el.checked;
        return;
      }

      // Store the current state before making the request
      const previousState = el.checked;
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
          // Revert to previous state on error
          el.checked = previousState;
          return;
        }

        const data = parsed.json || {};
        const newStatus = data.new_status || desired;
        
        if (managerRow) {
          managerRow.dataset.status = newStatus;
        }
        
        if (statusBadge) {
          statusBadge.textContent = newStatus.charAt(0).toUpperCase() + newStatus.slice(1);
          statusBadge.className = 'manager-status-badge ' + (newStatus === 'active' ? 'active' : 'inactive');
        }
        
        // Update the stored state
        if (managerId) {
          toggleStates.set(managerId, newStatus === 'active');
        }
        
        showToast(`${managerName} is now ${newStatus}`);
      } catch (err) {
        console.error('Network/error toggling status', err);
        showToast('Network error toggling status: ' + err.message, true);
        // Revert to previous state on error
        el.checked = previousState;
      }
    });
  }

  // Delegated click for menu actions
  if (managers.table) {
    managers.table.addEventListener('click', async (e) => {
      const del = e.target.closest('.manager-delete');
      if (del) {
        e.preventDefault();
        const url = del.dataset.deleteUrl;
        const managerName = del.dataset.name;
        const managerId = del.dataset.managerId || del.closest('.manager-row')?.dataset.managerId;
        
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
                // Remove from toggle states
                if (managerId) {
                  toggleStates.delete(managerId);
                }
                
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
        const currentName = edt.dataset.name || (edt.closest('.manager-row')?.querySelector('.manager-name-text')?.textContent || '');
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
      const viewJobs = e.target.closest('.view-jobs');
      if (viewJobs) {
        e.preventDefault();
        const jobsUrl = viewJobs.href;
        if (jobsUrl) {
          window.location.href = jobsUrl;
        }
        return;
      }
    });
  }

  // Initialize the manager creation dialog
  initManagerCreationDialog();
  
  // Initialize the add job dialog
  initAddJobDialog();

  // Initialize toggle states
  initializeToggleStates();

  // Auto-hide toast on click outside
  document.addEventListener('click', (e) => {
    if (managers.toast && managers.toast.style.display === 'flex' && !e.target.closest('.managers-toast')) {
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

  console.log('Managers JS loaded successfully');
});