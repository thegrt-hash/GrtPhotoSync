/* ─────────────────────────────────────────────────────────────────────────
   Google Photo Downloader – Single-Page App
   ─────────────────────────────────────────────────────────────────────────*/

const API = {
  async request(method, path, body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' }, credentials: 'include' };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    if (res.status === 401) { showLogin(); return null; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    return res.json().catch(() => null);
  },
  get:    (p)    => API.request('GET',    p),
  post:   (p, b) => API.request('POST',   p, b),
  put:    (p, b) => API.request('PUT',    p, b),
  delete: (p)    => API.request('DELETE', p),
};

// ── State ─────────────────────────────────────────────────────────────────

let state = {
  tab: 'dashboard',
  browserSide: 'local',
  localPage: 1,
  localYear: '',
  localMonth: '',
  localAlbum: '',
  sourcePageToken: null,
  syncPolling: null,
  statusPolling: null,
};

// ── Init ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  const status = await API.get('/api/auth/status');
  if (status) {
    showApp();
  } else {
    showLogin();
  }
});

// ── Auth ──────────────────────────────────────────────────────────────────

function showLogin() {
  document.getElementById('login-screen').classList.remove('hidden');
  document.getElementById('app').classList.add('hidden');
  stopPolling();
}

function showApp() {
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  initApp();
}

document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  const timeout  = parseInt(document.getElementById('timeout').value);
  const errEl    = document.getElementById('login-error');
  errEl.classList.add('hidden');

  try {
    await API.post('/api/auth/login', { username, password, timeout_minutes: timeout });
    showApp();
  } catch (err) {
    errEl.textContent = err.message || 'Login failed';
    errEl.classList.remove('hidden');
  }
});

document.getElementById('logout-btn').addEventListener('click', async () => {
  await API.post('/api/auth/logout');
  showLogin();
});

// ── Navigation ────────────────────────────────────────────────────────────

document.querySelectorAll('.nav-item').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    switchTab(link.dataset.tab);
  });
});

function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll('.nav-item').forEach(l => l.classList.toggle('active', l.dataset.tab === tab));
  document.querySelectorAll('.tab-content').forEach(s => s.classList.add('hidden'));
  document.getElementById(`tab-${tab}`).classList.remove('hidden');
  if (tab === 'browser') loadBrowser();
  if (tab === 'sync')    loadSyncLog();
  if (tab === 'settings') loadSettings();
}

// ── App Init ──────────────────────────────────────────────────────────────

function initApp() {
  switchTab('dashboard');
  startPolling();
  bindSyncControls();
  bindBrowserControls();
  bindSettingsForm();
}

// ── Status Polling ────────────────────────────────────────────────────────

function startPolling() {
  loadStatus();
  state.statusPolling = setInterval(loadStatus, 5000);
}
function stopPolling() {
  clearInterval(state.statusPolling);
  clearInterval(state.syncPolling);
}

async function loadStatus() {
  const data = await API.get('/api/status');
  if (!data) return;

  // Google banner
  const banner = document.getElementById('google-banner');
  banner.classList.toggle('hidden', data.google_connected);

  // Stats
  const mc = data.media_counts || {};
  setText('stat-total',     mc.total     ?? '—');
  setText('stat-completed', mc.completed ?? '—');
  setText('stat-pending',   mc.pending   ?? '—');
  setText('stat-failed',    mc.failed    ?? '—');

  // Disk
  if (data.disk_total_bytes) {
    const used = data.disk_total_bytes - data.disk_free_bytes;
    const pct  = Math.round((used / data.disk_total_bytes) * 100);
    document.getElementById('disk-bar').style.width = pct + '%';
    setText('disk-used', `${fmtBytes(used)} used of ${fmtBytes(data.disk_total_bytes)} (${pct}%)`);
    setText('disk-path', data.destination_path);
  }

  // Sync progress
  updateSyncProgressUI(data.sync || {});
}

function updateSyncProgressUI(sync) {
  const state_ = sync.state || 'idle';
  const badge  = document.getElementById('sync-state-badge');
  badge.className = `badge badge-${state_}`;
  badge.textContent = state_.charAt(0).toUpperCase() + state_.slice(1);

  const discovered = sync.discovered || 0;
  const downloaded = sync.downloaded || 0;
  const pct        = discovered > 0 ? Math.min(100, Math.round((downloaded / discovered) * 100)) : 0;
  document.getElementById('sync-progress-bar').style.width = pct + '%';
  setText('sync-current-file', sync.current_file || '—');
  setText('pg-downloaded', sync.downloaded ?? 0);
  setText('pg-skipped',    sync.skipped    ?? 0);
  setText('pg-failed',     sync.failed     ?? 0);
  setText('pg-bytes',      fmtBytes(sync.bytes_transferred ?? 0));

  // Buttons
  const running  = state_ === 'running';
  const paused   = state_ === 'paused';
  const idle     = state_ === 'idle';
  toggleEl('sync-start-btn',  idle || state_ === 'cancelled' || state_ === 'completed');
  toggleEl('sync-pause-btn',  running);
  toggleEl('sync-cancel-btn', running || paused);
}

