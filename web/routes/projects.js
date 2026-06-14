import { api, fmt } from '/web/app.js';

const RANGES = [
  { key: '7d', label: '7d', days: 7 },
  { key: '30d', label: '30d', days: 30 },
  { key: '90d', label: '90d', days: 90 },
  { key: 'all', label: 'All', days: null },
];

function readRange() {
  const q = (location.hash.split('?')[1] || '');
  const m = /(?:^|&)range=([^&]+)/.exec(q);
  const k = m && decodeURIComponent(m[1]);
  return RANGES.find(r => r.key === k) || RANGES[1];
}

function writeRange(key) {
  location.hash = '#/projects?range=' + encodeURIComponent(key);
}

function sinceIso(range) {
  if (!range.days) return null;
  return new Date(Date.now() - range.days * 86400 * 1000).toISOString();
}

function pct(value, max) {
  if (!max) return 0;
  return Math.max(2, Math.min(100, (value / max) * 100));
}

export default async function (root) {
  const range = readRange();
  const since = sinceIso(range);
  const rows = await api('/api/projects' + (since ? '?since=' + encodeURIComponent(since) : ''));
  const totals = rows.reduce((acc, r) => {
    acc.sessions += r.sessions || 0;
    acc.turns += r.turns || 0;
    acc.billable += r.billable_tokens || 0;
    acc.cache += r.cache_read_tokens || 0;
    return acc;
  }, { sessions: 0, turns: 0, billable: 0, cache: 0 });
  const maxBillable = Math.max(...rows.map(r => r.billable_tokens || 0), 0);
  const maxCache = Math.max(...rows.map(r => r.cache_read_tokens || 0), 0);
  const cacheReuse = totals.billable ? totals.cache / (totals.billable + totals.cache) : 0;

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h2>Projects</h2>
        <p class="muted">Workspaces ranked by API-equivalent activity and cached context reuse.</p>
      </div>
      <div class="range-tabs" role="tablist">
        ${RANGES.map(r => `<button data-range="${r.key}" class="${r.key === range.key ? 'active' : ''}">${r.label}</button>`).join('')}
      </div>
    </div>

    <div class="row cols-4 project-summary">
      <div class="card kpi"><div class="label">Projects</div><div class="value">${fmt.int(rows.length)}</div></div>
      <div class="card kpi"><div class="label">Sessions</div><div class="value">${fmt.int(totals.sessions)}</div></div>
      <div class="card kpi"><div class="label">Billable tokens</div><div class="value big">${fmt.compact(totals.billable)}</div></div>
      <div class="card kpi saved"><div class="label">Cache reuse</div><div class="value">${fmt.pct(cacheReuse)}</div><div class="sub">${fmt.compact(totals.cache)} cache reads</div></div>
    </div>

    <div class="card project-panel">
      <div class="panel-title">
        <div>
          <h3>Project activity</h3>
          <p class="muted">High cache reads usually mean Codex is reusing context instead of rebuilding it as fresh input.</p>
        </div>
        <span class="badge">${range.days ? `last ${range.days} days` : 'all time'}</span>
      </div>
      <div class="table-wrap">
        <table class="project-table">
          <thead><tr><th>project</th><th class="num">sessions</th><th class="num">turns</th><th>billable tokens</th><th>cache reads</th></tr></thead>
          <tbody>
            ${rows.map(r => {
              const name = fmt.htmlSafe(r.project_name || r.project_slug);
              const slug = fmt.htmlSafe(r.project_slug);
              return `
                <tr>
                  <td title="${slug}">
                    <div class="project-name">${name}</div>
                    <div class="project-slug">${slug}</div>
                  </td>
                  <td class="num">${fmt.int(r.sessions)}</td>
                  <td class="num">${fmt.int(r.turns)}</td>
                  <td class="metric-col">
                    <div class="metric-cell">
                      <span>${fmt.int(r.billable_tokens)}</span>
                      <span class="metric-compact">${fmt.compact(r.billable_tokens)}</span>
                    </div>
                    <div class="metric-bar"><i style="width:${pct(r.billable_tokens || 0, maxBillable).toFixed(2)}%"></i></div>
                  </td>
                  <td class="metric-col">
                    <div class="metric-cell">
                      <span>${fmt.int(r.cache_read_tokens)}</span>
                      <span class="metric-compact">${fmt.compact(r.cache_read_tokens)}</span>
                    </div>
                    <div class="metric-bar cache"><i style="width:${pct(r.cache_read_tokens || 0, maxCache).toFixed(2)}%"></i></div>
                  </td>
                </tr>`;
            }).join('') || '<tr><td colspan="5" class="muted">No projects in this range.</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>`;

  root.querySelectorAll('.range-tabs button').forEach(btn => {
    btn.addEventListener('click', () => writeRange(btn.dataset.range));
  });
}
