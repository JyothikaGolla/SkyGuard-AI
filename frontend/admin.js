const API_BASE = 'http://127.0.0.1:5000';
let authToken = null;
let currentUser = null;
let users = [];
let auditLogs = [];
let metricsChart = null;

// Pagination state
let usersPage = 1;
let auditPage = 1;
const perPage = 20;

// Check authentication
function checkAuth() {
    authToken = localStorage.getItem('authToken');
    const userStr = localStorage.getItem('currentUser');
    
    if (!authToken || !userStr) {
        window.location.href = 'login.html';
        return false;
    }
    
    try {
        currentUser = JSON.parse(userStr);
        
        // Check if user is admin
        if (currentUser.role !== 'admin') {
            alert('Access denied. Admin privileges required.');
            window.location.href = 'index.html';
            return false;
        }
        
        // Update UI with user info
        const userInfoDiv = document.getElementById('user-info');
        const userNameEl = document.getElementById('user-name');
        if (userInfoDiv && userNameEl) {
            userNameEl.textContent = currentUser.full_name || currentUser.username;
            userInfoDiv.style.display = 'flex';
        }
        
        return true;
    } catch (e) {
        console.error('Invalid user data:', e);
        logout();
        return false;
    }
}

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

// Initialize admin panel
async function initAdmin() {
    if (!checkAuth()) return;
    
    showLoading();
    try {
        await Promise.all([
            loadDashboardStats(),
            loadUsers(),
            loadSystemMetrics(),
            loadAuditLogs()
        ]);
    } catch (error) {
        showError('Failed to load admin data: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Dashboard Stats
async function loadDashboardStats() {
    try {
        const response = await fetch(`${API_BASE}/api/admin/dashboard/stats`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.status === 401 || response.status === 403) {
            logout();
            return;
        }
        
        if (response.ok) {
            const data = await response.json();
            document.getElementById('stat-total-users').textContent = data.users.total || 0;
            document.getElementById('stat-active-users').textContent = data.users.active || 0;
            document.getElementById('stat-new-users').textContent = data.users.new_this_week || 0;
            document.getElementById('stat-total-alerts').textContent = data.alerts.total || 0;
            document.getElementById('stat-total-watchlists').textContent = data.watchlists.total || 0;
            document.getElementById('stat-activity-24h').textContent = data.activity.actions_24h || 0;
        }
    } catch (error) {
        console.error('Failed to load dashboard stats:', error);
    }
}

// Users Management
async function loadUsers() {
    try {
        const search = document.getElementById('user-search')?.value || '';
        const role = document.getElementById('role-filter')?.value || '';
        const active = document.getElementById('active-filter')?.value || '';
        
        const url = new URL(`${API_BASE}/api/admin/users`);
        url.searchParams.set('page', usersPage);
        url.searchParams.set('per_page', perPage);
        if (search) url.searchParams.set('search', search);
        if (role) url.searchParams.set('role', role);
        if (active) url.searchParams.set('active_only', active);
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            users = data.users;
            renderUsers();
            // Calculate total pages if not provided by API
            const totalPages = data.total_pages || Math.ceil(data.total / data.per_page);
            renderUsersPagination(data.total, data.page, data.per_page, totalPages);
        }
    } catch (error) {
        console.error('Failed to load users:', error);
    }
}

function renderUsers() {
    const tbody = document.getElementById('users-table');
    
    if (users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 40px; color: #94a3b8;">No users found</td></tr>';
        return;
    }
    
    tbody.innerHTML = users.map(u => {
        const activateBtn = u.is_active 
            ? `<button class="btn-icon" onclick="deactivateUser(${u.id})" title="Deactivate">⏸️</button>`
            : `<button class="btn-icon" onclick="activateUser(${u.id})" title="Activate">▶️</button>`;
        
        const roleBtn = u.role === 'user'
            ? `<button class="btn-icon" onclick="promoteToAdmin(${u.id})" title="Promote to Admin">⬆️</button>`
            : (u.id !== currentUser.id 
                ? `<button class="btn-icon" onclick="demoteToUser(${u.id})" title="Demote to User">⬇️</button>`
                : '');
        
        return `
            <tr>
                <td>
                    <strong>${u.full_name || u.username}</strong><br>
                    <small style="color: #64748b;">@${u.username}</small>
                </td>
                <td>${u.email}</td>
                <td><span class="badge badge-${u.role}">${u.role.toUpperCase()}</span></td>
                <td><span class="badge badge-${u.is_active ? 'active' : 'inactive'}">${u.is_active ? 'Active' : 'Inactive'}</span></td>
                <td><small>${new Date(u.created_at).toLocaleDateString()}</small></td>
                <td>
                    ${activateBtn}
                    ${roleBtn}
                    <button class="btn-icon" onclick="viewUserDetails(${u.id})" title="View Details">👁️</button>
                </td>
            </tr>
        `;
    }).join('');
}

function renderUsersPagination(total, page, perPage, totalPages) {
    const container = document.getElementById('users-pagination');
    
    // Ensure we don't go beyond available pages
    const isFirstPage = page === 1;
    const isLastPage = page >= totalPages || total === 0;
    
    let html = `
        <button onclick="usersPage = 1; loadUsers()" ${isFirstPage ? 'disabled' : ''}>First</button>
        <button onclick="usersPage = ${page - 1}; loadUsers()" ${isFirstPage ? 'disabled' : ''}>Previous</button>
        <span style="color: #94a3b8;">Page ${page} of ${totalPages} (${total} users)</span>
        <button onclick="usersPage = ${page + 1}; loadUsers()" ${isLastPage ? 'disabled' : ''}>Next</button>
        <button onclick="usersPage = ${totalPages}; loadUsers()" ${isLastPage ? 'disabled' : ''}>Last</button>
    `;
    
    container.innerHTML = html;
}

function searchUsers() {
    clearTimeout(window.searchTimeout);
    window.searchTimeout = setTimeout(() => {
        usersPage = 1;
        loadUsers();
    }, 500);
}

function filterUsers() {
    usersPage = 1;
    loadUsers();
}

async function activateUser(id) {
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/api/admin/users/${id}/activate`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            showSuccess('User activated successfully!');
            await Promise.all([loadUsers(), loadDashboardStats()]);
        } else {
            const error = await response.json();
            showError(error.error || 'Failed to activate user');
        }
    } catch (error) {
        showError('Failed to activate user: ' + error.message);
    } finally {
        hideLoading();
    }
}

async function deactivateUser(id) {
    if (!confirm('Are you sure you want to deactivate this user?')) return;
    
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/api/admin/users/${id}/deactivate`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const errorEl = document.getElementById('error-message');
            errorEl.textContent = '⚠️ User deactivated successfully!';
            errorEl.style.background = 'rgba(239, 68, 68, 0.1)';
            errorEl.style.borderColor = 'rgba(239, 68, 68, 0.3)';
            errorEl.style.color = '#ef4444';
            errorEl.style.display = 'block';
            setTimeout(() => {
                errorEl.style.display = 'none';
            }, 3000);
            await Promise.all([loadUsers(), loadDashboardStats()]);
        } else {
            const error = await response.json();
            showError(error.error || 'Failed to deactivate user');
        }
    } catch (error) {
        showError('Failed to deactivate user: ' + error.message);
    } finally {
        hideLoading();
    }
}

