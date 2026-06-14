// app.js — router, state, fetch helpers

export const $  = (sel, root=document) => root.querySelector(sel);
export const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

const COMPACT = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });
export const fmt = {
  int:   n => (n ?? 0).toLocaleString(),
  compact: n => COMPACT.format(n ?? 0),
  usd:   n => n == null ? '—' : '$' + Number(n).toFixed(2),
  usd4:  n => n == null ? '—' : '$' + Number(n).toFixed(4),
  pct:   n => n == null ? '—' : (n * 100).toFixed(0) + '%',
  short: (s, n=80) => s == null ? '' : (s.length > n ? s.slice(0, n - 1) + '…' : s),
  htmlSafe: s => (s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  modelClass: m => {
    const s = (m || '').toLowerCase();
    if (s.includes('haiku')) return 'mini';
    if (s.includes('sonnet')) return 'large';
    if (s.includes('opus') || s.includes('fable') || s.includes('mythos')) return 'frontier';
    if (s.includes('mini') || s.includes('nano')) return 'mini';
    if (s.includes('5.5')) return 'frontier';
    if (s.includes('gpt') || s.includes('codex')) return 'large';
    return '';
  },
  modelShort: m => (m || '').replace(/^openai[:/]/, ''),
  ts: t => (t || '').slice(0, 16).replace('T', ' '),
};

const SOURCE_META = {
  codex:  { label: 'Codex', brand: 'H&K Codex Dashboard', accent: '#C7A65A', secondary: '#64A7A0', good: '#8CBF75', warn: '#D58A4B' },
  claude: { label: 'Claude Code', brand: 'H&K Claude Code Dashboard', accent: '#D97745', secondary: '#B78B68', good: '#8FAE76', warn: '#D2A55F' },
};

function sourceParam(path) {
  if (!path.startsWith('/api/') || !state.source || state.source === 'all') return path;
  const sep = path.includes('?') ? '&' : '?';
  return `${path}${sep}source=${encodeURIComponent(state.source)}`;
}

export async function api(path, opts) {
  const r = await fetch(sourceParam(path), opts);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

export const state = {
  plan: 'api',
  pricing: null,
  source: localStorage.getItem('cd.source') || 'codex',
  sourceMeta: SOURCE_META,
  palette: SOURCE_META.codex,
};
let renderedSignature = null;

const ROUTES = {
  '/overview': () => import('/web/routes/overview.js'),
  '/prompts':  () => import('/web/routes/prompts.js'),
  '/sessions': () => import('/web/routes/sessions.js'),
  '/projects': () => import('/web/routes/projects.js'),
  '/skills':   () => import('/web/routes/skills.js'),
  '/tips':     () => import('/web/routes/tips.js'),
  '/settings': () => import('/web/routes/settings.js'),
};

function buildTopbar() {
  const wrap = document.createElement('header');
  wrap.className = 'topbar';
  wrap.innerHTML = `
    <div class="brand" id="brand-label">H&K Codex Dashboard</div>
    <nav>
      ${Object.keys(ROUTES).map(p => `<a href="#${p}" data-route="${p}">${p.slice(1)}</a>`).join('')}
    </nav>
    <div class="spacer"></div>
    <div class="source-switch" role="tablist" aria-label="Data source">
      <button type="button" data-source="codex">Codex</button>
      <button type="button" data-source="claude">Claude Code</button>
    </div>
    <span class="pill" id="plan-pill">api</span>
  `;
  document.body.prepend(wrap);
  wrap.querySelectorAll('.source-switch button').forEach(btn => {
    btn.addEventListener('click', () => {
      const nextSource = btn.dataset.source;
      if (state.source === nextSource) return;
      const previousSource = state.source;
      state.source = nextSource;
      localStorage.setItem('cd.source', state.source);
      playThemeTransition(state.source, previousSource);
      applySourceTheme();
      renderedSignature = null;
      render();
    });
  });
}

function playThemeTransition(source, previousSource) {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.querySelector('.theme-wipe')?.remove();
  const wipe = document.createElement('div');
  wipe.className = `theme-wipe to-${source} from-${previousSource || 'none'}`;
  const switcher = $('.source-switch');
  const brand = $('#brand-label');

  switcher?.classList.remove('switch-kick');
  brand?.classList.remove('brand-swap');
  void switcher?.offsetWidth;
  void brand?.offsetWidth;

  document.body.classList.add('theme-switching', `theme-to-${source}`);
  switcher?.classList.add('switch-kick');
  brand?.classList.add('brand-swap');
  document.body.appendChild(wipe);
  wipe.addEventListener('animationend', () => {
    wipe.remove();
    document.body.classList.remove('theme-switching', `theme-to-${source}`);
    switcher?.classList.remove('switch-kick');
    brand?.classList.remove('brand-swap');
  }, { once: true });
}

function applySourceTheme() {
  state.palette = SOURCE_META[state.source] || SOURCE_META.codex;
  document.body.classList.toggle('source-claude', state.source === 'claude');
  document.body.classList.toggle('source-codex', state.source !== 'claude');
  const brand = $('#brand-label');
  if (brand) brand.textContent = state.palette.brand;
  document.title = state.palette.brand;
  const active = state.source;
  $$('.source-switch button').forEach(btn => btn.classList.toggle('active', btn.dataset.source === active));
  $$('.source-switch').forEach(el => el.dataset.active = active);
}

function setActiveTab(routeKey) {
  $$('header.topbar nav a').forEach(a => a.classList.toggle('active', a.dataset.route === routeKey));
}

async function render() {
  const hash = location.hash.replace(/^#/, '') || '/overview';
  const path = hash.split('?')[0];
  const routeSignature = `${state.source}:${hash}`;
  const shouldAnimate = routeSignature !== renderedSignature;
  let key = path;
  if (path.startsWith('/sessions/')) key = '/sessions';
  setActiveTab(key);
  const loader = ROUTES[key] || ROUTES['/overview'];
  const mod = await loader();
  const app = $('#app');
  app.classList.remove('route-enter');
  app.innerHTML = '';
  try {
    await mod.default(app);
    if (shouldAnimate) {
      app.querySelectorAll('.card, .range-tabs, table').forEach((el, i) => {
        el.style.setProperty('--stagger', Math.min(i, 18));
      });
      requestAnimationFrame(() => app.classList.add('route-enter'));
      renderedSignature = routeSignature;
    }
  } catch (e) {
    app.innerHTML = `<div class="card"><h2>Error</h2><pre>${fmt.htmlSafe(String(e.stack || e))}</pre></div>`;
  }
}

async function firstRun() {
  if (localStorage.getItem('cd.plan-set')) return;
  const plans = Object.entries(state.pricing.plans);
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <h2>Welcome — pick your plan</h2>
      <p>This sets how API-equivalent costs are displayed. Change it later in Settings.</p>
      <select id="firstplan" style="width:100%">
        ${plans.map(([k,v]) => `<option value="${k}">${v.label}${v.monthly ? ` — $${v.monthly}/mo` : ''}</option>`).join('')}
      </select>
      <div class="actions">
        <div class="spacer"></div>
        <button class="primary" id="firstsave">Continue</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  await new Promise(res => $('#firstsave', overlay).addEventListener('click', async () => {
    const plan = $('#firstplan', overlay).value;
    await fetch('/api/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan }) });
    localStorage.setItem('cd.plan-set', '1');
    overlay.remove();
    res();
  }));
  state.plan = (await api('/api/plan')).plan;
}

async function boot() {
  buildTopbar();
  applySourceTheme();
  const planResp = await api('/api/plan');
  state.plan = planResp.plan;
  state.pricing = planResp.pricing;
  $('#plan-pill').textContent = state.plan;

  await firstRun();

  window.addEventListener('hashchange', render);
  await render();

  // Privacy blur (Cmd+B / Ctrl+B)
  window.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
      e.preventDefault();
      document.body.classList.toggle('privacy-on');
    }
  });

  // SSE diff stream
  try {
    const es = new EventSource('/api/stream');
    es.onmessage = ev => {
      try {
        const evt = JSON.parse(ev.data);
        if (evt.type === 'scan') render();
      } catch {}
    };
  } catch {}
}

boot();
