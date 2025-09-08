document.addEventListener('DOMContentLoaded', function() {
  const passwordInput = document.getElementById('password');
  const passwordToggle = document.getElementById('passwordToggle');
  const signupForm = document.getElementById('signupForm');
  const strengthFill = document.getElementById('strengthFill');
  const successMessage = document.getElementById('successMessage');

  // Toggle password visibility
  passwordToggle.addEventListener('click', function() {
    if (passwordInput.type === 'password') {
      passwordInput.type = 'text';
      passwordToggle.innerHTML = `<svg class="eye-icon" xmlns="http://www.w3.org/2000/svg" fill="none" 
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" 
        viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 
        0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 
        9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 
        0 0 1-2.16 3.19m-6.72-1.07a3 
        3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" 
        x2="23" y2="23"></line></svg>`;
    } else {
      passwordInput.type = 'password';
      passwordToggle.innerHTML = `<svg class="eye-icon" xmlns="http://www.w3.org/2000/svg" fill="none" 
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" 
        viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 
        8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
    }
  });

  // Password strength meter
  passwordInput.addEventListener('input', function() {
    const password = passwordInput.value;
    const score = calculatePasswordStrength(password);
    updateStrengthMeter(score);
  });

  function calculatePasswordStrength(password) {
    let score = 0;
    if (password.length >= 6) score++;
    if (password.length >= 10) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;
    if (score <= 2) return 1;
    if (score <= 3) return 2;
    return 3;
  }

  function updateStrengthMeter(level) {
    strengthFill.style.width = (level * 33) + "%";
    if (level === 1) strengthFill.style.background = "#e53e3e";
    else if (level === 2) strengthFill.style.background = "#d69e2e";
    else if (level === 3) { strengthFill.style.background = "#38a169"; strengthFill.style.width = "100%"; }
    else strengthFill.style.width = "0%";
  }

  // Signup form submit with success message + redirect
  signupForm.addEventListener('submit', function(e) {
    e.preventDefault();

    const name = document.getElementById('full_name').value.trim();
    const email = document.getElementById('email').value.trim();
    const password = passwordInput.value;

    if (!name || !email || !password) {
      alert('Please fill in all fields before signing up.');
      return;
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      alert('Please enter a valid email address.');
      return;
    }

    // ✅ Submit via fetch to backend
    const formData = new FormData(signupForm);
    fetch(signupForm.action, {
      method: "POST",
      body: formData
    })
    .then(res => {
      if (res.ok) {
        // Show success message
        successMessage.classList.add('show');
        signupForm.style.display = "none";

        // Redirect after 2s
        setTimeout(() => {
          window.location.href = "/login";
        }, 3000);
      } else {
        alert("Signup failed. Please try again.");
      }
    })
    .catch(() => alert("Error occurred. Please try again."));
  });
});
