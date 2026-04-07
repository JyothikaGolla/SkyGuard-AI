// Authentication check
function checkAuth() {
    const token = localStorage.getItem('authToken');
    const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
    
    if (!token || !currentUser.id) {
        window.location.href = 'login.html';
        return null;
    }
    
    return { token, currentUser };
}

// Logout function
function logout() {
    localStorage.removeItem('authToken');
    localStorage.removeItem('currentUser');
    window.location.href = 'login.html';
}

// Toggle user dropdown menu
function toggleUserMenu() {
    const dropdown = document.getElementById('user-dropdown');
    if (!dropdown) return;
    
    const isVisible = dropdown.style.display === 'block';
    dropdown.style.display = isVisible ? 'none' : 'block';
    
    if (!isVisible) {
        // Populate dropdown info
        const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
        const userEmail = localStorage.getItem('userEmail') || '';
        
        const dropdownUsername = document.getElementById('dropdown-username');
        const dropdownEmail = document.getElementById('dropdown-email');
        
        if (dropdownUsername) {
            dropdownUsername.textContent = currentUser.full_name || currentUser.username || '';
        }
        if (dropdownEmail) {
            dropdownEmail.textContent = userEmail || currentUser.email || '';
        }
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', function(event) {
    const userMenuContainer = document.getElementById('user-menu-container');
    const dropdown = document.getElementById('user-dropdown');
    
    if (dropdown && userMenuContainer && !userMenuContainer.contains(event.target)) {
        dropdown.style.display = 'none';
    }
});

// Initialize page
async function initPage() {
    const auth = checkAuth();
    if (!auth) return;
    
    const { currentUser } = auth;
    
    // Update header
    document.getElementById('user-name').textContent = currentUser.full_name || currentUser.username;
    
    // Show/hide admin button based on role
    const adminBtn = document.getElementById('admin-btn');
    if (currentUser.role !== 'admin' && adminBtn) {
        adminBtn.style.display = 'none';
    }
    
    // Load account status and profile
    await loadAccountStatus();
    await loadProfile();
}

// Load account status
async function loadAccountStatus() {
    const auth = checkAuth();
    if (!auth) return;
    
    // Set email from current user
    document.getElementById('user-email').textContent = auth.currentUser.email || '-';
    
    try {
        const response = await fetch(`${API_BASE}/api/user/account/status`, {
            headers: {
                'Authorization': `Bearer ${auth.token}`
            }
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Update status display
            const statusSpan = document.getElementById('account-status');
            if (data.deletion_requested) {
                statusSpan.textContent = '❌ Deletion Scheduled';
                statusSpan.style.color = '#ef4444';
                
                // Show deletion warning
                const warningDiv = document.getElementById('deletion-warning');
                const messageP = document.getElementById('deletion-message');
                warningDiv.style.display = 'block';
                messageP.innerHTML = `Your account deletion is scheduled for <strong>${new Date(data.deletion_scheduled_at).toLocaleDateString()}</strong> (${data.days_until_deletion} days remaining).<br>You can cancel this by clicking the button below.`;
                
                // Hide danger zone actions
                document.querySelector('.danger-zone').style.display = 'none';
            } else if (!data.is_active) {
                statusSpan.textContent = '⏸️ Deactivated';
                statusSpan.style.color = '#f59e0b';
            } else {
                statusSpan.textContent = '✅ Active';
                statusSpan.style.color = '#22c55e';
            }
            
            const emailVerifiedSpan = document.getElementById('email-verified');
            emailVerifiedSpan.textContent = data.email_verified ? '✓ Verified' : '✗ Not Verified';
            emailVerifiedSpan.style.color = data.email_verified ? '#22c55e' : '#94a3b8';
        }
    } catch (error) {
        console.error('Failed to load account status:', error);
    }
}

// Load profile
async function loadProfile() {
    const auth = checkAuth();
    if (!auth) return;
    
    // Set initial values from localStorage
    document.getElementById('full_name').value = auth.currentUser.full_name || '';
    document.getElementById('username').value = auth.currentUser.username || '';
    
    try {
        const response = await fetch(`${API_BASE}/api/auth/me`, {
            headers: {
                'Authorization': `Bearer ${auth.token}`
            }
        });
        
        const data = await response.json();
        
        if (response.ok && data.user) {
            // Update with fresh data from server
            document.getElementById('full_name').value = data.user.full_name || '';
            document.getElementById('username').value = data.user.username || '';
            
            // Update localStorage with fresh data
            localStorage.setItem('currentUser', JSON.stringify(data.user));
        }
    } catch (error) {
        console.error('Failed to load profile:', error);
        // Keep the values from localStorage that we already set
    }
}

// Show message
function showMessage(message, type = 'info') {
    const messageBox = document.getElementById('message-box');
    messageBox.textContent = message;
    messageBox.className = `message-box message-${type}`;
    messageBox.style.display = 'block';
    
    setTimeout(() => {
        messageBox.style.display = 'none';
    }, 5000);
}

// Deactivate account
document.getElementById('deactivate-btn').addEventListener('click', () => {
    document.getElementById('deactivate-modal').style.display = 'flex';
});

document.getElementById('cancel-deactivate-btn').addEventListener('click', () => {
    document.getElementById('deactivate-modal').style.display = 'none';
    document.getElementById('deactivate-form').reset();
});

document.getElementById('deactivate-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const auth = checkAuth();
    if (!auth) return;
    
    const password = document.getElementById('deactivate-password').value;
    const reason = document.getElementById('deactivate-reason').value;
    
    try {
        const response = await fetch(`${API_BASE}/api/user/account/deactivate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${auth.token}`
            },
            body: JSON.stringify({ password, reason })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showMessage('Account deactivated successfully. Logging out...', 'success');
            setTimeout(() => {
                localStorage.removeItem('authToken');
                localStorage.removeItem('currentUser');
                window.location.href = 'login.html';
            }, 2000);
        } else {
            showMessage(data.error || 'Failed to deactivate account', 'error');
        }
    } catch (error) {
        showMessage('Network error. Please try again.', 'error');
    }
    
    document.getElementById('deactivate-modal').style.display = 'none';
    document.getElementById('deactivate-form').reset();
});