async function promoteToAdmin(id) {
    if (!confirm('Are you sure you want to promote this user to admin?')) return;
    
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/api/admin/users/${id}/role`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ role: 'admin' })
        });
        
        if (response.ok) {
            showSuccess('User promoted to admin!');
            await Promise.all([loadUsers(), loadDashboardStats()]);
        } else {
            const error = await response.json();
            showError(error.error || 'Failed to promote user');
        }
    } catch (error) {
        showError('Failed to promote user: ' + error.message);
    } finally {
        hideLoading();
    }
}

async function demoteToUser(id) {
    if (!confirm('Are you sure you want to demote this admin to user?')) return;
    
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/api/admin/users/${id}/role`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ role: 'user' })
        });
        
        if (response.ok) {
            showSuccess('Admin demoted to user!');
            await Promise.all([loadUsers(), loadDashboardStats()]);
        } else {
            const error = await response.json();
            showError(error.error || 'Failed to demote user');
        }
    } catch (error) {
        showError('Failed to demote user: ' + error.message);
    } finally {
        hideLoading();
    }
}

async function viewUserDetails(id) {
    try {
        const response = await fetch(`${API_BASE}/api/admin/users/${id}`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            const user = data.user;
            const stats = data.stats;
            alert(`User Details:\n\nName: ${user.full_name || 'N/A'}\nUsername: ${user.username}\nEmail: ${user.email}\nRole: ${user.role}\nStatus: ${user.is_active ? 'Active' : 'Inactive'}\nJoined: ${new Date(user.created_at).toLocaleString()}\nLast Login: ${user.last_login ? new Date(user.last_login).toLocaleString() : 'Never'}\n\nWatchlists: ${stats.watchlist_count}\nAlerts: ${stats.alert_count}\nUnread Alerts: ${stats.unread_alerts}`);
        }
    } catch (error) {
        showError('Failed to load user details: ' + error.message);
    }
}