// ── Sync Controls ─────────────────────────────────────────────────────────

function bindSyncControls() {
  btnClick('sync-start-btn',  () => API.post('/api/sync/start'));
  btnClick('sync-pause-btn',  () => API.post('/api/sync/pause'));
  btnClick('sync-cancel-btn', () => API.post('/api/sync/cancel'));

  document.getElementById('sync-pause-btn').textContent = 'Pause';
  // Toggle pause/resume label handled in updateSyncProgressUI via state

  btnClick('retry-failed-btn', async () => {
    const r = await API.post('/api/sync/retry-failed');
    if (r) showToast(`Reset ${r.reset} failed items to pending`);
  });
}

// ── Google OAuth ──────────────────────────────────────────────────────────

document.getElementById('connect-google-link')?.addEventListener('click', async (e) => {
  e.preventDefault();
  startGoogleAuth();
});

async function startGoogleAuth() {
  const data = await API.get('/api/google/auth-url');
  if (data?.auth_url) window.location.href = data.auth_url;
}

// Handle callback redirect params
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('connected') === '1') {
  window.history.replaceState({}, '', '/');
  document.addEventListener('DOMContentLoaded', () => showToast('Google Photos connected!', 'success'));
}
if (urlParams.get('error') === 'google_auth_failed') {
  window.history.replaceState({}, '', '/');
  document.addEventListener('DOMContentLoaded', () => showToast('Google auth failed. Check your credentials.', 'error'));
}

// ── Browser ───────────────────────────────────────────────────────────────

function bindBrowserControls() {
  document.querySelectorAll('.browser-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.browser-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.browserSide = btn.dataset.side;
      loadBrowser();
    });
  });

  document.getElementById('filter-year').addEventListener('change', e => { state.localYear = e.target.value; state.localPage = 1; loadBrowser(); });
  document.getElementById('filter-month').addEventListener('change', e => { state.localMonth = e.target.value; state.localPage = 1; loadBrowser(); });
  document.getElementById('filter-album').addEventListener('change', e => { state.localAlbum = e.target.value; state.localPage = 1; loadBrowser(); });

  document.getElementById('lightbox-close').addEventListener('click', () => {
    document.getElementById('lightbox').classList.add('hidden');
  });
  document.getElementById('lightbox').addEventListener('click', e => {
    if (e.target === document.getElementById('lightbox')) {
      document.getElementById('lightbox').classList.add('hidden');
    }
  });
}

async function loadBrowser() {
  if (state.tab !== 'browser') return;
  populateYearFilter();
  populateAlbumFilter();

  const side = state.browserSide;
  const filters = document.getElementById('local-filters');
  filters.classList.toggle('hidden', side !== 'local');

  const grid = document.getElementById('photo-grid');
  grid.innerHTML = '<div style="color:var(--text-muted);padding:20px">Loading…</div>';

  if (side === 'local') {
    await loadLocalBrowser();
  } else if (side === 'source') {
    await loadSourceBrowser();
  } else if (side === 'compare') {
    grid.innerHTML = '<div style="padding:20px;color:var(--text-muted)">Click a photo from Local or Google Photos view, then use Compare.</div>';
  }
}

async function loadLocalBrowser() {
  const params = new URLSearchParams({ page: state.localPage, page_size: 50 });
  if (state.localYear)  params.append('year', state.localYear);
  if (state.localMonth) params.append('month', state.localMonth);
  if (state.localAlbum) params.append('album_id', state.localAlbum);

  const data = await API.get(`/api/browse/local?${params}`);
  if (!data) return;

  renderPhotoGrid(data.items, item => ({
    thumb: item.thumbnail_url,
    name: item.filename,
    date: item.creation_time ? new Date(item.creation_time).toLocaleDateString() : '—',
    onClick: () => openLocalLightbox(item),
  }));

  renderPagination(data.total, data.page, data.page_size, page => { state.localPage = page; loadBrowser(); });
}

