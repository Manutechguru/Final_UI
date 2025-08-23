// Example: simple client-side validation
document.querySelector(".login-form").addEventListener("submit", function(e) {
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();

  if (!email || !password) {
    e.preventDefault();
    alert("Please fill in all fields.");
  }
});
