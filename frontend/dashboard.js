const API_BASE = 'http://127.0.0.1:5000';
let authToken = null;
let currentUser = null;
let watchlists = [];
let alerts = [];
let preferences = null;

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
        document.getElementById('user-name').textContent = currentUser.full_name || currentUser.username;
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

// Initialize dashboard
async function initDashboard() {
    if (!checkAuth()) return;
    
    showLoading();
    try {
        await Promise.all([
            loadPreferences(),
            loadWatchlists(),
            loadAlerts(),
            loadAnalyticsHistory()
        ]);
        await updateStats();
    } catch (error) {
        showError('Failed to load dashboard data: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Preferences
async function loadPreferences() {
    try {
        const response = await fetch(`${API_BASE}/api/user/preferences`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.status === 401) {
            logout();
            return;
        }
        
        if (response.ok) {
            const data = await response.json();
            preferences = data.preferences;
            
            document.getElementById('pref-email-alerts').checked = preferences.email_alerts || false;
            document.getElementById('pref-risk-threshold').value = preferences.risk_threshold || 'MEDIUM';
            document.getElementById('pref-alert-frequency').value = preferences.alert_frequency || 'immediate';
        }
    } catch (error) {
        console.error('Failed to load preferences:', error);
    }
}

async function savePreferences() {
    const data = {
        email_alerts: document.getElementById('pref-email-alerts').checked,
        risk_threshold: document.getElementById('pref-risk-threshold').value,
        alert_frequency: document.getElementById('pref-alert-frequency').value
    };
    
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/api/user/preferences`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            preferences = data; // Update local preferences
            showSuccess('Preferences saved successfully!');
            await loadPreferences(); // Reload to confirm
        } else {
            const error = await response.json();
            console.error('Save preferences error:', error);
            showError(error.error || 'Failed to save preferences');
        }
    } catch (error) {
        console.error('Save preferences exception:', error);
        showError('Failed to save preferences: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Watchlists
async function loadWatchlists() {
    try {
        const response = await fetch(`${API_BASE}/api/user/watchlists`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            watchlists = data.watchlists;
            renderWatchlists();
        }
    } catch (error) {
        console.error('Failed to load watchlists:', error);
    }
}

function renderWatchlists() {
    const container = document.getElementById('watchlists-container');
    
    if (watchlists.length === 0) {
        container.innerHTML = '<div class="empty-state">No watchlists yet. Create one to start monitoring specific regions!</div>';
        return;
    }
    
    container.innerHTML = watchlists.map(w => `
        <div class="watchlist-item">
            <div class="watchlist-info">
                <div class="watchlist-name">
                    ${w.name}
                    <span class="badge ${w.is_active ? 'badge-active' : 'badge-inactive'}">
                        ${w.is_active ? 'Active' : 'Inactive'}
                    </span>
                </div>
                <div class="watchlist-desc">${w.description || 'No description'}</div>
                <div style="font-size: 0.95rem; color: #e0e7ff; margin-top: 8px; 
                            font-family: 'Courier New', monospace; 
                            background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(59, 130, 246, 0.2)); 
                            padding: 10px 14px; 
                            border-radius: 8px; 
                            border: 1px solid rgba(99, 102, 241, 0.5);
                            display: inline-block;
                            font-weight: 500;
                            letter-spacing: 0.5px;
                            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.2);">
                    📍 BBox: <span style="color: #60a5fa; font-weight: 600;">${w.bbox}</span>
                </div>
            </div>
            <div class="watchlist-actions">
                <button class="btn-icon" onclick="editWatchlist(${w.id})" title="Edit">✏️</button>
                <button class="btn-icon" onclick="toggleWatchlist(${w.id}, ${!w.is_active})" title="${w.is_active ? 'Deactivate' : 'Activate'}">
                    ${w.is_active ? '⏸️' : '▶️'}
                </button>
                <button class="btn-icon" onclick="deleteWatchlist(${w.id})" title="Delete">🗑️</button>
            </div>
        </div>
    `).join('');
}

function openCreateWatchlist() {
    document.getElementById('modal-title').textContent = 'Create Watchlist';
    document.getElementById('watchlist-id').value = '';
    document.getElementById('watchlist-name').value = '';
    document.getElementById('watchlist-description').value = '';
    document.getElementById('watchlist-bbox').value = '';
    document.getElementById('region-preset').value = '';
    document.getElementById('watchlist-active').checked = true;
    document.getElementById('watchlist-modal').classList.add('active');
}

function fillBboxFromPreset() {
    const preset = document.getElementById('region-preset').value;
    if (preset) {
        document.getElementById('watchlist-bbox').value = preset;
    }
}

function editWatchlist(id) {
    const watchlist = watchlists.find(w => w.id === id);
    if (!watchlist) return;
    
    document.getElementById('modal-title').textContent = 'Edit Watchlist';
    document.getElementById('watchlist-id').value = watchlist.id;
    document.getElementById('watchlist-name').value = watchlist.name;
    document.getElementById('watchlist-description').value = watchlist.description || '';
    document.getElementById('watchlist-bbox').value = watchlist.bbox;
    document.getElementById('watchlist-active').checked = watchlist.is_active;
    document.getElementById('watchlist-modal').classList.add('active');
}

function closeWatchlistModal() {
    document.getElementById('watchlist-modal').classList.remove('active');
}

async function saveWatchlist(event) {
    event.preventDefault();
    
    const id = document.getElementById('watchlist-id').value;
    const data = {
        name: document.getElementById('watchlist-name').value,
        description: document.getElementById('watchlist-description').value,
        bbox: document.getElementById('watchlist-bbox').value,
        region_type: 'bbox',
        is_active: document.getElementById('watchlist-active').checked
    };
    
    try {
        showLoading();
        const url = id ? `${API_BASE}/api/user/watchlists/${id}` : `${API_BASE}/api/user/watchlists`;
        const method = id ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method,
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showSuccess(id ? 'Watchlist updated!' : 'Watchlist created!');
            closeWatchlistModal();
            await loadWatchlists();
            await updateStats();
        } else {
            const error = await response.json();
            showError(error.error || 'Failed to save watchlist');
        }
    } catch (error) {
        showError('Failed to save watchlist: ' + error.message);
    } finally {
        hideLoading();
    }
}

async function toggleWatchlist(id, isActive) {
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/api/user/watchlists/${id}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ is_active: isActive })
        });
        
        if (response.ok) {
            showSuccess(`Watchlist ${isActive ? 'activated' : 'deactivated'}!`);
            await loadWatchlists();
            await updateStats();
        } else {
            const error = await response.json();
            showError(error.error || 'Failed to update watchlist');
        }
    } catch (error) {
        showError('Failed to update watchlist: ' + error.message);
    } finally {
        hideLoading();
    }
}

async function deleteWatchlist(id) {
    if (!confirm('Are you sure you want to delete this watchlist?')) return;
    
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/api/user/watchlists/${id}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            showSuccess('Watchlist deleted!');
            await loadWatchlists();
            await updateStats();
        } else {
            const error = await response.json();
            showError(error.error || 'Failed to delete watchlist');
        }
    } catch (error) {
        showError('Failed to delete watchlist: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Alerts
async function loadAlerts() {
    try {
        const response = await fetch(`${API_BASE}/api/user/alerts?limit=20`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            alerts = data.alerts;
            renderAlerts();
        }
    } catch (error) {
        console.error('Failed to load alerts:', error);
    }
}

function renderAlerts() {
    const container = document.getElementById('alerts-container');
    
    if (alerts.length === 0) {
        container.innerHTML = '<div class="empty-state">No alerts yet. Alerts will appear here when high-risk flights are detected in your watchlists.</div>';
        return;
    }
    
    container.innerHTML = alerts.map(a => `
        <div class="alert-item" style="opacity: ${a.is_read ? 0.6 : 1}">
            <div class="alert-info">
                <div class="alert-title">
                    ${a.title}
                    <span class="badge badge-${a.severity.toLowerCase()}">${a.severity}</span>
                    ${!a.is_read ? '<span class="badge badge-unread">New</span>' : ''}
                </div>
                <div class="alert-message">${a.message}</div>
                <div style="font-size: 0.75rem; color: #64748b; margin-top: 4px;">
                    ${new Date(a.created_at).toLocaleString('en-IN', { 
                        timeZone: 'Asia/Kolkata',
                        hour12: false,
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit'
                    })} IST
                </div>
            </div>
            ${!a.is_read ? `
                <div class="alert-actions">
                    <button class="btn-icon" onclick="markAlertRead(${a.id})" title="Mark as read">✓</button>
                </div>
            ` : ''}
        </div>
    `).join('');
}

async function markAlertRead(id) {
    try {
        const response = await fetch(`${API_BASE}/api/user/alerts/${id}/read`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            await loadAlerts();
            await updateStats();
        }
    } catch (error) {
        console.error('Failed to mark alert as read:', error);
    }
}

// Analytics History
async function loadAnalyticsHistory() {
    try {
        const response = await fetch(`${API_BASE}/api/user/analytics-history?limit=10`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            renderAnalyticsHistory(data.history);
        }
    } catch (error) {
        console.error('Failed to load analytics history:', error);
    }
}

function renderAnalyticsHistory(history) {
    const container = document.getElementById('history-container');
    
    if (!history || history.length === 0) {
        container.innerHTML = '<div class="empty-state">No analytics history yet. Run analytics from the main page to see your query history.</div>';
        return;
    }
    
    container.innerHTML = `
        <div style="overflow-x: auto;">
            <table class="data-table">
                <thead>
                    <tr>
                        <th style="width: 180px; text-align: left;">Query Type</th>
                        <th style="width: 120px; text-align: center;">Total Flights</th>
                        <th style="width: 120px; text-align: center;">High Risk</th>
                        <th style="width: 120px; text-align: center;">Anomalies</th>
                        <th style="width: 180px; text-align: left;">Date & Time</th>
                    </tr>
                </thead>
                <tbody>
                    ${history.map(h => `
                        <tr>
                            <td style="width: 180px; font-weight: 500; color: #60a5fa;">${h.query_type}</td>
                            <td style="width: 120px; text-align: center; font-weight: 600; color: #e2e8f0;">${h.total_flights}</td>
                            <td style="width: 120px; text-align: center;">
                                <span class="badge badge-${h.high_risk_count > 0 ? 'high' : 'low'}">${h.high_risk_count}</span>
                            </td>
                            <td style="width: 120px; text-align: center;">
                                <span class="badge badge-${h.anomaly_count > 0 ? 'medium' : 'low'}">${h.anomaly_count}</span>
                            </td>
                            <td style="width: 180px; font-size: 0.85rem; color: #94a3b8;">
                                ${(() => {
                                    // Parse as UTC and convert to IST
                                    const utcDate = new Date(h.created_at + 'Z'); // Force UTC parsing
                                    return utcDate.toLocaleString('en-IN', { 
                                        timeZone: 'Asia/Kolkata', 
                                        year: 'numeric', 
                                        month: '2-digit', 
                                        day: '2-digit', 
                                        hour: '2-digit', 
                                        minute: '2-digit', 
                                        second: '2-digit', 
                                        hour12: false 
                                    }).replace(',', '') + ' IST';
                                })()}
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

// Update stats
async function updateStats() {
    document.getElementById('stat-watchlists').textContent = watchlists.length;
    document.getElementById('stat-active').textContent = watchlists.filter(w => w.is_active).length;
    const unreadAlerts = alerts.filter(a => !a.is_read).length;
    document.getElementById('stat-alerts').textContent = unreadAlerts;
    
    // Fetch analytics queries count from history
    try {
        console.log('🔍 Fetching analytics count...');
        const response = await fetch(`${API_BASE}/api/user/analytics-history?limit=1000`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        console.log('📊 Analytics response status:', response.status);
        
        if (response.ok) {
            const data = await response.json();
            console.log('📊 Analytics data:', data);
            console.log('📊 Analytics count:', data.history.length);
            document.getElementById('stat-queries').textContent = data.history.length;
        } else {
            const errorData = await response.json();
            console.error('❌ Failed to fetch analytics:', response.status, errorData);
        }
    } catch (error) {
        console.error('❌ Error fetching analytics count:', error);
    }
}

// Email and Monitoring functions
async function testEmail() {
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/api/email/test`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess('Test email sent! Check your inbox (and spam folder).');
        } else {
            showError(data.error || 'Failed to send test email');
        }
    } catch (error) {
        console.error('Test email error:', error);
        showError('Failed to send test email: ' + error.message);
    } finally {
        hideLoading();
    }
}

async function checkWatchlistsNow() {
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/api/monitoring/check-watchlists`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const stats = data.stats;
            showSuccess(
                `Monitoring complete! Checked ${stats.watchlists_checked} watchlist(s), ` +
                `created ${stats.alerts_created} alert(s), sent ${stats.emails_sent} email(s).`
            );
            // Reload alerts to show new ones
            await loadAlerts();
            await updateStats();
        } else {
            showError(data.error || 'Failed to check watchlists');
        }
    } catch (error) {
        console.error('Monitoring error:', error);
        showError('Failed to check watchlists: ' + error.message);
    } finally {
        hideLoading();
    }
}

// UI helpers
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

// Flight Risk Explanation Feature
async function explainFlightRisk(icao24, callsign) {
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/api/flights/${icao24}/explain`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            showRiskExplanationModal(data);
        } else {
            const error = await response.json();
            showError(error.error || 'Failed to get risk explanation');
        }
    } catch (error) {
        console.error('Explanation error:', error);
        showError('Failed to get risk explanation: ' + error.message);
    } finally {
        hideLoading();
    }
}

