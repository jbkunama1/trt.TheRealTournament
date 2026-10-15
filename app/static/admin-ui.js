/* Admin-UI v2: ueberschreibt Darstellungsfunktionen aus app.js (app.js bleibt unveraendert) */
(function () {
  let TSUB = 'plan';

  window.setTSub = function (s) {
    TSUB = s;
    document.querySelectorAll('.subtab').forEach(b => b.classList.toggle('active', b.dataset.sub === s));
    document.querySelectorAll('.subpane').forEach(p => p.classList.toggle('hidden', p.dataset.sub !== s));
  };

  window.renderTours = function () {
    $('tDetail').classList.add('hidden');
    $('tList').classList.remove('hidden');
    const sports = ['Fußball', 'Volleyball', 'Basketball', 'Handball', 'Badminton', 'Hockey', 'Tischtennis', 'Völkerball', 'Sonstiges'];
    let html = `<div class="page-head"><div><h2>🏆 Turniere</h2><p class="hint">${TOURS.length} Turnier(e)</p></div>
      ${canWrite() ? `<div class="actions"><button class="btn primary" onclick="openWizard()">🧙 Turnier-Assistent</button></div>` : ''}</div>`;
    if (canWrite()) html += `
      <details class="card form-card collapsible">
        <summary>➕ Turnier manuell anlegen</summary>
        <div class="grid3">
          <input id="nName" placeholder="Name, z. B. Bundesjugendturnier 2026 🥳">
          <select id="nSport">${sports.map(s => `<option>${s}</option>`).join('')}</select>
          <select id="nFormat">${Object.entries(FORMAT_LABEL).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select>
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
      </details>`;
    html += `<div class="cards">` + (TOURS.map(t => `
      <div class="card tcard" onclick="openTour(${t.id})">
        <span class="badge">${STATUS_LABEL[t.status] || t.status}</span>
        <h3>${sportEm(t.sport)} ${esc(t.name)}</h3>
        <p class="meta">${FORMAT_LABEL[t.format] || t.format}</p>
        <p class="meta">👥 ${t.team_count} Teams · 🎮 ${t.match_count} Spiele · 📅 ${esc(t.start_date || 'offen')}</p>
      </div>`).join('') || '<p class="hint">Noch keine Turniere – leg los! 💪</p>') + '</div>';
    $('tList').innerHTML = html;
  };

  window.renderTourDetail = function () {
    const t = CUR, d = $('tDetail'), w = canWrite();
    d.classList.remove('hidden');
    const inTour = new Set(t.teams.map(x => x.id));
    const total = (t.matches || []).length;
    const done = (t.matches || []).filter(m => m.status === 'erledigt').length;
    const tabs = [['plan', '🎮 Spielplan'], ['tabelle', '📊 Tabelle'], ['info', 'ℹ️ Übersicht & Export']]
      .concat(w ? [['teams', '👥 Teams & Zeiten'], ['live', '📣 Live-Ansicht']] : []);
    if (!tabs.some(x => x[0] === TSUB)) TSUB = 'plan';
    const pub = t.public_token;

    const info = `
      ${CUR.champion ? `<div class="banner">🎉🏆 Turniersieger: ${teamChip(CUR.champion)} 🏆🎉</div>` : ''}
      <div class="stats">
        <div class="stat"><b>${t.teams.length}</b><span>Teams</span></div>
        <div class="stat"><b>${total}</b><span>Spiele</span></div>
        <div class="stat"><b>${done}</b><span>gespielt</span></div>
        <div class="stat"><b>${Math.max(total - done, 0)}</b><span>offen</span></div>
      </div>
      <div class="card form-card"><h3>📤 Export</h3><div class="actions">
        <button class="btn" onclick="downloadFile('/api/tournaments/${t.id}/export.pdf', 'turnier.pdf')">📄 PDF-Export</button>
        <button class="btn" onclick="downloadFile('/api/tournaments/${t.id}/export.ics', 'turnier.ics')">📅 Kalender (.ics)</button>
        <button class="btn" onclick="downloadFile('/api/tournaments/${t.id}/urkunden.pdf', 'urkunden.pdf')">🏅 Urkunden (Top 3)</button>
      </div></div>
      ${w ? `<div class="card form-card"><h3>⚙️ Verwaltung</h3><div class="actions">
        <button class="btn ok" onclick="genPlan()">⚙️ Spielplan (neu) generieren</button>
        ${t.status !== 'entwurf' ? `<button class="btn ghost" onclick="setTourStatus('finalrunde')">🔥 Finalrunde</button>` : ''}
        ${t.status !== 'beendet' ? `<button class="btn ghost" onclick="setTourStatus('beendet')">🏁 Beenden</button>` : ''}
        <button class="btn danger" onclick="delTour(${t.id})">🗑️ Turnier löschen</button>
      </div></div>` : ''}`;

    const teamsPane = w ? `
      <div class="card form-card">
        <h3>👥 Teams zuweisen (${t.teams.length})</h3>
        <div>${TEAMS.map(tm => `<label class="teamchip" style="--tc:${esc(tm.color)};cursor:pointer">
          <input type="checkbox" ${inTour.has(tm.id) ? 'checked' : ''} onchange="toggleTT(${t.id}, ${tm.id}, this.checked)" style="width:auto"> ${esc(tm.emoji)} ${esc(tm.name)}</label>`).join('')}</div>
        ${t.format === 'ko' ? '<p class="hint">Reihenfolge = Setzliste (1 = bestgesetzt) 🔢</p>' : ''}
        <p class="hint">Danach unter „Übersicht & Export“ den Spielplan generieren.</p>
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
      </div>` : '';

    const livePane = w ? `
      <div class="card form-card">
        <h3>📣 Öffentliche Live-Ansicht</h3>
        ${pub ? `<p class="hint">Anzeige-Link ohne Login, aktualisiert automatisch:</p>
          <div class="actions">
            <a class="btn" target="_blank" href="/view/${esc(pub)}">📺 Anzeige öffnen</a>
            <a class="btn ghost" target="_blank" href="/p/${esc(pub)}">🔗 Link teilen</a>
            <a class="btn ghost" target="_blank" href="/api/public/${esc(pub)}/qr.svg">📱 QR-Code</a>
            <button class="btn danger small" onclick="togglePublic(false)">🔒 Deaktivieren</button>
          </div>`
        : `<p class="hint">Für Beamer/Anzeige ohne Login – mit großem TV-Layout und automatischer Aktualisierung.</p>
           <button class="btn primary" onclick="togglePublic(true)">📣 Öffentlichen Link erzeugen</button>`}
      </div>` : '';

    const panes = {
      plan: '<div id="matchList"></div>',
      tabelle: '<div id="standingBox"></div>',
      info, teams: teamsPane, live: livePane
    };

    d.innerHTML = `
      <div class="tour-head">
        <div>
          <button class="btn ghost small" onclick="renderTours()">⬅️ Alle Turniere</button>
          <h2>${sportEm(t.sport)} ${esc(t.name)}</h2>
          <div class="chips">
            <span class="chip accent">${STATUS_LABEL[t.status] || esc(t.status)}</span>
            <span class="chip">${FORMAT_LABEL[t.format] || esc(t.format)}</span>
            <span class="chip">📅 ${esc(t.start_date || '?')} – ${esc(t.end_date || '?')}</span>
            <span class="chip">🎯 ${t.points_win} / ${t.points_draw} Punkte</span>
          </div>
        </div>
      </div>
      <div class="subtabs">${tabs.map(([k, l]) => `<button class="subtab ${k === TSUB ? 'active' : ''}" data-sub="${k}" onclick="setTSub('${k}')">${l}</button>`).join('')}</div>
      ${tabs.map(([k]) => `<div class="subpane ${k === TSUB ? '' : 'hidden'}" data-sub="${k}">${panes[k]}</div>`).join('')}`;
    renderMatches();
    renderStandings();
  };

  function markSwatches() {
    const cur = document.documentElement.dataset.theme;
    document.querySelectorAll('.swatch').forEach(s => s.classList.toggle('active', s.dataset.val === cur));
  }
  window.pickTheme = function (v) {
    const sel = $('globalThemeSel');
    if (sel) sel.value = v;
    previewTheme(v);
  };
  function buildSwatches() {
    const sel = $('globalThemeSel'), box = $('themeSwatches');
    if (!sel || !box) return;
    box.innerHTML = [...sel.options].map(o =>
      `<button type="button" class="swatch" data-theme="${o.value}" data-val="${o.value}" onclick="pickTheme('${o.value}')">${o.textContent}</button>`).join('');
    markSwatches();
  }
  new MutationObserver(markSwatches).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
  buildSwatches();
})();
