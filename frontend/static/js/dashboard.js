/**
 * SecureEye Dashboard — frontend/static/js/dashboard.js
 * Handles tab navigation, API polling, table rendering, and camera controls.
 */

const API = '/api';
const POLL_INTERVAL_MS = 5000;

// ── State ───────────────────────────────────────────────────────────────────
let pollTimer  = null;
let activeTab  = 'overview';

// ── Boot ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initClock();
  initCameraControls();
  initSearch();
  initRebuild();
  startPolling();
  loadLogs();
  loadUnknownGallery();
  loadUsers();
});

// ── Clock ────────────────────────────────────────────────────────────────────
function initClock() {
  const el = document.getElementById('clockDisplay');
  function tick() {
    const now = new Date();
    el.textContent = now.toLocaleTimeString('en-GB', { hour12: false });
  }
  tick();
  setInterval(tick, 1000);
}

// ── Tab navigation ───────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.nav-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll('.nav-tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${tab}`).classList.add('active');
      activeTab = tab;

      if (tab === 'logs')    loadLogs();
      if (tab === 'unknown') loadUnknownGallery();
      if (tab === 'users')   loadUsers();
    });
  });
}

// ── Polling loop ─────────────────────────────────────────────────────────────
function startPolling() {
  fetchAll();
  pollTimer = setInterval(fetchAll, POLL_INTERVAL_MS);
}

async function fetchAll() {
  await Promise.allSettled([
    fetchStats(),
    fetchInsideList(),
    fetchTimeline(),
    fetchCameraStatus(),
  ]);
}

// ── Stats ────────────────────────────────────────────────────────────────────
async function fetchStats() {
  try {
    const data = await get('/stats');
    animateValue('totalEvents',  data.total_events);
    animateValue('insideNow',    data.currently_inside);
    animateValue('todayEvents',  data.today_events);
    animateValue('unknownFaces', data.unknown_faces);
    animateValue('knownPeople',  data.known_people);
  } catch (e) { /* silently skip on network error */ }
}

function animateValue(id, newVal) {
  const el = document.getElementById(id);
  if (!el) return;
  const displayed = el.textContent;
  if (displayed === String(newVal)) return;
  el.style.animation = 'none';
  el.offsetHeight; // force reflow
  el.style.animation = 'count-up .35s ease';
  el.textContent = (newVal !== undefined && newVal !== null) ? newVal : '—';
}

// ── Inside list ───────────────────────────────────────────────────────────────
async function fetchInsideList() {
  try {
    const rows = await get('/logs/inside');
    const container = document.getElementById('insideList');
    if (!rows || !rows.length) {
      container.innerHTML = '<div class="empty-state">No one detected yet</div>';
      return;
    }
    container.innerHTML = rows.map(r => `
      <div class="inside-item">
        <div class="inside-avatar">${avatarChar(r.name)}</div>
        <div>
          <div class="inside-name">${esc(r.name)}</div>
          <div class="inside-time">Since ${formatTime(r.entry_time)}</div>
        </div>
        <div class="inside-badge ${r.is_known ? 'known' : 'unknown'}">
          ${r.is_known ? 'KNOWN' : 'UNKNOWN'}
        </div>
      </div>
    `).join('');
  } catch(e) {}
}

// ── Timeline ──────────────────────────────────────────────────────────────────
async function fetchTimeline() {
  try {
    const rows = await get('/logs?limit=20');
    const container = document.getElementById('timeline');
    if (!rows || !rows.length) {
      container.innerHTML = '<div class="empty-state">Waiting for events…</div>';
      return;
    }
    container.innerHTML = rows.map(r => {
      const hasExit = r.exit_time && r.exit_time !== 'None' && r.exit_time !== null;
      const evType  = !r.is_known ? 'unknown' : hasExit ? 'exit' : 'entry';
      const label   = evType === 'entry' ? 'ENTRY' : evType === 'exit' ? 'EXIT' : 'UNKNOWN';
      const dur     = r.duration_sec ? `${Math.round(r.duration_sec)}s` : '—';
      return `
        <div class="timeline-item ${evType}">
          <span class="tl-time">${formatTime(r.entry_time)}</span>
          <span class="tl-name">${esc(r.name)}</span>
          <span class="tl-badge ${evType}">${label}</span>
          <span class="tl-duration">${dur}</span>
        </div>
      `;
    }).join('');
  } catch(e) {}
}

