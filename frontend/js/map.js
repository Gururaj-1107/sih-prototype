/**
 * CashOut Forecast — GIS Geospatial Radar (Leaflet.js)
 * Visualizes candidate ATM clusters, complaint origin vectors, and inter-city fund flow polylines.
 */

window.miniMap = null;
window.radarMap = null;
let flowPolylines = [];
let atmMarkers = [];

// Coordinates dictionary for Indian metropolitan fraud intelligence nodes
const CITY_COORDINATES = {
  'Ahmedabad': [23.0225, 72.5714],
  'Mumbai': [19.0760, 72.8777],
  'Delhi': [28.6139, 77.2090],
  'Bengaluru': [12.9716, 77.5946],
  'Hyderabad': [17.3850, 78.4867],
  'Kolkata': [22.5726, 88.3639],
  'Jaipur': [26.9124, 75.7873],
  'Surat': [21.1702, 72.8311],
  'Pune': [18.5204, 73.8567],
  'Indore': [22.7196, 75.8577],
  'Lucknow': [26.8467, 80.9462],
  'Chandigarh': [30.7333, 76.7794]
};

// Tile Layer with dark cyber theme
const DARK_TILES = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

function initMaps() {
  const miniElem = document.getElementById('miniMap');
  const radarElem = document.getElementById('radarMap');

  if (miniElem && !window.miniMap) {
    window.miniMap = L.map('miniMap', {
      center: [21.5, 78.5],
      zoom: 4,
      zoomControl: false,
      attributionControl: false
    });
    L.tileLayer(DARK_TILES, { maxZoom: 18 }).addTo(window.miniMap);
  }

  if (radarElem && !window.radarMap) {
    window.radarMap = L.map('radarMap', {
      center: [21.5, 78.5],
      zoom: 5
    });
    L.tileLayer(DARK_TILES, { maxZoom: 18, attribution: TILE_ATTR }).addTo(window.radarMap);
  }

  loadLocationsOnMap();
}

async function loadLocationsOnMap() {
  const resp = await authFetch('/locations');
  if (!resp || !resp.ok) return;
  const locations = await resp.json();

  const alertsResp = await authFetch('/alerts');
  const alerts = alertsResp && alertsResp.ok ? await alertsResp.json() : [];

  renderMapMarkers(locations, alerts);
}

function renderMapMarkers(locations, alerts) {
  // Clear previous markers
  atmMarkers.forEach(m => m.remove());
  flowPolylines.forEach(p => p.remove());
  atmMarkers = [];
  flowPolylines = [];

  const targetMaps = [window.radarMap, window.miniMap].filter(Boolean);

  // Group locations by city to aggregate scores
  const cityAlertMap = {};
  alerts.forEach(a => {
    if (a.city) {
      if (!cityAlertMap[a.city] || a.score > cityAlertMap[a.city].score) {
        cityAlertMap[a.city] = a;
      }
    }
  });

  // Plot candidate location markers
  locations.forEach(loc => {
    const lat = loc.latitude;
    const lng = loc.longitude;
    if (!lat || !lng) return;

    const alertForCity = cityAlertMap[loc.city];
    const isAlerted = !!alertForCity;
    const score = alertForCity ? alertForCity.score : 0.2;
    const color = score >= 0.6 ? '#f43f5e' : (score >= 0.4 ? '#f59e0b' : '#38bdf8');
    const radius = isAlerted ? 12 : 6;

    targetMaps.forEach(m => {
      const circle = L.circleMarker([lat, lng], {
        radius: radius,
        fillColor: color,
        color: '#ffffff',
        weight: isAlerted ? 2 : 1,
        opacity: 0.9,
        fillOpacity: 0.7
      }).addTo(m);

      circle.bindPopup(`
        <div style="font-family: 'Outfit', sans-serif; color: #0f172a; padding: 4px;">
          <h4 style="margin: 0 0 4px; font-weight: 700; color: #0284c7;">${loc.city} • Cluster ${loc.cluster_code || loc.location_id}</h4>
          <div style="font-size: 11px; margin-bottom: 4px;">State: <strong>${loc.state}</strong> | Type: <strong>${loc.location_type}</strong></div>
          ${alertForCity ? `
            <div style="background: #fee2e2; border-left: 3px solid #ef4444; padding: 4px 6px; font-size: 11px; margin-bottom: 6px;">
              <strong>INTERCEPTION ALERT</strong><br/>
              Priority: <span style="color:#b91c1c; font-weight: bold;">${alertForCity.priority}</span> (${(alertForCity.score * 100).toFixed(0)}% Risk)
            </div>
            <button onclick="openCaseFromPrediction('${alertForCity.prediction_id}')" style="background: #0284c7; color: white; border: none; border-radius: 4px; padding: 4px 8px; font-size: 11px; cursor: pointer; width: 100%;">
              Open Investigation Workbench
            </button>
          ` : '<div style="font-size: 10px; color: #64748b;">Baseline surveillance node</div>'}
        </div>
      `);

      atmMarkers.push(circle);
    });
  });

  // Draw inter-city cybercrime fund flow trajectories
  // Prominent vectors: Ahmedabad -> Mumbai, Delhi -> Jaipur, Hyderabad -> Bengaluru
  const sampleTrajectories = [
    { from: 'Ahmedabad', to: 'Mumbai', label: 'Fraud ₹4.5L ➔ Cash-Out Target' },
    { from: 'Delhi', to: 'Jaipur', label: 'Impersonation Scam ➔ ATM Extraction' },
    { from: 'Hyderabad', to: 'Bengaluru', label: 'Layering Chain ➔ Mule Withdrawal' }
  ];

  sampleTrajectories.forEach(traj => {
    const p1 = CITY_COORDINATES[traj.from];
    const p2 = CITY_COORDINATES[traj.to];
    if (p1 && p2) {
      targetMaps.forEach(m => {
        const poly = L.polyline([p1, p2], {
          color: '#f43f5e',
          weight: 2.5,
          opacity: 0.8,
          dashArray: '6, 8'
        }).addTo(m);

        poly.bindTooltip(`${traj.from} ➔ ${traj.to} (${traj.label})`, {
          sticky: true,
          className: 'map-flow-tooltip'
        });

        flowPolylines.push(poly);
      });
    }
  });

  // Update floating map summary stats
  const statsElem = document.getElementById('mapSummaryStats');
  if (statsElem) {
    statsElem.innerHTML = `
      <div class="mb-1"><span class="text-rose font-bold">● ${alerts.length}</span> Active Interception Targets</div>
      <div class="mb-1"><span class="text-cyan font-bold">● ${locations.length}</span> Surveillance Clusters</div>
      <div><span class="text-amber font-bold">● ${sampleTrajectories.length}</span> Active Cross-City Money Trails</div>
    `;
  }
}

function toggleFlowPolylines() {
  const show = document.getElementById('chkShowPolylines')?.checked ?? true;
  flowPolylines.forEach(p => {
    if (show) {
      p.addTo(window.radarMap);
    } else {
      p.remove();
    }
  });
}

function toggleAtmMarkers() {
  const show = document.getElementById('chkShowAtms')?.checked ?? true;
  atmMarkers.forEach(m => {
    if (show) {
      m.addTo(window.radarMap);
    } else {
      m.remove();
    }
  });
}

window.addEventListener('DOMContentLoaded', () => {
  setTimeout(initMaps, 500);
});
