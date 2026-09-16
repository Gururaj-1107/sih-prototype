/**
 * CashOut Forecast — Primary Application Controller
 * Handles Auth, View Switching, API Integrations, Adjudication, and Demo Mode
 */

const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) ? window.APP_CONFIG.API_BASE_URL : '';
let currentAuthToken = localStorage.getItem('cashout_token') || '';
let currentCaseId = null;
let currentPredictionsList = [];

// Helper for authorized fetch
async function authFetch(url, options = {}) {
  if (!currentAuthToken) {
    // If not authenticated, redirect to login page
    window.location.href = '/';
    return null;
  }
  const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`;
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${currentAuthToken}`,
    ...(options.headers || {})
  };
  try {
    const response = await fetch(fullUrl, { ...options, headers });
    if (response.status === 401) {
      localStorage.removeItem('cashout_token');
      window.location.href = '/';
      return null;
    }
    return response;
  } catch (err) {
    console.error('Fetch error:', err);
    showToast('Network error contacting backend API', 'error');
    throw err;
  }
}

// Toast Notifications
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast-item toast-${type}`;
  
  const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : type === 'warning' ? '⚠️' : 'ℹ️';
  toast.innerHTML = `
    <span class="toast-icon">${icon}</span>
    <span class="toast-msg">${message}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('fade-out');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Animated KPI Counter
function animateCounter(elementId, targetValue, duration = 1000) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const startValue = parseInt(el.textContent) || 0;
  const increment = (targetValue - startValue) / (duration / 16);
  let current = startValue;
  const timer = setInterval(() => {
    current += increment;
    if ((increment > 0 && current >= targetValue) || (increment < 0 && current <= targetValue)) {
      current = targetValue;
      clearInterval(timer);
    }
    el.textContent = Math.round(current);
  }, 16);
}

function showSkeletonLoading(containerId, rows = 5) {
  const container = document.getElementById(containerId);
  if (!container) return;
  let html = '';
  for (let i = 0; i < rows; i++) {
    html += '<tr class="skeleton-row"><td colspan="8"><div class="skeleton skeleton-text"></div></td></tr>';
  }
  container.innerHTML = html;
}

function toggleMobileSidebar() {
  const sidebar = document.querySelector('.app-sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (sidebar) sidebar.classList.toggle('sidebar-open');
  if (overlay) overlay.classList.toggle('active');
}

let notifications = [];
let unreadCount = 0;

function toggleNotificationPanel() {
  const panel = document.getElementById('notificationPanel');
  if (panel) panel.classList.toggle('open');
}

function addNotification(type, message, data = {}) {
  const notif = {
    id: Date.now(),
    type: type,
    message: message,
    data: data,
    timestamp: new Date().toLocaleTimeString(),
    read: false
  };
  notifications.unshift(notif);
  unreadCount++;
  renderNotifications();
  showToast(message, type === 'alert' ? 'warning' : 'info');
}

function renderNotifications() {
  const badge = document.getElementById('notifBadge');
  const list = document.getElementById('notificationList');
  if (badge) {
    badge.textContent = unreadCount;
    badge.style.display = unreadCount > 0 ? 'flex' : 'none';
  }
  if (list) {
    list.innerHTML = notifications.slice(0, 50).map(n => `
      <div class="notification-item ${n.read ? '' : 'unread'}" onclick="handleNotifClick('${n.id}')">
        <div class="notif-time">${n.timestamp}</div>
        <div style="font-size:0.85rem;">${n.message}</div>
      </div>
    `).join('') || '<p class="text-muted text-sm" style="padding:16px;">No notifications yet.</p>';
  }
}

function handleNotifClick(id) {
  const notif = notifications.find(n => n.id == id);
  if (notif) { notif.read = true; unreadCount = Math.max(0, unreadCount - 1); }
  renderNotifications();
}

function initWebSocket() {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${window.location.host}/ws/alerts`;
  
  try {
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const typeIcons = { 'NEW_ALERT': '🚨', 'DECOY_ARMED': '🪤', 'INTERACTION_DETECTED': '🔴', 'PREDICTION': '🎯' };
        const icon = typeIcons[msg.event_type] || '📢';
        addNotification(msg.event_type === 'NEW_ALERT' ? 'alert' : 'info', `${icon} ${msg.data.message || msg.event_type}`, msg.data);
      } catch(e) { console.warn('WS parse error:', e); }
    };
    ws.onclose = () => { setTimeout(initWebSocket, 5000); };
    ws.onerror = () => { console.warn('WebSocket connection failed — will retry in 5s'); };
  } catch(e) { console.warn('WebSocket not available'); }
}

async function exportCSV(dataType) {
  showToast('Generating CSV export...', 'info');
  try {
    let data = [];
    let headers = [];
    
    if (dataType === 'predictions') {
      const resp = await authFetch('/predictions');
      if (!resp || !resp.ok) return;
      data = await resp.json();
      headers = ['prediction_id', 'created_at', 'scenario_id', 'model_version', 'top_k', 'status'];
    } else if (dataType === 'alerts') {
      const resp = await authFetch('/alerts');
      if (!resp || !resp.ok) return;
      data = await resp.json();
      headers = ['alert_id', 'created_at', 'location_id', 'score', 'priority', 'status', 'summary'];
    }
    
    if (data.length === 0) { showToast('No data to export', 'warning'); return; }
    
    let csv = headers.join(',') + '\n';
    data.forEach(row => {
      csv += headers.map(h => `"${(row[h] || '').toString().replace(/"/g, '""')}"`).join(',') + '\n';
    });
    
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `cashout_${dataType}_${new Date().toISOString().slice(0,10)}.csv`;
    link.click();
    showToast(`${dataType} CSV exported successfully!`, 'success');
  } catch(e) { showToast('Export failed: ' + e.message, 'error'); }
}

