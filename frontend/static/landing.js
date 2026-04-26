// ═══ Splash ═══
(function () {
  const fill = document.getElementById('splashFill');
  const pct  = document.getElementById('splashPct');
  const splash = document.getElementById('splash');
  if (!splash) return;

  let loaded = 0, total = 0, done = false;

  function setProgress(p) {
    const v = Math.min(100, Math.round(p));
    if (fill) fill.style.width = v + '%';
    if (pct)  pct.textContent  = v + '%';
  }

  function finish() {
    if (done) return;
    done = true;
    setProgress(100);
    setTimeout(() => splash.classList.add('hidden'), 400);
  }

  // Count resources via PerformanceObserver
  if (window.PerformanceObserver) {
    // Seed total with already-queued entries
    const existing = performance.getEntriesByType('resource');
    total = Math.max(existing.length + 8, 20); // +8 buffer for upcoming resources
    loaded = existing.length;
    setProgress((loaded / total) * 95);

    const obs = new PerformanceObserver((list) => {
      loaded += list.getEntries().length;
      if (loaded > total) total = loaded + 2;
      setProgress((loaded / total) * 95);
    });
    obs.observe({ type: 'resource', buffered: true });
  }

  window.addEventListener('load', () => {
    if (window.PerformanceObserver) {
      // Recalculate with final resource count
      const final = performance.getEntriesByType('resource').length;
      loaded = final; total = final;
      setProgress(95);
    }
    setTimeout(finish, 300);
  });

  // Fallback — hide after 5s no matter what
  setTimeout(finish, 5000);
})();

// ═══ Theme ═══
const themeToggle = document.getElementById('themeToggle');
const themeToggleCta = document.getElementById('themeToggleCta');
const applyTheme = (t) => {
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('physlab_theme', t);
  if (themeToggle) themeToggle.checked = (t === 'dark');
  if (themeToggleCta) themeToggleCta.checked = (t === 'dark');
};
applyTheme(localStorage.getItem('physlab_theme') || 'dark');
themeToggle?.addEventListener('change', () => applyTheme(themeToggle.checked ? 'dark' : 'light'));
themeToggleCta?.addEventListener('change', () => applyTheme(themeToggleCta.checked ? 'dark' : 'light'));

window.addEventListener('load', () => {
  requestAnimationFrame(() => document.body.classList.remove('preload'));
});

// ═══ Features ═══
const FEATURES = [
  {icon:'ph-lock-key',       cls:'',   title:'JWT Authentication',       desc:'Token-based sessions with bcrypt hashing and role-based access control on every route.'},
  {icon:'ph-file-doc',       cls:'cy', title:'DOCX → Interactive',        desc:'parser.py turns Word lab sheets into live worksheets — tables, equations, images intact.'},
  {icon:'ph-pencil-line',    cls:'vi', title:'Manual Activity Builder',   desc:'Build from scratch with data tables, equation blocks, file prompts and section scoring.'},
  {icon:'ph-users-three',    cls:'gr', title:'Real-time Collaboration',   desc:'Flask-SocketIO keeps groups in sync — live cursors, shared tables, synced equations.'},
  {icon:'ph-bell-ringing',   cls:'gd', title:'Live Notifications',        desc:'Grades posted, comments added, classes joined — every event pushed instantly.'},
  {icon:'ph-rss',            cls:'pk', title:'Live Activity Feed',        desc:'A running timeline of who did what — per class, per group, per student.'},
  {icon:'ph-check-square-offset', cls:'', title:'Submission & Grading',   desc:'Inline rubrics, per-question comments, retraction window, auto-notify on release.'},
  {icon:'ph-broadcast',      cls:'cy', title:'Class Stream',              desc:'Announcements, posts and threaded comments — the classroom wall, done right.'},
  {icon:'ph-users-four',     cls:'vi', title:'Group Management',          desc:'Form, balance and reassign groups. Every worksheet is group-scoped.'},
  {icon:'ph-calendar-check', cls:'gr', title:'Session Attendance',        desc:'Live roll call tied to the class roster — no separate spreadsheet to maintain.'},
  {icon:'ph-envelope-simple-open', cls:'gd', title:'Invite System',       desc:'Class codes, direct links, email invitations — all tracked back to a clean roster.'},
  {icon:'ph-user-circle',    cls:'pk', title:'Profile Management',        desc:'Roles, photos, contact info, password resets — self-service where safe.'},
  {icon:'ph-shield-check',   cls:'',   title:'Admin Dashboard',           desc:'User approvals, class archival, and system-wide statistics in one operator view.'}
];

