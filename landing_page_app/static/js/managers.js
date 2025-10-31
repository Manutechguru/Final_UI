// static/js/managers.js
document.addEventListener("DOMContentLoaded", () => {
  const managers = {
    toast: document.getElementById('managersToast'),
    toastMessage: document.getElementById('managersToastMessage'),
    toastIcon: document.getElementById('managersToastIcon'),
    toastClose: document.querySelector('.managers-toast-close')
  };

  // Filter Sidebar Elements
  const filterSidebar = document.getElementById('filterSidebar');
  const sidebarOverlay = document.getElementById('sidebarOverlay');
  const filterToggle = document.getElementById('filterToggle');
  const closeFilters = document.getElementById('closeFilters');
  const mainContent = document.querySelector('.mainContent');
  const searchManager = document.getElementById('searchManager');
  const statusFilter = document.getElementById('statusFilter');
  const recentFilter = document.getElementById('recentFilter');
  const clearFilters = document.getElementById('clearFilters');
  const activeFilters = document.getElementById('activeFilters');
  const managersTableBody = document.getElementById('managersTableBody');
  const loadingState = document.getElementById('loadingState');
  const emptyState = document.getElementById('emptyState');

  let desktopSidebarHidden = false;

  // Modal Elements
  const managerDetailsModal = document.getElementById("managerDetailsModal");
  const modalManagerName = document.getElementById("modalManagerName");
  const modalCreatedAt = document.getElementById("modalCreatedAt");
  const modalCreatedBy = document.getElementById("modalCreatedBy");
  const modalUpdatedAt = document.getElementById("modalUpdatedAt");
  const modalUpdatedBy = document.getElementById("modalUpdatedBy");

  // Delete Confirmation Modal Elements
  const confirmDeleteModal = document.getElementById('confirmDeleteModal');
  const deleteManagerName = document.getElementById('deleteManagerName');
  const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
  const cancelDeleteBtns = document.querySelectorAll('.confirm-cancel');

  // Edit Manager Modal Elements
  const editManagerModal = document.getElementById('editManagerModal');
  const editManagerForm = document.getElementById('editManagerForm');
  const editManagerId = document.getElementById('editManagerId');
  const editManagerName = document.getElementById('editManagerName');
  const editModalClose = document.querySelector('.edit-modal-close');
  const editModalCancel = document.querySelector('.edit-modal-cancel');

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

  // Delete Confirmation Variables
  let currentDeleteManagerId = null;
  let currentDeleteManagerName = null;
  let currentDeleteButton = null;

  // Modal toggle functions
  function toggleModal(modal, show) {
    if (show) {
      modal.classList.remove('hidden');
    } else {
      modal.classList.add('hidden');
    }
  }

  // Filter toggle functionality
  function initFilterToggle() {
    if (!filterToggle || !filterSidebar) return;

    filterToggle.addEventListener('click', () => {
      if (window.innerWidth >= 1024) {
        desktopSidebarHidden = !desktopSidebarHidden;
        if (desktopSidebarHidden) {
          filterSidebar.classList.add('hidden-desktop');
          mainContent.classList.add('expanded-by-sidebar');
          filterToggle.setAttribute('aria-pressed', 'true');
        } else {
          filterSidebar.classList.remove('hidden-desktop');
          mainContent.classList.remove('expanded-by-sidebar');
          filterToggle.setAttribute('aria-pressed', 'false');
        }
      } else {
        const isOpen = !filterSidebar.classList.contains('-translate-x-full');
        if (isOpen) {
          filterSidebar.classList.add('-translate-x-full');
          sidebarOverlay.classList.add('hidden');
        } else {
          filterSidebar.classList.remove('-translate-x-full');
          sidebarOverlay.classList.remove('hidden');
        }
      }
    });

    closeFilters.addEventListener('click', () => {
      filterSidebar.classList.add('-translate-x-full');
      sidebarOverlay.classList.add('hidden');
    });

    sidebarOverlay.addEventListener('click', () => {
      filterSidebar.classList.add('-translate-x-full');
      sidebarOverlay.classList.add('hidden');
    });

    window.addEventListener('resize', () => {
      if (window.innerWidth >= 1024) {
        sidebarOverlay.classList.add('hidden');
        if (desktopSidebarHidden) {
          filterSidebar.classList.add('hidden-desktop');
        } else {
          filterSidebar.classList.remove('hidden-desktop');
        }
      } else {
        filterSidebar.classList.add('-translate-x-full');
        sidebarOverlay.classList.add('hidden');
      }
    });
  }

  // Initialize filter sidebar functionality
  function initFilterSidebar() {
    if (!filterToggle || !filterSidebar) return;

    // Filter event listeners
    if (searchManager) {
      searchManager.addEventListener('input', debounce(applyFilters, 300));
    }

    if (statusFilter) {
      statusFilter.addEventListener('change', applyFilters);
    }

    if (recentFilter) {
      recentFilter.addEventListener('change', applyFilters);
    }

    if (clearFilters) {
      clearFilters.addEventListener('click', () => {
        if (searchManager) searchManager.value = '';
        if (statusFilter) statusFilter.value = '';
        if (recentFilter) recentFilter.value = 'oldest';
        applyFilters();
      });
    }
  }

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

  function applyFilters() {
    if (!managersTableBody) return;

    if (loadingState) loadingState.classList.remove('hidden');
    if (emptyState) emptyState.classList.add('hidden');

    updateActiveFilters();

    try {
      const managerRows = Array.from(managersTableBody.querySelectorAll('.manager-row'));
      let filteredRows = [...managerRows];

      // --- Search filter ---
      if (searchManager && searchManager.value.trim()) {
        const term = searchManager.value.toLowerCase().trim();
        filteredRows = filteredRows.filter(row => {
          const nameEl = row.querySelector('.manager-name-text');
          return nameEl && nameEl.textContent.toLowerCase().includes(term);
        });
      }

      // --- Status filter ---
      if (statusFilter && statusFilter.value && statusFilter.value !== 'all') {
        const statusVal = statusFilter.value.toLowerCase();
        filteredRows = filteredRows.filter(row => (row.dataset.status || '').toLowerCase() === statusVal);
      }

      // --- Recent/Oldest sorting ---
      if (recentFilter && recentFilter.value) {
        filteredRows.sort((a, b) => {
          const dateA = parseDate(a.dataset.createdAt);
          const dateB = parseDate(b.dataset.createdAt);

          if (recentFilter.value === 'recent') {
            // Recently Created: newest first (descending)
            return dateB - dateA;
          } else if (recentFilter.value === 'oldest') {
            // Oldest First: oldest first (ascending)
            return dateA - dateB;
          }
          return 0;
        });
      }

      // --- Show/hide rows ---
      managerRows.forEach(row => {
        row.style.display = filteredRows.includes(row) ? '' : 'none';
      });

      // --- Reorder the table based on filtered/sorted rows ---
      filteredRows.forEach(row => {
        managersTableBody.appendChild(row);
      });

      // --- Empty state ---
      if (emptyState) {
        const anyVisible = filteredRows.length > 0;
        emptyState.classList.toggle('hidden', anyVisible);
      }
    } catch (err) {
      console.error('Error filtering managers:', err);
      if (emptyState) emptyState.classList.remove('hidden');
    } finally {
      if (loadingState) loadingState.classList.add('hidden');
    }
  }

  // Helper function to parse dates safely
  function parseDate(dateString) {
    if (!dateString) return 0;
    
    // Try parsing ISO format first
    let timestamp = Date.parse(dateString);
    if (!isNaN(timestamp)) return timestamp;
    
    return 0; // Return 0 for invalid dates
  }

  function updateActiveFilters() {
    if (!activeFilters) return;
    activeFilters.innerHTML = '';

    if (searchManager && searchManager.value.trim()) {
      addActiveFilterBadge('Search', searchManager.value, 'search');
    }
    if (statusFilter && statusFilter.value) {
      addActiveFilterBadge('Status', statusFilter.value, 'status');
    }
    if (recentFilter && recentFilter.value === 'recent') {
      addActiveFilterBadge('Sort', 'Recently Created', 'recent');
    }
  }

  function addActiveFilterBadge(label, value, type) {
    const badge = document.createElement('div');
    badge.className = 'bg-gray-100 text-gray-800 px-3 py-1 rounded-full text-sm flex items-center border border-gray-200';
    badge.innerHTML = `
      <span class="font-medium">${label}:</span>
      <span class="ml-1">${value}</span>
      <button type="button" class="ml-2 text-gray-600 hover:text-gray-800 font-bold" data-filter-type="${type}">&times;</button>
    `;
    activeFilters.appendChild(badge);
    
    badge.querySelector('button').addEventListener('click', (e) => {
      e.stopPropagation();
      removeFilter(type);
    });
  }

  function removeFilter(type) {
    switch(type) {
      case 'search': 
        if (searchManager) searchManager.value = ''; 
        break;
      case 'status': 
        if (statusFilter) statusFilter.value = ''; 
        break;
      case 'recent': 
        if (recentFilter) recentFilter.value = 'oldest'; 
        break;
    }
    applyFilters();
  }

  // Initialize delete confirmation functionality
  function initDeleteConfirmation() {
    if (!confirmDeleteModal) return;

    // Confirm delete button handler
    confirmDeleteBtn.addEventListener('click', performDeletion);
    
    // Modal close handlers
    cancelDeleteBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        toggleModal(confirmDeleteModal, false);
        resetDeleteContext();
      });
    });
    
    // Close modal when clicking outside
    confirmDeleteModal.addEventListener('click', (e) => {
      if (e.target === confirmDeleteModal) {
        toggleModal(confirmDeleteModal, false);
        resetDeleteContext();
      }
    });
  }

  // Initialize edit manager modal functionality
  function initEditManagerModal() {
    if (!editManagerModal) return;

    // Close modal handlers
    editModalClose.addEventListener('click', () => toggleModal(editManagerModal, false));
    editModalCancel.addEventListener('click', () => toggleModal(editManagerModal, false));

    // Close modal when clicking outside
    editManagerModal.addEventListener('click', (e) => {
      if (e.target === editManagerModal) {
        toggleModal(editManagerModal, false);
      }
    });

    // Form submission handler
    editManagerForm.addEventListener('submit', handleEditManager);
  }

  function openEditModal(managerId, managerName, editUrl) {
    // Set form values
    editManagerId.value = managerId;
    editManagerName.value = managerName;
    
    // Clear any validation errors
    editManagerName.classList.remove('error');
    const errorElement = document.getElementById('editManagerName_error');
    if (errorElement) {
      errorElement.classList.add('hidden');
    }
    
    // Store edit URL in form dataset
    editManagerForm.dataset.editUrl = editUrl;
    
    // Show modal
    toggleModal(editManagerModal, true);
    editManagerName.focus();
    
    // Close any open dropdowns
    closeAllDropdowns();
  }

  async function handleEditManager(e) {
    e.preventDefault();
    
    const managerId = editManagerId.value;
    const editUrl = editManagerForm.dataset.editUrl;
    const newName = editManagerName.value.trim();
    
    // Validation
    if (!newName) { 
      editManagerName.classList.add('error');
      const errorElement = document.getElementById('editManagerName_error');
      if (errorElement) {
        errorElement.classList.remove('hidden');
      }
      showToast('Manager name is required', true); 
      return; 
    }

    const saveBtn = editManagerForm.querySelector('button[type="submit"]');
    const originalText = saveBtn.textContent;
    
    try {
      saveBtn.disabled = true;
      saveBtn.innerHTML = `
        <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
        Saving...
      `;
      
      const formData = new FormData();
      formData.append('manager_name', newName);
      formData.append('manager_id', managerId);

      const response = await fetch(editUrl, {
        method: 'POST',
        body: formData
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `HTTP ${response.status}`);
      }
      
      // Try to parse as JSON, but if it fails, assume success
      let data;
      try {
        data = await response.json();
      } catch (jsonError) {
        // If it's not JSON, assume the update was successful
        data = { success: true, manager_name: newName };
      }
      
      if (data.success || response.ok) {
        // Update UI for all manager elements with this ID
        const managerElements = document.querySelectorAll(`.manager-row[data-manager-id="${managerId}"]`);
        
        managerElements.forEach(managerElement => {
          // Update name
          const nameElement = managerElement.querySelector('.manager-name-text');
          if (nameElement) nameElement.textContent = data.manager_name || newName;
          
          // Update the data-name attribute on the edit button
          const editBtn = managerElement.querySelector('.edit-manager-btn');
          if (editBtn) {
            editBtn.dataset.name = data.manager_name || newName;
          }
          
          // Update the data-name attribute on the delete button
          const deleteBtn = managerElement.querySelector('.manager-delete');
          if (deleteBtn) {
            deleteBtn.dataset.name = data.manager_name || newName;
          }
        });
        
        showToast(data.message || `Manager "${data.manager_name || newName}" updated successfully`);
        toggleModal(editManagerModal, false);
      } else {
        throw new Error(data.message || 'Failed to update manager');
      }
      
    } catch(err) {
      console.error('Edit manager error:', err);
      
      // If there's an error but the update actually worked (common with Flask redirects)
      // We'll still update the UI and show success message
      if (err.message.includes('redirect') || response && response.ok) {
        // Update UI anyway since the request was successful
        const managerElements = document.querySelectorAll(`.manager-row[data-manager-id="${managerId}"]`);
        
        managerElements.forEach(managerElement => {
          const nameElement = managerElement.querySelector('.manager-name-text');
          if (nameElement) nameElement.textContent = newName;
          
          const editBtn = managerElement.querySelector('.edit-manager-btn');
          if (editBtn) editBtn.dataset.name = newName;
          
          const deleteBtn = managerElement.querySelector('.manager-delete');
          if (deleteBtn) deleteBtn.dataset.name = newName;
        });
        
        showToast(`Manager "${newName}" updated successfully`);
        toggleModal(editManagerModal, false);
      } else {
        showToast('Error updating manager: ' + err.message, true);
      }
    } finally {
      saveBtn.disabled = false;
      saveBtn.innerHTML = `Save Changes`;
    }
  }

  function showDeleteConfirmation(managerName) {
    // Update modal content with manager name
    deleteManagerName.textContent = managerName;
    
    // Show modal
    toggleModal(confirmDeleteModal, true);
  }

  async function performDeletion() {
    if (!currentDeleteManagerId || !currentDeleteButton) return;

    const managerId = currentDeleteManagerId;
    const managerName = currentDeleteManagerName;
    const deleteUrl = currentDeleteButton.dataset.deleteUrl;

    // Get ALL manager elements
    const managerElements = document.querySelectorAll(`.manager-row[data-manager-id="${managerId}"]`);
    
    // Add deleting class to ALL elements
    managerElements.forEach(managerElement => {
      managerElement.classList.add('deleting');
    });

    // Close modal
    toggleModal(confirmDeleteModal, false);

    try {
      const res = await fetch(deleteUrl, {
        method: "POST",
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'application/json'
        }
      });

      if (res.ok) {
        setTimeout(() => {
          // Remove ALL manager elements
          managerElements.forEach(managerElement => {
            managerElement.remove();
          });
          showToast(`"${managerName}" deleted successfully`);
        }, 400);
      } else {
        // Remove deleting class if failed
        managerElements.forEach(managerElement => {
          managerElement.classList.remove('deleting');
        });
        showToast('Failed to delete manager', true);
      }
    } catch (err) {
      console.error("Error deleting manager:", err);
      // Remove deleting class if error
      managerElements.forEach(managerElement => {
        managerElement.classList.remove('deleting');
      });
      showToast('Network error', true);
    } finally {
      resetDeleteContext();
    }
  }

  function resetDeleteContext() {
    currentDeleteManagerId = null;
    currentDeleteManagerName = null;
    currentDeleteButton = null;
  }

  // Initialize manager creation functionality
  function initManagerCreationDialog() {
    if (!managerCreationDialog) return;
    
    openManagerDialogBtn.addEventListener('click', () => {
      toggleModal(managerCreationDialog, true);
      managerCreationForm.reset();
      resetJobFields();
      document.getElementById('manager_name').focus();
    });
    
    function closeManagerDialog() {
      toggleModal(managerCreationDialog, false);
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
      
      // Clear any previous validation errors
      const titleInput = document.getElementById('add_job_title');
      const descInput = document.getElementById('add_job_description');
      if (titleInput) {
        titleInput.classList.remove('error');
      }
      if (descInput) {
        descInput.classList.remove('error');
      }
      
      const titleError = document.getElementById('add_job_title_error');
      const descError = document.getElementById('add_job_description_error');
      if (titleError) {
        titleError.classList.add('hidden');
      }
      if (descError) {
        descError.classList.add('hidden');
      }
      
      // Use the provided URL from data attribute
      if (addJobUrl) {
        addJobForm.action = addJobUrl;
      } else {
        // Fallback to the correct URL pattern
        addJobForm.action = `/clients/vendors/vendors/${managerId}/add-job-from-list`;
      }
      
      toggleModal(addJobDialog, true);
      
      // Focus on title field after a small delay to ensure dialog is visible
      setTimeout(() => {
        const titleInput = document.getElementById('add_job_title');
        if (titleInput) titleInput.focus();
      }, 100);
    }

    function closeAddJobDialog() {
      toggleModal(addJobDialog, false);
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
    document.addEventListener('click', (e) => {
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

  async function handleAddJob(e) {
    e.preventDefault();
    
    const titleInput = document.getElementById('add_job_title');
    const descInput = document.getElementById('add_job_description');
    
    const jobTitle = titleInput ? titleInput.value.trim() : '';
    const jobDescription = descInput ? descInput.value.trim() : '';

    // Validation for both fields
    let hasErrors = false;

    if (!jobTitle) {
      titleInput.classList.add('error');
      const errorElement = document.getElementById('add_job_title_error');
      if (errorElement) {
        errorElement.classList.remove('hidden');
      }
      hasErrors = true;
    }

    if (!jobDescription) {
      descInput.classList.add('error');
      const errorElement = document.getElementById('add_job_description_error');
      if (errorElement) {
        errorElement.classList.remove('hidden');
      }
      hasErrors = true;
    }

    if (hasErrors) {
      showToast('Please fill in all required fields', true);
      return;
    }

    if (!currentManagerId) {
      showToast('Manager ID is missing!', true);
      return;
    }

    const submitBtn = addJobForm.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;

    try {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `
        <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
        Adding...
      `;

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

      // Handle both JSON and HTML responses properly
      const contentType = response.headers.get('content-type');
      let responseData;

      if (contentType && contentType.includes('application/json')) {
        responseData = await response.json();
      } else {
        // If it's not JSON, it might be a redirect or HTML response
        const textResponse = await response.text();
        
        // Try to parse as JSON anyway (in case content-type is wrong)
        try {
          responseData = JSON.parse(textResponse);
        } catch {
          // If it's not JSON, check if the request was successful
          if (response.ok) {
            // Assume success for non-JSON responses with OK status
            responseData = { success: true };
          } else {
            // If not successful and not JSON, create error object
            responseData = { 
              success: false, 
              message: textResponse || 'Failed to add job' 
            };
          }
        }
      }

      if (response.ok) {
        // Check both response.ok and responseData.success
        if (responseData.success !== false) {
          showToast(`Job "${jobTitle}" added successfully to ${currentManagerName}!`);
          toggleModal(addJobDialog, false);
        } else {
          // Handle server-side validation errors
          const errorMessage = responseData.message || responseData.detail || 'Failed to add job';
          
          // Check for duplicate job error messages
          if (errorMessage.toLowerCase().includes('already exists') || 
              errorMessage.toLowerCase().includes('duplicate')) {
            showToast(`Job "${jobTitle}" already exists for this manager!`, true);
          } else {
            showToast(errorMessage, true);
          }
        }
      } else {
        // Handle HTTP error status
        const errorMessage = responseData.message || responseData.detail || `Failed to add job (HTTP ${response.status})`;
        
        // Check for duplicate job error messages
        if (errorMessage.toLowerCase().includes('already exists') || 
            errorMessage.toLowerCase().includes('duplicate')) {
          showToast(`Job "${jobTitle}" already exists for this manager!`, true);
        } else {
          showToast(errorMessage, true);
        }
      }

    } catch (err) {
      console.error('Error adding job:', err);
      showToast('Network error adding job: ' + err.message, true);
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `Add Job`;
    }
  }

  // Enhanced manager creation with better error handling
  async function handleManagerCreation(e) {
    e.preventDefault();
    
    const formData = new FormData(managerCreationForm);
    const managerName = formData.get('manager_name').trim();
    
    // Validate manager name
    if (!managerName) {
      const managerNameInput = document.getElementById('manager_name');
      managerNameInput.classList.add('error');
      const errorElement = document.getElementById('manager_name_error');
      if (errorElement) {
        errorElement.classList.remove('hidden');
      }
      showToast('Manager name is required!', true);
      return;
    }

    // Get all job entries and validate them
    const jobEntries = document.querySelectorAll('.managers-job-entry');
    let hasJobErrors = false;
    const jobTitles = [];
    
    jobEntries.forEach((entry, index) => {
      const titleInput = entry.querySelector(`#job_title_${index}`);
      const descInput = entry.querySelector(`#job_description_${index}`);
      const titleError = entry.querySelector(`#job_title_${index}_error`);
      const descError = entry.querySelector(`#job_description_${index}_error`);
      
      const jobTitle = titleInput ? titleInput.value.trim() : '';
      const jobDescription = descInput ? descInput.value.trim() : '';
      
      // Clear previous errors
      if (titleInput) titleInput.classList.remove('error');
      if (descInput) descInput.classList.remove('error');
      if (titleError) titleError.classList.add('hidden');
      if (descError) descError.classList.add('hidden');
      
      // Validate job title
      if (!jobTitle) {
        if (titleInput) titleInput.classList.add('error');
        if (titleError) titleError.classList.remove('hidden');
        hasJobErrors = true;
      }
      
      // Validate job description
      if (!jobDescription) {
        if (descInput) descInput.classList.add('error');
        if (descError) descError.classList.remove('hidden');
        hasJobErrors = true;
      }
      
      if (jobTitle) {
        jobTitles.push(jobTitle);
      }
    });
    
    if (hasJobErrors) {
      showToast('Please fill in all required job fields', true);
      return;
    }

    if (jobTitles.length === 0) {
      showToast('At least one job is required!', true);
      return;
    }

    // Check for duplicate job titles in the form itself
    const uniqueTitles = new Set(jobTitles.map(title => title.toLowerCase().trim()));
    if (uniqueTitles.size !== jobTitles.length) {
      showToast('Duplicate job titles are not allowed in the same manager!', true);
      return;
    }

    const submitBtn = managerCreationForm.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;
    
    try {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `
        <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
        Creating...
      `;

      const response = await fetch(managerCreationForm.action, {
        method: 'POST',
        body: formData,
        credentials: 'same-origin'
      });

      // Handle both JSON and HTML responses properly
      const contentType = response.headers.get('content-type');
      let responseData;

      if (contentType && contentType.includes('application/json')) {
        responseData = await response.json();
      } else {
        // If it's not JSON, it might be a redirect or HTML response
        const textResponse = await response.text();
        
        // Try to parse as JSON anyway (in case content-type is wrong)
        try {
          responseData = JSON.parse(textResponse);
        } catch {
          // If it's not JSON, check if the request was successful
          if (response.ok) {
            // Assume success for non-JSON responses with OK status
            responseData = { success: true };
          } else {
            // If not successful and not JSON, create error object
            responseData = { 
              success: false, 
              message: textResponse || 'Failed to add manager' 
            };
          }
        }
      }
      
      if (response.ok) {
        if (responseData.success !== false) {
          showToast(`Manager "${managerName}" created successfully with ${jobTitles.length} job(s)`);
          toggleModal(managerCreationDialog, false);
          
          // Reload the page to show the new manager
          setTimeout(() => {
            window.location.reload();
          }, 1500);
        } else {
          // Handle server-side validation errors
          const errorMessage = responseData.message || responseData.detail || 'Failed to add manager';
          
          // Check for duplicate job error messages
          if (errorMessage.toLowerCase().includes('already exists') || 
              errorMessage.toLowerCase().includes('duplicate')) {
            
            // Extract job title from error message if possible
            const jobMatch = errorMessage.match(/job[^"]*"([^"]+)"/i);
            const duplicateJob = jobMatch ? jobMatch[1] : 'a job';
            showToast(`Job "${duplicateJob}" already exists! Please use a different job title.`, true);
          } else {
            showToast(errorMessage, true);
          }
        }
      } else {
        // Handle HTTP error status
        const errorMessage = responseData.message || responseData.detail || `Failed to add manager (HTTP ${response.status})`;
        
        // Check for duplicate job error messages
        if (errorMessage.toLowerCase().includes('already exists') || 
            errorMessage.toLowerCase().includes('duplicate')) {
          
          const jobMatch = errorMessage.match(/job[^"]*"([^"]+)"/i);
          const duplicateJob = jobMatch ? jobMatch[1] : 'a job';
          showToast(`Job "${duplicateJob}" already exists! Please use a different job title.`, true);
        } else {
          showToast(errorMessage, true);
        }
      }
    } catch (err) {
      console.error('Error creating manager:', err);
      showToast('Network error adding manager: ' + err.message, true);
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `Create Manager`;
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
    jobEntry.className = 'managers-job-entry bg-gray-50 border border-gray-200 rounded-md p-4 mb-4';
    jobEntry.setAttribute('data-job-index', jobIndex);
    
    jobEntry.innerHTML = `
      <label class="block text-gray-600 font-medium mb-1">Job Title *</label>
      <input type="text" name="job_title" id="job_title_${jobIndex}" required 
             class="w-full border border-gray-300 rounded-md p-3 mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent">
      <div class="field-error bg-red-50 border border-red-200 rounded px-3 py-2 mb-4 hidden" id="job_title_${jobIndex}_error">
        <span class="text-red-600 text-sm font-medium">⚠️ Please enter a job title</span>
      </div>

      <label class="block text-gray-600 font-medium mb-1">Job Description</label>
      <textarea name="job_description" id="job_description_${jobIndex}" 
                class="w-full border border-gray-300 rounded-md p-3 h-28 mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"></textarea>
      <div class="field-error bg-red-50 border border-red-200 rounded px-3 py-2 mb-4 hidden" id="job_description_${jobIndex}_error">
        <span class="text-red-600 text-sm font-medium">⚠️ Please enter a job description</span>
      </div>
      ${jobIndex > 0 ? '<button type="button" class="managers-remove-job text-red-600 hover:text-red-800 font-medium">Remove Job</button>' : ''}
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

  // Close all dropdowns
  function closeAllDropdowns() {
    document.querySelectorAll('.dropdown-menu.show').forEach(menu => {
      // Return menu to its original container
      const originalContainer = menu._originalContainer;
      if (originalContainer && !originalContainer.contains(menu)) {
        originalContainer.appendChild(menu);
      }

      menu.classList.remove('show');
      menu.classList.add('hidden');
      menu.style.top = '';
      menu.style.left = '';
    });

    document.querySelectorAll('.dropdown-toggle').forEach(btn => {
      btn.setAttribute('aria-expanded', 'false');
    });
  }

  function initDropdowns() {
    document.querySelectorAll('.dropdown-toggle').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();

        const container = btn.closest('.dropdown-container');
        const menu = container.querySelector('.dropdown-menu');
        const expanded = btn.getAttribute('aria-expanded') === 'true';

        // Close any other open dropdowns first
        closeAllDropdowns();

        if (!expanded) {
          // Save where the menu originally came from
          menu._originalContainer = container;

          // Move menu to body
          document.body.appendChild(menu);

          // Calculate position (right side of button)
          const rect = btn.getBoundingClientRect();
          const scrollTop = window.scrollY || document.documentElement.scrollTop;
          const scrollLeft = window.scrollX || document.documentElement.scrollLeft;

          menu.style.position = 'absolute';
          menu.style.top = `${rect.top + scrollTop}px`;
          menu.style.left = `${rect.right + scrollLeft + 8}px`; // 8px gap

          menu.classList.remove('hidden');
          menu.classList.add('show');
          btn.setAttribute('aria-expanded', 'true');
        }
      });
    });

    // Close when clicking outside
    document.addEventListener('click', closeAllDropdowns);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeAllDropdowns();
    });

    // Reposition while scrolling if open
    window.addEventListener('scroll', () => {
      const openMenu = document.querySelector('.dropdown-menu.show');
      if (openMenu) {
        const btn = document.querySelector('.dropdown-toggle[aria-expanded="true"]');
        if (btn) {
          const rect = btn.getBoundingClientRect();
          openMenu.style.top = `${rect.top + window.scrollY}px`;
          openMenu.style.left = `${rect.right + window.scrollX + 8}px`;
        }
      }
    }, { passive: true });
  }

  // Toggle status functionality - UPDATED FOR BLACK TEXT AND LARGER FONT
  function initToggleStatus() {
    document.addEventListener('change', async (e) => {
      if (e.target.classList.contains('manager-toggle-input')) {
        const toggle = e.target;
        const managerId = toggle.dataset.managerId;
        const managerName = toggle.dataset.name;
        const toggleUrl = toggle.dataset.toggleUrl;
        const isActive = toggle.checked;
        
        try {
          const response = await fetch(toggleUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({
              status: isActive ? 'active' : 'inactive'
            })
          });

          if (response.ok) {
            // Update the status badge and data attribute - BLACK TEXT AND LARGER FONT
            const managerRow = document.querySelector(`.manager-row[data-manager-id="${managerId}"]`);
            if (managerRow) {
              managerRow.dataset.status = isActive ? 'active' : 'inactive';
              
              // Update status badge - BLACK TEXT AND LARGER FONT FOR BOTH STATUSES
              const statusBadge = managerRow.querySelector('.manager-status-text');
              if (statusBadge) {
                statusBadge.textContent = isActive ? 'Active' : 'Inactive';
                // UPDATED: Black text color and larger font size for both active and inactive
                statusBadge.className = `manager-status-text text-sm font-medium text-gray-900`;
              }
            }
            
            showToast(`Manager "${managerName}" ${isActive ? 'activated' : 'deactivated'} successfully`);
          } else {
            // Revert the toggle if the request failed
            toggle.checked = !isActive;
            showToast('Failed to update manager status', true);
          }
        } catch (err) {
          console.error('Error toggling manager status:', err);
          // Revert the toggle on error
          toggle.checked = !isActive;
          showToast('Network error updating status', true);
        }
      }
    });
  }

  // Delegated click for menu actions
  function initTableEventHandlers() {
    document.addEventListener('click', async (e) => {
      // Handle edit with popup modal
      const edt = e.target.closest('.edit-manager-btn');
      if (edt) {
        e.preventDefault();
        e.stopPropagation();
        
        const managerId = edt.dataset.managerId;
        const managerName = edt.dataset.name;
        const editUrl = edt.dataset.editUrl;
        
        if (!managerId || !editUrl) {
          showToast('Manager ID or edit URL is missing!', true);
          return;
        }
        
        openEditModal(managerId, managerName, editUrl);
        return;
      }

      // Handle delete with confirmation popup
      const del = e.target.closest('.manager-delete');
      if (del) {
        e.preventDefault();
        e.stopPropagation();
        
        const managerId = del.dataset.managerId;
        const managerName = del.dataset.name || 'Unnamed Manager';
        
        // Store current deletion context
        currentDeleteManagerId = managerId;
        currentDeleteManagerName = managerName;
        currentDeleteButton = del;
        
        // Close any open dropdowns
        closeAllDropdowns();
        
        // Show confirmation modal
        showDeleteConfirmation(managerName);
        return;
      }

      // Handle view details action
      const viewDetails = e.target.closest('.view-details-btn');
      if (viewDetails) {
        e.preventDefault();
        e.stopPropagation();
        
        // Fill modal fields with dataset values
        modalManagerName.textContent = viewDetails.dataset.managerName || '-';
        modalCreatedBy.textContent = viewDetails.dataset.createdBy || '-';
        modalCreatedAt.textContent = viewDetails.dataset.createdAt || '-';
        modalUpdatedBy.textContent = viewDetails.dataset.updatedBy || '-';
        modalUpdatedAt.textContent = viewDetails.dataset.updatedAt || '-';

        // Show modal
        toggleModal(managerDetailsModal, true);
        
        // Close any open dropdowns
        closeAllDropdowns();
        return;
      }

      // Handle view jobs action
      const viewJobs = e.target.closest('.view-jobs');
      if (viewJobs) {
        // Let the default link behavior happen
        return;
      }
    });
  }

  // View Details Modal handlers
  function initViewDetailsModal() {
    const closeModalBtn = document.getElementById('closeModal');
    const closeDetailsBtn = document.getElementById('closeDetailsButton');

    if (closeModalBtn) {
      closeModalBtn.addEventListener('click', () => toggleModal(managerDetailsModal, false));
    }
    if (closeDetailsBtn) {
      closeDetailsBtn.addEventListener('click', () => toggleModal(managerDetailsModal, false));
    }

    managerDetailsModal.addEventListener('click', (e) => {
      if (e.target === managerDetailsModal) {
        toggleModal(managerDetailsModal, false);
      }
    });
  }

  // Enhanced toast notification with icons
  function showToast(message, isError = false) {
    if (!managers.toastMessage || !managers.toast || !managers.toastIcon) return;
    
    managers.toastMessage.textContent = message;
    
    if (isError) {
      managers.toast.className = 'managers-toast error';
      managers.toastIcon.innerHTML = `
        <svg class="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
        </svg>
      `;
    } else {
      managers.toast.className = 'managers-toast';
      managers.toastIcon.innerHTML = `
        <svg class="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
        </svg>
      `;
    }
    
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

  if (managers.toastClose) {
    managers.toastClose.addEventListener('click', hideToast);
  }

  // Initialize all functionality
  function init() {
    // Initialize filter toggle
    initFilterToggle();
    
    // Initialize filter sidebar
    initFilterSidebar();
    
    // Initialize the manager creation dialog
    initManagerCreationDialog();
    
    // Initialize the add job dialog
    initAddJobDialog();

    // Initialize delete confirmation
    initDeleteConfirmation();

    // Initialize edit manager modal
    initEditManagerModal();

    // Initialize view details modal
    initViewDetailsModal();

    // Initialize dropdowns
    initDropdowns();

    // Initialize table event handlers
    initTableEventHandlers();

    // Initialize toggle status
    initToggleStatus();

    // Auto-hide toast on click outside
    document.addEventListener('click', (e) => {
      if (managers.toast && managers.toast.style.display === 'flex' && !e.target.closest('.managers-toast')) {
        hideToast();
      }
    });

    console.log('Managers JS loaded successfully with black text and larger font!');
  }

  // Start the initialization
  init();
});