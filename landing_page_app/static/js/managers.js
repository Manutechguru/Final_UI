document.addEventListener("DOMContentLoaded", () => {

  // Toggle manager status
  document.querySelectorAll(".toggle-btn").forEach(button => {
    button.addEventListener("click", async (e) => {
      const managerId = button.dataset.id;
      try {
        const res = await fetch(`/vendors/toggle/${managerId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" }
        });
        const data = await res.json();
        if (res.ok) {
          const row = document.querySelector(`#manager-${managerId}`);
          const statusSpan = row.querySelector(".status-badge");
          statusSpan.textContent = data.new_status.charAt(0).toUpperCase() + data.new_status.slice(1);
          statusSpan.className = "status-badge " + data.new_status;
          button.textContent = data.new_status === "active" ? "Deactivate" : "Activate";
        }
      } catch (err) {
        alert("Error toggling status");
      }
    });
  });

  // Delete manager
  document.querySelectorAll(".delete-btn").forEach(button => {
    button.addEventListener("click", async (e) => {
      if (!confirm("Are you sure you want to delete this vendor?")) return;
      const managerId = button.dataset.id;
      try {
        const res = await fetch(`/vendors/delete/${managerId}`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
          document.querySelector(`#manager-${managerId}`).remove();
          alert(data.message);
        }
      } catch (err) {
        alert("Error deleting manager");
      }
    });
  });

});
