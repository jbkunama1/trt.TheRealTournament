/* 🏆 TheRealTournament Frontend */
const $ = id => document.getElementById(id);
let TOKEN = localStorage.getItem('trt_token') || '';
let ME = null, TEAMS = [], TOURS = [], CUR = null;

const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const canWrite = () => ME && ['admin','lehrer'].includes(ME.role);

async function api(path, opts = {}) {
  opts.headers = Object.assign({'X-Token': TOKEN}, opts.headers || {});
  if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, opts);
  if (res.status === 401 && !path.endsWith('/login')) { showLogin(); throw new Error('401'); }
  if (!res.ok) {
    const d = await res.json().catch(() => ({detail: res.statusText}));
    alert('⚠️ ' + (typeof d.detail === 'string' ? d.detail : 'Fehler ' + res.status));
    throw new Error('api');
  }
  return res.json();
}

/* ---------- Login ---------- */
function showLogin() {
  $('loginView').classList.remove('hidden');
  $('appView').classList.add('hidden');
}
async function showApp() {
  try { ME = await api('/api/auth/me'); } catch (e) { showLogin(); return; }
  $('loginView').classList.add('hidden');
  $('appView').classList.remove('hidden');
  $('meBadge').textContent = `${ME.display_name || ME.username} ${ME.role === 'admin' ? '👑' : ME.role === 'lehrer' ? '🧑‍🏫' : '👀'}`;
  document.querySelectorAll('.admin-only').forEach(e => e.style.display = ME.role === 'admin' ? '' : 'none');
  $('themeSel').value = ME.theme || 'ksc';
  if (!canWrite()) $('teamForm').style.display = 'none';
  await loadAll();
}
async function doLogin() {
  try {
    const r = await api('/api/auth/login', {method: 'POST',
      body: {username: $('loginUser').value.trim(), password: $('loginPw').value}});
    TOKEN = r.token;
    localStorage.setItem('trt_token', TOKEN);
    $('loginErr').textContent = '';
    await showApp();
  } catch (e) { $('loginErr').textContent = '❌ Login fehlgeschlagen'; }
}
async function doLogout() {
  await api('/api/auth/logout', {method: 'POST'}).catch(() => {});
  TOKEN = ''; localStorage.removeItem('trt_token'); ME = null; showLogin();
}
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  if (ME) api('/api/auth/me/theme', {method: 'PUT', body: {theme: t}}).catch(() => {});
}

/* ---------- Tabs ---------- */
function showTab(t) {
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === t));
  document.querySelectorAll('.tabpane').forEach(p => p.classList.add('hidden'));
  $('tab-' + t).classList.remove('hidden');
  if (t === 'kalender') renderCalendar();
}
async function loadAll() {
  TEAMS = await api('/api/teams');
  TOURS = await api('/api/tournaments');
  renderTours(); renderTeams();
  if (ME.role === 'admin') renderUsers();
}

/* ---------- Teams ---------- */
function teamLogo(t) {
  return t.logo ? `<img src="/logos/${esc(t.logo)}" alt="">` : '';
}
function teamChip(t) {
  if (!t) return '<span class="teamchip">❔ TBD</span>';
  return `<span class="teamchip" style="--tc:${esc(t.color)}">${teamLogo(t)}${esc(t.emoji)} ${esc(t.name)}</span>`;
}
async function addTeam() {
  const name = $('tName').value.trim();
  if (!name) return alert('⚠️ Name fehlt');
  await api('/api/teams', {method: 'POST', body: {name, klasse: $('tKlasse').value.trim(),
    sport: $('tSport').value.trim(), emoji: $('tEmoji').value.trim() || '🏅', color: $('tColor').value}});
  ['tName','tKlasse','tSport','tEmoji'].forEach(i => $(i).value = '');
  TEAMS = await api('/api/teams'); renderTeams();
}
async function delTeam(id) {
  if (!confirm('Team wirklich löschen? 🗑️')) return;
  await api('/api/teams/' + id, {method: 'DELETE'});
  TEAMS = await api('/api/teams'); renderTeams();
}
async function uploadLogo(id, input) {
  if (!input.files.length) return;
  const fd = new FormData();
  fd.append('file', input.files[0]);
  await api(`/api/teams/${id}/logo`, {method: 'POST', body: fd});
  TEAMS = await api('/api/teams'); renderTeams();
}
function renderTeams() {
  $('teamList').innerHTML = TEAMS.map(t => `
    <div class="card">
      <h3>${esc(t.emoji)} ${esc(t.name)}</h3>
      <p class="meta" style="color:var(--muted)">🏫 ${esc(t.klasse || '-')} · ${esc(t.sport || '-')}
        <span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:${esc(t.color)};vertical-align:middle"></span></p>
      ${t.logo ? `<img src="/logos/${esc(t.logo)}" style="max-height:60px;border-radius:8px;margin:.5rem 0">` : ''}
      ${canWrite() ? `<div class="actions">
        <label class="btn ghost small">🖼️ Logo hochladen
          <input type="file" accept="image/*" style="display:none" onchange="uploadLogo(${t.id}, this)"></label>
        <button class="btn danger small" onclick="delTeam(${t.id})">🗑️</button>
      </div>` : ''}
    </div>`).join('') || '<p class="hint">Noch keine Teams angelegt 😅</p>';
}

