document.addEventListener('DOMContentLoaded', function() {
  const passwordInput = document.getElementById('password');
  const passwordToggle = document.getElementById('passwordToggle');
  const loginForm = document.getElementById('loginForm');
  const validationMessage = document.getElementById('passwordValidation');
  
  // Toggle password visibility
  passwordToggle.addEventListener('click', function() {
    if (passwordInput.type === 'password') {
      passwordInput.type = 'text';
      passwordToggle.innerHTML = `
        <svg class="eye-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
          <line x1="1" y1="1" x2="23" y2="23"></line>
        </svg>
      `;
    } else {
      passwordInput.type = 'password';
      passwordToggle.innerHTML = `
        <svg class="eye-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
          <circle cx="12" cy="12" r="3"></circle>
        </svg>
      `;
    }
  });
  
  // Form validation
  loginForm.addEventListener('submit', function(e) {
    const email = document.getElementById('email').value;
    const password = passwordInput.value;
    
    const invalidCredentials = password === 'wrongpassword' || password === '' || !isValidEmail(email);
    
    if (invalidCredentials) {
      e.preventDefault();
      validationMessage.style.display = 'block';
      passwordInput.classList.add('input-error');
      setTimeout(() => passwordInput.classList.remove('input-error'), 400);
      passwordInput.focus();
    } else {
      validationMessage.style.display = 'none';
      console.log('Form submitted:', { email, password });
    }
  });
  
  // Clear validation on input
  passwordInput.addEventListener('input', function() {
    validationMessage.style.display = 'none';
  });
  
  function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }
});