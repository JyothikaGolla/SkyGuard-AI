const API_BASE = "http://127.0.0.1:5000";

let map;
let markersLayer;
let flightsData = [];
let charts = {};
let authToken = null;
let currentUser = null;

// Check authentication on page load
function checkAuth() {
    authToken = localStorage.getItem('authToken');
    const userStr = localStorage.getItem('currentUser');
    
    if (!authToken || !userStr) {
        // Redirect to login page if not authenticated
        window.location.href = 'login.html';
        return false;
    }
    
    try {
        currentUser = JSON.parse(userStr);
        
        // Update UI with user info
        const userInfoEl = document.getElementById('user-info');
        const userNameEl = document.getElementById('user-name');
        const adminBtnEl = document.getElementById('admin-btn');
        
        if (userInfoEl && userNameEl) {
            userNameEl.textContent = currentUser.full_name || currentUser.username;
            userInfoEl.style.display = 'flex';
            
            // Show admin button if user is admin
            if (currentUser.role === 'admin' && adminBtnEl) {
                adminBtnEl.style.display = 'block';
            }
        }
        
        return true;
    } catch (e) {
        console.error('Invalid user data:', e);
        localStorage.removeItem('authToken');
        localStorage.removeItem('currentUser');
        window.location.href = 'login.html';
        return false;
    }
}

// Logout function
function logout() {
    localStorage.removeItem('authToken');
    localStorage.removeItem('currentUser');
    localStorage.removeItem('cachedFlights');
    localStorage.removeItem('cachedRegion');
    localStorage.removeItem('cachedMapView');
    localStorage.removeItem('cacheTimestamp');
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

// Initialize the application
function initApp() {
    // Check authentication (but don't block initialization)
    checkAuth();
    
    initMap();
    checkModelStatus();
    setupEventListeners();
    loadCachedFlights();
}

function initMap() {
    map = L.map("map").setView([20.5937, 78.9629], 5); // India approx

    // Dark theme map
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap contributors, &copy; CARTO'
    }).addTo(map);

    markersLayer = L.layerGroup().addTo(map);
}

function setupEventListeners() {
    document.getElementById("fetch-btn").addEventListener("click", fetchFlights);
    document.getElementById("my-location-btn").addEventListener("click", useMyLocation);
    document.getElementById("analytics-btn").addEventListener("click", showAnalytics);
    document.getElementById("close-analytics")?.addEventListener("click", hideAnalytics);
    document.getElementById("sort-select").addEventListener("change", sortFlights);
    document.getElementById("region-select").addEventListener("change", handleRegionChange);
    
    // Auth event listeners
    document.getElementById("dashboard-btn")?.addEventListener("click", () => {
        window.location.href = 'dashboard.html';
    });
    document.getElementById("admin-btn")?.addEventListener("click", () => {
        window.location.href = 'admin.html';
    });
}

function useMyLocation() {
    const statusEl = document.getElementById("status");
    const bboxInput = document.getElementById("bbox-input");
    
    if (navigator.geolocation) {
        statusEl.textContent = "🔄 Detecting your location...";
        statusEl.style.background = "rgba(59, 130, 246, 0.2)";
        
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const lat = position.coords.latitude;
                const lon = position.coords.longitude;
                // Create a 500km radius around user's location (~5 degrees)
                const bbox = `${(lat - 5).toFixed(2)},${(lat + 5).toFixed(2)},${(lon - 5).toFixed(2)},${(lon + 5).toFixed(2)}`;
                bboxInput.value = bbox;
                
                // Center map on user location
                map.setView([lat, lon], 7);
                
                // Remove any existing user location marker
                map.eachLayer((layer) => {
                    if (layer.options && layer.options.className === 'user-location-marker') {
                        map.removeLayer(layer);
                    }
                });
                
                // Add a marker for user's location
                L.marker([lat, lon], {
                    icon: L.divIcon({
                        className: 'user-location-marker',
                        html: '<div style="font-size: 24px;">📍</div>',
                        iconSize: [30, 30]
                    })
                }).addTo(map).bindPopup("Your Location");
                
                statusEl.textContent = "✅ Location detected. Click 'Fetch Flights' to load.";
                statusEl.style.background = "rgba(34, 197, 94, 0.2)";
                
                // Set region to custom to show the bbox
                document.getElementById("region-select").value = "custom";
                document.getElementById("bbox-label").style.display = "block";
            },
            (error) => {
                statusEl.textContent = "❌ Location access denied. Please enable location in browser settings.";
                statusEl.style.background = "rgba(239, 68, 68, 0.2)";
            }
        );
    } else {
        statusEl.textContent = "❌ Geolocation not supported by your browser";
        statusEl.style.background = "rgba(239, 68, 68, 0.2)";
    }
}

function handleRegionChange() {
    const region = document.getElementById("region-select").value;
    const bboxLabel = document.getElementById("bbox-label");
    const bboxInput = document.getElementById("bbox-input");
    
    if (region === "custom") {
        bboxLabel.style.display = "block";
        bboxInput.value = "";
    } else {
        bboxLabel.style.display = "none";
        
        // Predefined regions (minLat, maxLat, minLon, maxLon)
        const regions = {
            "india": "6,38,68,98",
            "europe": "35,72,-10,40",
            "usa": "25,50,-125,-65",
            "china": "18,54,73,135",
            "japan": "24,46,123,146",
            "australia": "-44,-10,113,154",
            "brazil": "-34,6,-74,-34",
            "middle-east": "12,42,34,63",
            "southeast-asia": "-11,28,92,141",
            "current-view": "current-view"
        };
        
        if (region === "current-view") {
            const bounds = map.getBounds();
            const bbox = `${bounds.getSouth().toFixed(2)},${bounds.getNorth().toFixed(2)},${bounds.getWest().toFixed(2)},${bounds.getEast().toFixed(2)}`;
            bboxInput.value = bbox;
            
            // Auto-center map on selected region
            map.fitBounds(bounds);
        } else {
            bboxInput.value = regions[region] || "";
            
            // Auto-center map on selected region
            if (regions[region]) {
                const [minLat, maxLat, minLon, maxLon] = regions[region].split(',').map(Number);
                map.fitBounds([[minLat, minLon], [maxLat, maxLon]]);
            }
        }
    }
}

async function checkModelStatus() {
    try {
        const res = await fetch(API_BASE + "/api/model-status");
        const status = await res.json();
        
        const statusEl = document.getElementById("model-status");
        if (status.models_available) {
            const loadedCount = Object.values(status.loaded_models).filter(Boolean).length;
            statusEl.innerHTML = `🤖 ML Models Active: ${loadedCount}/5 loaded`;
            statusEl.style.background = "rgba(34, 197, 94, 0.1)";
            statusEl.style.borderColor = "rgba(34, 197, 94, 0.3)";
        } else {
            statusEl.innerHTML = "⚠️ ML Models: Using heuristic scoring (train models to enable ML)";
            statusEl.style.background = "rgba(251, 191, 36, 0.1)";
            statusEl.style.borderColor = "rgba(251, 191, 36, 0.3)";
        }
    } catch (err) {
        console.error("Failed to check model status:", err);
    }
}

