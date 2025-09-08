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

// ====== ADD CLIENT ======
const form = document.getElementById('addClientForm');
const clientsContainer = document.getElementById('clientsContainer');
const activeCountEl = document.getElementById('activeCount');
const inactiveCountEl = document.getElementById('inactiveCount');
const searchBox = document.getElementById('searchBox');

form.addEventListener('submit', async function(e){
    e.preventDefault();
    const clientName = form.client_name.value.trim();
    if(!clientName){ 
        showNotification("Client name is required!", "error");
        return; 
    }

    try{
        const response = await fetch('/clients/new-arrivals', {
            method: 'POST',
            headers: {'Content-Type':'application/x-www-form-urlencoded'},
            body: new URLSearchParams({client_name: clientName})
        });
        
        if(!response.ok){ 
            const errorText = await response.text(); 
            showNotification(errorText || "Error adding client.", "error");
            return; 
        }

        const html = await response.text();
        const doc = new DOMParser().parseFromString(html,'text/html');
        clientsContainer.innerHTML = doc.querySelector('#clientsContainer').innerHTML;
        
        // Update counts
        const activeCount = doc.querySelector('#activeCount').textContent;
        const inactiveCount = doc.querySelector('#inactiveCount').textContent;
        activeCountEl.textContent = activeCount;
        inactiveCountEl.textContent = inactiveCount;
        
        form.client_name.value = '';
        showNotification(`Client "${clientName}" added successfully!`, "success");
    }catch(err){ 
        showNotification("Something went wrong: " + err.message, "error");
    }
});

// ====== DROPDOWN ======
document.addEventListener('click', e => {
    document.querySelectorAll('.dropdown').forEach(dropdown => {
        if(dropdown.contains(e.target)) dropdown.classList.toggle('show');
        else dropdown.classList.remove('show');
    });
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
        
        const clientCard = document.getElementById(`client-${clientToDeleteId}`);
        if(clientCard) clientCard.remove();
        
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
        formData.append('updated_by', 'admin'); // You might want to get this from your auth system
        
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
        
        // Update the client name in the UI
        const clientCard = document.getElementById(`client-${clientToEditId}`);
        if (clientCard) {
            const nameElement = clientCard.querySelector('h3');
            nameElement.textContent = newName;
        }
        
        showNotification("Client name updated successfully!", "success");
        closeEditModal();
    } catch(err) {
        errorElement.textContent = "Something went wrong: " + err.message;
        errorElement.style.display = 'block';
    }
});

// Close modals when clicking outside
window.addEventListener('click', function(e) {
    const deleteModal = document.getElementById('deleteModal');
    const editModal = document.getElementById('editModal');
    
    if (e.target === deleteModal) {
        closeModal();
    }
    if (e.target === editModal) {
        closeEditModal();
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
        const statusText = checkbox.parentElement.nextElementSibling;
        statusText.textContent = data.new_status === "active" ? "Active" : "Inactive";
        
        updateSummaryCounts();
        showNotification(`Client status updated to ${data.new_status}`, "success");
    } catch(err) { 
        showNotification("Something went wrong: " + err.message, "error");
        checkbox.checked = !checkbox.checked; 
    }
}

// ====== UPDATE COUNTS ======
function updateSummaryCounts(){
    const allCards = document.querySelectorAll('.client-card');
    let active = 0, inactive = 0;
    
    allCards.forEach(card => { 
        card.querySelector('.switch input').checked ? active++ : inactive++; 
    });
    
    activeCountEl.textContent = active;
    inactiveCountEl.textContent = inactive;
}

// ====== SEARCH ======
searchBox.addEventListener('input', function(){
    const query = this.value.toLowerCase();
    document.querySelectorAll('.client-card').forEach(card => {
        const name = card.querySelector('h3').textContent.toLowerCase();
        card.style.display = name.includes(query) ? 'flex' : 'none';
    });
});

// Initialize the page
document.addEventListener('DOMContentLoaded', function() {
    updateSummaryCounts();
});