/* ---------- Turniere ---------- */
const SPORT_EMOJI = {'Fußball':'⚽','Volleyball':'🏐','Basketball':'🏀','Handball':'🤾','Badminton':'🏸','Hockey':'🏑','Tischtennis':'🏓','Völkerball':'🏃'};
const sportEm = s => { for (const k in SPORT_EMOJI) if ((s||'').includes(k)) return SPORT_EMOJI[k]; return (s||'').match(/\p{Emoji}/u)?.[0] || '🎯'; };
const FORMAT_LABEL = {liga:'⚽ Jeder gegen Jeden', ko:'🏆 K.o.-System', gruppen:'🌍 Gruppen + K.o.'};
const STATUS_LABEL = {entwurf:'📝 Entwurf', laeuft:'▶️ Läuft', finalrunde:'🔥 Finalrunde', beendet:'🏁 Beendet'};

function renderTours() {
  $('tDetail').classList.add('hidden'); $('tList').classList.remove('hidden');
  let html = `<h2>🏆 Turniere</h2>`;
  if (canWrite()) html += `
    <div class="card form-card">
      <h3>➕ Neues Turnier</h3>
      <div class="grid3">
        <input id="nName" placeholder="Name, z. B. Bundesjugendturnier 2026 🥳">
        <select id="nSport">${['Fußball','Volleyball','Basketball','Handball','Badminton','Hockey','Tischtennis','Völkerball','Sonstiges'].map(s=>`<option>${s}</option>`).join('')}</select>
        <select id="nFormat">${Object.entries(FORMAT_LABEL).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>
      </div>
      <div class="grid4">
        <label class="hint">Von 📅<input id="nStart" type="date"></label>
        <label class="hint">Bis 📅<input id="nEnd" type="date"></label>
        <label class="hint">Punkte/Sieg 🎯<input id="nPW" type="number" value="3" min="1"></label>
        <label class="hint">Punkte/Unentsch. 🤝<input id="nPD" type="number" value="1" min="0"></label>
      </div>
      <label class="hint">Gruppen (nur bei Gruppenmodus) 🌍
        <input id="nGroups" type="number" value="2" min="2" max="8" style="max-width:90px"></label>
      <button class="btn primary" onclick="addTournament()">Turnier anlegen 🚀</button>
    </div>`;
  html += `<div class="cards">`;
  html += TOURS.map(t => `
    <div class="card tcard" onclick="openTour(${t.id})">
      <span class="badge">${STATUS_LABEL[t.status] || t.status}</span>
      <h3>${sportEm(t.sport)} ${esc(t.name)}</h3>
      <p class="meta">${FORMAT_LABEL[t.format] || t.format}</p>
      <p class="meta">👥 ${t.team_count} Teams · 🎮 ${t.match_count} Spiele · 📅 ${esc(t.start_date || 'offen')}</p>
    </div>`).join('') || '<p class="hint">Noch keine Turniere – leg los! 💪</p>';
  $('tList').innerHTML = html + '</div>';
}

async function addTournament() {
  const name = $('nName').value.trim();
  if (!name) return alert('⚠️ Name fehlt');
  await api('/api/tournaments', {method: 'POST', body: {name,
    sport: $('nSport').value, format: $('nFormat').value,
    start_date: $('nStart').value, end_date: $('nEnd').value,
    points_win: +$('nPW').value || 3, points_draw: +$('nPD').value || 1,
    num_groups: +$('nGroups').value || 2}});
  TOURS = await api('/api/tournaments'); renderTours();
}