async function loadSourceBrowser() {
  const params = state.sourcePageToken ? `?page_token=${encodeURIComponent(state.sourcePageToken)}` : '';
  const data = await API.get(`/api/browse/source${params}`);
  if (!data) return;

  renderPhotoGrid(data.items, item => ({
    thumb: item.thumbnail_url,
    name: item.filename,
    date: item.creation_time ? new Date(item.creation_time).toLocaleDateString() : '—',
    onClick: () => openSourceLightbox(item),
  }));

  // Simple next/prev for source
  const pag = document.getElementById('pagination');
  pag.innerHTML = data.next_page_token
    ? `<button class="page-btn" onclick="state.sourcePageToken='${data.next_page_token}';loadBrowser()">Next →</button>`
    : '';
}

function renderPhotoGrid(items, mapper) {
  const grid = document.getElementById('photo-grid');
  if (!items.length) { grid.innerHTML = '<div style="color:var(--text-muted);padding:20px">No photos found.</div>'; return; }

  grid.innerHTML = items.map(item => {
    const { thumb, name, date } = mapper(item);
    return `<div class="photo-card" data-id="${item.id || item.google_id}">
      <img src="${thumb || '/static/img/placeholder.svg'}" loading="lazy" alt="${name}" onerror="this.src='/static/img/placeholder.svg'" />
      <div class="photo-card-info">
        <div class="photo-card-name">${name}</div>
        <div class="photo-card-date">${date}</div>
      </div>
    </div>`;
  }).join('');

  grid.querySelectorAll('.photo-card').forEach((card, i) => {
    card.addEventListener('click', () => mapper(items[i]).onClick());
  });
}

function renderPagination(total, page, pageSize, onPage) {
  const pag   = document.getElementById('pagination');
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) { pag.innerHTML = ''; return; }

  const start = Math.max(1, page - 2);
  const end   = Math.min(pages, page + 2);
  let html    = page > 1 ? `<button class="page-btn" data-p="${page-1}">← Prev</button>` : '';
  for (let p = start; p <= end; p++) {
    html += `<button class="page-btn${p===page?' active':''}" data-p="${p}">${p}</button>`;
  }
  html += page < pages ? `<button class="page-btn" data-p="${page+1}">Next →</button>` : '';
  pag.innerHTML = html;
  pag.querySelectorAll('[data-p]').forEach(btn => btn.addEventListener('click', () => onPage(+btn.dataset.p)));
}

function openLocalLightbox(item) {
  document.getElementById('lightbox-img').src = `/api/browse/file/${item.id}`;
  const meta = document.getElementById('lightbox-meta');
  meta.innerHTML = `<h4>${item.filename}</h4>
    ${metaRow('Date', item.creation_time ? new Date(item.creation_time).toLocaleString() : '—')}
    ${metaRow('Size', fmtBytes(item.file_size))}
    ${metaRow('Camera', [item.camera_make, item.camera_model].filter(Boolean).join(' ') || '—')}
    ${item.latitude ? metaRow('Location', `${item.latitude.toFixed(5)}, ${item.longitude.toFixed(5)}`) : ''}
    <div style="margin-top:12px">
      <a href="/api/browse/compare/${item.google_id}" target="_blank" class="btn btn-secondary btn-sm">Compare with Source</a>
    </div>`;
  document.getElementById('lightbox').classList.remove('hidden');
}

function openSourceLightbox(item) {
  document.getElementById('lightbox-img').src = item.thumbnail_url?.replace('=w256-h256-c', '=w1024-h1024-c') || '';
  const meta = document.getElementById('lightbox-meta');
  meta.innerHTML = `<h4>${item.filename}</h4>
    ${metaRow('Date', item.creation_time ? new Date(item.creation_time).toLocaleString() : '—')}
    ${metaRow('Type', item.is_video ? 'Video' : 'Photo')}
    ${metaRow('Source', 'Google Photos')}`;
  document.getElementById('lightbox').classList.remove('hidden');
}

function metaRow(label, value) {
  return `<div class="meta-row"><span class="meta-label">${label}</span><span>${value}</span></div>`;
}

async function populateYearFilter() {
  if (document.getElementById('filter-year').options.length > 1) return; // already loaded
  const data = await API.get('/api/browse/years');
  if (!data) return;
  const sel = document.getElementById('filter-year');
  data.forEach(({ year }) => sel.add(new Option(year, year)));
}

async function populateAlbumFilter() {
  if (document.getElementById('filter-album').options.length > 1) return;
  const data = await API.get('/api/browse/albums');
  if (!data) return;
  const sel = document.getElementById('filter-album');
  data.forEach(a => sel.add(new Option(a.title, a.id)));
}