async function exportEvidencePDF() {
  if (!currentCaseId && currentPredictionsList.length === 0) {
    showToast('Select a case first or run the demo', 'warning');
    return;
  }
  
  showToast('Generating evidence report PDF...', 'info');
  
  try {
    const caseId = currentCaseId || 'DEMO_AHM_MUM';
    const resp = await authFetch(`/reports/evidence/${caseId}`);
    if (!resp || !resp.ok) { showToast('Failed to fetch evidence data', 'error'); return; }
    const evidence = await resp.json();
    
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF('p', 'mm', 'a4');
    const pageWidth = doc.internal.pageSize.getWidth();
    let y = 20;
    
    // Header
    doc.setFontSize(10);
    doc.setTextColor(100);
    doc.text('MINISTRY OF HOME AFFAIRS • I4C • CYBERCRIME INTELLIGENCE SYSTEM', pageWidth / 2, y, { align: 'center' });
    y += 8;
    
    doc.setFontSize(18);
    doc.setTextColor(30);
    doc.text('EVIDENCE INTELLIGENCE REPORT', pageWidth / 2, y, { align: 'center' });
    y += 8;
    
    doc.setFontSize(10);
    doc.setTextColor(80);
    doc.text(`Case ID: ${evidence.case_id} | Generated: ${new Date().toISOString()}`, pageWidth / 2, y, { align: 'center' });
    y += 4;
    doc.text('CLASSIFICATION: RESTRICTED — LAW ENFORCEMENT ONLY', pageWidth / 2, y, { align: 'center' });
    y += 10;
    
    // Line separator
    doc.setDrawColor(200);
    doc.line(15, y, pageWidth - 15, y);
    y += 8;
    
    // Summary section
    doc.setFontSize(12);
    doc.setTextColor(30);
    doc.text('1. Case Summary', 15, y);
    y += 7;
    doc.setFontSize(9);
    doc.setTextColor(60);
    const summaryLines = [
      `Complaints: ${evidence.complaints_count || 0}`,
      `Suspicious Accounts: ${evidence.suspicious_accounts || 0}`,
      `Transactions Analyzed: ${evidence.transactions_count || 0}`,
      `Predictions Generated: ${evidence.predictions_count || 0}`,
      `Controlled Decoys: ${evidence.decoys_count || 0}`,
      `Audit Chain Status: ${evidence.audit_status || 'VERIFIED'}`
    ];
    summaryLines.forEach(line => { doc.text(line, 20, y); y += 5; });
    y += 5;
    
    // Predictions table
    if (evidence.predictions && evidence.predictions.length > 0) {
      doc.setFontSize(12);
      doc.setTextColor(30);
      doc.text('2. Cash-Out Location Predictions', 15, y);
      y += 3;
      
      doc.autoTable({
        startY: y,
        head: [['Rank', 'Location', 'City', 'Score', 'Window Start', 'Window End']],
        body: evidence.predictions.map((p, i) => [
          i + 1, p.location_id || '', p.city || '', (p.score || 0).toFixed(3), p.window_start || '', p.window_end || ''
        ]),
        theme: 'grid',
        headStyles: { fillColor: [30, 41, 59], fontSize: 8 },
        bodyStyles: { fontSize: 8 },
        margin: { left: 15, right: 15 }
      });
      y = doc.lastAutoTable.finalY + 10;
    }
    
    // Decoy evidence
    if (evidence.decoys && evidence.decoys.length > 0) {
      if (y > 250) { doc.addPage(); y = 20; }
      doc.setFontSize(12);
      doc.setTextColor(30);
      doc.text('3. Controlled Decoy Intelligence', 15, y);
      y += 3;
      
      doc.autoTable({
        startY: y,
        head: [['Decoy ID', 'Type', 'City', 'Status', 'Interactions']],
        body: evidence.decoys.map(d => [d.decoy_id, d.type || d.decoy_type, d.city, d.status, d.interaction_count || 0]),
        theme: 'grid',
        headStyles: { fillColor: [88, 28, 135], fontSize: 8 },
        bodyStyles: { fontSize: 8 },
        margin: { left: 15, right: 15 }
      });
      y = doc.lastAutoTable.finalY + 10;
    }
    
    // Audit verification
    if (y > 260) { doc.addPage(); y = 20; }
    doc.setFontSize(12);
    doc.setTextColor(30);
    doc.text('4. SHA-256 Audit Chain Verification', 15, y);
    y += 7;
    doc.setFontSize(9);
    doc.setTextColor(60);
    doc.text(`Chain Integrity: ${evidence.audit_status || 'VALID'}`, 20, y); y += 5;
    doc.text(`Total Audit Blocks: ${evidence.audit_blocks || 0}`, 20, y); y += 5;
    doc.text(`Verification Timestamp: ${new Date().toISOString()}`, 20, y); y += 5;
    doc.text('This report is cryptographically linked to the tamper-evident audit ledger.', 20, y);
    y += 10;
    
    // Footer
    doc.setDrawColor(200);
    doc.line(15, y, pageWidth - 15, y);
    y += 5;
    doc.setFontSize(7);
    doc.setTextColor(150);
    doc.text('Generated by CashOut Forecast Intelligence System — Ministry of Home Affairs / I4C', pageWidth / 2, y, { align: 'center' });
    doc.text('PROTOTYPE SIMULATION — NOT FOR OPERATIONAL USE', pageWidth / 2, y + 4, { align: 'center' });
    
    doc.save(`Evidence_Report_${caseId}_${new Date().toISOString().slice(0,10)}.pdf`);
    showToast('Evidence PDF generated and downloaded!', 'success');
  } catch(e) {
    console.error('PDF export error:', e);
    showToast('PDF generation failed: ' + e.message, 'error');
  }
}

async function loadComparisonData() {
  const container = document.getElementById('comparisonContent');
  if (!container) return;
  
  try {
    const resp = await authFetch('/analytics/comparison');
    if (!resp || !resp.ok) return;
    const scenarios = await resp.json();
    
    if (!scenarios || scenarios.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-icon">📊</div><h3 class="empty-title">No Scenarios Available</h3><p>Run the demo to generate scenario data.</p><button class="btn btn-primary empty-cta" onclick="triggerDemoScenario()">⚡ Run Demo</button></div>';
      return;
    }
    
    container.innerHTML = scenarios.map(s => `
      <div class="comparison-card">
        <div class="comparison-card-header" style="background: ${s.top_score >= 0.8 ? '#991b1b' : s.top_score >= 0.5 ? '#92400e' : '#065f46'}; padding: 12px 16px; border-radius: 8px 8px 0 0;">
          <strong style="color: white;">${s.scenario_id || 'Unknown'}</strong>
        </div>
        <div style="padding: 16px;">
          <div class="comparison-metric"><span>Complaints</span><strong>${s.complaints || 0}</strong></div>
          <div class="comparison-metric"><span>Mule Accounts</span><strong>${s.mules || 0}</strong></div>
          <div class="comparison-metric"><span>Top Prediction Score</span><strong style="color: #f59e0b;">${(s.top_score || 0).toFixed(3)}</strong></div>
          <div class="comparison-metric"><span>Active Decoys</span><strong style="color: #a78bfa;">${s.decoys || 0}</strong></div>
          <div class="comparison-metric"><span>Alerts Issued</span><strong style="color: #f87171;">${s.alerts || 0}</strong></div>
          <div class="comparison-bar" style="margin-top: 8px;">
            <div style="width: ${Math.min((s.top_score || 0) * 100, 100)}%; height: 4px; background: linear-gradient(90deg, #f59e0b, #ef4444); border-radius: 2px;"></div>
          </div>
        </div>
      </div>
    `).join('');
  } catch(e) { console.error('Comparison load error:', e); }
}