function renderFeatures() {
  const grid = document.getElementById('featuresGrid');
  if (!grid) return;
  grid.innerHTML = FEATURES.map(f => `
    <div class="feat">
      <div class="feat-icon ${f.cls}"><i class="ph-bold ${f.icon}"></i></div>
      <div class="feat-title">${f.title}</div>
      <div class="feat-desc">${f.desc}</div>
    </div>`).join('');
}
renderFeatures();

// ═══ Hero variants HTML ═══
function heroWorkflow() {
  return `
  <div class="hv-workflow">
    <div class="hv-wf-stage">
      <svg class="hv-flow" viewBox="0 0 480 480" preserveAspectRatio="none">
        <defs>
          <linearGradient id="hvGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#0A66C2"/>
            <stop offset="100%" stop-color="#06B6D4"/>
          </linearGradient>
        </defs>
        <path d="M 110 90 Q 190 140 240 190"/>
        <path d="M 320 230 Q 380 290 420 320"/>
      </svg>
      <div class="hv-node docx">
        <div class="nhead"><i class="ph-fill ph-file-doc"></i> experiment.docx <span class="ntag" style="margin-left:auto">IN</span></div>
        <div class="n-rows">
          <div class="n-row">Title · Objective</div>
          <div class="n-row">Materials · Theory</div>
          <div class="n-row">Data Table (6×4)</div>
        </div>
      </div>
      <div class="hv-node sheet">
        <div class="nhead"><i class="ph-fill ph-cursor-click"></i> Live Worksheet <span class="ntag" style="margin-left:auto">SYNC</span></div>
        <div class="table-mini">
          <div class="tcell f"></div><div class="tcell f"></div><div class="tcell"></div>
          <div class="tcell f"></div><div class="tcell f2"></div><div class="tcell"></div>
          <div class="tcell f2"></div><div class="tcell"></div><div class="tcell"></div>
        </div>
        <div class="n-rows" style="margin-top:8px">
          <div class="n-row">3 editors · auto-saved 0.2s</div>
        </div>
      </div>
      <div class="hv-node grade">
        <div class="nhead"><i class="ph-fill ph-medal"></i> Graded <span class="ntag" style="margin-left:auto">OUT</span></div>
        <div class="score">92<span style="opacity:.4;font-size:14px">/100</span></div>
        <div class="gradebar"><div class="gradefill"></div></div>
      </div>
      <div class="hv-packet p1"></div>
      <div class="hv-packet p2"></div>
    </div>
  </div>`;
}