function showRiskExplanationModal(data) {
    const modal = document.getElementById('explanation-modal');
    if (!modal) {
        // Create modal if it doesn't exist
        createExplanationModal();
        return showRiskExplanationModal(data);
    }
    
    const riskColor = {
        'HIGH': '#ef4444',
        'MEDIUM': '#f59e0b',
        'LOW': '#22c55e'
    }[data.risk_level] || '#94a3b8';
    
    document.getElementById('explain-callsign').textContent = data.callsign || data.icao24;
    document.getElementById('explain-risk-level').textContent = data.risk_level;
    document.getElementById('explain-risk-level').style.color = riskColor;
    document.getElementById('explain-risk-score').textContent = (data.risk_score * 100).toFixed(1) + '%';
    
    const factorsList = document.getElementById('explain-factors');
    factorsList.innerHTML = data.top_factors.map((factor, index) => {
        const impactColor = factor.impact > 0 ? '#ef4444' : '#22c55e';
        const impactDirection = factor.impact > 0 ? '↑' : '↓';
        const impactMagnitude = Math.abs(factor.impact);
        
        return `
            <div class="explain-factor">
                <div class="explain-factor-header">
                    <span class="explain-rank">#${index + 1}</span>
                    <span class="explain-feature">${factor.feature.replace(/_/g, ' ').toUpperCase()}</span>
                    <span class="explain-impact" style="color: ${impactColor}">
                        ${impactDirection} ${impactMagnitude.toFixed(3)}
                    </span>
                </div>
                <div class="explain-factor-detail">
                    Value: <strong>${factor.value}</strong> &nbsp;|&nbsp; 
                    ${factor.explanation}
                </div>
            </div>
        `;
    }).join('');
    
    modal.style.display = 'flex';
}