async function openTour(id) {
  CUR = await api('/api/tournaments/' + id);
  CUR.matches = await api(`/api/tournaments/${id}/matches`);
  CUR.standings = await api(`/api/tournaments/${id}/standings`);
  CUR.champion = (await api(`/api/tournaments/${id}/champion`)).champion;
  $('tList').classList.add('hidden');
  renderTourDetail();
}

function renderTourDetail() {
  const t = CUR, d = $('tDetail');
  d.classList.remove('hidden');
  const inTour = new Set(t.teams.map(x => x.id));
  let html = `
    <div class="actions">
      <button class="btn ghost" onclick="renderTours()">⬅️ Zur Übersicht</button>
      ${canWrite() ? `<button class="btn danger small" onclick="delTour(${t.id})">🗑️ Turnier löschen</button>` : ''}
    </div>
    <h2>${sportEm(t.sport)} ${esc(t.name)}</h2>
    <p class="hint">${FORMAT_LABEL[t.format]} · 📅 ${esc(t.start_date || '?')} – ${esc(t.end_date || '?')}
      · Punkte: ${t.points_win} Sieg / ${t.points_draw} Unentschieden</p>`;
  if (CUR.champion) html += `<div class="banner">🎉🏆 Turniersieger: ${teamChip(CUR.champion)} 🏆🎉</div>`;

  html += `<div class="actions">
      <a class="btn" href="/api/tournaments/${t.id}/export.pdf">📄 PDF-Export</a>
      <a class="btn" href="/api/tournaments/${t.id}/export.ics">📅 Kalender (.ics)</a>
      ${canWrite() ? `<button class="btn ok" onclick="genPlan()">⚙️ Spielplan (neu) generieren</button>` : ''}
    </div>`;

  if (canWrite()) html += `
    <div class="card form-card">
      <h3>👥 Teams zuweisen (${t.teams.length})</h3>
      <div>${TEAMS.map(tm => `<label class="teamchip" style="--tc:${esc(tm.color)};cursor:pointer">
        <input type="checkbox" ${inTour.has(tm.id) ? 'checked' : ''}
          onchange="toggleTT(${t.id}, ${tm.id}, this.checked)" style="width:auto"> ${esc(tm.emoji)} ${esc(tm.name)}</label>`).join('')}</div>
      ${t.format === 'ko' ? '<p class="hint">Reihenfolge = Setzliste (1 = bestgesetzt) 🔢</p>' : ''}
    </div>
    <div class="card form-card">
      <h3>⏱️ Zeiten & Plätze zuweisen</h3>
      <div class="grid4">
        <label class="hint">Datum 📅<input id="sDate" type="date" value="${esc(t.start_date)}"></label>
        <label class="hint">Start ⏰<input id="sTime" type="time" value="09:00"></label>
        <label class="hint">Spieldauer (Min) ⏳<input id="sDur" type="number" value="10" min="1"></label>
        <label class="hint">Plätze 🏟️<input id="sCourts" value="Platz 1, Platz 2"></label>
      </div>
      <button class="btn primary" onclick="doSchedule()">Zeitplan setzen ✅</button>
    </div>`;

  html += `<div class="two-col"><div><h2>🎮 Spielplan</h2><div id="matchList"></div></div>
    <div><h2>📊 Tabelle</h2><div id="standingBox"></div></div></div>`;
  d.innerHTML = html;
  renderMatches(); renderStandings();
}

async function toggleTT(tid, teamId, on) {
  await api(`/api/tournaments/${tid}/teams/${teamId}`, {method: on ? 'POST' : 'DELETE'});
  CUR = await api('/api/tournaments/' + tid);
}
async function delTour(id) {
  if (!confirm('Turnier inkl. aller Spiele löschen? 🗑️')) return;
  await api('/api/tournaments/' + id, {method: 'DELETE'});
  TOURS = await api('/api/tournaments'); renderTours();
}
async function genPlan() {
  if (!confirm('Spielplan wird neu generiert – vorhandene Spiele/Ergebnisse gehen verloren ⚠️ Weiter?')) return;
  await api(`/api/tournaments/${CUR.id}/generate`, {method: 'POST'});
  await openTour(CUR.id);
}
async function doSchedule() {
  await api(`/api/tournaments/${CUR.id}/schedule`, {method: 'POST', body: {
    date: $('sDate').value, start_time: $('sTime').value,
    duration: +$('sDur').value || 10, courts: $('sCourts').value}});
  CUR.matches = await api(`/api/tournaments/${CUR.id}/matches`);
  renderMatches();
}

