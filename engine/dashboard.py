"""
Generates a self-contained dashboard.html from your real data:
data/vault.json (bred/vaulted strategies) and data/signal_log.json
(every signal ever fired + its outcome).

No server needed -- it's a static file with the data embedded directly,
regenerated fresh each time you run `python run.py dashboard`.
"""
import json
import os
import webbrowser

VAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "vault.json")
SIGNAL_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "signal_log.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "dashboard.html")


def _load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _calc_rr(entry, stop, target):
    risk = abs(entry - stop)
    reward = abs(target - entry)
    return round(reward / risk, 2) if risk else 0.0


def generate_dashboard() -> str:
    vault = _load_json(VAULT_PATH, [])
    signals = _load_json(SIGNAL_LOG_PATH, [])

    # summary stats
    symbols = sorted(set(g["symbol"] for g in vault))
    timeframes = sorted(set(g["timeframe"] for g in vault))
    pending = [s for s in signals if s["taken"] is None or s["outcome"] is None]
    closed = [s for s in signals if s["outcome"] is not None]
    wins = sum(1 for s in closed if s["outcome"] == "WIN")
    live_win_rate = round(100 * wins / len(closed), 1) if closed else None

    vault_json = json.dumps(vault)
    signals_json = json.dumps(signals)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Helios // Strategy Vault</title>