function heroDashboard() {
  return `
  <div class="hv-dashboard">
    <div class="hv-db-chrome">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span class="addr">physlab.edu/class/phys101</span>
    </div>
    <div class="hv-db-body">
      <div class="hv-db-side">
        <i class="ph-bold ph-squares-four on"></i>
        <i class="ph-bold ph-flask"></i>
        <i class="ph-bold ph-users-three"></i>
        <i class="ph-bold ph-chat-circle"></i>
        <i class="ph-bold ph-chart-bar"></i>
      </div>
      <div class="hv-db-main">
        <div class="hv-db-head">
          <div class="hv-db-title">PHYS 101 · Lab 07 <span>Pendulum &amp; Gravity</span></div>
          <div class="hv-db-badge">● Live</div>
        </div>
        <div class="hv-db-kpis">
          <div class="hv-db-kpi"><b>24</b><span>Students</span></div>
          <div class="hv-db-kpi"><b>6</b><span>Groups</span></div>
          <div class="hv-db-kpi"><b>18</b><span>Submitted</span></div>
        </div>
        <div class="hv-db-chart">
          <svg viewBox="0 0 300 100" preserveAspectRatio="none">
            <defs>
              <linearGradient id="areaG" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#0A66C2" stop-opacity=".4"/>
                <stop offset="100%" stop-color="#0A66C2" stop-opacity="0"/>
              </linearGradient>
            </defs>
            <path d="M 0 70 L 30 60 L 60 55 L 90 40 L 120 48 L 150 30 L 180 35 L 210 20 L 240 25 L 270 15 L 300 18 L 300 100 L 0 100 Z" fill="url(#areaG)"/>
            <path d="M 0 70 L 30 60 L 60 55 L 90 40 L 120 48 L 150 30 L 180 35 L 210 20 L 240 25 L 270 15 L 300 18" fill="none" stroke="#0A66C2" stroke-width="2"/>
            <circle cx="210" cy="20" r="3" fill="#06B6D4"/>
          </svg>
        </div>
        <div class="hv-db-list">
          <div class="hv-db-row"><div class="rl"><span class="dotg"></span>Group Alpha · Trial 4 complete</div><span class="score-p">94%</span></div>
          <div class="hv-db-row"><div class="rl"><span class="dotg" style="background:#fcd34d"></span>Group Beta · editing Analysis</div><span class="score-p">—</span></div>
          <div class="hv-db-row"><div class="rl"><span class="dotg" style="background:#a78bfa"></span>Group Gamma · submitted 2m ago</div><span class="score-p">91%</span></div>
        </div>
      </div>
    </div>
  </div>`;
}

function heroSplit() {
  const gridLines = [0,35,70,105,140].map(y => `<line x1="0" y1="${y}" x2="400" y2="${y}"/>`).join('')
    + [0,50,100,150,200,250,300,350,400].map(x => `<line x1="${x}" y1="0" x2="${x}" y2="140"/>`).join('');
  return `
  <div class="hv-split">
    <div class="hv-split-top">
      <div class="hv-split-head"><b><i class="ph-bold ph-wave-sine"></i> Oscillation · Trial 3</b><span>9.81 m/s²</span></div>
      <div class="hv-scope">
        <svg viewBox="0 0 400 140" preserveAspectRatio="none">
          <defs>
            <linearGradient id="wavG" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stop-color="#0A66C2"/>
              <stop offset="100%" stop-color="#06B6D4"/>
            </linearGradient>
          </defs>
          <g stroke="currentColor" stroke-opacity=".08" stroke-width="1">${gridLines}</g>
          <line x1="0" y1="70" x2="400" y2="70" stroke="currentColor" stroke-opacity=".25" stroke-dasharray="2 4"/>
          <path id="wave" d="" fill="none" stroke="url(#wavG)" stroke-width="2.5" stroke-linecap="round"/>
          <circle id="wavePt" r="4" fill="#06B6D4"/>
        </svg>
      </div>
    </div>
    <div class="hv-split-bot">
      <div class="hv-split-head"><b><i class="ph-bold ph-users-three"></i> Group Alpha — Worksheet</b><span>auto-saved</span></div>
      <div class="hv-worksheet">
        <div class="hv-ws-row"><label>Mass (kg)</label><div class="vinput">0.250</div></div>
        <div class="hv-ws-row"><label>Length (m)</label><div class="vinput">1.000</div></div>
        <div class="hv-ws-row"><label>Period T</label><div class="vinput">2.007 <span class="hv-ws-cursor"></span></div></div>
        <div class="hv-ws-row"><label>g calc</label><div class="vinput" style="color:var(--accent-l)">9.80 m/s²</div></div>
      </div>
    </div>
  </div>`;
}