async function exportUsers() {
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/api/admin/export/users`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `users_export_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            showSuccess('Users exported successfully!');
        } else {
            showError('Failed to export users');
        }
    } catch (error) {
        showError('Failed to export users: ' + error.message);
    } finally {
        hideLoading();
    }
}

// System Metrics
async function loadSystemMetrics() {
    try {
        const response = await fetch(`${API_BASE}/api/admin/system-metrics?period=daily`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            // Convert endpoint stats object to array format
            const metricsArray = Object.entries(data.endpoints || {}).map(([endpoint, stats]) => ({
                api_endpoint: endpoint,
                request_count: stats.request_count,
                error_count: stats.error_count,
                avg_response_time: stats.avg_response_time
            }));
            renderMetricsChart(metricsArray);
            renderMetricsTable(metricsArray);
        } else {
            console.error('Failed to load metrics:', response.status);
            renderMetricsTable([]);
        }
    } catch (error) {
        console.error('Failed to load system metrics:', error);
        renderMetricsTable([]);
    }
}

function renderMetricsChart(metrics) {
    const ctx = document.getElementById('metrics-chart');
    
    if (metricsChart) {
        metricsChart.destroy();
    }
    
    const endpoints = metrics.map(m => m.api_endpoint);
    const requests = metrics.map(m => m.request_count);
    const errors = metrics.map(m => m.error_count);
    
    metricsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: endpoints,
            datasets: [
                {
                    label: 'Requests',
                    data: requests,
                    backgroundColor: 'rgba(59, 130, 246, 0.5)',
                    borderColor: 'rgba(59, 130, 246, 1)',
                    borderWidth: 1
                },
                {
                    label: 'Errors',
                    data: errors,
                    backgroundColor: 'rgba(239, 68, 68, 0.5)',
                    borderColor: 'rgba(239, 68, 68, 1)',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                },
                x: {
                    ticks: { color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                }
            },
            plugins: {
                legend: {
                    labels: { color: '#f1f5f9' }
                }
            }
        }
    });
}

function renderMetricsTable(metrics) {
    const tbody = document.getElementById('metrics-table');
    
    if (metrics.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 40px; color: #94a3b8;">No metrics available</td></tr>';
        return;
    }
    
    tbody.innerHTML = metrics.map(m => {
        const errorRate = m.request_count > 0 ? (m.error_count / m.request_count * 100).toFixed(1) : 0;
        return `
            <tr>
                <td>${m.api_endpoint}</td>
                <td>${m.request_count.toLocaleString()}</td>
                <td>${m.error_count.toLocaleString()}</td>
                <td>${m.avg_response_time.toFixed(2)}</td>
                <td>
                    <span class="badge ${errorRate > 5 ? 'badge-inactive' : 'badge-active'}">
                        ${errorRate}%
                    </span>
                </td>
            </tr>
        `;
    }).join('');
}

// Audit Logs
async function loadAuditLogs() {
    try {
        const action = document.getElementById('action-filter')?.value || '';
        
        const url = new URL(`${API_BASE}/api/admin/audit-logs`);
        url.searchParams.set('page', auditPage);
        url.searchParams.set('per_page', perPage);
        if (action) url.searchParams.set('action', action);
        
        const response = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            auditLogs = data.logs;
            const totalPages = data.total_pages || Math.ceil(data.total / data.per_page);
            renderAuditLogs();
            renderAuditPagination(data.total, data.page, data.per_page, totalPages);
        }
    } catch (error) {
        console.error('Failed to load audit logs:', error);
    }
}

