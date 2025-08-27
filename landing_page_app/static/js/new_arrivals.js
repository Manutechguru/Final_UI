// ====== ADD CLIENT ======
const form = document.getElementById('addClientForm');
const messageDiv = document.getElementById('message');
const errorDiv = document.getElementById('error');
const clientsContainer = document.getElementById('clientsContainer');
const activeCountEl = document.getElementById('activeCount');
const inactiveCountEl = document.getElementById('inactiveCount');
const searchBox = document.getElementById('searchBox');

form.addEventListener('submit', async function(e){
    e.preventDefault();
    messageDiv.innerHTML = '';
    errorDiv.innerHTML = '';
    const clientName = form.client_name.value.trim();
    if(!clientName){ errorDiv.innerHTML = "Client name is required!"; return; }

    try{
        const response = await fetch('/clients/new-arrivals', {
            method: 'POST',
            headers: {'Content-Type':'application/x-www-form-urlencoded'},
            body: new URLSearchParams({client_name: clientName})
        });
        if(!response.ok){ const errorText = await response.text(); errorDiv.innerHTML = errorText||"Error adding client."; return; }

        const html = await response.text();
        const doc = new DOMParser().parseFromString(html,'text/html');
        clientsContainer.innerHTML = doc.querySelector('#clientsContainer').innerHTML;
        messageDiv.innerHTML = doc.querySelector('#message').innerHTML;
        activeCountEl.textContent = doc.querySelector('#activeCount').textContent;
        inactiveCountEl.textContent = doc.querySelector('#inactiveCount').textContent;
        form.client_name.value = '';
    }catch(err){ errorDiv.innerHTML = "Something went wrong: "+err.message; }
});

// ====== DROPDOWN ======
document.addEventListener('click', e => {
    document.querySelectorAll('.dropdown').forEach(dropdown => {
        if(dropdown.contains(e.target)) dropdown.classList.toggle('show');
        else dropdown.classList.remove('show');
    });
});

// ====== DELETE CLIENT ======
async function deleteClient(clientId){
    clientId = Number(clientId);
    if(!confirm("Are you sure you want to delete this client and all its jobs?")) return;
    try{
        const response = await fetch(`/clients/delete/${clientId}`,{ method:'POST' });
        if(!response.ok){ const errorText = await response.text(); alert(errorText||"Error deleting client."); return; }
        const data = await response.json();
        alert(data.message);
        const clientCard = document.getElementById(`client-${clientId}`);
        if(clientCard) clientCard.remove();
        updateSummaryCounts();
    }catch(err){ alert("Something went wrong: "+err.message); }
}

// ====== TOGGLE ACTIVE ======
async function toggleActive(clientId, checkbox){
    try{
        const response = await fetch(`/clients/toggle/${clientId}`, { method:'POST' });
        if(!response.ok){ const errorText = await response.text(); alert(errorText||"Error updating status."); checkbox.checked = !checkbox.checked; return; }
        const data = await response.json();
        const statusText = checkbox.parentElement.nextElementSibling;
        statusText.textContent = data.new_status==="active"?"Active":"Inactive";
        updateSummaryCounts();
    }catch(err){ alert("Something went wrong: "+err.message); checkbox.checked = !checkbox.checked; }
}

// ====== UPDATE COUNTS ======
function updateSummaryCounts(){
    const allCards = document.querySelectorAll('.client-card');
    let active=0, inactive=0;
    allCards.forEach(card => { card.querySelector('.switch input').checked ? active++ : inactive++; });
    activeCountEl.textContent = active;
    inactiveCountEl.textContent = inactive;
}

// ====== SEARCH ======
searchBox.addEventListener('input', function(){
    const query = this.value.toLowerCase();
    document.querySelectorAll('.client-card').forEach(card=>{
        const name = card.querySelector('h3').textContent.toLowerCase();
        card.style.display = name.includes(query)?'flex':'none';
    });
});