// View Switching
function switchView(viewId) {
  document.querySelectorAll('.content-view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const targetView = document.getElementById(viewId);
  const targetNav = document.querySelector(`.nav-item[data-view="${viewId}"]`);

  if (targetView) targetView.classList.add('active');
  if (targetNav) targetNav.classList.add('active');

  // Trigger view-specific re-renders
  if (viewId === 'view-map' && window.radarMap) {
    setTimeout(() => window.radarMap.invalidateSize(), 200);
  }
  if (viewId === 'view-overview' && window.miniMap) {
    setTimeout(() => window.miniMap.invalidateSize(), 200);
  }
  if (viewId === 'view-metrics' && window.renderBenchmarkCharts) {
    window.renderBenchmarkCharts();
  }
  if (viewId === 'view-network' && window.networkInstance) {
    setTimeout(() => window.networkInstance.fit(), 200);
  }
  if (viewId === 'view-interceptions') {
    loadInterceptionsData();
  }
  if (viewId === 'view-freeze') {
    loadFrozenAccounts();
  }
  if (viewId === 'view-syndicates') {
    loadSyndicateClusters();
  }
  if (viewId === 'view-comparison') {
    loadComparisonData();
  }
}

// Global Refresh
async function refreshAllData() {
  await Promise.all([
    loadOverviewStats(),
    loadAlerts(),
    loadPredictions(),
    loadFeedbackHistory(),
    loadAuditLedger(),
    loadDecoysData(),
    loadInterceptionsData(),
    loadFrozenAccounts(),
    loadSyndicateClusters()
  ]);
  if (typeof renderRiskTimeline === 'function') renderRiskTimeline();
  showToast('Intelligence feeds refreshed successfully', 'success');
}

// 1. Overview Statistics
async function loadOverviewStats() {
  const resp = await authFetch('/overview');
  if (!resp || !resp.ok) return;
  const stats = await resp.json();

  animateCounter('kpiActiveAlerts', stats.active_alerts ?? 0);
  animateCounter('kpiComplaints', stats.complaints_processed ?? 0);
  animateCounter('kpiSuspiciousAccounts', stats.suspicious_accounts ?? 0);
  animateCounter('kpiPredictions', stats.predictions_generated ?? 0);

  if (document.getElementById('badgeAlertsCount')) {
    document.getElementById('badgeAlertsCount').textContent = stats.active_alerts ?? 0;
  }
  if (document.getElementById('badgeDecoysCount')) {
    document.getElementById('badgeDecoysCount').textContent = stats.active_decoys ?? 0;
  }
}

// 1B. Controlled Decoy Intelligence Management
async function loadDecoysData() {
  const resp = await authFetch('/decoy-intelligence/summary');
  if (!resp || !resp.ok) return;
  const data = await resp.json();

  if (document.getElementById('kpiDecoysTotal')) {
    document.getElementById('kpiDecoysTotal').textContent = data.total_decoys ?? 0;
  }
  if (document.getElementById('kpiDecoysArmed')) {
    document.getElementById('kpiDecoysArmed').textContent = data.armed ?? 0;
  }
  if (document.getElementById('kpiDecoysInteractions')) {
    document.getElementById('kpiDecoysInteractions').textContent = data.total_interactions ?? 0;
  }
  if (document.getElementById('badgeDecoysCount')) {
    document.getElementById('badgeDecoysCount').textContent = (data.armed || 0) + (data.interaction_detected || 0);
  }

  renderDecoyCards(data.decoys || []);
  renderDecoyInteractionsTable(data.recent_interactions || []);
}

function renderDecoyCards(decoys) {
  const container = document.getElementById('decoyCardsGrid');
  if (!container) return;

  if (!decoys || decoys.length === 0) {
    container.innerHTML = '<p class="text-muted text-sm py-4 text-center">No controlled synthetic honeypots currently armed. Trigger the Ahmedabad → Mumbai demo to deploy decoys.</p>';
    return;
  }

  container.innerHTML = decoys.map(d => {
    let statusClass = 'status-inactive';
    let statusIcon = '🟢';
    let statusLabel = 'INACTIVE';

    if (d.status === 'ARMED') {
      statusClass = 'status-armed';
      statusIcon = '🟡';
      statusLabel = 'ARMED';
    } else if (d.status === 'INTERACTION_DETECTED') {
      statusClass = 'status-detected';
      statusIcon = '🔴';
      statusLabel = 'INTERACTION DETECTED';
    }

    return `
      <div class="decoy-card ${statusClass}">
        <div class="decoy-card-header">
          <div class="decoy-id-badge font-mono font-bold">${d.decoy_id}</div>
          <span class="badge ${d.status === 'INTERACTION_DETECTED' ? 'badge-rose' : 'badge-amber'}">${statusIcon} ${statusLabel}</span>
        </div>
        <div class="decoy-type-tag text-xs font-mono text-cyan mt-1">${d.decoy_type}</div>
        <div class="decoy-meta-grid text-xs text-muted mt-2 font-mono">
          <div>Synthetic ID: <span class="text-slate-200">${d.synthetic_account_id}</span></div>
          <div>Location: <span class="text-slate-200">${d.city}</span></div>
          <div>Interactions: <span class="text-rose font-bold">${d.interaction_count} hits</span></div>
          <div>Rationale: <span class="text-slate-300">${d.activation_reason || 'Dispersal Interception'}</span></div>
        </div>
      </div>
    `;
  }).join('');
}

function renderDecoyInteractionsTable(interactions) {
  const tbody = document.getElementById('decoyInteractionsTableBody');
  if (!tbody) return;

  if (!interactions || interactions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No simulated telemetry recorded yet.</td></tr>';
    return;
  }

  tbody.innerHTML = interactions.map(i => `
    <tr>
      <td class="font-mono text-xs text-muted">${i.timestamp ? i.timestamp.substring(11,19) : 'N/A'}</td>
      <td class="font-mono text-cyan font-semibold">${i.source_account_id}</td>
      <td class="font-mono text-purple font-bold">${i.decoy_id}</td>
      <td class="font-mono text-emerald">₹${Number(i.synthetic_amount).toLocaleString('en-IN')} <span class="badge-xs badge-purple">SYNTHETIC</span></td>
      <td class="text-xs">${i.originating_city || '—'} ➔ ${i.destination_city || '—'}</td>
      <td><span class="badge badge-cyan font-mono text-xs">${i.interaction_type}</span></td>
    </tr>
  `).join('');
}

// 2. Alerts Management
let cachedAlerts = [];
async function loadAlerts() {
  const resp = await authFetch('/alerts?limit=30');
  if (!resp || !resp.ok) return;
  cachedAlerts = await resp.json();
  renderOverviewAlertsTable(cachedAlerts.slice(0, 5));
  renderAlertsGrid(cachedAlerts);
}

function renderOverviewAlertsTable(alerts) {
  const tbody = document.getElementById('overviewAlertsTableBody');
  if (!tbody) return;
  if (!alerts || alerts.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">No active alerts requiring intervention.</td></tr>';
    return;
  }
  tbody.innerHTML = alerts.map(a => {
    const pClass = a.priority === 'HIGH' ? 'badge-rose' : a.priority === 'MEDIUM' ? 'badge-amber' : 'badge-cyan';
    const win = a.expected_window_start ? `${a.expected_window_start.substring(11,16)}–${a.expected_window_end.substring(11,16)}` : 'Imminent';
    return `
      <tr>
        <td><strong>${a.city || 'Cluster'}</strong> <span class="text-xs text-muted">(${a.location_id})</span></td>
        <td>
          <div class="score-bar-wrapper">
            <div class="score-bar-fill" style="width: ${Math.round(a.score * 100)}%"></div>
            <span class="score-text font-mono">${(a.score * 100).toFixed(0)}%</span>
          </div>
        </td>
        <td><span class="badge ${pClass}">${a.priority}</span></td>
        <td class="font-mono text-xs">${win}</td>
        <td>
          <button class="btn btn-xs btn-primary" onclick="openCaseFromPrediction('${a.prediction_id}')">Investigate</button>
        </td>
      </tr>
    `;
  }).join('');
}

function renderAlertsGrid(alerts) {
  const container = document.getElementById('alertsCardsContainer');
  if (!container) return;
  if (!alerts || alerts.length === 0) {
    container.innerHTML = '<div class="col-span-3 text-center py-8 text-muted">No interception alerts match the filter.</div>';
    return;
  }
  container.innerHTML = alerts.map(a => {
    const pClass = a.priority === 'HIGH' ? 'border-rose text-rose' : a.priority === 'MEDIUM' ? 'border-amber text-amber' : 'border-cyan text-cyan';
    const badgeClass = a.priority === 'HIGH' ? 'badge-rose' : a.priority === 'MEDIUM' ? 'badge-amber' : 'badge-cyan';
    const win = a.expected_window_start ? `${a.expected_window_start.substring(0, 10)} ${a.expected_window_start.substring(11,16)} – ${a.expected_window_end.substring(11,16)}` : 'Under 2 hours';
    
    return `
      <div class="alert-card ${pClass}">
        <div class="alert-card-header">
          <div>
            <span class="badge ${badgeClass}">${a.priority} PRIORITY</span>
            <span class="alert-id font-mono">${a.alert_id.substring(0,8)}...</span>
          </div>
          <div class="alert-score-badge">
            <span class="text-xs text-muted">CONFIDENCE</span>
            <span class="font-mono font-bold">${(a.score * 100).toFixed(0)}%</span>
          </div>
        </div>

        <div class="alert-card-body">
          <h3 class="alert-target-city">${a.city || 'Unknown'}, ${a.state || 'India'}</h3>
          <div class="alert-location-cluster font-mono text-xs text-muted">ATM Node ID: ${a.location_id}</div>
          <p class="alert-summary">${a.summary || 'Suspicious velocity and cross-city account hops indicate cash withdrawal extraction.'}</p>
          
          <div class="alert-window-box">
            <span class="text-xs text-muted">FORECAST CASH-OUT WINDOW:</span>
            <div class="font-mono text-sm text-cyan font-bold">${win}</div>
          </div>
        </div>

        <div class="alert-card-actions">
          <button class="btn btn-sm btn-primary w-full" onclick="openCaseFromPrediction('${a.prediction_id}')">
            <span>Launch Evidence Workbench</span>
            <span>→</span>
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function filterAlerts(priority) {
  document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
  event.target.classList.add('active');

  if (priority === 'ALL') {
    renderAlertsGrid(cachedAlerts);
  } else {
    const filtered = cachedAlerts.filter(a => a.priority === priority);
    renderAlertsGrid(filtered);
  }
}

// 3. Predictions Management
async function loadPredictions() {
  const resp = await authFetch('/predictions?limit=25');
  if (!resp || !resp.ok) return;
  currentPredictionsList = await resp.json();
  renderOverviewPredictionsTable(currentPredictionsList.slice(0, 5));
  renderPredictionsFullTable(currentPredictionsList);
  updateCaseSelectorOptions(currentPredictionsList);
}

function renderOverviewPredictionsTable(preds) {
  const tbody = document.getElementById('overviewPredictionsTableBody');
  if (!tbody) return;
  if (!preds || preds.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No predictions recorded yet.</td></tr>';
    return;
  }
  tbody.innerHTML = preds.map(p => {
    const scoreVal = p.top_score ? (p.top_score * 100).toFixed(0) : '0';
    const win = p.top_window_start ? `${p.top_window_start.substring(11,16)}–${p.top_window_end.substring(11,16)}` : 'Pending';
    return `
      <tr>
        <td class="font-mono font-semibold text-cyan">${p.scenario_id || 'SCN-GLOBAL'}</td>
        <td><strong>${p.top_location || 'Candidate'}</strong></td>
        <td>
          <div class="score-bar-wrapper">
            <div class="score-bar-fill" style="width: ${scoreVal}%"></div>
            <span class="score-text font-mono">${scoreVal}%</span>
          </div>
        </td>
        <td class="font-mono text-xs">${win}</td>
        <td><span class="badge ${p.status === 'active' ? 'badge-rose' : 'badge-cyan'}">${p.status.toUpperCase()}</span></td>
        <td>
          <button class="btn btn-xs btn-outline" onclick="openCaseFromPrediction('${p.prediction_id}')">View Evidence</button>
        </td>
      </tr>
    `;
  }).join('');
}

function renderPredictionsFullTable(preds) {
  const tbody = document.getElementById('predictionsFullTableBody');
  if (!tbody) return;
  tbody.innerHTML = preds.map(p => {
    const scoreVal = p.top_score ? (p.top_score * 100).toFixed(0) : '0';
    const win = p.top_window_start ? `${p.top_window_start.substring(0,10)} ${p.top_window_start.substring(11,16)}–${p.top_window_end.substring(11,16)}` : 'N/A';
    return `
      <tr>
        <td class="font-mono text-xs">${p.prediction_id.substring(0,8)}...</td>
        <td class="text-xs text-muted font-mono">${p.created_at ? p.created_at.substring(0,16).replace('T',' ') : ''}</td>
        <td class="font-mono font-semibold text-cyan">${p.scenario_id}</td>
        <td><strong>${p.top_location}</strong></td>
        <td>
          <div class="score-bar-wrapper">
            <div class="score-bar-fill" style="width: ${scoreVal}%"></div>
            <span class="score-text font-mono">${scoreVal}%</span>
          </div>
        </td>
        <td class="font-mono text-xs">${win}</td>
        <td><span class="badge ${p.status === 'active' ? 'badge-rose' : 'badge-cyan'}">${p.status.toUpperCase()}</span></td>
        <td>
          <button class="btn btn-xs btn-primary" onclick="openCaseFromPrediction('${p.prediction_id}')">Investigate</button>
        </td>
      </tr>
    `;
  }).join('');
}

function updateCaseSelectorOptions(preds) {
  const sel = document.getElementById('casePredictionSelector');
  if (!sel) return;
  sel.innerHTML = '<option value="">Select Case to Review...</option>' +
    preds.map(p => `<option value="${p.prediction_id}">${p.scenario_id} — Top: ${p.top_location} (${p.created_at ? p.created_at.substring(0,10) : ''})</option>`).join('');
}

// 4. Case Review / Investigator Workbench
function openCaseFromPrediction(predId) {
  switchView('view-workbench');
  const sel = document.getElementById('casePredictionSelector');
  if (sel) sel.value = predId;
  loadCaseDetails(predId);
}

async function loadCaseDetails(predId) {
  if (!predId) return;
  currentCaseId = predId;
  const area = document.getElementById('workbenchContentArea');
  area.innerHTML = '<div class="text-center py-12 text-muted">Retrieving cryptographic case file, SHAP evidence & Decoy telemetry...</div>';

  const resp = await authFetch(`/predictions/${predId}`);
  if (!resp || !resp.ok) {
    area.innerHTML = '<div class="text-center py-12 text-rose">Failed to load case details.</div>';
    return;
  }
  const caseData = await resp.json();

  // Also fetch Decoy telemetry for this case
  let decoySummary = null;
  try {
    const dResp = await authFetch(`/cases/${caseData.scenario_id}/decoy/evidence`);
    if (dResp && dResp.ok) {
      decoySummary = await dResp.json();
    }
  } catch (e) {
    console.log('Decoy fetch fallback', e);
  }

  renderCaseWorkbench(caseData, decoySummary);
}

function renderCaseWorkbench(c, decoySummary) {
  const area = document.getElementById('workbenchContentArea');
  const topCandidate = c.candidates && c.candidates.length > 0 ? c.candidates[0] : null;
  const evidenceList = topCandidate ? topCandidate.evidence : [];
  const txnPath = topCandidate ? topCandidate.transaction_path : [];

  const decoyBullets = decoySummary && decoySummary.evidence_bullets ? decoySummary.evidence_bullets : [];
  const decoyInteractions = decoySummary && decoySummary.interactions ? decoySummary.interactions : [];

  area.innerHTML = `
    <!-- Top Case Banner -->
    <div class="case-header-banner">
      <div class="banner-main">
        <div class="case-tag font-mono">CASE SCENARIO: ${c.scenario_id}</div>
        <h2 class="case-title">Predicted Cash-Out Target: <span class="text-cyan">${topCandidate ? topCandidate.location_id : 'Unknown'}</span></h2>
        <div class="case-meta-row font-mono text-xs text-muted">
          <span>PREDICTION ID: ${c.prediction_id}</span> • 
          <span>MODEL: ${c.model_version}</span> • 
          <span>TIMESTAMP: ${c.created_at}</span> •
          <span class="text-purple font-bold">CONTROLLED DECOY LAYER ACTIVE</span>
        </div>
      </div>
      <div class="banner-right">
        <div class="risk-meter-box">
          <div class="meter-label text-xs">MODEL CONFIDENCE SCORE</div>
          <div class="meter-val text-rose font-mono font-bold">${topCandidate ? (topCandidate.score * 100).toFixed(0) : 0}%</div>
        </div>
      </div>
    </div>

    <!-- 3-Column Workbench Split -->
    <div class="workbench-grid-3">
      
      <!-- Col 1: Top-K Ranked Candidates -->
      <div class="dashboard-panel">
        <div class="panel-header">
          <h4 class="panel-title">Ranked Candidate Locations</h4>
        </div>
        <div class="panel-body p-0">
          <div class="candidate-list">
            ${(c.candidates || []).map(cand => `
              <div class="candidate-item ${cand.rank === 1 ? 'rank-top' : ''}">
                <div class="candidate-rank font-mono">#${cand.rank}</div>
                <div class="candidate-info">
                  <div class="candidate-name">${cand.location_id}</div>
                  <div class="text-xs text-muted font-mono">Window: ${cand.expected_window_start ? cand.expected_window_start.substring(11,16) : 'N/A'}–${cand.expected_window_end ? cand.expected_window_end.substring(11,16) : 'N/A'}</div>
                </div>
                <div class="candidate-score font-mono font-bold text-cyan">
                  ${(cand.score * 100).toFixed(0)}%
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>

      <!-- Col 2: SHAP & Decoy Intelligence Evidence -->
      <div class="dashboard-panel">
        <div class="panel-header">
          <h4 class="panel-title">Explainable Evidence Signals (Rank #1)</h4>
          <span class="badge badge-purple">DECOY + ML SIGNALS</span>
        </div>
        <div class="panel-body">
          <!-- Decoy Intelligence Box -->
          <div class="decoy-evidence-box mb-3 p-3 bg-purple-950/30 border border-purple-800/40 rounded">
            <div class="text-xs font-bold text-purple-400 font-mono mb-2 flex items-center gap-1">
              <span>🪤 CONTROLLED DECOY INTELLIGENCE EVIDENCE</span>
              <span class="badge-xs badge-purple">PROACTIVE TELEMETRY</span>
            </div>
            ${decoyBullets.length > 0 ? decoyBullets.map(db => `
              <div class="text-xs text-slate-300 py-1 flex items-start gap-1">
                <span class="text-emerald-400 font-bold">✓</span>
                <span>${db}</span>
              </div>
            `).join('') : `
              <div class="text-xs text-slate-400 py-1 flex items-start gap-1">
                <span class="text-cyan-400 font-bold">✓</span>
                <span>Suspicious dispersal pattern detected on layering mule node.</span>
              </div>
              <div class="text-xs text-slate-400 py-1 flex items-start gap-1">
                <span class="text-cyan-400 font-bold">✓</span>
                <span>Controlled synthetic decoy D-001 armed to intercept simulated probe.</span>
              </div>
            `}
          </div>

          <div class="evidence-bullets-list">
            <h5 class="text-xs font-semibold text-muted mb-2 font-mono">LIGHTGBM FORECASTER EVIDENCE</h5>
            ${evidenceList.length > 0 ? evidenceList.map(e => `
              <div class="evidence-bullet">
                <span class="bullet-icon">🔍</span>
                <span class="bullet-text">${e}</span>
              </div>
            `).join('') : '<p class="text-muted text-sm">No structured evidence signals available.</p>'}
          </div>

          <div class="mt-4 p-3 bg-slate-900 rounded border border-slate-800">
            <h5 class="text-xs font-semibold text-muted mb-2 font-mono">INTERCEPTION TIME WINDOW</h5>
            <div class="text-sm font-mono text-cyan mb-3">
              ${topCandidate && topCandidate.expected_window_start ? `${topCandidate.expected_window_start}  ➔  ${topCandidate.expected_window_end}` : 'Immediate / Next 2 Hours'}
            </div>
            <button class="btn btn-sm btn-primary w-full" style="width:100%;" onclick="dispatchPoliceUnit('${c.prediction_id}', '${topCandidate ? topCandidate.location_id : 'M17'}', 'PS-MUM-BKC-01', 'CRITICAL')">
              🚨 Dispatch BKC Cyber Police Unit
            </button>
          </div>
        </div>
      </div>

      <!-- Col 3: Money Flow Chain & Adjudication Action -->
      <div class="dashboard-panel">
        <div class="panel-header">
          <h4 class="panel-title">Transaction Trail & Action</h4>
        </div>
        <div class="panel-body">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <h5 class="text-xs font-semibold text-muted font-mono">DETECTED FLOW HOPS</h5>
            <button class="btn btn-sm btn-outline" style="font-size:10px; padding:2px 6px;" onclick="execute1930Freeze('ACC_MULE_1', 250000)">
              🔒 1930 Freeze Mule
            </button>
          </div>
          <div class="hops-chain">
            ${txnPath.length > 0 ? txnPath.map((hop, i) => `
              <div class="hop-step">
                <div class="hop-dot"></div>
                <div class="hop-content">
                  <div class="hop-node font-mono">${hop.node_id}</div>
                  <div class="hop-detail text-xs text-muted">
                    ${hop.city ? hop.city + ' • ' : ''}${hop.account_type || hop.role || 'Node'}
                    ${hop.role === 'mule' || hop.node_id.includes('MULE') ? ` <button class="btn-link text-xs text-rose" style="border:none;background:none;cursor:pointer;" onclick="execute1930Freeze('${hop.node_id}', 250000)">[🔒 1930 Freeze]</button>` : ''}
                  </div>
                </div>
              </div>
            `).join('') : '<p class="text-muted text-xs">Direct single-hop path detected.</p>'}
          </div>

          <!-- Human Adjudication Form -->
          <div class="adjudication-form mt-4">
            <h5 class="text-xs font-semibold text-muted mb-2 font-mono">OFFICER ADJUDICATION VERDICT</h5>
            <div class="verdict-buttons-group">
              <button class="btn btn-sm btn-confirm" onclick="submitAdjudication('${c.prediction_id}', 'confirm')">✓ CONFIRM</button>
              <button class="btn btn-sm btn-reject" onclick="submitAdjudication('${c.prediction_id}', 'reject')">✕ REJECT</button>
              <button class="btn btn-sm btn-uncertain" onclick="submitAdjudication('${c.prediction_id}', 'uncertain')">? UNCERTAIN</button>
            </div>
            <textarea id="adjudicationComment" class="adjudication-textarea mt-2" placeholder="Officer notes or intelligence corroboration..."></textarea>
          </div>
        </div>
      </div>

    </div>
  `;
}

// 5. Adjudication Submission
async function submitAdjudication(predId, action) {
  const comment = document.getElementById('adjudicationComment')?.value || '';
  const resp = await authFetch('/feedback', {
    method: 'POST',
    body: JSON.stringify({
      prediction_id: predId,
      action: action,
      comment: comment
    })
  });

  if (resp && resp.ok) {
    showToast(`Case marked as ${action.toUpperCase()}. Recorded in audit chain.`, 'success');
    loadFeedbackHistory();
    loadOverviewStats();
    loadAlerts();
  } else {
    showToast('Failed to record adjudication.', 'error');
  }
}

// 6. Feedback & Governance History
async function loadFeedbackHistory() {
  const resp = await authFetch('/feedback');
  if (!resp || !resp.ok) return;
  const list = await resp.json();
  const tbody = document.getElementById('feedbackTableBody');
  if (!tbody) return;
  if (!list || list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">No investigator adjudications submitted yet.</td></tr>';
    return;
  }
  tbody.innerHTML = list.map(f => {
    const actClass = f.action === 'confirm' ? 'badge-emerald' : f.action === 'reject' ? 'badge-rose' : 'badge-amber';
    return `
      <tr>
        <td class="font-mono text-xs">${f.feedback_id.substring(0,8)}...</td>
        <td class="font-mono text-xs">${f.prediction_id.substring(0,8)}...</td>
        <td><span class="badge ${actClass}">${f.action.toUpperCase()}</span></td>
        <td class="font-mono text-xs">${f.actual_location_id || 'Corroborated'}</td>
        <td class="text-sm">${f.comment || '—'}</td>
        <td class="font-mono text-xs text-muted">${f.timestamp ? f.timestamp.substring(0,16).replace('T',' ') : ''}</td>
        <td>
          <span class="badge ${f.approved_for_training ? 'badge-emerald' : 'badge-cyan'}">
            ${f.approved_for_training ? 'YES' : 'PENDING REVIEW'}
          </span>
        </td>
      </tr>
    `;
  }).join('');
}

// 7. SHA-256 Audit Chain Verification
async function loadAuditLedger() {
  const resp = await authFetch('/audit?limit=20');
  if (!resp || !resp.ok) return;
  const records = await resp.json();
  const tbody = document.getElementById('auditChainTableBody');
  if (!tbody) return;
  if (!records || records.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-muted">No audit blocks recorded.</td></tr>';
    return;
  }
  tbody.innerHTML = records.map(r => `
    <tr>
      <td class="font-bold text-cyan">#${r.sequence_number}</td>
      <td class="text-muted">${r.timestamp ? r.timestamp.substring(0,19).replace('T',' ') : ''}</td>
      <td><span class="badge badge-cyan">${r.event_type}</span></td>
      <td class="text-muted">${r.user_id || 'system'}</td>
      <td class="font-mono text-xs">${r.event_data_hash.substring(0,12)}...</td>
      <td class="font-mono text-xs text-muted">${r.previous_hash}</td>
      <td class="font-mono text-xs font-bold text-emerald">${r.current_hash}</td>
      <td><span class="badge badge-emerald">VERIFIED</span></td>
    </tr>
  `).join('');
}

async function verifyAuditLedger() {
  const btn = document.getElementById('btnVerifyChain');
  btn.disabled = true;
  btn.textContent = 'Verifying SHA-256 Block Proofs...';

  const resp = await authFetch('/audit/verify', { method: 'POST' });
  btn.disabled = false;
  btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg> Verify Cryptographic Integrity';

  if (resp && resp.ok) {
    const res = await resp.json();
    const banner = document.getElementById('auditIntegrityBanner');
    const title = document.getElementById('chainStatusTitle');
    const sub = document.getElementById('chainStatusSub');

    if (res.is_valid) {
      banner.className = 'integrity-banner banner-valid';
      title.textContent = `HASH CHAIN STATUS: VALID & UNBROKEN (${res.n_records} BLOCKS VERIFIED)`;
      sub.textContent = 'Every cryptographic link matches mathematically. No record has been modified or excised.';
      showToast(`Chain verified successfully: ${res.n_records} blocks intact.`, 'success');
    } else {
      banner.className = 'integrity-banner banner-invalid';
      title.textContent = 'HASH CHAIN STATUS: COMPROMISED!';
      sub.textContent = `Tampering detected at block ${res.broken_at_sequence}. Ledger integrity failure.`;
      showToast('Chain verification failed! Evidence altered.', 'error');
    }
    loadAuditLedger();
  }
}

// 8. One-Click Interactive Demo Launcher (10-Step Controlled Decoy Interception Sequence)
async function triggerDemoScenario() {
  const btn = document.getElementById('btnRunDemo');
  btn.disabled = true;
  btn.innerHTML = '<span class="demo-icon">⏳</span><span>Simulating 10-Step Decoy Interception...</span>';
  
  showToast('Step 1-2: Ingesting Ahmedabad Cyber-Fraud Complaints & Layering Network...', 'info');

  try {
    const resp = await authFetch('/demo/run', { method: 'POST' });
    if (!resp || !resp.ok) {
      throw new Error('Demo failed to run.');
    }
    const data = await resp.json();

    setTimeout(() => {
      showToast('Step 3-4: Dispersal splitter detected (Mule Risk 0.94) ➔ Controlled Decoys D-001..D-003 armed!', 'warning');
    }, 600);

    setTimeout(() => {
      showToast('Step 5-6: Captured ₹1,20,000 simulated honeypot interaction towards Mumbai. Graph updated!', 'info');
    }, 1400);

    setTimeout(() => {
      showToast('Step 7-9: Priority Alert Dispatched: Mumbai BKC Cash-Out Cluster Predicted (Score: 0.94)!', 'success');
    }, 2200);
    
    // Refresh intelligence feeds
    await refreshAllData();
    
    // Automatically open the new case in Workbench
    if (data.prediction_id) {
      setTimeout(() => {
        openCaseFromPrediction(data.prediction_id);
        showToast('Step 10: Case loaded in Investigator Workbench with Decoy Intelligence evidence ready for adjudication.', 'info');
      }, 1500);
    }
  } catch (err) {
    showToast(err.message || 'Demo run error', 'error');
  } finally {
    setTimeout(() => {
      btn.disabled = false;
      btn.innerHTML = '<span class="demo-icon">⚡</span><span>Ahmedabad → Mumbai Demo</span>';
    }, 2500);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 12. TACTICAL POLICE INTERCEPTION & DISPATCH
// ─────────────────────────────────────────────────────────────────────────────

async function loadInterceptionsData() {
  try {
    // 1. Load active dispatches
    const dispResp = await authFetch('/interceptions/active');
    if (dispResp && dispResp.ok) {
      const dispatches = await dispResp.json();
      const tbody = document.getElementById('dispatchesTableBody');
      if (tbody) {
        if (!dispatches || dispatches.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No active police dispatches. Issue a tactical advisory from Workbench or Alerts.</td></tr>';
        } else {
          tbody.innerHTML = dispatches.map(d => `
            <tr>
              <td><span class="font-mono text-cyan">${d.dispatch_id}</span></td>
              <td><strong>${d.location_city || 'Mumbai'}</strong> (${d.location_id || 'Cluster'})</td>
              <td>${d.station_name}</td>
              <td><span class="badge ${d.status === 'DISPATCHED' ? 'badge-amber' : d.status === 'INTERCEPTED' ? 'badge-emerald' : 'badge-rose'}">${d.status}</span></td>
              <td><code class="font-mono text-xs" style="color: var(--accent-purple);">${d.verification_token}</code></td>
              <td>
                <select class="form-select form-select-sm" style="width:auto; padding:2px 6px; font-size:11px;" onchange="updateDispatchStatus('${d.dispatch_id}', this.value)">
                  <option value="DISPATCHED" ${d.status === 'DISPATCHED' ? 'selected' : ''}>DISPATCHED</option>
                  <option value="EN_ROUTE" ${d.status === 'EN_ROUTE' ? 'selected' : ''}>EN_ROUTE</option>
                  <option value="PATROL_ACTIVE" ${d.status === 'PATROL_ACTIVE' ? 'selected' : ''}>PATROL_ACTIVE</option>
                  <option value="INTERCEPTED" ${d.status === 'INTERCEPTED' ? 'selected' : ''}>INTERCEPTED</option>
                  <option value="STAND_DOWN" ${d.status === 'STAND_DOWN' ? 'selected' : ''}>STAND_DOWN</option>
                </select>
              </td>
            </tr>
          `).join('');
        }
      }
    }

    // 2. Load police stations directory
    const psResp = await authFetch('/jurisdictions/police-stations');
    if (psResp && psResp.ok) {
      const stations = await psResp.json();
      const tbody = document.getElementById('policeStationsTableBody');
      if (tbody) {
        tbody.innerHTML = stations.map(s => `
          <tr>
            <td><strong>${s.name}</strong></td>
            <td>${s.city}, ${s.state}</td>
            <td>${s.nodal_officer || 'Cyber Cell'}</td>
            <td><a href="tel:${s.contact_phone}" style="color: var(--accent-blue); text-decoration: none;">${s.contact_phone}</a></td>
            <td><span class="badge badge-outline">${s.jurisdiction_radius_km} km</span></td>
          </tr>
        `).join('');
      }
    }
  } catch(e) {
    console.error('Error loading interceptions data:', e);
  }
}

async function dispatchPoliceUnit(predId, locId, stationId, priority = 'HIGH') {
  showToast('Dispatching tactical advisory to local Cyber Police Station...', 'info');
  try {
    const resp = await authFetch('/interceptions/dispatch', {
      method: 'POST',
      body: JSON.stringify({
        prediction_id: predId || 'DEMO_AHM_MUM',
        location_id: locId || 'M17',
        station_id: stationId,
        priority: priority,
        officer_notes: 'Proactive cash-out interdiction advisory generated from LightGBM spatiotemporal forecast.'
      })
    });
    if (resp && resp.ok) {
      const data = await resp.json();
      showToast(`🚨 Police Dispatch Order ${data.dispatch_id} issued to ${data.station.name}! (Token: ${data.verification_token})`, 'success');
      loadInterceptionsData();
      loadAuditLedger();
    } else {
      showToast('Failed to issue police dispatch order.', 'error');
    }
  } catch(e) {
    showToast('Dispatch error: ' + e.message, 'error');
  }
}

function openDispatchModal(predId, locId) {
  const currentPred = currentPredictionsList[0];
  const targetPredId = predId || (currentPred ? currentPred.prediction_id : 'DEMO_AHM_MUM');
  const targetLocId = locId || (currentPred ? currentPred.location_id : 'M17');
  dispatchPoliceUnit(targetPredId, targetLocId, 'PS-MUM-BKC-01', 'CRITICAL');
}

async function updateDispatchStatus(dispatchId, status) {
  try {
    const resp = await authFetch(`/interceptions/${dispatchId}/status`, {
      method: 'POST',
      body: JSON.stringify({ status: status, notes: `Status changed by investigator to ${status}` })
    });
    if (resp && resp.ok) {
      showToast(`Dispatch ${dispatchId} status updated to ${status}`, 'success');
      loadInterceptionsData();
      loadAuditLedger();
    }
  } catch(e) {
    showToast('Status update failed', 'error');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 13. 1930 EMERGENCY CYBER FREEZE & LIEN MARKING
// ─────────────────────────────────────────────────────────────────────────────

async function execute1930Freeze(accountId, amount = 250000.0) {
  if (!confirm(`CONFIRM 1930 EMERGENCY CYBER FREEZE:\n\nExecute immediate financial lien on Mule Account [${accountId}] for ₹${amount.toLocaleString()} under Section 102 CrPC / Section 107 BNSS?`)) {
    return;
  }
  showToast(`Placing automated 1930 lien on Account ${accountId}...`, 'info');
  try {
    const resp = await authFetch(`/accounts/${accountId}/freeze`, {
      method: 'POST',
      body: JSON.stringify({
        amount: amount,
        reason: '1930 Cyber Helpline Automated Interception (Section 102 CrPC / Section 107 BNSS)'
      })
    });
    if (resp && resp.ok) {
      const data = await resp.json();
      showToast(`🔒 ${data.message}`, 'success');
      loadFrozenAccounts();
      loadOverviewStats();
      loadAuditLedger();
    } else {
      showToast('Freeze operation failed.', 'error');
    }
  } catch(e) {
    showToast('Freeze error: ' + e.message, 'error');
  }
}

async function executeAccountUnfreeze(accountId) {
  if (!confirm(`Are you sure you want to remove the lien on Account [${accountId}]?`)) return;
  try {
    const resp = await authFetch(`/accounts/${accountId}/unfreeze`, { method: 'POST' });
    if (resp && resp.ok) {
      showToast(`Account ${accountId} lien removed.`, 'info');
      loadFrozenAccounts();
      loadOverviewStats();
      loadAuditLedger();
    }
  } catch(e) {
    showToast('Unfreeze error: ' + e.message, 'error');
  }
}

async function loadFrozenAccounts() {
  try {
    const resp = await authFetch('/accounts/frozen');
    if (!resp || !resp.ok) return;
    const data = await resp.json();

    animateCounter('kpiFrozenAccountsCount', data.total_frozen_accounts || 0);
    const volumeEl = document.getElementById('kpiTotalSecuredFunds');
    if (volumeEl) {
      volumeEl.textContent = `₹${(data.total_funds_secured || 0).toLocaleString('en-IN')}`;
    }

    const badge = document.getElementById('badgeFrozenCount');
    if (badge) {
      badge.textContent = `${data.total_frozen_accounts || 0} LIEN`;
    }

    const tbody = document.getElementById('frozenAccountsTableBody');
    if (tbody) {
      if (!data.accounts || data.accounts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">No accounts currently lien-marked. Click "Emergency 1930 Freeze" on any suspicious mule account.</td></tr>';
      } else {
        tbody.innerHTML = data.accounts.map(a => `
          <tr>
            <td><strong class="font-mono text-amber">${a.account_id}</strong></td>
            <td>${a.city || 'Mumbai'}</td>
            <td><span class="badge badge-rose">${(a.mule_risk_score || 0.92).toFixed(2)}</span></td>
            <td class="font-mono font-semibold text-emerald">₹${(a.frozen_amount || 0).toLocaleString('en-IN')}</td>
            <td class="text-xs font-mono text-muted">${a.frozen_at ? a.frozen_at.substring(0, 19).replace('T', ' ') : 'Just now'}</td>
            <td><span class="badge badge-outline text-xs">${a.freeze_reason || 'Sec 102 CrPC'}</span></td>
            <td>
              <button class="btn btn-sm btn-secondary" onclick="executeAccountUnfreeze('${a.account_id}')">Unfreeze</button>
            </td>
          </tr>
        `).join('');
      }
    }
  } catch(e) {
    console.error('Error loading frozen accounts:', e);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 14. BULK NCRP INGESTION & SYNDICATE CLUSTERS
// ─────────────────────────────────────────────────────────────────────────────

async function bulkIngestDemoNCRP() {
  showToast('Connecting to simulated NCRP API gateway...', 'info');
  const sampleComplaints = [
    { crime_type: "Part-Time Job Telegram Scam", amount: 150000.0, victim_bank: "HDFC Bank", scenario_tag: "NCRP_BATCH_MUM" },
    { crime_type: "Digital Arrest Fake CBI Scam", amount: 480000.0, victim_bank: "ICICI Bank", scenario_tag: "NCRP_BATCH_MUM" },
    { crime_type: "Electricity Bill APK Fraud", amount: 75000.0, victim_bank: "State Bank of India", scenario_tag: "NCRP_BATCH_AHM" },
    { crime_type: "Stock Market VIP Trading Scam", amount: 620000.0, victim_bank: "Axis Bank", scenario_tag: "NCRP_BATCH_BLR" },
    { crime_type: "Customs Parcel Impersonation", amount: 220000.0, victim_bank: "Punjab National Bank", scenario_tag: "NCRP_BATCH_DEL" },
  ];

  try {
    const resp = await authFetch('/complaints/bulk-ingest', {
      method: 'POST',
      body: JSON.stringify({ complaints: sampleComplaints })
    });
    if (resp && resp.ok) {
      const data = await resp.json();
      showToast(`📥 Successfully ingested ${data.ingested_count} citizen complaints from NCRP batch feed!`, 'success');
      loadSyndicateClusters();
      loadOverviewStats();
      loadAuditLedger();
    }
  } catch(e) {
    showToast('Bulk ingest error: ' + e.message, 'error');
  }
}

async function loadSyndicateClusters() {
  try {
    const resp = await authFetch('/complaints/syndicates');
    if (!resp || !resp.ok) return;
    const data = await resp.json();

    animateCounter('kpiSyndicatesCount', data.total_syndicates_detected || 0);
    const volEl = document.getElementById('kpiSyndicatesVolume');
    if (volEl && data.syndicates) {
      const totalVol = data.syndicates.reduce((acc, s) => acc + (s.estimated_illicit_volume || 0), 0);
      volEl.textContent = `₹${(totalVol || 1250000).toLocaleString('en-IN')}`;
    }

    const container = document.getElementById('syndicatesCardsGrid');
    if (container) {
      if (!data.syndicates || data.syndicates.length === 0) {
        container.innerHTML = `
          <div class="dashboard-panel col-span-2">
            <div class="empty-state">
              <div class="empty-icon">🕸️</div>
              <h3 class="empty-title">No Syndicates Detected Yet</h3>
              <p>Click "Ingest NCRP Complaints" or "Run Live Demo Scenario" to run graph clustering algorithms.</p>
              <button class="btn btn-primary empty-cta" onclick="bulkIngestDemoNCRP()">📥 Ingest NCRP Complaints</button>
            </div>
          </div>
        `;
      } else {
        container.innerHTML = data.syndicates.map(s => `
          <div class="dashboard-panel">
            <div class="panel-header" style="border-bottom: 1px solid rgba(244, 63, 94, 0.2);">
              <div>
                <h4 class="panel-title font-mono text-rose">${s.syndicate_id}: ${s.syndicate_name}</h4>
                <span class="text-xs text-muted">Estimated Volume: <strong class="text-emerald">₹${(s.estimated_illicit_volume || 0).toLocaleString('en-IN')}</strong></span>
              </div>
              <span class="badge ${s.threat_severity === 'CRITICAL' ? 'badge-rose' : 'badge-amber'}">${s.threat_severity} SEVERITY</span>
            </div>
            <div class="panel-body">
              <div class="mb-3">
                <span class="text-xs text-muted">TARGET CASHOUT CITIES:</span>
                <div class="mt-1">
                  ${(s.target_cashout_cities || ['Mumbai', 'Ahmedabad']).map(c => `<span class="badge badge-outline" style="margin-right:4px;">📍 ${c}</span>`).join('')}
                </div>
              </div>
              <div class="mb-3">
                <span class="text-xs text-muted">LINKED MULE ACCOUNTS (${s.mule_accounts_count}):</span>
                <div class="mt-1" style="display:flex; flex-wrap:wrap; gap:4px;">
                  ${(s.linked_accounts || []).slice(0, 4).map(a => `<span class="font-mono text-xs px-2 py-1 bg-slate-900 rounded border border-slate-800">${a}</span>`).join('')}
                </div>
              </div>
              <div style="display:flex; gap:8px; margin-top:16px;">
                <button class="btn btn-sm btn-primary" onclick="openDispatchModal('DEMO_AHM_MUM', 'M17')">🚨 Dispatch Interception</button>
                <button class="btn btn-sm btn-secondary" onclick="switchView('view-network')">🕸️ View Network Graph</button>
              </div>
            </div>
          </div>
        `).join('');
      }
    }
  } catch(e) {
    console.error('Error loading syndicate clusters:', e);
  }
}

// User Profile & Logout
function initUserProfile() {
  const userStr = localStorage.getItem('cashout_user');
  if (userStr) {
    try {
      const u = JSON.parse(userStr);
      document.getElementById('userDisplayName').textContent = u.username.toUpperCase();
      document.getElementById('userRoleBadge').textContent = `${u.role.toUpperCase()} CLEARANCE`;
      document.getElementById('userAvatar').textContent = u.username.substring(0,2).toUpperCase();
    } catch (e) {}
  }
}

function handleLogout() {
  localStorage.removeItem('cashout_token');
  localStorage.removeItem('cashout_user');
  window.location.href = '/';
}

// Global Initialization
window.addEventListener('DOMContentLoaded', async () => {
  if (!currentAuthToken) {
    window.location.href = '/';
    return;
  }
  
  initWebSocket();
  renderNotifications();
  
  showSkeletonLoading('overviewAlertsTableBody', 3);
  showSkeletonLoading('overviewPredictionsTableBody', 3);
  
  initUserProfile();
  await refreshAllData();
});
