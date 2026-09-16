/**
 * CashOut Forecast — Primary Application Controller
 * Handles Auth, View Switching, API Integrations, Adjudication, and Demo Mode
 */

const API_BASE = '';
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
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${currentAuthToken}`,
    ...(options.headers || {})
  };
  try {
    const response = await fetch(url, { ...options, headers });
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
}

// Global Refresh
async function refreshAllData() {
  await Promise.all([
    loadOverviewStats(),
    loadAlerts(),
    loadPredictions(),
    loadFeedbackHistory(),
    loadAuditLedger()
  ]);
  showToast('Intelligence feeds refreshed successfully', 'success');
}

// 1. Overview Statistics
async function loadOverviewStats() {
  const resp = await authFetch('/overview');
  if (!resp || !resp.ok) return;
  const stats = await resp.json();

  document.getElementById('kpiActiveAlerts').textContent = stats.active_alerts ?? 0;
  document.getElementById('kpiComplaints').textContent = stats.complaints_processed ?? 0;
  document.getElementById('kpiSuspiciousAccounts').textContent = stats.suspicious_accounts ?? 0;
  document.getElementById('kpiPredictions').textContent = stats.predictions_generated ?? 0;
  document.getElementById('badgeAlertsCount').textContent = stats.active_alerts ?? 0;
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
  area.innerHTML = '<div class="text-center py-12 text-muted">Retrieving cryptographic case file & SHAP evidence...</div>';

  const resp = await authFetch(`/predictions/${predId}`);
  if (!resp || !resp.ok) {
    area.innerHTML = '<div class="text-center py-12 text-rose">Failed to load case details.</div>';
    return;
  }
  const caseData = await resp.json();
  renderCaseWorkbench(caseData);
}

function renderCaseWorkbench(c) {
  const area = document.getElementById('workbenchContentArea');
  const topCandidate = c.candidates && c.candidates.length > 0 ? c.candidates[0] : null;
  const evidenceList = topCandidate ? topCandidate.evidence : [];
  const txnPath = topCandidate ? topCandidate.transaction_path : [];

  area.innerHTML = `
    <!-- Top Case Banner -->
    <div class="case-header-banner">
      <div class="banner-main">
        <div class="case-tag font-mono">CASE SCENARIO: ${c.scenario_id}</div>
        <h2 class="case-title">Predicted Cash-Out Target: <span class="text-cyan">${topCandidate ? topCandidate.location_id : 'Unknown'}</span></h2>
        <div class="case-meta-row font-mono text-xs text-muted">
          <span>PREDICTION ID: ${c.prediction_id}</span> • 
          <span>MODEL: ${c.model_version}</span> • 
          <span>TIMESTAMP: ${c.created_at}</span>
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

      <!-- Col 2: SHAP & Natural Language Evidence -->
      <div class="dashboard-panel">
        <div class="panel-header">
          <h4 class="panel-title">Explainable Evidence Signals (Rank #1)</h4>
          <span class="badge badge-cyan">SHAP / EVIDENCE</span>
        </div>
        <div class="panel-body">
          <div class="evidence-bullets-list">
            ${evidenceList.length > 0 ? evidenceList.map(e => `
              <div class="evidence-bullet">
                <span class="bullet-icon">🔍</span>
                <span class="bullet-text">${e}</span>
              </div>
            `).join('') : '<p class="text-muted text-sm">No structured evidence signals available.</p>'}
          </div>

          <div class="mt-4 p-3 bg-slate-900 rounded border border-slate-800">
            <h5 class="text-xs font-semibold text-muted mb-2 font-mono">INTERCEPTION TIME WINDOW</h5>
            <div class="text-sm font-mono text-cyan">
              ${topCandidate && topCandidate.expected_window_start ? `${topCandidate.expected_window_start}  ➔  ${topCandidate.expected_window_end}` : 'Immediate / Next 2 Hours'}
            </div>
          </div>
        </div>
      </div>

      <!-- Col 3: Money Flow Chain & Adjudication Action -->
      <div class="dashboard-panel">
        <div class="panel-header">
          <h4 class="panel-title">Transaction Trail & Action</h4>
        </div>
        <div class="panel-body">
          <h5 class="text-xs font-semibold text-muted mb-2 font-mono">DETECTED FLOW HOPS</h5>
          <div class="hops-chain">
            ${txnPath.length > 0 ? txnPath.map((hop, i) => `
              <div class="hop-step">
                <div class="hop-dot"></div>
                <div class="hop-content">
                  <div class="hop-node font-mono">${hop.node_id}</div>
                  <div class="hop-detail text-xs text-muted">${hop.city ? hop.city + ' • ' : ''}${hop.account_type || hop.role || 'Node'}</div>
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

// 8. One-Click Interactive Demo Launcher
async function triggerDemoScenario() {
  const btn = document.getElementById('btnRunDemo');
  btn.disabled = true;
  btn.innerHTML = '<span class="demo-icon">⏳</span><span>Injecting Ahmedabad ➔ Mumbai Cybercrime Scenario...</span>';
  showToast('Generating multi-hop fraud network: Ahmedabad victim complaints ➔ Mumbai mule extraction...', 'info');

  try {
    const resp = await authFetch('/demo/run', { method: 'POST' });
    if (!resp || !resp.ok) {
      throw new Error('Demo failed to run.');
    }
    const data = await resp.json();
    showToast('Cross-city fraud network synthesized. Cash-out predicted at Mumbai!', 'success');
    
    // Refresh intelligence feeds
    await refreshAllData();
    
    // Automatically open the new case in Workbench
    if (data.prediction_id) {
      openCaseFromPrediction(data.prediction_id);
    }
  } catch (err) {
    showToast(err.message || 'Demo run error', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="demo-icon">⚡</span><span>Ahmedabad → Mumbai Demo</span>';
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
  initUserProfile();
  await refreshAllData();
});
