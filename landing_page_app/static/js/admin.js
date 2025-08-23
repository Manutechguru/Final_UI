function showTab(tabId, event) {
    const tabs = document.querySelectorAll('.tab-content');
    const buttons = document.querySelectorAll('.tab-btn');

    tabs.forEach(tab => tab.classList.add('hidden'));
    buttons.forEach(btn => btn.classList.remove('bg-indigo-500', 'text-white'));

    document.getElementById(tabId).classList.remove('hidden');
    event.currentTarget.classList.add('bg-indigo-500', 'text-white');
}