function renderAuditLogs() {
    const tbody = document.getElementById('audit-table');
    
    if (auditLogs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 40px; color: #94a3b8;">No audit logs found</td></tr>';
        return;
    }
    
    tbody.innerHTML = auditLogs.map(log => {
        // Parse UTC timestamp (ensure it's treated as UTC by adding 'Z' if not present)
        const utcString = log.created_at.endsWith('Z') ? log.created_at : log.created_at + 'Z';
        const utcDate = new Date(utcString);
        const istDate = new Date(utcDate.getTime() + (5.5 * 60 * 60 * 1000));
        
        // Format: DD/MM/YYYY, HH:MM:SS
        const day = String(istDate.getUTCDate()).padStart(2, '0');
        const month = String(istDate.getUTCMonth() + 1).padStart(2, '0');
        const year = istDate.getUTCFullYear();
        const hours = String(istDate.getUTCHours()).padStart(2, '0');
        const minutes = String(istDate.getUTCMinutes()).padStart(2, '0');
        const seconds = String(istDate.getUTCSeconds()).padStart(2, '0');
        const formatted = `${day}/${month}/${year}, ${hours}:${minutes}:${seconds}`;
        
        return `
        <tr>
            <td><small>${formatted}</small></td>
            <td>${log.username || '<em>Anonymous</em>'}</td>
            <td><span class="badge badge-user">${log.action}</span></td>
            <td><small>${log.resource}</small></td>
            <td><small>${log.ip_address}</small></td>
            <td>
                <span class="badge ${log.success ? 'badge-active' : 'badge-inactive'}">
                    ${log.success ? 'Success' : 'Failed'}
                </span>
            </td>
        </tr>
        `;
    }).join('');
}

function renderAuditPagination(total, page, perPage, totalPages) {
    const container = document.getElementById('audit-pagination');
    
    const isLastPage = page >= totalPages;
    
    let html = `
        <button onclick="auditPage = 1; loadAuditLogs()" ${page === 1 ? 'disabled' : ''}>First</button>
        <button onclick="auditPage = ${page - 1}; loadAuditLogs()" ${page === 1 ? 'disabled' : ''}>Previous</button>
        <span style="color: #94a3b8;">Page ${page} of ${totalPages} (${total} logs)</span>
        <button onclick="auditPage = ${page + 1}; loadAuditLogs()" ${isLastPage ? 'disabled' : ''}>Next</button>
        <button onclick="auditPage = ${totalPages}; loadAuditLogs()" ${isLastPage ? 'disabled' : ''}>Last</button>
    `;
    
    container.innerHTML = html;
}

function filterAuditLogs() {
    auditPage = 1;
    loadAuditLogs();
}

// Tab Switching
function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
    event.target.classList.add('active');
    
    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(`${tabName}-tab`).classList.add('active');
}

// UI Helpers
function showLoading() {
    document.getElementById('loading').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loading').style.display = 'none';
}

function showError(message) {
    const errorEl = document.getElementById('error-message');
    errorEl.textContent = message;
    errorEl.style.display = 'block';
    setTimeout(() => {
        errorEl.style.display = 'none';
    }, 5000);
}

function showSuccess(message) {
    const errorEl = document.getElementById('error-message');
    errorEl.textContent = '✓ ' + message;
    errorEl.style.background = 'rgba(34, 197, 94, 0.1)';
    errorEl.style.borderColor = 'rgba(34, 197, 94, 0.3)';
    errorEl.style.color = '#22c55e';
    errorEl.style.display = 'block';
    setTimeout(() => {
        errorEl.style.display = 'none';
        errorEl.style.background = 'rgba(239, 68, 68, 0.1)';
        errorEl.style.borderColor = 'rgba(239, 68, 68, 0.3)';
        errorEl.style.color = '#ef4444';
    }, 3000);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initAdmin();
    
    // Add event listeners for navigation buttons
    document.getElementById('flight-tracker-btn')?.addEventListener('click', () => {
        window.location.href = 'index.html';
    });

    document.getElementById('dashboard-btn')?.addEventListener('click', () => {
        window.location.href = 'dashboard.html';
    });
});