function getWeatherIcon(condition) {
    const icons = {
        'Clear': '☀️',
        'Clouds': '☁️',
        'Rain': '🌧️',
        'Drizzle': '🌦️',
        'Thunderstorm': '⛈️',
        'Snow': '❄️',
        'Mist': '🌫️',
        'Fog': '🌫️',
        'Haze': '🌫️'
    };
    return icons[condition] || '🌤️';
}

function getWeatherBadge(weather) {
    if (!weather) return '';
    
    const warnings = [];
    if (weather.severe_weather) warnings.push('⛈️ Severe');
    if (weather.icing_risk) warnings.push('🧊 Icing');
    if (weather.high_winds) warnings.push('💨 High Winds');
    if (weather.low_visibility) warnings.push('🌫️ Low Vis');
    
    if (warnings.length > 0) {
        return `<div style="color: #ef4444; font-weight: bold; margin-top: 4px;">${warnings.join(' ')}</div>`;
    }
    return '';
}

function riskColor(level) {
    if (level === "HIGH") return "#ef4444";
    if (level === "MEDIUM") return "#f59e0b";
    return "#22c55e";
}

function getRiskBadge(score, level) {
    const percentage = (score * 100).toFixed(0);
    return `<span class="risk-${level.toLowerCase()}">${level}</span> (${percentage}%)`;
}

function getAnomalyBadge(score) {
    const percentage = (score * 100).toFixed(0);
    let level = 'low';
    if (score > 0.66) level = 'high';
    else if (score > 0.33) level = 'medium';
    return `<span class="risk-${level}">${percentage}%</span>`;
}

function updateMapAndTable(flights) {
    flightsData = flights;
    markersLayer.clearLayers();
    
    const tbody = document.querySelector("#flights-table tbody");
    tbody.innerHTML = "";

    flights.forEach((f, index) => {
        if (f.lat == null || f.lon == null) return;

        // Determine which risk score to use (ML if available, otherwise heuristic)
        const riskScore = f.ml_risk_score !== undefined ? f.ml_risk_score : f.risk_score;
        const riskLevel = f.ml_risk_level || f.risk_level;
        const anomalyScore = f.ml_anomaly_score !== undefined ? f.ml_anomaly_score : f.anomaly_score;

        // Create marker with enhanced popup
        const marker = L.circleMarker([f.lat, f.lon], {
            radius: 8,
            stroke: true,
            color: 'rgba(255, 255, 255, 0.6)',
            weight: 2,
            fillColor: riskColor(riskLevel),
            fillOpacity: 0.9
        });

        const popupContent = `
            <div style="min-width: 200px; font-family: system-ui;">
                <h3 style="margin: 0 0 8px 0; color: #1e293b;">${f.callsign || f.icao24}</h3>
                <div style="font-size: 0.9rem; color: #475569;">
                    <strong>Country:</strong> ${f.origin_country}<br/>
                    <strong>Altitude:</strong> ${f.altitude?.toFixed(0) || "N/A"} m<br/>
                    <strong>Speed:</strong> ${f.speed_kmh?.toFixed(0) || "N/A"} km/h<br/>
                    <strong>Velocity:</strong> ${f.velocity?.toFixed(1) || "N/A"} m/s<br/>
                    <strong>Vertical Rate:</strong> ${f.vertical_rate?.toFixed(1) || "N/A"} m/s<br/>
                    <strong>Heading:</strong> ${f.heading?.toFixed(0) || "N/A"}°<br/>
                    <strong>Phase:</strong> ${f.flight_phase || "unknown"}<br/>
                    ${f.weather ? `
                    <hr style="margin: 8px 0; border: none; border-top: 1px solid #e5e7eb;"/>
                    <strong>Weather:</strong> ${getWeatherIcon(f.weather.condition)} ${f.weather.condition}<br/>
                    ${f.weather.temperature !== null ? `<strong>Temperature:</strong> ${f.weather.temperature.toFixed(1)}°C<br/>` : ''}
                    ${f.weather.wind_speed !== null ? `<strong>Wind:</strong> ${f.weather.wind_speed.toFixed(1)} m/s<br/>` : ''}
                    ${f.weather.visibility !== null ? `<strong>Visibility:</strong> ${(f.weather.visibility/1000).toFixed(1)} km<br/>` : ''}
                    ${f.weather.weather_risk_score > 0 ? `<strong>Weather Risk:</strong> ${f.weather.weather_risk_score.toFixed(0)}/100<br/>` : ''}
                    ${getWeatherBadge(f.weather)}
                    ` : ''}
                    <hr style="margin: 8px 0; border: none; border-top: 1px solid #e5e7eb;"/>
                    <strong>Risk Score:</strong> ${(riskScore * 100).toFixed(1)}% (${riskLevel})<br/>
                    <strong>Anomaly Score:</strong> ${(anomalyScore * 100).toFixed(1)}%<br/>
                    ${f.cluster !== undefined ? `<strong>Flight Pattern:</strong> Cluster ${f.cluster}<br/>` : ''}
                    ${f.ml_risk_score !== undefined ? '<em style="color: #3b82f6;">✓ ML-enhanced</em>' : ''}
                </div>
            </div>
        `;

        marker.bindPopup(popupContent);
        marker.addTo(markersLayer);

        // Add to table
        const tr = document.createElement("tr");
        const riskClass = riskLevel === "HIGH" ? "risk-high" :
                         riskLevel === "MEDIUM" ? "risk-medium" : "risk-low";

        tr.innerHTML = `
            <td><strong>${f.callsign || f.icao24}</strong></td>
            <td>${f.origin_country}</td>
            <td>${f.altitude != null ? f.altitude.toFixed(0) : "N/A"}</td>
            <td>${f.speed_kmh != null ? f.speed_kmh.toFixed(0) : "N/A"}</td>
            <td class="${riskClass}">${riskLevel}</td>
            <td>${getAnomalyBadge(anomalyScore)}</td>
            <td>
                <button class="btn-explain" onclick='explainFlightRisk(${JSON.stringify(f)})' title="Why this risk level?">
                    🔍 Explain
                </button>
                <button class="btn-future-risk" onclick='showFutureRisk(${JSON.stringify(f)})' title="Predict future risk">
                    🔮 Future
                </button>
            </td>
        `;

        tr.addEventListener("click", (e) => {
            // Don't trigger map view if clicking the explain or future risk button
            if (e.target.classList.contains('btn-explain') || e.target.classList.contains('btn-future-risk')) return;
            map.setView([f.lat, f.lon], 9);
            marker.openPopup();
        });

        tbody.appendChild(tr);
    });
}