// ── Camera status ─────────────────────────────────────────────────────────────
async function fetchCameraStatus() {
  try {
    const data = await get('/camera/status');
    const dot   = document.getElementById('systemDot');
    const label = document.getElementById('systemLabel');
    const startBtn = document.getElementById('btnStart');
    const stopBtn  = document.getElementById('btnStop');

    if (data.status === 'running') {
      dot.className   = 'status-dot running';
      label.className = 'status-label running';
      label.textContent = 'ACTIVE';
      startBtn.disabled = true;
      stopBtn.disabled  = false;
    } else if (data.status === 'error') {
      dot.className   = 'status-dot error';
      label.className = 'status-label';
      label.textContent = 'ERROR';
      startBtn.disabled = false;
      stopBtn.disabled  = true;
    } else {
      dot.className   = 'status-dot';
      label.className = 'status-label';
      label.textContent = 'IDLE';
      startBtn.disabled = false;
      stopBtn.disabled  = true;
    }
  } catch(e) {}
}

// ── Camera controls ───────────────────────────────────────────────────────────
function initCameraControls() {
  const startBtn = document.getElementById('btnStart');
  const stopBtn  = document.getElementById('btnStop');

  startBtn.addEventListener('click', async () => {
    startBtn.textContent = '▶ Starting…';
    startBtn.disabled = true;
    try {
      const r = await post('/camera/start');
      toast(`Camera: ${r.status}`, 'success');
      await fetchCameraStatus();
    } catch(e) {
      toast('Failed to start camera', 'error');
      startBtn.disabled = false;
    }
    startBtn.textContent = '▶ START';
  });

  stopBtn.addEventListener('click', async () => {
    stopBtn.textContent = '■ Stopping…';
    stopBtn.disabled = true;
    try {
      const r = await post('/camera/stop');
      toast(`Camera: ${r.status}`, 'success');
      await fetchCameraStatus();
    } catch(e) {
      toast('Failed to stop camera', 'error');
    }
    stopBtn.textContent = '■ STOP';
  });

  // Initial state: stop disabled
  stopBtn.disabled = true;
}

// ── Logs table ────────────────────────────────────────────────────────────────
async function loadLogs(params = {}) {
  const qs = new URLSearchParams({ limit: 100, ...params }).toString();
  try {
    const rows = await get(`/logs?${qs}`);
    renderLogsTable(rows);
    // Update count
    const countEl = document.getElementById('logCount');
    if (countEl) countEl.textContent = rows.length ? `${rows.length} records` : '';
  } catch(e) { toast('Failed to load logs', 'error'); }
}

function renderLogsTable(rows) {
  const tbody = document.getElementById('logsTableBody');
  if (!rows || !rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No results found.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const statusBadge = r.status === 'INSIDE'
      ? `<span class="badge-inside">INSIDE</span>`
      : `<span class="badge-outside">OUTSIDE</span>`;
    const typeBadge = r.is_known
      ? `<span class="badge-known">KNOWN</span>`
      : `<span class="badge-unknown">UNKNOWN</span>`;
    const dur = r.duration_sec ? `${Math.round(r.duration_sec)}s` : '—';
    const exitTime = (r.exit_time && r.exit_time !== 'None') ? formatDateTime(r.exit_time) : '—';
    return `<tr>
      <td>${esc(r.name)}</td>
      <td>${statusBadge}</td>
      <td class="mono">${formatDateTime(r.entry_time)}</td>
      <td class="mono">${exitTime}</td>
      <td class="mono">${dur}</td>
      <td>${typeBadge}</td>
    </tr>`;
  }).join('');
}

function initSearch() {
  document.getElementById('btnSearch').addEventListener('click', () => {
    const params = {};
    const name   = document.getElementById('searchName').value.trim();
    const date   = document.getElementById('searchDate').value;
    const status = document.getElementById('searchStatus').value;
    if (name)   params.name   = name;
    if (date)   params.date   = date;
    if (status) params.status = status;
    loadLogs(params);
  });

  document.getElementById('btnClear').addEventListener('click', () => {
    document.getElementById('searchName').value   = '';
    document.getElementById('searchDate').value   = '';
    document.getElementById('searchStatus').value = '';
    loadLogs();
  });

  ['searchName', 'searchDate'].forEach(id => {
    document.getElementById(id).addEventListener('keydown', e => {
      if (e.key === 'Enter') document.getElementById('btnSearch').click();
    });
  });
}

