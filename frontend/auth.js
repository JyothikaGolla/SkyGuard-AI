// Authentication handling
const API_BASE = "http://127.0.0.1:5000";

// Check if user is already logged in
function checkAuth() {
    const token = localStorage.getItem('authToken');
    if (token) {
        // Verify token
        fetch(`${API_BASE}/api/auth/verify-token`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        })
        .then(res => {
            if (res.ok) {
                // Token is valid, redirect to main app
                window.location.href = 'index.html';
            } else {
                // Token invalid, clear it
                localStorage.removeItem('authToken');
                localStorage.removeItem('currentUser');
            }
        })
        .catch(() => {
            localStorage.removeItem('authToken');
            localStorage.removeItem('currentUser');
        });
    }
}

// Login form handler
const loginForm = document.getElementById('login-form');
if (loginForm) {
    checkAuth(); // Check if already logged in
    
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;
        const errorDiv = document.getElementById('error-message');
        const loginBtn = document.getElementById('login-btn');
        const btnText = loginBtn.querySelector('.btn-text');
        const btnLoader = loginBtn.querySelector('.btn-loader');
        
        // Clear previous errors
        errorDiv.classList.remove('show');
        errorDiv.textContent = '';
        
        // Show loading state
        loginBtn.disabled = true;
        btnText.style.display = 'none';
        btnLoader.style.display = 'flex';
        
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout
            
            const response = await fetch(`${API_BASE}/api/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email, password }),
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            const data = await response.json();
            
            if (response.ok) {
                // Store token and user info
                localStorage.setItem('authToken', data.token);
                localStorage.setItem('currentUser', JSON.stringify(data.user));
                
                // Redirect to main app
                window.location.href = 'index.html';
            } else if (data.error === 'account_deletion_pending' && data.can_cancel) {
                // Account deletion is pending - offer to cancel
                errorDiv.innerHTML = `
                    <strong>⚠️ Account Deletion Pending</strong><br>
                    ${data.message}<br>
                    <button id="cancel-deletion-login-btn" class="btn-primary" style="margin-top: 12px; padding: 8px 16px; font-size: 14px;">
                        Cancel Deletion & Login
                    </button>
                `;
                errorDiv.classList.add('show');
                
                // Add event listener to cancel button
                document.getElementById('cancel-deletion-login-btn').addEventListener('click', async () => {
                    try {
                        // First login to get token
                        const loginResponse = await fetch(`${API_BASE}/api/auth/login`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json'},
                            body: JSON.stringify({ email, password })
                        });
                        
                        if (!loginResponse.ok) {
                            errorDiv.textContent = 'Failed to authenticate. Please try again.';
                            return;
                        }
                        
                        const loginData = await loginResponse.json();
                        const tempToken = loginData.token;
                        
                        // Now cancel deletion with the token
                        const cancelResponse = await fetch(`${API_BASE}/api/user/account/cancel-deletion`, {
                            method: 'POST',
                            headers: {
                                'Authorization': `Bearer ${tempToken}`
                            }
                        });
                        
                        const cancelData = await cancelResponse.json();
                        
                        if (cancelResponse.ok) {
                            errorDiv.textContent = 'Account deletion cancelled! Logging you in...';
                            errorDiv.style.background = '#22c55e';
                            setTimeout(() => {
                                localStorage.setItem('authToken', tempToken);
                                localStorage.setItem('currentUser', JSON.stringify(loginData.user));
                                window.location.href = 'index.html';
                            }, 1500);
                        } else {
                            errorDiv.textContent = cancelData.error || 'Failed to cancel deletion';
                            errorDiv.style.background = '';
                        }
                    } catch (error) {
                        errorDiv.textContent = 'Failed to cancel deletion. Please try again.';
                        errorDiv.style.background = '';
                    }
                });
            } else {
                // Show error
                errorDiv.textContent = data.error || 'Login failed. Please try again.';
                errorDiv.classList.add('show');
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                errorDiv.textContent = 'Request timeout. Server may be starting up, please try again.';
            } else {
                errorDiv.textContent = 'Network error. Please ensure the backend server is running.';
            }
            errorDiv.classList.add('show');
        } finally {
            // Reset button state
            loginBtn.disabled = false;
            btnText.style.display = 'inline';
            btnLoader.style.display = 'none';
        }
    });
}

// Signup form handler
const signupForm = document.getElementById('signup-form');
if (signupForm) {
    checkAuth(); // Check if already logged in
    
    let currentStep = 1;
    let signupData = {};
    let otpTimer = null;
    let otpExpireTime = null;
    
    // Timer function
    function startOTPTimer() {
        if (otpTimer) clearInterval(otpTimer);
        
        otpExpireTime = Date.now() + (10 * 60 * 1000); // 10 minutes from now
        
        otpTimer = setInterval(() => {
            const remaining = Math.max(0, otpExpireTime - Date.now());
            const minutes = Math.floor(remaining / 60000);
            const seconds = Math.floor((remaining % 60000) / 1000);
            
            const timerDisplay = document.getElementById('timer-display');
            if (timerDisplay) {
                timerDisplay.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
            }
            
            if (remaining <= 0) {
                clearInterval(otpTimer);
                if (timerDisplay) {
                    timerDisplay.textContent = 'Expired';
                    timerDisplay.style.color = '#ef4444';
                }
            }
        }, 1000);
    }
    
    // Resend OTP button
    const resendOTPBtn = document.getElementById('resend-otp-btn');
    if (resendOTPBtn) {
        resendOTPBtn.addEventListener('click', async () => {
            const errorDiv = document.getElementById('error-message');
            errorDiv.classList.remove('show');
            
            resendOTPBtn.disabled = true;
            resendOTPBtn.textContent = 'Sending...';
            
            try {
                const response = await fetch(`${API_BASE}/api/auth/resend-otp`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        email: signupData.email,
                        purpose: 'signup'
                    })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    errorDiv.textContent = 'New verification code sent to your email!';
                    errorDiv.style.background = '#22c55e';
                    errorDiv.classList.add('show');
                    startOTPTimer();
                    
                    setTimeout(() => {
                        errorDiv.classList.remove('show');
                        errorDiv.style.background = '';
                    }, 3000);
                } else {
                    errorDiv.textContent = data.error || 'Failed to resend code';
                    errorDiv.classList.add('show');
                }
            } catch (error) {
                errorDiv.textContent = 'Network error. Please try again.';
                errorDiv.classList.add('show');
            } finally {
                resendOTPBtn.disabled = false;
                resendOTPBtn.textContent = 'Resend Code';
            }
        });
    }
    
    // Change email button
    const changeEmailBtn = document.getElementById('change-email-btn');
    if (changeEmailBtn) {
        changeEmailBtn.addEventListener('click', () => {
            currentStep = 1;
            document.getElementById('step1-fields').style.display = 'block';
            document.getElementById('step2-fields').style.display = 'none';
            document.getElementById('btn-text-step1').style.display = 'inline';
            document.getElementById('btn-text-step2').style.display = 'none';
            document.getElementById('otp_code').value = '';
            if (otpTimer) clearInterval(otpTimer);
        });
    }
    
    signupForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const errorDiv = document.getElementById('error-message');
        const signupBtn = document.getElementById('signup-btn');
        const btnText1 = document.getElementById('btn-text-step1');
        const btnText2 = document.getElementById('btn-text-step2');
        const btnLoader = signupBtn.querySelector('.btn-loader');
        const loaderText = document.getElementById('loader-text');
        
        // Clear previous errors
        errorDiv.classList.remove('show');
        errorDiv.textContent = '';
        errorDiv.style.background = '';
        
        if (currentStep === 1) {
            // Step 1: Send OTP
            const full_name = document.getElementById('full_name').value.trim();
            const username = document.getElementById('username').value.trim();
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;
            const confirm_password = document.getElementById('confirm_password').value;
            
            // Validate passwords match
            if (password !== confirm_password) {
                errorDiv.textContent = 'Passwords do not match';
                errorDiv.classList.add('show');
                return;
            }
            
            // Store signup data for later
            signupData = { full_name, username, email, password };
            
            // Show loading state
            signupBtn.disabled = true;
            btnText1.style.display = 'none';
            btnLoader.style.display = 'flex';
            loaderText.textContent = 'Sending verification code...';
            
            try {
                const response = await fetch(`${API_BASE}/api/auth/send-otp`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, purpose: 'signup' })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    // Move to step 2
                    currentStep = 2;
                    document.getElementById('step1-fields').style.display = 'none';
                    document.getElementById('step2-fields').style.display = 'block';
                    btnText1.style.display = 'none';
                    btnText2.style.display = 'inline';
                    document.getElementById('otp_code').focus();
                    
                    // Start timer
                    startOTPTimer();
                    
                    // Show success message
                    errorDiv.textContent = `Verification code sent to ${email}`;
                    errorDiv.style.background = '#22c55e';
                    errorDiv.classList.add('show');
                    
                    setTimeout(() => {
                        errorDiv.classList.remove('show');
                        errorDiv.style.background = '';
                    }, 5000);
                } else {
                    errorDiv.textContent = data.error || 'Failed to send verification code';
                    errorDiv.classList.add('show');
                }
            } catch (error) {
                errorDiv.textContent = 'Network error. Please check your connection.';
                errorDiv.classList.add('show');
            } finally {
                signupBtn.disabled = false;
                btnText1.style.display = 'inline';
                btnLoader.style.display = 'none';
            }
            
        } else if (currentStep === 2) {
            // Step 2: Verify OTP and complete registration
            const otp_code = document.getElementById('otp_code').value.trim();
            
            if (!otp_code || otp_code.length !== 6) {
                errorDiv.textContent = 'Please enter a valid 6-digit code';
                errorDiv.classList.add('show');
                return;
            }
            
            // Show loading state
            signupBtn.disabled = true;
            btnText2.style.display = 'none';
            btnLoader.style.display = 'flex';
            loaderText.textContent = 'Verifying...';
            
            try {
                // First verify OTP
                const verifyResponse = await fetch(`${API_BASE}/api/auth/verify-otp`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: signupData.email,
                        otp_code: otp_code,
                        purpose: 'signup'
                    })
                });
                
                const verifyData = await verifyResponse.json();
                
                if (!verifyResponse.ok) {
                    errorDiv.textContent = verifyData.error || 'Invalid verification code';
                    errorDiv.classList.add('show');
                    signupBtn.disabled = false;
                    btnText2.style.display = 'inline';
                    btnLoader.style.display = 'none';
                    return;
                }
                
                // OTP verified, now register
                loaderText.textContent = 'Creating account...';
                
                const registerResponse = await fetch(`${API_BASE}/api/auth/register`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(signupData)
                });
                
                const registerData = await registerResponse.json();
                
                if (registerResponse.ok) {
                    // Store token and user info
                    localStorage.setItem('authToken', registerData.token);
                    localStorage.setItem('currentUser', JSON.stringify(registerData.user));
                    
                    // Clear timer
                    if (otpTimer) clearInterval(otpTimer);
                    
                    // Redirect to main app
                    window.location.href = 'index.html';
                } else {
                    errorDiv.textContent = registerData.error || 'Registration failed. Please try again.';
                    errorDiv.classList.add('show');
                }
            } catch (error) {
                errorDiv.textContent = 'Network error. Please check your connection.';
                errorDiv.classList.add('show');
            } finally {
                // Reset button state
                signupBtn.disabled = false;
                btnText2.style.display = 'inline';
                btnLoader.style.display = 'none';
            }
        }
    });
}