function sortFlights() {
    const sortBy = document.getElementById("sort-select").value;
    
    const sorted = [...flightsData].sort((a, b) => {
        switch (sortBy) {
            case 'risk':
                const riskA = a.ml_risk_score !== undefined ? a.ml_risk_score : a.risk_score;
                const riskB = b.ml_risk_score !== undefined ? b.ml_risk_score : b.risk_score;
                return riskB - riskA;
            case 'anomaly':
                const anomalyA = a.ml_anomaly_score !== undefined ? a.ml_anomaly_score : a.anomaly_score;
                const anomalyB = b.ml_anomaly_score !== undefined ? b.ml_anomaly_score : b.anomaly_score;
                return anomalyB - anomalyA;
            case 'altitude':
                return (b.altitude || 0) - (a.altitude || 0);
            case 'speed':
                return (b.speed_kmh || 0) - (a.speed_kmh || 0);
            default:
                return 0;
        }
    });
    
    updateMapAndTable(sorted);
}

async function fetchFlights() {
    const statusEl = document.getElementById("status");
    const region = document.getElementById("region-select").value;
    let bboxInput = document.getElementById("bbox-input").value.trim();
    // Always use ML predictions
    const useML = true;
    
    // Check if user is logged in
    if (!authToken) {
        statusEl.textContent = "🔐 Please login to fetch flights";
        statusEl.style.background = "rgba(251, 191, 36, 0.2)";
        setTimeout(() => window.location.href = 'login.html', 1500);
        return;
    }
    
    // Handle "current-view" option
    if (region === "current-view") {
        const bounds = map.getBounds();
        bboxInput = `${bounds.getSouth().toFixed(2)},${bounds.getNorth().toFixed(2)},${bounds.getWest().toFixed(2)},${bounds.getEast().toFixed(2)}`;
    }

    statusEl.textContent = "🔄 Loading flights...";
    statusEl.style.background = "rgba(59, 130, 246, 0.2)";
    
    // Validate bbox format if provided
    if (bboxInput) {
        const parts = bboxInput.split(',');
        if (parts.length !== 4) {
            statusEl.textContent = "❌ Invalid bbox format. Use: minLat,maxLat,minLon,maxLon";
            statusEl.style.background = "rgba(239, 68, 68, 0.2)";
            return;
        }
        // Check if all parts are valid numbers
        if (parts.some(p => isNaN(parseFloat(p.trim())))) {
            statusEl.textContent = "❌ Invalid bbox format. All values must be numbers.";
            statusEl.style.background = "rgba(239, 68, 68, 0.2)";
            return;
        }
    }
    
    try {
        const url = new URL(API_BASE + "/api/flights");
        if (bboxInput) {
            url.searchParams.set("bbox", bboxInput);
        }
        url.searchParams.set("use_ml", useML ? "true" : "false");

        const res = await fetch(url, {
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            }
        });
        
        if (res.status === 401) {
            // Token expired or invalid
            statusEl.textContent = "❌ Session expired. Please login again.";
            statusEl.style.background = "rgba(239, 68, 68, 0.2)";
            setTimeout(() => logout(), 2000);
            return;
        }
        
        if (!res.ok) {
            const errorText = await res.text();
            throw new Error(`Backend error: ${res.status} - ${errorText}`);
        }
        const data = await res.json();
        updateMapAndTable(data);
        
        // Save to localStorage
        saveFlightsToCache(data, bboxInput);
        
        statusEl.textContent = `✅ Loaded ${data.length} flights (ML-enhanced)`;
        statusEl.style.background = "rgba(34, 197, 94, 0.2)";
    } catch (err) {
        console.error(err);
        statusEl.textContent = "❌ Error fetching flights. Check console.";
        statusEl.style.background = "rgba(239, 68, 68, 0.2)";
    }
}

async function showAnalytics() {
    const analyticsSection = document.getElementById("analytics-section");
    analyticsSection.classList.remove("hidden");
    
    const statusEl = document.getElementById("status");
    
    // Check if we have flights data
    if (!flightsData || flightsData.length === 0) {
        statusEl.textContent = "⚠️ No flights loaded. Click 'Fetch Flights' first.";
        statusEl.style.background = "rgba(251, 191, 36, 0.2)";
        return;
    }
    
    statusEl.textContent = "📊 Calculating analytics...";
    
    try {
        // Calculate analytics from the already-loaded flights data
        const analytics = calculateAnalytics(flightsData);
        displayAnalytics(analytics);
        statusEl.textContent = "✅ Analytics loaded";
        statusEl.style.background = "rgba(34, 197, 94, 0.2)";
        
        // Save analytics history if user is authenticated
        const authToken = localStorage.getItem('authToken');
        if (authToken) {
            await saveAnalyticsHistory(analytics);
        }
        
        // Scroll to analytics section smoothly with offset for fixed header
        setTimeout(() => {
            const headerHeight = 60; // Height of fixed header
            const elementPosition = analyticsSection.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - headerHeight ;
            
            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            });
        }, 100);
    } catch (err) {
        console.error(err);
        statusEl.textContent = "❌ Error calculating analytics";
        statusEl.style.background = "rgba(239, 68, 68, 0.2)";
    }
}

async function saveAnalyticsHistory(analytics) {
    const authToken = localStorage.getItem('authToken');
    if (!authToken) {
        console.log('Not saving analytics history - no auth token');
        return;
    }
    
    try {
        const bboxInput = document.getElementById("bbox-input");
        const bbox = bboxInput ? bboxInput.value : 'default';
        
        const payload = {
            query_type: 'flight_analytics',
            query_params: {
                bbox: bbox,
                timestamp: new Date().toISOString()
            },
            total_flights: analytics.total_flights || 0,
            high_risk_count: analytics.risk_stats?.high_risk_count || 0,
            anomaly_count: analytics.anomaly_stats?.high_anomaly_count || 0,
            analytics_data: {
                by_country: analytics.by_country,
                by_risk_level: analytics.by_risk_level,
                altitude_stats: analytics.altitude_stats,
                speed_stats: analytics.speed_stats,
                weather_stats: analytics.weather_stats
            }
        };
        
        console.log('Saving analytics history:', payload);
        
        const response = await fetch(`${API_BASE}/api/user/analytics-history`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            const result = await response.json();
            console.log('✅ Analytics history saved successfully:', result);
        } else {
            const error = await response.json();
            console.error('❌ Failed to save analytics history:', response.status, error);
        }
    } catch (error) {
        console.error('❌ Error saving analytics history:', error);
    }
}