// ═══ Wave animation for split variant ═══
let rafWave = 0;
function startWaveAnim() {
  const path = document.getElementById('wave');
  const pt   = document.getElementById('wavePt');
  if (!path || !pt) return;
  let t = 0;
  const build = () => {
    const pts = [];
    for (let x = 0; x <= 400; x += 4) {
      const y = 70 + Math.sin((x + t) * 0.035) * 38 * Math.exp(-Math.pow((x - 200) / 260, 2) * 0.5);
      pts.push(`${x === 0 ? 'M' : 'L'} ${x} ${y.toFixed(1)}`);
    }
    path.setAttribute('d', pts.join(' '));
    const hx = 320;
    const hy = 70 + Math.sin((hx + t) * 0.035) * 38 * Math.exp(-Math.pow((hx - 200) / 260, 2) * 0.5);
    pt.setAttribute('cx', hx);
    pt.setAttribute('cy', hy.toFixed(1));
    t += 1.6;
    rafWave = requestAnimationFrame(build);
  };
  cancelAnimationFrame(rafWave);
  build();
}

// ═══ Auto-cycling hero ═══
const VARIANTS = ['workflow', 'dashboard', 'split'];
const VARIANT_LABELS = ['Workflow', 'Dashboard', 'Live Data'];
let currentVariant = 0;
let heroTimer = null;

function buildHeroHTML(variant) {
  if (variant === 'dashboard') return heroDashboard();
  if (variant === 'split')     return heroSplit();
  return heroWorkflow();
}

// Build all slides once into the DOM
function initHero() {
  const host = document.getElementById('heroVisual');
  if (!host) return;

  const slides = VARIANTS.map((v, i) => `
    <div class="hv-slide${i === 0 ? ' active' : ''}" data-variant="${v}">${buildHeroHTML(v)}</div>
  `).join('');
  const dots = VARIANTS.map((_, i) => `
    <button class="hv-dot${i === 0 ? ' on' : ''}" data-idx="${i}" aria-label="${VARIANT_LABELS[i]}"></button>
  `).join('');

  host.innerHTML = `<div class="hv-slides">${slides}</div><div class="hv-dots">${dots}</div>`;

  host.querySelectorAll('.hv-dot').forEach(btn => {
    btn.addEventListener('click', () => goToVariant(Number(btn.dataset.idx)));
  });

  // Start wave for split slide (it's hidden initially, so anim runs in background)
  setTimeout(startWaveAnim, 100);

  scheduleNext();
}

// Switch to a variant by index — only toggles classes, no DOM rebuild
function goToVariant(idx) {
  clearTimeout(heroTimer);
  currentVariant = ((idx % VARIANTS.length) + VARIANTS.length) % VARIANTS.length;

  const host = document.getElementById('heroVisual');
  if (!host) return;

  host.querySelectorAll('.hv-slide').forEach((s, i) => s.classList.toggle('active', i === currentVariant));
  host.querySelectorAll('.hv-dot').forEach((d, i) => d.classList.toggle('on', i === currentVariant));

  scheduleNext();
}

function scheduleNext() {
  heroTimer = setTimeout(() => goToVariant(currentVariant + 1), 4500);
}

initHero();

// ═══ Role tabs ═══
document.querySelectorAll('.role-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const r = tab.dataset.role;
    document.querySelectorAll('.role-tab').forEach(t => t.classList.toggle('active', t === tab));
    document.querySelectorAll('.role-panel').forEach(p => p.classList.toggle('active', p.dataset.role === r));
  });
});

// ═══ Scroll reveal ═══
const io = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
  });
}, { threshold: 0.12 });
document.querySelectorAll('.step, .why-card, .feat, .faq-item').forEach(el => io.observe(el));
