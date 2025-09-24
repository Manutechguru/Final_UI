// ====== GLOBAL VARIABLES ======
let clientToDeleteId = null;
let clientToEditId = null;

// ====== NOTIFICATION SYSTEM ======
function showNotification(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle';
    if (type === 'error') icon = 'fa-exclamation-circle';
    
    toast.innerHTML = `
        <i class="fas ${icon}"></i>
        <span>${message}</span>
    `;
    
    document.getElementById('notification-toast').appendChild(toast);
    
    // Remove toast after animation completes
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// ====== CREATE CLIENT MODAL ======
function showCreateDialog() {
    document.getElementById('createModal').style.display = 'block';
}

function closeCreateModal() {
    document.getElementById('createModal').style.display = 'none';
    document.getElementById('createClientForm').reset();
}

// Create form submission
document.getElementById('createClientForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const formData = new FormData(this);
    const clientName = formData.get('client_name').trim();
    
    if (!clientName) {
        showNotification("Client name is required!", "error");
        return;
    }
    
    try {
        const response = await fetch('/clients/new-arrivals', {
            method: 'POST',
            body: new URLSearchParams(formData)
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            showNotification(errorText || "Error creating client.", "error");
            return;
        }
        
        // Reload the page to show the new client
        window.location.reload();
    } catch(err) {
        showNotification("Something went wrong: " + err.message, "error");
    }
});

// ====== DELETE CLIENT MODAL ======
function showDeleteDialog(clientId, clientName) {
    clientToDeleteId = clientId;
    document.getElementById('clientToDeleteName').textContent = clientName;
    document.getElementById('deleteModal').style.display = 'block';
}

function closeModal() {
    document.getElementById('deleteModal').style.display = 'none';
    clientToDeleteId = null;
}

// Confirm delete action
document.getElementById('confirmDeleteBtn').addEventListener('click', async function() {
    if (!clientToDeleteId) return;
    
    try {
        const response = await fetch(`/clients/delete/${clientToDeleteId}`, { method:'POST' });
        if(!response.ok){ 
            const errorText = await response.text(); 
            showNotification(errorText || "Error deleting client.", "error");
            return; 
        }
        
        const data = await response.json();
        showNotification(data.message, "success");
        
        // Remove the row from the table
        const row = document.getElementById(`client-${clientToDeleteId}`);
        if(row) row.remove();
        
        updateSummaryCounts();
        closeModal();
    } catch(err) { 
        showNotification("Something went wrong: " + err.message, "error");
    }
});

// ====== EDIT CLIENT MODAL ======
function showEditDialog(clientId, clientName) {
    clientToEditId = clientId;
    document.getElementById('clientToEditId').value = clientId;
    document.getElementById('newClientName').value = clientName;
    document.getElementById('editError').style.display = 'none';
    document.getElementById('editModal').style.display = 'block';
}

function closeEditModal() {
    document.getElementById('editModal').style.display = 'none';
    clientToEditId = null;
}

// Edit form submission
document.getElementById('editClientForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const newName = document.getElementById('newClientName').value.trim();
    const errorElement = document.getElementById('editError');
    
    if (!newName) {
        errorElement.textContent = "Client name cannot be empty";
        errorElement.style.display = 'block';
        return;
    }
    
    try {
        const formData = new URLSearchParams();
        formData.append('new_name', newName);
        
        const response = await fetch(`/clients/edit/${clientToEditId}`, {
            method: 'POST',
            headers: {'Content-Type':'application/x-www-form-urlencoded'},
            body: formData
        });
        
        if (!response.ok) {
            if (response.status === 400 || response.status === 404) {
                const errorData = await response.json();
                errorElement.textContent = errorData.detail;
                errorElement.style.display = 'block';
                return;
            }
            throw new Error('Failed to update client');
        }
        
        // Update the client name in the table
        const row = document.getElementById(`client-${clientToEditId}`);
        if (row) {
            const nameCell = row.querySelector('.client-name');
            nameCell.textContent = newName;
        }
        
        showNotification("Client name updated successfully!", "success");
        closeEditModal();
    } catch(err) {
        errorElement.textContent = "Something went wrong: " + err.message;
        errorElement.style.display = 'block';
    }
});

// ====== TOGGLE ACTIVE ======
async function toggleActive(clientId, checkbox){
    try{
        const response = await fetch(`/clients/toggle/${clientId}`, { method:'POST' });
        if(!response.ok){ 
            const errorText = await response.text(); 
            showNotification(errorText || "Error updating status.", "error");
            checkbox.checked = !checkbox.checked; 
            return; 
        }
        
        const data = await response.json();
        const row = document.getElementById(`client-${clientId}`);
        if (row) {
            const statusText = row.querySelector('.status-text');
            statusText.textContent = data.new_status === "active" ? "Active" : "Inactive";
        }
        
        updateSummaryCounts();
        showNotification(`Client status updated to ${data.new_status}`, "success");
    } catch(err) { 
        showNotification("Something went wrong: " + err.message, "error");
        checkbox.checked = !checkbox.checked; 
    }
}

// ====== UPDATE COUNTS ======
function updateSummaryCounts(){
    const allRows = document.querySelectorAll('.clients-table tbody tr');
    let active = 0, inactive = 0;
    
    allRows.forEach(row => { 
        const checkbox = row.querySelector('.switch input');
        if (checkbox && checkbox.checked) active++; 
        else inactive++;
    });
    
    document.getElementById('activeCount').textContent = active;
    document.getElementById('inactiveCount').textContent = inactive;
    document.getElementById('totalCount').textContent = active + inactive;
}

// ====== SEARCH ======
document.getElementById('searchBox').addEventListener('input', function(){
    const query = this.value.toLowerCase();
    const rows = document.querySelectorAll('.clients-table tbody tr');
    
    rows.forEach(row => {
        const name = row.querySelector('.client-name').textContent.toLowerCase();
        row.style.display = name.includes(query) ? '' : 'none';
    });
});

// Close modals when clicking outside
window.addEventListener('click', function(e) {
    const createModal = document.getElementById('createModal');
    const deleteModal = document.getElementById('deleteModal');
    const editModal = document.getElementById('editModal');
    
    if (e.target === createModal) closeCreateModal();
    if (e.target === deleteModal) closeModal();
    if (e.target === editModal) closeEditModal();
});

// Initialize the page
document.addEventListener('DOMContentLoaded', function() {
    updateSummaryCounts();
});