function calculateAnalytics(flights) {
    // Calculate analytics from the flights array
    const analytics = {
        total_flights: flights.length,
        by_country: {},
        by_risk_level: { LOW: 0, MEDIUM: 0, HIGH: 0 },
        by_flight_phase: {},
        altitude_stats: { mean: 0, median: 0, max: 0, min: Infinity, distribution: {} },
        speed_stats: { mean_kmh: 0, median_kmh: 0, max_kmh: 0 },
        risk_stats: { mean_risk_score: 0, high_risk_count: 0, medium_risk_count: 0, low_risk_count: 0 },
        anomaly_stats: { mean_anomaly_score: 0, high_anomaly_count: 0 },
        weather_stats: {
            mean_temperature: null,
            mean_wind_speed: null,
            mean_visibility: null,
            mean_weather_risk: null,
            flights_with_weather: 0,
            conditions: {},
            severe_weather_count: 0,
            icing_risk_count: 0,
            high_winds_count: 0,
            low_visibility_count: 0
        }
    };
    
    if (flights.length === 0) return analytics;
    
    // Arrays for calculations
    const altitudes = [];
    const speeds = [];
    const riskScores = [];
    const anomalyScores = [];
    const temperatures = [];
    const windSpeeds = [];
    const visibilities = [];
    const weatherRisks = [];
    
    const altBuckets = { "0-1k": 0, "1-5k": 0, "5-10k": 0, "10-20k": 0, "20k+": 0 };
    
    flights.forEach(f => {
        // Use ML values if available, otherwise heuristic
        const riskLevel = f.ml_risk_level || f.risk_level;
        const riskScore = f.ml_risk_score !== undefined ? f.ml_risk_score : f.risk_score;
        const anomalyScore = f.ml_anomaly_score !== undefined ? f.ml_anomaly_score : f.anomaly_score;
        
        // Country
        analytics.by_country[f.origin_country] = (analytics.by_country[f.origin_country] || 0) + 1;
        
        // Risk level
        if (riskLevel) {
            analytics.by_risk_level[riskLevel] = (analytics.by_risk_level[riskLevel] || 0) + 1;
            if (riskLevel === 'LOW') analytics.risk_stats.low_risk_count++;
            if (riskLevel === 'MEDIUM') analytics.risk_stats.medium_risk_count++;
            if (riskLevel === 'HIGH') analytics.risk_stats.high_risk_count++;
        }
        
        // Flight phase
        if (f.flight_phase) {
            analytics.by_flight_phase[f.flight_phase] = (analytics.by_flight_phase[f.flight_phase] || 0) + 1;
        }
        
        // Altitude
        if (f.altitude != null) {
            altitudes.push(f.altitude);
            if (f.altitude < 1000) altBuckets["0-1k"]++;
            else if (f.altitude < 5000) altBuckets["1-5k"]++;
            else if (f.altitude < 10000) altBuckets["5-10k"]++;
            else if (f.altitude < 20000) altBuckets["10-20k"]++;
            else altBuckets["20k+"]++;
        }
        
        // Speed
        if (f.speed_kmh != null) speeds.push(f.speed_kmh);
        
        // Risk & Anomaly scores
        if (riskScore != null) riskScores.push(riskScore);
        if (anomalyScore != null) {
            anomalyScores.push(anomalyScore);
            if (anomalyScore > 0.66) analytics.anomaly_stats.high_anomaly_count++;
        }
        
        // Weather
        if (f.weather) {
            analytics.weather_stats.flights_with_weather++;
            
            if (f.weather.temperature != null) temperatures.push(f.weather.temperature);
            if (f.weather.wind_speed != null) windSpeeds.push(f.weather.wind_speed);
            if (f.weather.visibility != null) visibilities.push(f.weather.visibility);
            if (f.weather.weather_risk_score != null) weatherRisks.push(f.weather.weather_risk_score);
            
            if (f.weather.condition) {
                analytics.weather_stats.conditions[f.weather.condition] = 
                    (analytics.weather_stats.conditions[f.weather.condition] || 0) + 1;
            }
            
            if (f.weather.severe_weather) analytics.weather_stats.severe_weather_count++;
            if (f.weather.icing_risk) analytics.weather_stats.icing_risk_count++;
            if (f.weather.high_winds) analytics.weather_stats.high_winds_count++;
            if (f.weather.low_visibility) analytics.weather_stats.low_visibility_count++;
        }
    });
    
    // Calculate stats
    const avg = arr => arr.reduce((a, b) => a + b, 0) / arr.length;
    const median = arr => {
        const sorted = [...arr].sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    };
    
    if (altitudes.length > 0) {
        analytics.altitude_stats.mean = avg(altitudes);
        analytics.altitude_stats.median = median(altitudes);
        analytics.altitude_stats.max = Math.max(...altitudes);
        analytics.altitude_stats.min = Math.min(...altitudes);
        analytics.altitude_stats.distribution = altBuckets;
    }
    
    if (speeds.length > 0) {
        analytics.speed_stats.mean_kmh = avg(speeds);
        analytics.speed_stats.median_kmh = median(speeds);
        analytics.speed_stats.max_kmh = Math.max(...speeds);
    }
    
    if (riskScores.length > 0) {
        analytics.risk_stats.mean_risk_score = avg(riskScores);
    }
    
    if (anomalyScores.length > 0) {
        analytics.anomaly_stats.mean_anomaly_score = avg(anomalyScores);
    }
    
    if (temperatures.length > 0) analytics.weather_stats.mean_temperature = avg(temperatures);
    if (windSpeeds.length > 0) analytics.weather_stats.mean_wind_speed = avg(windSpeeds);
    if (visibilities.length > 0) analytics.weather_stats.mean_visibility = avg(visibilities);
    if (weatherRisks.length > 0) analytics.weather_stats.mean_weather_risk = avg(weatherRisks);
    
    return analytics;
}

function hideAnalytics() {
    document.getElementById("analytics-section").classList.add("hidden");
}

