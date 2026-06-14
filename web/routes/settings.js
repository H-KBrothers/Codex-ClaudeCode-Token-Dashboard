import { api, state, $, fmt } from '/web/app.js';

export default async function (root) {
  const [cur, sources, config] = await Promise.all([
    api('/api/plan'),
    api('/api/sources'),
    api('/api/config'),
  ]);
  const plans = Object.entries(cur.pricing.plans);
  const source = state.source === 'claude' ? 'claude' : 'codex';
  const meta = state.sourceMeta[source];
  const summary = sources.find(s => s.source === source) || {};
  const sourceConfig = config.sources?.[source] || {};
  const modelEntries = Object.entries(cur.pricing.models)
    .filter(([key, value]) => source === 'claude'
      ? key.startsWith('claude-') || String(value.tier || '').startsWith('claude_')
      : !(key.startsWith('claude-') || String(value.tier || '').startsWith('claude_')));
  const planCopy = source === 'claude'
    ? 'Claude Code is shown with Anthropic API-equivalent model rates. The plan selector only changes the global display label.'
    : 'Sets how Codex cost is labeled. Codex Free and subscriptions still show API-equivalent dollars, not an actual bill.';

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h2>${meta.label} Settings</h2>
        <p class="muted">Source-specific tracking, pricing, and display controls.</p>
      </div>
    </div>

    <div class="settings-grid">
      <section class="card settings-panel source-panel">
        <div class="settings-title">
          <div>
            <h3>Data source</h3>
            <p class="muted">${meta.brand} is reading local transcript files from this root.</p>
          </div>
          <span class="source-chip">${meta.label}</span>
        </div>
        <div class="source-path">${fmt.htmlSafe(sourceConfig.root || 'Not configured')}</div>
        <div class="source-stats">
          <div><span>Sessions</span><strong>${fmt.int(summary.sessions || 0)}</strong></div>
          <div><span>Messages</span><strong>${fmt.int(summary.messages || 0)}</strong></div>
          <div><span>Tokens</span><strong>${fmt.compact(summary.tokens || 0)}</strong></div>
          <div><span>Status</span><strong class="${sourceConfig.exists ? 'ok' : 'warn'}">${sourceConfig.exists ? 'Ready' : 'Missing'}</strong></div>
        </div>
        <div class="settings-actions">
          <button class="primary" id="scan-now">Scan now</button>
          <span id="scan-msg" class="muted">${summary.last_seen ? `Last seen ${fmt.ts(summary.last_seen)}` : 'No local records loaded yet.'}</span>
        </div>
      </section>

      <section class="card settings-panel">
        <div class="settings-title">
          <div>
            <h3>Cost display</h3>
            <p class="muted">${planCopy}</p>
          </div>
        </div>
        <div class="control-row">
          <label class="select-shell" for="plan">
            <span>Plan label</span>
            <select id="plan">
              ${plans.map(([k,v]) => `<option value="${k}" ${k===cur.plan?'selected':''}>${v.label}${v.monthly?` - $${v.monthly}/mo`: v.api_equivalent_only ? ' - estimate only' : ''}</option>`).join('')}
            </select>
          </label>
          <button class="primary" id="save">Save</button>
        </div>
        <div id="msg" class="settings-msg muted"></div>
      </section>
    </div>

    <div class="card settings-panel pricing-panel">
      <div class="settings-title">
        <div>
          <h3>${meta.label} pricing table</h3>
          <p class="muted">Edit <code>pricing.json</code> in the project root to change rates. Reload the page after editing.</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>model</th><th class="num">input</th><th class="num">output</th><th class="num">cache read</th><th class="num">cache 5m</th><th class="num">cache 1h</th></tr></thead>
          <tbody>
            ${modelEntries.map(([k,v]) => `
              <tr><td><span class="badge ${v.tier}">${k}</span></td>
                <td class="num">$${v.input.toFixed(2)}</td>
                <td class="num">$${v.output.toFixed(2)}</td>
                <td class="num">$${v.cache_read.toFixed(2)}</td>
                <td class="num">$${v.cache_create_5m.toFixed(2)}</td>
                <td class="num">$${v.cache_create_1h.toFixed(2)}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
      <p class="muted fine-print">Rates per 1M tokens, USD.</p>
    </div>

    <div class="card settings-panel privacy-panel">
      <h3>Privacy</h3>
      <p class="muted">Press <code>Cmd/Ctrl + B</code> anywhere to blur prompt text and other sensitive content for screenshots.</p>
    </div>`;

  $('#save').addEventListener('click', async () => {
    const plan = $('#plan').value;
    await fetch('/api/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan }) });
    state.plan = plan;
    document.getElementById('plan-pill').textContent = plan;
    $('#msg').textContent = 'Saved.';
    $('#msg').style.color = 'var(--good)';
  });
  $('#scan-now').addEventListener('click', async () => {
    const btn = $('#scan-now');
    btn.disabled = true;
    $('#scan-msg').textContent = 'Scanning local transcripts...';
    try {
      const result = await api('/api/scan');
      const detail = result.sources?.[source];
      $('#scan-msg').textContent = detail
        ? `Loaded ${fmt.int(detail.messages)} messages from ${fmt.int(detail.files)} files.`
        : 'Scan complete.';
    } catch (e) {
      $('#scan-msg').textContent = 'Scan failed.';
      $('#scan-msg').style.color = 'var(--bad)';
    } finally {
      btn.disabled = false;
    }
  });
}