/* ---------- Spiele ---------- */
const teamById = id => TEAMS.find(t => t.id === id);

function matchRow(m) {
  const tBy = id => CUR.teams.find(x => x.id === id) || teamById(id);
  const when = [m.date, m.time, m.court].filter(Boolean).join(' · ');
  const isKO = !m.group_name;
  let scoreBlock;
  if (m.status === 'bye') {
    scoreBlock = '<span class="hint">Freilos 🎫</span>';
  } else if (canWrite()) {
    scoreBlock = `<span class="scores ${m.status === 'erledigt' ? 'done' : ''}">
      <input type="number" min="0" id="hs${m.id}" value="${m.home_score ?? ''}" placeholder="-">
      <span>:</span>
      <input type="number" min="0" id="as${m.id}" value="${m.away_score ?? ''}" placeholder="-">
      ${isKO ? `<span class="pen hint">n.E.: <input type="number" min="0" id="hp${m.id}" value="${m.home_pen ?? ''}" placeholder="-"> :
        <input type="number" min="0" id="ap${m.id}" value="${m.away_pen ?? ''}" placeholder="-"></span>` : ''}
      <button class="btn ok small" onclick="saveResult(${m.id})">💾</button></span>`;
  } else {
    scoreBlock = m.status === 'erledigt'
      ? `<b>${m.home_score}:${m.away_score}${m.home_pen != null ? ` (${m.home_pen}:${m.away_pen} n.E.)` : ''}</b>`
      : '<span class="hint">⏳ offen</span>';
  }
  return `<div class="match ${m.status === 'erledigt' ? 'done' : ''}">
    <div class="when">${esc(when || 'noch offen 📅')}</div>
    <div class="pair">${teamChip(tBy(m.home_id))} <span class="vs">vs</span> ${teamChip(tBy(m.away_id))}</div>
    ${scoreBlock}</div>`;
}

function renderMatches() {
  const ms = CUR.matches;
  if (!ms.length) { $('matchList').innerHTML = '<p class="hint">Noch kein Spielplan – erst Teams zuweisen, dann <b>Spielplan generieren</b> ⚙️</p>'; return; }
  const groups = {};
  ms.forEach(m => { const key = (m.group_name && m.group_name !== 'Liga' ? `Gruppe ${m.group_name}` : null);
    (groups[key || '_'] ??= []).push(m); });
  let html = '';
  for (const [g, list] of Object.entries(groups)) {
    if (g !== '_') html += `<h3 style="color:var(--accent2);margin-top:1rem">${g === 'Gruppe Liga' ? '⚽ Liga' : '🌍 ' + g}</h3>`;
    let lastRound = null;
    for (const m of list) {
      if (m.round_name !== lastRound) { html += `<div class="roundbox"><h3>${esc(m.round_name)}</h3>`; lastRound = m.round_name; }
      html += matchRow(m);
      const idx = list.indexOf(m);
      const nxt = list[idx + 1];
      if (!nxt || nxt.round_name !== m.round_name) html += '</div>';
    }
  }
  $('matchList').innerHTML = html;
}

async function saveResult(mid) {
  const gv = id => { const v = $(id)?.value; return v === '' ? null : +v; };
  await api('/api/matches/' + mid, {method: 'PATCH', body: {
    home_score: gv('hs' + mid), away_score: gv('as' + mid),
    home_pen: gv('hp' + mid), away_pen: gv('ap' + mid)}});
  await openTour(CUR.id);
}

function renderStandings() {
  const st = CUR.standings;
  const fmt = CUR.format;
  if (!st.length || fmt === 'ko') {
    $('standingBox').innerHTML = fmt === 'ko'
      ? '<p class="hint">Im K.o.-Modus entscheidet der Baum 🏆 – Tabelle entfällt.</p>'
      : '<p class="hint">Noch keine Tabelle 😴</p>';
    return;
  }
  const groups = [...new Set(st.map(s => s.group || '-'))].sort();
  let html = '';
  for (const g of groups) {
    const rows = st.filter(s => (s.group || '-') === g);
    html += `<h3 style="color:var(--accent2);margin-top:.8rem">${g === 'Liga' ? '⚽ Liga-Tabelle' : g === '-' ? '📊 Tabelle' : '🌍 Gruppe ' + g}</h3>
      <table><tr><th>#</th><th>Team</th><th>Sp</th><th>S</th><th>U</th><th>N</th><th>Tore</th><th>Pkt</th></tr>
      ${rows.map((s, i) => `<tr><td>${i + 1}</td><td>${esc(s.emoji)} ${esc(s.name)}${s.klasse ? ` <span class="hint">(${esc(s.klasse)})</span>` : ''}</td>
        <td>${s.sp}</td><td>${s.w}</td><td>${s.d}</td><td>${s.l}</td><td>${s.gs}:${s.gc}</td><td><b>${s.pts}</b></td></tr>`).join('')}
      </table>`;
  }
  $('standingBox').innerHTML = html;
}