function displayAnalytics(analytics) {
    // Update stats cards
    document.getElementById("stat-total").textContent = analytics.total_flights || 0;
    document.getElementById("stat-high-risk").textContent = analytics.risk_stats?.high_risk_count || 0;
    document.getElementById("stat-anomalies").textContent = analytics.anomaly_stats?.high_anomaly_count || 0;
    document.getElementById("stat-altitude").textContent = 
        (analytics.altitude_stats?.mean?.toFixed(0) || 0) + "m";
    
    // Update weather stats cards
    const weather = analytics.weather_stats || {};
    document.getElementById("stat-temperature").textContent = 
        weather.mean_temperature !== null ? weather.mean_temperature.toFixed(1) + "°C" : "--°C";
    document.getElementById("stat-wind").textContent = 
        weather.mean_wind_speed !== null ? weather.mean_wind_speed.toFixed(1) + " m/s" : "-- m/s";
    document.getElementById("stat-visibility").textContent = 
        weather.mean_visibility !== null ? (weather.mean_visibility / 1000).toFixed(1) + " km" : "-- km";
    document.getElementById("stat-weather-risk").textContent = 
        weather.mean_weather_risk !== null ? weather.mean_weather_risk.toFixed(0) + "/100" : "--";
    
    // Risk Distribution Chart
    createPieChart("risk-chart", "Risk Distribution", {
        labels: ['Low Risk', 'Medium Risk', 'High Risk'],
        data: [
            analytics.risk_stats?.low_risk_count || 0,
            analytics.risk_stats?.medium_risk_count || 0,
            analytics.risk_stats?.high_risk_count || 0
        ],
        colors: ['#22c55e', '#f59e0b', '#ef4444']
    });
    
    // Flight Phases Chart
    const phaseData = analytics.by_flight_phase || {};
    createPieChart("phase-chart", "Flight Phases", {
        labels: Object.keys(phaseData),
        data: Object.values(phaseData),
        colors: ['#3b82f6', '#a855f7', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#6366f1']
    });
    
    // Country Chart
    const countryData = analytics.by_country || {};
    const topCountries = Object.entries(countryData).slice(0, 5);
    createBarChart("country-chart", "Top 5 Countries", {
        labels: topCountries.map(([country]) => country),
        data: topCountries.map(([, count]) => count),
        datasetLabel: 'Number of Flights',
        xAxisLabel: 'Country',
        yAxisLabel: 'Flight Count'
    });
    
    // Altitude Distribution - Real data from backend
    const altDist = analytics.altitude_stats?.distribution || {};
    createBarChart("altitude-chart", "Altitude Distribution", {
        labels: ['0-1k', '1-5k', '5-10k', '10-20k', '20k+'],
        data: [
            altDist['0-1k'] || 0,
            altDist['1-5k'] || 0,
            altDist['5-10k'] || 0,
            altDist['10-20k'] || 0,
            altDist['20k+'] || 0
        ],
        datasetLabel: 'Number of Flights',
        xAxisLabel: 'Altitude Range (meters)',
        yAxisLabel: 'Flight Count'
    });
    
    // Weather Conditions Chart (reuse weather variable from above)
    if (weather.flights_with_weather > 0) {
        createBarChart("weather-conditions-chart", "Weather Metrics (Averages)", {
            labels: ['Temperature (°C)', 'Wind Speed (m/s)', 'Visibility (km)', 'Weather Risk'],
            data: [
                weather.mean_temperature || 0,
                weather.mean_wind_speed || 0,
                (weather.mean_visibility || 0) / 1000,
                weather.mean_weather_risk || 0
            ],
            datasetLabel: 'Average Value',
            xAxisLabel: 'Weather Metric',
            yAxisLabel: 'Value'
        });
        
        // Weather Hazards Chart
        createPieChart("weather-hazards-chart", "Weather Hazards", {
            labels: ['Severe Weather', 'Low Visibility', 'High Winds', 'Icing Risk'],
            data: [
                weather.severe_weather_count || 0,
                weather.low_visibility_count || 0,
                weather.high_winds_count || 0,
                weather.icing_risk_count || 0
            ],
            colors: ['#ef4444', '#f59e0b', '#3b82f6', '#8b5cf6']
        });
    } else {
        // Show placeholder if no weather data
        const weatherConditionsCtx = document.getElementById("weather-conditions-chart");
        const weatherHazardsCtx = document.getElementById("weather-hazards-chart");
        if (weatherConditionsCtx) {
            weatherConditionsCtx.getContext('2d').fillStyle = '#94a3b8';
            weatherConditionsCtx.getContext('2d').font = '14px sans-serif';
            weatherConditionsCtx.getContext('2d').textAlign = 'center';
            weatherConditionsCtx.getContext('2d').fillText('No weather data available', 150, 100);
        }
        if (weatherHazardsCtx) {
            weatherHazardsCtx.getContext('2d').fillStyle = '#94a3b8';
            weatherHazardsCtx.getContext('2d').font = '14px sans-serif';
            weatherHazardsCtx.getContext('2d').textAlign = 'center';
            weatherHazardsCtx.getContext('2d').fillText('No weather data available', 150, 100);
        }
    }
}

function createPieChart(canvasId, title, config) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    
    // Destroy existing chart
    if (charts[canvasId]) {
        charts[canvasId].destroy();
    }
    
    charts[canvasId] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: config.labels,
            datasets: [{
                data: config.data,
                backgroundColor: config.colors,
                borderWidth: 2,
                borderColor: '#1e293b'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#e2e8f0',
                        padding: 15,
                        font: { size: 12 }
                    }
                }
            }
        }
    });
}

