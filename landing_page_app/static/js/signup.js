// Basic client-side validation
document.querySelector(".signup-form").addEventListener("submit", function(e) {
  const name = document.getElementById("full_name").value.trim();
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();

  if (!name || !email || !password) {
    e.preventDefault();
    alert("Please fill in all fields before signing up.");
  }
});