<style>
  :root {{
    --bg: #0a0a0c;
    --panel: #111114;
    --border: #2a1418;
    --red: #e8384f;
    --red-dim: #7a2530;
    --green: #3ecf8e;
    --text: #e4e2e0;
    --text-dim: #8a8785;
    --mono: 'SF Mono', 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--mono);
    margin: 0;
    padding: 24px;
    font-size: 13px;
  }}
  h1 {{
    font-size: 22px;
    letter-spacing: 2px;
    margin: 0 0 4px 0;
    color: var(--text);
  }}
  h1 span {{ color: var(--red); }}
  .subtitle {{
    color: var(--text-dim);
    font-size: 12px;
    margin-bottom: 24px;
    letter-spacing: 1px;
    text-transform: uppercase;
  }}
  .stats-row {{
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
    flex-wrap: wrap;
  }}
  .stat-box {{
    background: var(--panel);
    border: 1px solid var(--border);
    padding: 14px 20px;
    min-width: 140px;
  }}
  .stat-box .label {{
    color: var(--text-dim);
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 6px;
  }}
  .stat-box .value {{
    font-size: 24px;
    font-weight: 600;
  }}
  .stat-box .value.red {{ color: var(--red); }}
  .stat-box .value.green {{ color: var(--green); }}
  .panel {{
    background: var(--panel);
    border: 1px solid var(--border);
    margin-bottom: 20px;
  }}
  .panel-header {{
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    color: var(--red);
    font-size: 11px;
    letter-spacing: 2px;
    text-transform: uppercase;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .panel-header .count {{ color: var(--text-dim); font-size: 10px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
  }}
  th {{
    text-align: left;
    padding: 8px 12px;
    color: var(--text-dim);
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    user-select: none;
  }}
  th:hover {{ color: var(--red); }}
  td {{
    padding: 8px 12px;
    border-bottom: 1px solid #1a1a1d;
    font-size: 12px;
  }}
  tr:hover td {{ background: #16161a; }}
  .buy {{ color: var(--green); }}
  .sell {{ color: var(--red); }}
  .fitness {{ color: var(--red); font-weight: 600; }}
  .dim {{ color: var(--text-dim); }}
  .filter-bar {{
    display: flex;
    gap: 8px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
  }}
  .filter-bar select, .filter-bar input {{
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 4px 8px;
    font-family: var(--mono);
    font-size: 11px;
  }}
  .empty {{
    padding: 24px;
    text-align: center;
    color: var(--text-dim);
  }}
  .badge {{
    display: inline-block;
    padding: 1px 6px;
    font-size: 10px;
    border: 1px solid var(--border);
    color: var(--text-dim);
  }}
</style>
</head>
<body>

<h1>HELIOS <span>//</span> STRATEGY VAULT</h1>
<div class="subtitle">generated locally from your data · no external calls</div>

<div class="stats-row">
  <div class="stat-box">
    <div class="label">Strategies Vaulted</div>
    <div class="value">{len(vault)}</div>
  </div>
  <div class="stat-box">
    <div class="label">Symbols / Timeframes</div>
    <div class="value">{len(symbols)} / {len(timeframes)}</div>
  </div>
  <div class="stat-box">
    <div class="label">Pending Signals</div>
    <div class="value red">{len(pending)}</div>
  </div>
  <div class="stat-box">
    <div class="label">Closed Signals</div>
    <div class="value">{len(closed)}</div>
  </div>
  <div class="stat-box">
    <div class="label">Live Win Rate</div>
    <div class="value {'green' if live_win_rate and live_win_rate >= 50 else 'red'}">{live_win_rate if live_win_rate is not None else '--'}{'%' if live_win_rate is not None else ''}</div>
  </div>
</div>

<div class="panel">
  <div class="panel-header">
    <span>Pending Signals</span>
    <span class="count">click a header to sort</span>
  </div>
  <div id="signals-table"></div>
</div>

<div class="panel">
  <div class="panel-header">
    <span>Strategy Vault</span>
    <div class="filter-bar">
      <select id="symbol-filter"><option value="">All Symbols</option></select>
      <select id="timeframe-filter"><option value="">All Timeframes</option></select>
    </div>
  </div>
  <div id="vault-table"></div>
</div>

<script>
const vault = {vault_json};
const signals = {signals_json};

function calcRR(entry, stop, target) {{
  const risk = Math.abs(entry - stop);
  const reward = Math.abs(target - entry);
  return risk ? (reward / risk).toFixed(2) : '0.00';
}}

function renderSignals(list) {{
  const el = document.getElementById('signals-table');
  if (!list.length) {{
    el.innerHTML = '<div class="empty">No pending signals right now.</div>';
    return;
  }}
  let rows = list.map(s => {{
    const dirClass = s.direction === 'BUY' ? 'buy' : 'sell';
    const rr = calcRR(s.entry, s.stop, s.target);
    const taken = s.taken === true ? 'TAKEN' : s.taken === false ? 'SKIPPED' : '?';
    const outcome = s.outcome || '?';
    return `<tr>
      <td class="dim">${{s.id}}</td>
      <td class="${{dirClass}}">${{s.direction}}</td>
      <td>${{s.symbol}}</td>
      <td class="dim">${{s.timeframe}}</td>
      <td>${{s.entry}}</td>
      <td>${{s.stop}}</td>
      <td>${{s.target}}</td>
      <td>1:${{rr}}</td>
      <td class="dim">${{s.genome_id}}</td>
      <td>${{taken}}</td>
      <td>${{outcome}}</td>
    </tr>`;
  }}).join('');
  el.innerHTML = `<table>
    <tr>
      <th>ID</th><th>Dir</th><th>Symbol</th><th>TF</th><th>Entry</th><th>Stop</th>
      <th>Target</th><th>RR</th><th>Genome</th><th>Taken</th><th>Outcome</th>
    </tr>${{rows}}</table>`;
}}

function renderVault(list) {{
  const el = document.getElementById('vault-table');
  if (!list.length) {{
    el.innerHTML = '<div class="empty">No strategies vaulted yet -- run a breed campaign first.</div>';
    return;
  }}
  let rows = list.map(g => {{
    const score = g.score || {{}};
    const test = score.test || {{}};
    return `<tr>
      <td class="dim">${{g.id}}</td>
      <td>${{g.symbol}}</td>
      <td class="dim">${{g.timeframe}}</td>
      <td>${{g.signal_indicator}}</td>
      <td class="dim">${{g.bias}}</td>
      <td class="dim">${{g.filter}}</td>
      <td class="fitness">${{score.fitness ?? '--'}}</td>
      <td>${{test.return_pct ?? '--'}}%</td>
      <td>${{test.max_dd_pct ?? '--'}}%</td>
      <td>${{test.win_rate ?? '--'}}%</td>
      <td class="dim">${{test.trades ?? '--'}}</td>
    </tr>`;
  }}).join('');
  el.innerHTML = `<table>
    <tr>
      <th onclick="sortVault('id')">ID</th>
      <th onclick="sortVault('symbol')">Symbol</th>
      <th onclick="sortVault('timeframe')">TF</th>
      <th onclick="sortVault('signal_indicator')">Indicator</th>
      <th>Bias</th><th>Filter</th>
      <th onclick="sortVault('fitness')">Fitness</th>
      <th onclick="sortVault('return')">Test Ret</th>
      <th onclick="sortVault('dd')">Test DD</th>
      <th onclick="sortVault('winrate')">Win Rate</th>
      <th onclick="sortVault('trades')">Trades</th>
    </tr>${{rows}}</table>`;
}}

let sortDir = {{}};
function sortVault(key) {{
  sortDir[key] = !sortDir[key];
  const dir = sortDir[key] ? 1 : -1;
  const getVal = (g) => {{
    const test = (g.score || {{}}).test || {{}};
    if (key === 'fitness') return (g.score || {{}}).fitness || 0;
    if (key === 'return') return test.return_pct || 0;
    if (key === 'dd') return test.max_dd_pct || 0;
    if (key === 'winrate') return test.win_rate || 0;
    if (key === 'trades') return test.trades || 0;
    return g[key] || '';
  }};
  const filtered = applyFilters();
  filtered.sort((a, b) => {{
    const av = getVal(a), bv = getVal(b);
    if (typeof av === 'string') return dir * av.localeCompare(bv);
    return dir * (av - bv);
  }});
  renderVault(filtered);
}}

function applyFilters() {{
  const symbol = document.getElementById('symbol-filter').value;
  const tf = document.getElementById('timeframe-filter').value;
  return vault.filter(g =>
    (!symbol || g.symbol === symbol) && (!tf || g.timeframe === tf)
  );
}}

function setupFilters() {{
  const symbols = [...new Set(vault.map(g => g.symbol))].sort();
  const timeframes = [...new Set(vault.map(g => g.timeframe))].sort();
  const symbolSel = document.getElementById('symbol-filter');
  const tfSel = document.getElementById('timeframe-filter');
  symbols.forEach(s => symbolSel.innerHTML += `<option value="${{s}}">${{s}}</option>`);
  timeframes.forEach(t => tfSel.innerHTML += `<option value="${{t}}">${{t}}</option>`);
  symbolSel.onchange = () => renderVault(applyFilters());
  tfSel.onchange = () => renderVault(applyFilters());
}}

const pendingSignals = signals.filter(s => s.taken === null || s.outcome === null);
renderSignals(pendingSignals);
renderVault(vault);
setupFilters();
</script>

</body>
</html>
"""
    return html


def build_and_open():
    html = generate_dashboard()
    with open(OUTPUT_PATH, "w") as f:
        f.write(html)
    webbrowser.open(f"file://{os.path.abspath(OUTPUT_PATH)}")
    return OUTPUT_PATH