// Delete account
document.getElementById('delete-btn').addEventListener('click', () => {
    document.getElementById('delete-modal').style.display = 'flex';
});

document.getElementById('cancel-delete-btn').addEventListener('click', () => {
    document.getElementById('delete-modal').style.display = 'none';
    document.getElementById('delete-form').reset();
});

document.getElementById('delete-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const auth = checkAuth();
    if (!auth) return;
    
    const password = document.getElementById('delete-password').value;
    const reason = document.getElementById('delete-reason').value;
    
    try {
        const response = await fetch(`${API_BASE}/api/user/account/request-deletion`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${auth.token}`
            },
            body: JSON.stringify({ password, reason })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showMessage(`Account deletion scheduled for ${new Date(data.deletion_scheduled_at).toLocaleDateString()}. You have 30 days to cancel. Logging out...`, 'success');
            setTimeout(() => {
                localStorage.removeItem('authToken');
                localStorage.removeItem('currentUser');
                window.location.href = 'login.html';
            }, 3000);
        } else {
            showMessage(data.error || 'Failed to request deletion', 'error');
        }
    } catch (error) {
        showMessage('Network error. Please try again.', 'error');
    }
    
    document.getElementById('delete-modal').style.display = 'none';
    document.getElementById('delete-form').reset();
});

// Cancel deletion
document.getElementById('cancel-deletion-btn')?.addEventListener('click', async () => {
    const auth = checkAuth();
    if (!auth) return;
    
    if (!confirm('Are you sure you want to cancel the deletion and reactivate your account?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/user/account/cancel-deletion`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${auth.token}`
            }
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showMessage('Account deletion cancelled! Your account has been reactivated.', 'success');
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else {
            showMessage(data.error || 'Failed to cancel deletion', 'error');
        }
    } catch (error) {
        showMessage('Network error. Please try again.', 'error');
    }
});

// Close modals on background click
document.querySelectorAll('.modal, #deactivate-modal, #delete-modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
});

// Navigation button event listeners
document.getElementById('flight-tracker-btn')?.addEventListener('click', () => {
    window.location.href = 'index.html';
});

document.getElementById('dashboard-btn')?.addEventListener('click', () => {
    window.location.href = 'dashboard.html';
});

document.getElementById('admin-btn')?.addEventListener('click', () => {
    window.location.href = 'admin.html';
});

// Initialize page on load
document.addEventListener('DOMContentLoaded', initPage);