/* ---------- Kalender ---------- */
async function renderCalendar() {
  const items = [];
  for (const t of TOURS) {
    const ms = await api(`/api/tournaments/${t.id}/matches`);
    ms.filter(m => m.date).forEach(m => items.push({t, m}));
  }
  items.sort((a, b) => (a.m.date + a.m.time).localeCompare(b.m.date + b.m.time));
  $('calList').innerHTML = items.length ? items.map(({t, m}) => `
    <div class="cal-item">
      <div class="date">📅 ${esc(m.date)}<br>⏰ ${esc(m.time || '')}</div>
      <div><b>${matchTitle(m)}</b><div class="meta">${sportEm(t.sport)} ${esc(t.name)} · ${esc(m.round_name)}${m.court ? ' · 🏟️ ' + esc(m.court) : ''}</div></div>
      <a class="btn small ghost" href="/api/tournaments/${t.id}/export.ics">.ics ⬇️</a>
    </div>`).join('') : '<p class="hint">Noch keine terminierten Spiele 📅</p>';
  function matchTitle(m) {
    const f = id => (TEAMS.find(x => x.id === id) || {}).name || 'TBD';
    return `${esc(f(m.home_id))} vs ${esc(f(m.away_id))}`;
  }
}

/* ---------- Benutzer ---------- */
async function renderUsers() {
  const users = await api('/api/users');
  $('userList').innerHTML = users.map(u => `
    <div class="card">
      <h3>${u.role === 'admin' ? '👑' : u.role === 'lehrer' ? '🧑‍🏫' : '👀'} ${esc(u.display_name || u.username)}</h3>
      <p class="hint">@${esc(u.username)} · Rolle: ${esc(u.role)}</p>
      <div class="actions">
        <button class="btn ghost small" onclick="resetPw(${u.id})">🔑 Neues Passwort</button>
        <button class="btn ghost small" onclick="swapRole(${u.id}, '${u.role}')">🔁 Rolle wechseln</button>
        <button class="btn danger small" onclick="delUser(${u.id})">🗑️</button>
      </div>
    </div>`).join('');
}
async function addUser() {
  if (!$('uName').value.trim() || !$('uPw').value) return alert('⚠️ Name & Passwort nötig');
  await api('/api/users', {method: 'POST', body: {username: $('uName').value.trim(),
    password: $('uPw').value, role: $('uRole').value, display_name: $('uDisp').value.trim()}});
  ['uName','uDisp','uPw'].forEach(i => $(i).value = '');
  renderUsers();
}
async function resetPw(id) {
  const pw = prompt('🔑 Neues Passwort:');
  if (!pw) return;
  await api('/api/users/' + id, {method: 'PUT', body: {password: pw}});
  alert('✅ Passwort geändert');
}
async function swapRole(id, cur) {
  const roles = ['leser', 'lehrer', 'admin'];
  const nxt = roles[(roles.indexOf(cur) + 1) % roles.length];
  if (!confirm(`Rolle zu „${nxt}“ ändern?`)) return;
  await api('/api/users/' + id, {method: 'PUT', body: {role: nxt}});
  renderUsers();
}
async function delUser(id) {
  if (!confirm('Benutzer löschen? 🗑️')) return;
  await api('/api/users/' + id, {method: 'DELETE'});
  renderUsers();
}

/* ---------- Init ---------- */
$('year').textContent = new Date().getFullYear();
$('loginPw').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
if (TOKEN) {
  document.documentElement.dataset.theme = 'ksc';
  api('/api/auth/me').then(u => {
    ME = u;
    document.documentElement.dataset.theme = ME.theme || 'ksc';
    showApp();
  }).catch(() => showLogin());
} else showLogin();