// ── Unknown gallery ───────────────────────────────────────────────────────────
async function loadUnknownGallery() {
  try {
    const rows = await get('/logs/unknown?limit=30');
    const container = document.getElementById('unknownGallery');
    if (!rows || !rows.length) {
      container.innerHTML = '<div class="empty-state">No unknown faces captured yet.</div>';
      return;
    }
    container.innerHTML = rows.map(r => {
      // Build correct image src from image_path
      let imgSrc = '/static/img/unknown_placeholder.svg';
      if (r.image_path) {
        const filename = r.image_path.split(/[/\\]/).pop();
        imgSrc = `/unknown_faces/${encodeURIComponent(filename)}`;
      }
      const suggestionHtml = r.suggested_id
        ? `<div class="suggestion-result">${esc(r.suggested_id)}</div>`
        : '';
      return `
        <div class="unknown-card">
          <img src="${imgSrc}" alt="${esc(r.name)}"
               onerror="this.src='/static/img/unknown_placeholder.svg'" />
          <div class="unknown-info">
            <div class="unknown-id">${esc(r.name)}</div>
            <div class="unknown-ts">${formatDateTime(r.entry_time)}</div>
            ${suggestionHtml}
            <button class="unknown-suggest-btn"
                    data-session="${esc(r.session_id || '')}"
                    data-image="${esc(r.image_path || '')}">
              ✦ Suggest Identity
            </button>
          </div>
        </div>
      `;
    }).join('');

    // Attach suggest button listeners (event delegation)
    container.querySelectorAll('.unknown-suggest-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        suggestIdentity(btn.dataset.session, btn.dataset.image, btn);
      });
    });
  } catch(e) { toast('Failed to load unknown faces', 'error'); }
}

async function suggestIdentity(sessionId, imagePath, btn) {
  btn.textContent = '…';
  btn.disabled = true;
  try {
    const r = await post('/suggest_identity', { session_id: sessionId, image_path: imagePath });
    const info = btn.closest('.unknown-info');
    // Remove old suggestion if any
    const existing = info.querySelector('.suggestion-result');
    if (existing) existing.remove();
    const div = document.createElement('div');
    div.className = 'suggestion-result';
    div.textContent = r.suggested_identity;
    btn.before(div);
    btn.textContent = '✓ Done';
  } catch(e) {
    btn.textContent = '✦ Suggest Identity';
    btn.disabled = false;
    toast('Identity lookup failed', 'error');
  }
}

// ── Users table ───────────────────────────────────────────────────────────────
async function loadUsers() {
  try {
    const rows = await get('/users');
    const tbody = document.getElementById('usersTableBody');
    if (!rows || !rows.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No registered users yet.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map((r, i) => `
      <tr>
        <td class="mono">${i + 1}</td>
        <td>
          <span class="user-avatar">${avatarChar(r.name)}</span>
          ${esc(r.name)}
        </td>
        <td class="mono" style="color:var(--text-muted); font-size:.75rem">${esc(r.encoding_path || '—')}</td>
        <td class="mono">${formatDateTime(r.created_at)}</td>
      </tr>
    `).join('');
  } catch(e) { toast('Failed to load users', 'error'); }
}

function initRebuild() {
  document.getElementById('btnRebuild').addEventListener('click', async () => {
    const btn = document.getElementById('btnRebuild');
    btn.textContent = '⟳ Rebuilding…';
    btn.disabled = true;
    try {
      const r = await post('/encodings/rebuild');
      toast(`Encodings rebuilt — ${r.identities} identit${r.identities === 1 ? 'y' : 'ies'} loaded`, 'success');
      loadUsers();
    } catch(e) { toast('Rebuild failed', 'error'); }
    btn.textContent = '⟳ Rebuild Encodings';
    btn.disabled = false;
  });
}

// ── HTTP helpers ──────────────────────────────────────────────────────────────
async function get(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`GET ${path}: ${r.status}`);
  return r.json();
}

async function post(path, body = {}) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${path}: ${r.status}`);
  return r.json();
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 400); }, 3600);
}

// ── Formatting helpers ────────────────────────────────────────────────────────
function formatTime(dt) {
  if (!dt || dt === 'None') return '—';
  try { return new Date(dt).toLocaleTimeString('en-GB', { hour12: false }); }
  catch { return dt; }
}

function formatDateTime(dt) {
  if (!dt || dt === 'None') return '—';
  try {
    const d = new Date(dt);
    if (isNaN(d)) return dt;
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' })
      + ' ' + d.toLocaleTimeString('en-GB', { hour12: false });
  } catch { return dt; }
}

function avatarChar(name) {
  return (name || '?').charAt(0).toUpperCase();
}

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