function createExplanationModal() {
    const modalHTML = `
        <div id="explanation-modal" class="modal" style="display: none;">
            <div class="modal-content" style="max-width: 600px;">
                <div class="modal-header">
                    <h2>🔍 Flight Risk Explanation</h2>
                    <button class="modal-close" onclick="closeExplanationModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="explain-summary">
                        <div class="explain-header-row">
                            <div>
                                <div class="explain-label">Flight:</div>
                                <div class="explain-value" id="explain-callsign">-</div>
                            </div>
                            <div>
                                <div class="explain-label">Risk Level:</div>
                                <div class="explain-value" id="explain-risk-level">-</div>
                            </div>
                            <div>
                                <div class="explain-label">Risk Score:</div>
                                <div class="explain-value" id="explain-risk-score">-</div>
                            </div>
                        </div>
                    </div>
                    <div class="explain-section">
                        <h3>Top Contributing Factors</h3>
                        <p style="font-size: 0.875rem; color: #94a3b8; margin-bottom: 16px;">
                            These features have the strongest influence on this flight's risk classification:
                        </p>
                        <div id="explain-factors"></div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Add styles
    const styles = `
        <style>
            .explain-summary {
                background: rgba(59, 130, 246, 0.05);
                padding: 20px;
                border-radius: 12px;
                margin-bottom: 24px;
                border: 1px solid rgba(59, 130, 246, 0.2);
            }
            .explain-header-row {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 16px;
            }
            .explain-label {
                font-size: 0.75rem;
                color: #94a3b8;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 4px;
            }
            .explain-value {
                font-size: 1.25rem;
                font-weight: 600;
                color: #f1f5f9;
            }
            .explain-section h3 {
                color: #f1f5f9;
                margin-bottom: 12px;
                font-size: 1.1rem;
            }
            .explain-factor {
                background: rgba(255, 255, 255, 0.02);
                padding: 14px;
                border-radius: 8px;
                margin-bottom: 10px;
                border: 1px solid rgba(255, 255, 255, 0.05);
                transition: all 0.2s ease;
            }
            .explain-factor:hover {
                background: rgba(255, 255, 255, 0.04);
                border-color: rgba(59, 130, 246, 0.3);
            }
            .explain-factor-header {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 8px;
            }
            .explain-rank {
                background: rgba(59, 130, 246, 0.2);
                color: #60a5fa;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 0.75rem;
                font-weight: 600;
            }
            .explain-feature {
                flex: 1;
                font-weight: 600;
                color: #f1f5f9;
                font-size: 0.875rem;
            }
            .explain-impact {
                font-weight: 700;
                font-size: 0.9rem;
            }
            .explain-factor-detail {
                font-size: 0.8125rem;
                color: #cbd5e1;
                padding-left: 38px;
            }
        </style>
    `;
    
    document.head.insertAdjacentHTML('beforeend', styles);
}

// Risk Threshold Simulator (NEW Feature)
async function simulateThresholds() {
    const altitude = parseFloat(document.getElementById('sim-altitude').value);
    const phase = document.getElementById('sim-phase').value;
    const weather = document.getElementById('sim-weather').value;
    
    try {
        showLoading();
        const response = await fetch(
            `${API_BASE}/api/thresholds/dynamic?altitude=${altitude}&flight_phase=${phase}&weather_condition=${weather}`,
            {
                headers: {
                    'Authorization': `Bearer ${authToken}`
                }
            }
        );
        
        if (response.ok) {
            const data = await response.json();
            displayThresholdResults(data);
        } else {
            const error = await response.json();
            showError(error.error || 'Failed to calculate thresholds');
        }
    } catch (error) {
        console.error('Threshold simulation error:', error);
        showError('Failed to calculate thresholds: ' + error.message);
    } finally {
        hideLoading();
    }
}

function displayThresholdResults(data) {
    const resultsDiv = document.getElementById('threshold-results');
    resultsDiv.style.display = 'block';
    
    const thresholds = data.thresholds;
    const context = data.context;
    const adjustments = context.adjustments;
    
    // Display threshold values
    document.getElementById('result-low').textContent = `< ${(thresholds.low_threshold * 100).toFixed(1)}%`;
    document.getElementById('result-medium').textContent = 
        `${(thresholds.low_threshold * 100).toFixed(1)}% - ${(thresholds.high_threshold * 100).toFixed(1)}%`;
    document.getElementById('result-high').textContent = `≥ ${(thresholds.high_threshold * 100).toFixed(1)}%`;
    
    // Display adjustments
    const adjustmentsEl = document.getElementById('threshold-adjustments');
    adjustmentsEl.innerHTML = `
        <strong>Applied Multipliers:</strong> 
        Phase: ${(adjustments.phase_multiplier * 100).toFixed(0)}% | 
        Altitude: ${(adjustments.altitude_multiplier * 100).toFixed(0)}% | 
        Weather: ${(adjustments.weather_multiplier * 100).toFixed(0)}%
    `;
    
    // Display comparison
    const comparisonEl = document.getElementById('threshold-comparison');
    const fixedLow = 0.33;
    const fixedHigh = 0.66;
    
    const lowDiff = ((thresholds.low_threshold - fixedLow) / fixedLow * 100).toFixed(1);
    const highDiff = ((thresholds.high_threshold - fixedHigh) / fixedHigh * 100).toFixed(1);
    
    const lowIcon = lowDiff < 0 ? '📉' : lowDiff > 0 ? '📈' : '➡️';
    const highIcon = highDiff < 0 ? '📉' : highDiff > 0 ? '📈' : '➡️';
    
    comparisonEl.innerHTML = `
        <div style="margin-bottom: 4px;">
            ${lowIcon} LOW: ${lowDiff > 0 ? '+' : ''}${lowDiff}% from fixed (33.0%)
        </div>
        <div>
            ${highIcon} HIGH: ${highDiff > 0 ? '+' : ''}${highDiff}% from fixed (66.0%)
        </div>
        <div style="margin-top: 8px; font-size: 0.8rem; color: #64748b;">
            ${Math.abs(parseFloat(lowDiff)) > 5 || Math.abs(parseFloat(highDiff)) > 5 
                ? '⚠️ Significant adjustment applied for these conditions' 
                : '✓ Minor adjustment - conditions are close to standard'}
        </div>
    `;
    
    // Scroll to results
    resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function closeExplanationModal() {
    const modal = document.getElementById('explanation-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Make functions globally accessible
window.explainFlightRisk = explainFlightRisk;
window.closeExplanationModal = closeExplanationModal;
window.simulateThresholds = simulateThresholds;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
    
    // Add event listeners for navigation buttons
    document.getElementById('flight-tracker-btn')?.addEventListener('click', () => {
        window.location.href = 'index.html';
    });

    document.getElementById('admin-btn')?.addEventListener('click', () => {
        window.location.href = 'admin.html';
    });
});