function createBarChart(canvasId, title, config) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    
    if (charts[canvasId]) {
        charts[canvasId].destroy();
    }
    
    charts[canvasId] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: config.labels,
            datasets: [{
                label: config.datasetLabel || title,
                data: config.data,
                backgroundColor: 'rgba(59, 130, 246, 0.8)',
                borderColor: 'rgba(59, 130, 246, 1)',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: '#e2e8f0',
                        font: { size: 12 }
                    }
                },
                title: {
                    display: !!config.chartTitle,
                    text: config.chartTitle || '',
                    color: '#e2e8f0',
                    font: { size: 14, weight: 'bold' }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: !!config.yAxisLabel,
                        text: config.yAxisLabel || '',
                        color: '#94a3b8',
                        font: { size: 12 }
                    },
                    ticks: {
                        color: '#94a3b8'
                    },
                    grid: {
                        color: 'rgba(148, 163, 184, 0.1)'
                    }
                },
                x: {
                    title: {
                        display: !!config.xAxisLabel,
                        text: config.xAxisLabel || '',
                        color: '#94a3b8',
                        font: { size: 12 }
                    },
                    ticks: {
                        color: '#94a3b8'
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

// localStorage functions (duplicate removed - using the complete version below)

function resetApp() {
    try {
        const cached = localStorage.getItem('flightRiskCache');
        if (!cached) return;
        
        const cacheData = JSON.parse(cached);
        const age = Date.now() - cacheData.timestamp;
        const ageMinutes = Math.floor(age / 60000);
        
        if (cacheData.flights && cacheData.flights.length > 0) {
            updateMapAndTable(cacheData.flights);
            
            const statusEl = document.getElementById("status");
            statusEl.textContent = `📦 Loaded ${cacheData.flights.length} cached flights (${ageMinutes} min old)`;
            statusEl.style.background = 'rgba(59, 130, 246, 0.2)';
            statusEl.style.color = '#3b82f6';
        }
    } catch (e) {
        console.warn('Failed to load from localStorage:', e);
    }
}

// localStorage functions
function saveFlightsToCache(flights, bbox) {
    try {
        const regionSelect = document.getElementById("region-select");
        const center = map.getCenter();
        const zoom = map.getZoom();
        
        const cacheData = {
            flights: flights,
            bbox: bbox,
            region: regionSelect.value,
            mapView: { lat: center.lat, lng: center.lng, zoom: zoom },
            timestamp: Date.now()
        };
        localStorage.setItem('flightRiskCache', JSON.stringify(cacheData));
    } catch (e) {
        console.warn('Failed to save to localStorage:', e);
    }
}

function loadCachedFlights() {
    try {
        const cached = localStorage.getItem('flightRiskCache');
        if (!cached) return;
        
        const cacheData = JSON.parse(cached);
        const age = Date.now() - cacheData.timestamp;
        const ageMinutes = Math.floor(age / 60000);
        
        if (cacheData.flights && cacheData.flights.length > 0) {
            updateMapAndTable(cacheData.flights);
            
            // Restore region selection
            if (cacheData.region) {
                document.getElementById("region-select").value = cacheData.region;
                if (cacheData.region === 'custom') {
                    document.getElementById("bbox-label").style.display = "block";
                    if (cacheData.bbox) {
                        document.getElementById("bbox-input").value = cacheData.bbox;
                    }
                }
            }
            
            // Restore map view
            if (cacheData.mapView) {
                map.setView([cacheData.mapView.lat, cacheData.mapView.lng], cacheData.mapView.zoom);
            }
            
            const statusEl = document.getElementById("status");
            statusEl.textContent = `📦 Loaded ${cacheData.flights.length} cached flights (${ageMinutes} min old)`;
            statusEl.style.background = 'rgba(59, 130, 246, 0.2)';
            statusEl.style.color = '#3b82f6';
        }
    } catch (e) {
        console.warn('Failed to load from localStorage:', e);
    }
}

function resetApp() {
    // Clear localStorage
    localStorage.removeItem('flightRiskCache');
    
    // Clear flight data
    flightsData = [];
    markersLayer.clearLayers();
    const tbody = document.querySelector("#flights-table tbody");
    if (tbody) tbody.innerHTML = "";
    
    // Clear status
    const statusEl = document.getElementById("status");
    statusEl.textContent = "";
    statusEl.style.background = "";
    
    // Hide analytics
    const analyticsSection = document.getElementById("analytics-section");
    if (analyticsSection) analyticsSection.classList.add("hidden");
    
    // Reset map view to default
    map.setView([20.5937, 78.9629], 5);
    
    // Reset region selector to default
    document.getElementById("region-select").value = "india";
}

// Future Risk Prediction Feature
async function showFutureRisk(flightData) {
    if (!authToken) {
        alert('Please log in to use this feature');
        return;
    }
    
    try {
        const statusEl = document.getElementById("status");
        statusEl.textContent = "Loading future risk prediction...";
        statusEl.style.background = "rgba(139, 92, 246, 0.1)";
        statusEl.style.color = "#8b5cf6";
        
        // Fetch default predictions at 2, 5, 10, 15 minutes (using 1-minute steps)
        const response = await fetch(`${API_BASE}/api/flights/${flightData.icao24}/future-risk?time_horizon=15&time_step_seconds=60`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            showFutureRiskModal(data, flightData);
            statusEl.textContent = "";
            statusEl.style.background = "";
        } else {
            const error = await response.json();
            alert(error.error || 'Failed to get future risk prediction');
            statusEl.textContent = "Failed to load prediction";
            statusEl.style.background = "rgba(239, 68, 68, 0.1)";
            statusEl.style.color = "#ef4444";
        }
    } catch (error) {
        console.error('Future risk error:', error);
        alert('Failed to get future risk prediction: ' + error.message);
    }
}

function showFutureRiskModal(data, flightData) {
    const modal = document.getElementById('future-risk-modal');
    if (!modal) {
        createFutureRiskModal();
        return showFutureRiskModal(data, flightData);
    }
    
    // Store flight data for custom prediction
    modal.flightData = flightData;
    
    document.getElementById('future-callsign').textContent = flightData.callsign || flightData.icao24;
    document.getElementById('future-current-risk').textContent = data.current_risk_level;
    document.getElementById('future-current-risk').style.color = riskColor(data.current_risk_level);
    
    // Display default predictions at specific intervals (2, 5, 10, 15 min)
    const timelineEl = document.getElementById('future-timeline');
    const targetMinutes = [2, 5, 10, 15];
    const filteredPredictions = data.predictions.filter(pred => {
        const minutes = Math.round(pred.time_offset_seconds / 60);
        return targetMinutes.includes(minutes);
    });
    
    // Display risk evolution with volatility indicator
    const evolutionEl = document.getElementById('future-evolution');
    const trend = data.risk_evolution;
    const trendIcon = trend === 'increasing' ? '📈' : trend === 'decreasing' ? '📉' : '➡️';
    const trendColor = trend === 'increasing' ? '#ef4444' : trend === 'decreasing' ? '#22c55e' : '#94a3b8';
    
    // Calculate volatility to show if predictions fluctuate
    const riskLevels = filteredPredictions.map(p => p.risk_level);
    const hasFluctuation = new Set(riskLevels).size > 2; // More than 2 different risk levels
    
    evolutionEl.innerHTML = `
        <div style="text-align: center;">
            <span style="color: ${trendColor}; font-size: 1.5rem;">${trendIcon} ${trend.toUpperCase()}</span>
            ${hasFluctuation ? '<div style="font-size: 0.75rem; color: #f59e0b; margin-top: 8px;">⚡ High volatility - risk levels fluctuating</div>' : ''}
        </div>
    `;
    
    timelineEl.innerHTML = filteredPredictions.map((pred, index) => {
        const minutes = Math.round(pred.time_offset_seconds / 60);
        return `
            <div class="future-prediction-item">
                <div class="future-time">+${minutes} min</div>
                <div class="future-risk-bar">
                    <div class="future-risk-fill" style="width: ${pred.risk_score * 100}%; background-color: ${riskColor(pred.risk_level)};"></div>
                </div>
                <div class="future-risk-value" style="color: ${riskColor(pred.risk_level)};">
                    ${pred.risk_level} <span style="font-size: 0.875rem; opacity: 0.8;">(Risk: ${(pred.risk_score * 100).toFixed(1)}%)</span>
                </div>
            </div>
        `;
    }).join('');
    
    // Clear previous custom prediction
    document.getElementById('custom-prediction-result').style.display = 'none';
    document.getElementById('custom-prediction-result').innerHTML = '';
    document.getElementById('custom-time-input').value = '';
    
    modal.style.display = 'flex';
}

function createFutureRiskModal() {
    const modalHTML = `
        <div id="future-risk-modal" class="modal" style="display: none;">
            <div class="modal-content" style="max-width: 700px;">
                <div class="modal-header">
                    <h2>🔮 Future Risk Prediction</h2>
                    <button class="modal-close" onclick="closeFutureRiskModal()" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border: none; border-radius: 6px; width: 32px; height: 32px; font-size: 24px; font-weight: 300; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; justify-content: center;" onmouseover="this.style.background='rgba(239, 68, 68, 0.2)'" onmouseout="this.style.background='rgba(239, 68, 68, 0.1)'">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="explain-summary">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                            <div>
                                <div class="explain-label">Flight:</div>
                                <div class="explain-value" id="future-callsign">-</div>
                            </div>
                            <div>
                                <div class="explain-label">Current Risk:</div>
                                <div class="explain-value" id="future-current-risk">-</div>
                            </div>
                        </div>
                    </div>
                    <div class="explain-section">
                        <h3>Risk Evolution</h3>
                        <div id="future-evolution" style="text-align: center; padding: 12px; background: rgba(255,255,255,0.02); border-radius: 8px; margin-bottom: 16px;">
                            -
                        </div>
                    </div>
                    <div class="explain-section">
                        <h3>Default Prediction Timeline</h3>
                        <p style="font-size: 0.875rem; color: #94a3b8; margin-bottom: 16px;">
                            Predicted risk at key intervals (2, 5, 10, 15 minutes):
                        </p>
                        <div id="future-timeline"></div>
                    </div>
                    <div class="explain-section">
                        <h3>⏱️ Custom Time Prediction</h3>
                        <p style="font-size: 0.875rem; color: #94a3b8; margin-bottom: 8px;">
                            Enter a specific time to predict risk at that moment:
                        </p>
                        <p style="font-size: 0.75rem; color: #64748b; margin-bottom: 12px; padding: 8px; background: rgba(59, 130, 246, 0.1); border-radius: 4px; border-left: 3px solid #3b82f6;">
                            <strong>📊 Valid Range:</strong> 1 to 60 minutes
                        </p>
                        <div style="display: flex; gap: 12px; align-items: flex-start; margin-bottom: 16px;">
                            <div style="flex: 1;">
                                <input type="number" id="custom-time-input" placeholder="e.g., 14" 
                                       min="1" max="60" 
                                       style="width: 100%; padding: 12px; background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 6px; color: white; font-size: 1rem;">
                                <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 4px;">Minutes ahead to predict</div>
                            </div>
                            <button onclick="predictCustomTime()" 
                                    style="padding: 12px 24px; background: linear-gradient(135deg, #8b5cf6, #7c3aed); border: none; border-radius: 6px; color: white; font-weight: 600; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 12px rgba(139, 92, 246, 0.3);">
                                🔮 Predict
                            </button>
                        </div>
                        <div id="custom-prediction-result" style="padding: 16px; background: rgba(255,255,255,0.02); border-radius: 8px; min-height: 80px; display: none;">
                            <!-- Prediction will be displayed here -->
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

function closeFutureRiskModal() {
    const modal = document.getElementById('future-risk-modal');
    if (modal) modal.style.display = 'none';
}

// Custom time prediction function
async function predictCustomTime() {
    const modal = document.getElementById('future-risk-modal');
    const timeInput = document.getElementById('custom-time-input');
    const resultDiv = document.getElementById('custom-prediction-result');
    
    const customMinutes = parseInt(timeInput.value);
    
    if (!customMinutes || customMinutes < 1 || customMinutes > 60) {
        alert('Please enter a valid time between 1 and 60 minutes');
        return;
    }
    
    const flightData = modal.flightData;
    if (!flightData) {
        alert('Flight data not available');
        return;
    }
    
    try {
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = '<div style="text-align: center; color: #8b5cf6;">⏳ Predicting...</div>';
        
        // Fetch prediction for the specific custom time (using 1-minute steps)
        const response = await fetch(`${API_BASE}/api/flights/${flightData.icao24}/future-risk?time_horizon=${customMinutes}&time_step_seconds=60`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            
            // Find the prediction closest to the custom time
            const targetSeconds = customMinutes * 60;
            const customPrediction = data.predictions.find(pred => 
                Math.abs(pred.time_offset_seconds - targetSeconds) < 30
            ) || data.predictions[data.predictions.length - 1];
            
            if (customPrediction) {
                const minutes = Math.round(customPrediction.time_offset_seconds / 60);
                const riskColorValue = riskColor(customPrediction.risk_level);
                
                resultDiv.innerHTML = `
                    <div style="border-left: 3px solid ${riskColorValue}; padding-left: 12px;">
                        <div style="font-size: 0.875rem; color: #94a3b8; margin-bottom: 4px;">After ${minutes} minutes:</div>
                        <div style="font-size: 1.25rem; font-weight: 600; color: ${riskColorValue}; margin-bottom: 8px;">
                            ${customPrediction.risk_level.toUpperCase()}
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <div style="flex: 1; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden;">
                                <div style="height: 100%; width: ${customPrediction.risk_score * 100}%; background: ${riskColorValue}; transition: width 0.3s;"></div>
                            </div>
                            <div style="font-size: 0.875rem; color: ${riskColorValue}; font-weight: 500;">
                                Risk: ${(customPrediction.risk_score * 100).toFixed(1)}%
                            </div>
                        </div>
                    </div>
                `;
            } else {
                resultDiv.innerHTML = '<div style="color: #ef4444;">❌ No prediction available</div>';
            }
        } else {
            const error = await response.json();
            resultDiv.innerHTML = `<div style="color: #ef4444;">❌ ${error.error || 'Prediction failed'}</div>`;
        }
    } catch (error) {
        console.error('Custom prediction error:', error);
        resultDiv.innerHTML = `<div style="color: #ef4444;">❌ Error: ${error.message}</div>`;
    }
}

// Flight Risk Explanation Feature (Enhanced with Dynamic Thresholds)
async function explainFlightRisk(flightData) {
    if (!authToken) {
        alert('Please log in to use this feature');
        return;
    }
    
    console.log('Explaining flight risk for:', flightData);
    
    try {
        const statusEl = document.getElementById("status");
        statusEl.textContent = "Loading explanation...";
        statusEl.style.background = "rgba(59, 130, 246, 0.1)";
        statusEl.style.color = "#3b82f6";
        
        // Send flight data directly to backend for SHAP analysis
        const [explanationResponse, thresholdsResponse] = await Promise.all([
            fetch(`${API_BASE}/api/flights/${flightData.icao24}/explain`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    flight_data: flightData,
                    risk_level: flightData.ml_risk_level || flightData.risk_level,
                    risk_score: flightData.ml_risk_score || flightData.risk_score
                })
            }),
            fetch(`${API_BASE}/api/thresholds/dynamic?altitude=${flightData.altitude || 0}&flight_phase=${flightData.flight_phase || 'cruise'}&weather_condition=${flightData.weather?.condition || 'Clear'}`, {
                headers: {
                    'Authorization': `Bearer ${authToken}`
                }
            })
        ]);
        
        console.log('Explanation response status:', explanationResponse.status);
        console.log('Thresholds response status:', thresholdsResponse.status);
        
        if (explanationResponse.ok) {
            const explanationData = await explanationResponse.json();
            console.log('Explanation data:', explanationData);
            const thresholdsData = thresholdsResponse.ok ? await thresholdsResponse.json() : null;
            console.log('Thresholds data:', thresholdsData);
            showRiskExplanationModal(explanationData, thresholdsData, flightData);
            statusEl.textContent = "";
            statusEl.style.background = "";
        } else {
            const error = await explanationResponse.json();
            console.error('Explanation error:', error);
            alert(error.error || 'Failed to get risk explanation');
            statusEl.textContent = "Failed to load explanation";
            statusEl.style.background = "rgba(239, 68, 68, 0.1)";
            statusEl.style.color = "#ef4444";
        }
    } catch (error) {
        console.error('Explanation error:', error);
        alert('Failed to get risk explanation: ' + error.message);
    }
}

function showRiskExplanationModal(data, thresholdsData, flightData) {
    const modal = document.getElementById('explanation-modal');
    if (!modal) {
        createExplanationModal();
        return showRiskExplanationModal(data, thresholdsData, flightData);
    }
    
    const riskColorMap = {
        'HIGH': '#ef4444',
        'MEDIUM': '#f59e0b',
        'LOW': '#22c55e'
    }[data.risk_level] || '#94a3b8';
    
    document.getElementById('explain-callsign').textContent = data.callsign || data.icao24;
    document.getElementById('explain-risk-level').textContent = data.risk_level;
    document.getElementById('explain-risk-level').style.color = riskColorMap;
    document.getElementById('explain-risk-score').textContent = (data.risk_score * 100).toFixed(1) + '%';
    
    // Display dynamic thresholds if available
    const thresholdsEl = document.getElementById('explain-thresholds');
    if (thresholdsData && thresholdsEl) {
        const thresholds = thresholdsData.dynamic_thresholds;
        const context = thresholdsData.context;
        const config = thresholdsData.configuration;
        
        thresholdsEl.innerHTML = `
            <div style="background: rgba(139, 92, 246, 0.05); padding: 16px; border-radius: 8px; border: 1px solid rgba(139, 92, 246, 0.2);">
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 12px;">
                    <div>
                        <div style="font-size: 0.75rem; color: #94a3b8;">LOW Threshold</div>
                        <div style="font-size: 1.1rem; font-weight: 600; color: #22c55e;">&lt; ${(thresholds.low * 100).toFixed(1)}%</div>
                    </div>
                    <div>
                        <div style="font-size: 0.75rem; color: #94a3b8;">HIGH Threshold</div>
                        <div style="font-size: 1.1rem; font-weight: 600; color: #ef4444;">≥ ${(thresholds.high * 100).toFixed(1)}%</div>
                    </div>
                </div>
                <div style="font-size: 0.8rem; color: #a78bfa;">
                    📍 Altitude: ${context.altitude ? context.altitude.toFixed(0) : 'N/A'}m &nbsp;|&nbsp; 
                    ✈️ Phase: ${context.flight_phase || 'N/A'} &nbsp;|&nbsp; 
                    ${getWeatherIcon(context.weather_condition)} ${context.weather_condition || 'N/A'}
                </div>
            </div>
        `;
    }
    
    const factorsList = document.getElementById('explain-factors');
    if (data.top_factors && data.top_factors.length > 0) {
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
    } else {
        factorsList.innerHTML = '<div style="color: #64748b; text-align: center; padding: 20px;">No detailed factors available</div>';
    }
    
    modal.style.display = 'flex';
}

function createExplanationModal() {
    const modalHTML = `
        <div id="explanation-modal" class="modal" style="display: none;">
            <div class="modal-content" style="max-width: 600px;">
                <div class="modal-header">
                    <h2>🔍 Flight Risk Explanation</h2>
                    <button class="modal-close" onclick="closeExplanationModal()" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border: none; border-radius: 6px; width: 32px; height: 32px; font-size: 24px; font-weight: 300; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; justify-content: center;" onmouseover="this.style.background='rgba(239, 68, 68, 0.2)'" onmouseout="this.style.background='rgba(239, 68, 68, 0.1)'">&times;</button>
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
                        <h3>🎯 Context-Aware Risk Thresholds</h3>
                        <p style="font-size: 0.875rem; color: #94a3b8; margin-bottom: 16px;">
                            Thresholds adjusted based on altitude, flight phase, and weather conditions:
                        </p>
                        <div id="explain-thresholds">
                            <div style="color: #64748b; text-align: center; padding: 12px;">
                                Loading threshold information...
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
            .btn-explain {
                background: rgba(59, 130, 246, 0.1);
                color: #60a5fa;
                border: 1px solid rgba(59, 130, 246, 0.3);
                padding: 6px 12px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 0.8rem;
                font-weight: 600;
                transition: all 0.2s ease;
                margin-right: 6px;
            }
            .btn-explain:hover {
                background: rgba(59, 130, 246, 0.2);
                border-color: rgba(59, 130, 246, 0.5);
                transform: scale(1.05);
            }
            .btn-future-risk {
                background: rgba(139, 92, 246, 0.1);
                color: #a78bfa;
                border: 1px solid rgba(139, 92, 246, 0.3);
                padding: 6px 12px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 0.8rem;
                font-weight: 600;
                transition: all 0.2s ease;
            }
            .btn-future-risk:hover {
                background: rgba(139, 92, 246, 0.2);
                border-color: rgba(139, 92, 246, 0.5);
                transform: scale(1.05);
            }
            .future-prediction-item {
                display: grid;
                grid-template-columns: 80px 1fr 120px;
                gap: 12px;
                align-items: center;
                padding: 12px;
                background: rgba(255, 255, 255, 0.02);
                border-radius: 8px;
                margin-bottom: 8px;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
            .future-time {
                font-weight: 600;
                color: #94a3b8;
                font-size: 0.9rem;
            }
            .future-risk-bar {
                height: 24px;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                overflow: hidden;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            .future-risk-fill {
                height: 100%;
                transition: width 0.3s ease;
            }
            .future-risk-value {
                font-weight: 600;
                font-size: 0.875rem;
                text-align: right;
            }
            .future-warning {
                background: rgba(239, 68, 68, 0.1);
                color: #fca5a5;
                padding: 10px 14px;
                border-radius: 8px;
                border: 1px solid rgba(239, 68, 68, 0.3);
                margin-bottom: 8px;
                font-size: 0.875rem;
            }
            .modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.7);
                backdrop-filter: blur(4px);
                z-index: 10000;
                justify-content: center;
                align-items: center;
            }
            .modal-content {
                background: #1e293b;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
                max-height: 90vh;
                overflow-y: auto;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            .modal-header {
                padding: 24px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .modal-header h2 {
                margin: 0;
                color: #f1f5f9;
                font-size: 1.5rem;
            }
            .modal-close {
                background: none;
                border: none;
                font-size: 2rem;
                color: #94a3b8;
                cursor: pointer;
                transition: color 0.2s ease;
            }
            .modal-close:hover {
                color: #f1f5f9;
            }
            .modal-body {
                padding: 24px;
            }
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

function closeExplanationModal() {
    const modal = document.getElementById('explanation-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", initApp);