// ── Sync Log ──────────────────────────────────────────────────────────────

async function loadSyncLog() {
  const [history, errors] = await Promise.all([
    API.get('/api/sync/history'),
    API.get('/api/sync/errors'),
  ]);

  if (history) {
    document.getElementById('sync-history-body').innerHTML = history.map(r => `
      <tr>
        <td>${r.started_at ? new Date(r.started_at).toLocaleString() : '—'}</td>
        <td>${r.started_at && r.ended_at ? fmtDuration(new Date(r.started_at), new Date(r.ended_at)) : '—'}</td>
        <td><span class="badge badge-${r.status}">${r.status}</span></td>
        <td>${r.items_downloaded}</td>
        <td>${r.items_skipped}</td>
        <td>${r.items_failed}</td>
        <td>${fmtBytes(r.bytes_transferred)}</td>
      </tr>`).join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">No sync sessions yet</td></tr>';
  }

  if (errors) {
    document.getElementById('errors-body').innerHTML = errors.map(e => `
      <tr>
        <td>${e.filename}</td>
        <td>${e.error_count}</td>
        <td style="max-width:300px;word-break:break-word">${e.error_message || '—'}</td>
        <td>${e.updated_at ? new Date(e.updated_at).toLocaleString() : '—'}</td>
      </tr>`).join('') || '<tr><td colspan="4" style="text-align:center;color:var(--text-muted)">No errors — great!</td></tr>';
  }
}

// ── Settings ──────────────────────────────────────────────────────────────

async function loadSettings() {
  const [s, g] = await Promise.all([
    API.get('/api/settings'),
    API.get('/api/google/status'),
  ]);

  if (s) {
    document.getElementById('speed-limit').value   = s.speed_limit_mbps;
    document.getElementById('sync-interval').value = s.sync_interval_minutes;
    document.getElementById('dest-path').value     = s.destination_path;
    document.getElementById('session-timeout').value = s.session_timeout_minutes;
  }

  if (g) updateGoogleStatus(g.connected);
}

function updateGoogleStatus(connected) {
  const detail = document.getElementById('google-status-detail');
  detail.innerHTML = connected
    ? `<div class="dot dot-green"></div><span>Connected to Google Photos</span>`
    : `<div class="dot dot-red"></div><span>Not connected</span>`;
  toggleEl('connect-google-btn',    !connected);
  toggleEl('disconnect-google-btn',  connected);
}

function bindSettingsForm() {
  btnClick('connect-google-btn',    startGoogleAuth);
  btnClick('disconnect-google-btn', async () => {
    await API.delete('/api/google/disconnect');
    updateGoogleStatus(false);
  });

  document.getElementById('sync-settings-form').addEventListener('submit', async e => {
    e.preventDefault();
    const body = {
      speed_limit_mbps:       parseFloat(document.getElementById('speed-limit').value) || 0,
      sync_interval_minutes:  parseInt(document.getElementById('sync-interval').value) || 60,
      session_timeout_minutes: parseInt(document.getElementById('session-timeout').value) || 60,
    };
    try {
      await API.put('/api/settings', body);
      const saved = document.getElementById('settings-saved');
      saved.classList.remove('hidden');
      setTimeout(() => saved.classList.add('hidden'), 2500);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function toggleEl(id, show) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('hidden', !show);
}

function btnClick(id, fn) {
  document.getElementById(id)?.addEventListener('click', fn);
}

function fmtBytes(bytes) {
  if (!bytes) return '0 B';
  const k = 1024, units = ['B','KB','MB','GB','TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${units[i]}`;
}

function fmtDuration(start, end) {
  const s = Math.round((end - start) / 1000);
  if (s < 60)  return `${s}s`;
  if (s < 3600) return `${Math.floor(s/60)}m ${s%60}s`;
  return `${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m`;
}

let _toastTimeout;
function showToast(msg, type = 'info') {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.style.cssText = 'position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:8px;font-size:14px;z-index:9999;transition:opacity 0.3s';
    document.body.appendChild(toast);
  }
  const colors = { info: '#5c6ef8', success: '#22c55e', error: '#ef4444' };
  toast.style.background = colors[type] || colors.info;
  toast.style.color = '#fff';
  toast.textContent = msg;
  toast.style.opacity = 1;
  clearTimeout(_toastTimeout);
  _toastTimeout = setTimeout(() => { toast.style.opacity = 0; }, 4000);
}
