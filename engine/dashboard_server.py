"""
Interactive local dashboard: real Taken/Win/Loss/Breakeven buttons that
actually write back to data/signal_log.json, instead of a static read-only
page. Also shows lot size inline per signal using your saved account
settings (see engine/risk.py: save_account/load_account).

Run with: python run.py dashboard
Opens http://127.0.0.1:5057 in your browser and keeps running until Ctrl+C.
"""
import json
import os
import threading
import webbrowser

from flask import Flask, jsonify, request

from .genome import genome_label, genome_mechanism, explain_genome, explain_genome_cards
from .portfolio import analyze_portfolio
from .active_strategies import get_active, activate, deactivate
from .risk import calculate_lot_size, load_account
from signals.signal_engine import list_signals, mark_taken, report_outcome

VAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "vault.json")
PORT = 5057

app = Flask(__name__)


def _load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _lot_size_for(signal: dict):
    account = load_account()
    if account.get("account_size") is None or account.get("default_risk_percent") is None:
        return None
    point_value = account.get("point_values", {}).get(signal["symbol"], 1.0)
    try:
        return calculate_lot_size(
            account["account_size"], account["default_risk_percent"],
            signal["entry"], signal["stop"], point_value,
        )
    except Exception:
        return None


@app.route("/")
def index():
    vault = _load_json(VAULT_PATH, [])
    signals = list_signals(pending_only=False)
    pending = [s for s in signals if s["taken"] is None or s["outcome"] is None]
    closed = [s for s in signals if s["outcome"] is not None]
    wins = sum(1 for s in closed if s["outcome"] == "WIN")
    live_win_rate = round(100 * wins / len(closed), 1) if closed else None

    labels = {g["id"]: genome_label(g) for g in vault}
    mechanisms = {g["id"]: genome_mechanism(g) for g in vault}
    explanations = {g["id"]: explain_genome_cards(g) for g in vault}
    explain_cards = {g["id"]: explain_genome_cards(g) for g in vault}
    active_ids = get_active()
    for s in signals:
        s["_lot"] = _lot_size_for(s)
        s["_label"] = labels.get(s["genome_id"], s["genome_id"])

    vault_json = json.dumps(vault)
    signals_json = json.dumps(signals)
    labels_json = json.dumps(labels)
    mechanisms_json = json.dumps(mechanisms)
    active_json = json.dumps(active_ids)
    explanations_json = json.dumps(explanations)
    explain_cards_json = json.dumps(explain_cards)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Helios // Strategy Vault</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0a0a0c; --panel: #111114; --border: #2a1418;
    --red: #e8384f; --green: #3ecf8e; --amber: #d4a03e;
    --text: #e4e2e0; --text-dim: #8a8785;
    --mono: 'SF Mono', 'JetBrains Mono', ui-monospace, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--mono); margin: 0; padding: 24px; font-size: 13px; }}
  h1 {{ font-size: 22px; letter-spacing: 2px; margin: 0 0 4px 0; }}
  h1 span {{ color: var(--red); }}
  .subtitle {{ color: var(--text-dim); font-size: 12px; margin-bottom: 24px; letter-spacing: 1px; text-transform: uppercase; }}
  .stats-row {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
  .stat-box {{ background: var(--panel); border: 1px solid var(--border); padding: 14px 20px; min-width: 140px; }}
  .stat-box .label {{ color: var(--text-dim); font-size: 10px; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 6px; }}
  .stat-box .value {{ font-size: 24px; font-weight: 600; }}
  .stat-box .value.red {{ color: var(--red); }}
  .stat-box .value.green {{ color: var(--green); }}
  .panel {{ background: var(--panel); border: 1px solid var(--border); margin-bottom: 20px; }}
  .panel-header {{ padding: 12px 16px; border-bottom: 1px solid var(--border); color: var(--red); font-size: 11px; letter-spacing: 2px; text-transform: uppercase; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; padding: 8px 12px; color: var(--text-dim); font-size: 10px; letter-spacing: 1px; text-transform: uppercase; border-bottom: 1px solid var(--border); }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #1a1a1d; font-size: 12px; vertical-align: middle; }}
  tr:hover td {{ background: #16161a; }}
  .buy {{ color: var(--green); }} .sell {{ color: var(--red); }}
  .fitness {{ color: var(--red); font-weight: 600; }}
  .dim {{ color: var(--text-dim); }}
  .empty {{ padding: 24px; text-align: center; color: var(--text-dim); }}
  .btn {{
    background: var(--bg); color: var(--text); border: 1px solid var(--border);
    padding: 4px 10px; font-family: var(--mono); font-size: 11px; cursor: pointer;
    margin-right: 4px; border-radius: 3px;
  }}
  .btn:hover {{ border-color: var(--red); color: var(--red); }}
  .btn.active-yes {{ background: var(--green); color: #06231a; border-color: var(--green); }}
  .btn.active-no {{ background: var(--text-dim); color: #0a0a0c; border-color: var(--text-dim); }}
  .btn.win:hover {{ border-color: var(--green); color: var(--green); }}
  .btn.loss:hover {{ border-color: var(--red); color: var(--red); }}
  .btn.be:hover {{ border-color: var(--amber); color: var(--amber); }}
  .btn.win.active {{ background: var(--green); color: #06231a; border-color: var(--green); }}
  .btn.loss.active {{ background: var(--red); color: #2a0508; border-color: var(--red); }}
  .btn.be.active {{ background: var(--amber); color: #2a1c04; border-color: var(--amber); }}
  .btn-group {{ display: flex; gap: 2px; margin-bottom: 4px; }}
  tr.vault-row {{ cursor: pointer; }}
  #inspector {{ display: none; }}
  #inspector.open {{ display: block; }}
  .insp-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px; }}
  .insp-box {{ border: 1px solid var(--border); padding: 12px; }}
  .insp-label {{ color: var(--text-dim); font-size: 10px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}
  .insp-stat-row {{ display: flex; justify-content: space-between; padding: 3px 0; font-size: 12px; }}
  .insp-tag {{ display: inline-block; border: 1px solid var(--border); padding: 2px 8px; margin: 2px 4px 2px 0; font-size: 11px; color: var(--text-dim); }}
  .close-insp {{ float: right; cursor: pointer; color: var(--text-dim); }}
  .close-insp:hover {{ color: var(--red); }}
  .explain-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding: 0 16px 16px 16px; }}
  .explain-card {{ border: 1px solid var(--border); padding: 10px; }}
  .explain-card .card-num {{ color: var(--red); font-size: 10px; font-weight: 600; }}
  .explain-card .card-title {{ font-size: 13px; font-weight: 600; margin: 4px 0 6px 0; }}
  .explain-card .card-text {{ font-size: 11px; line-height: 1.5; color: var(--text-dim); }}
  .trade-diagram {{ position: relative; height: 90px; margin: 12px 0; }}
  .trade-bar {{ position: relative; height: 24px; border-radius: 3px; overflow: hidden; display: flex; }}
  .trade-bar .risk-zone {{ background: rgba(232,56,79,0.25); border-right: 2px solid var(--red); }}
  .trade-bar .reward-zone {{ background: rgba(62,207,142,0.25); border-left: 2px solid var(--green); }}
  .trade-label {{ position: absolute; font-size: 10px; white-space: nowrap; transform: translateX(-50%); }}
  .trade-label.stop {{ color: var(--red); }}
  .trade-label.entry {{ color: var(--text); }}
  .trade-label.target {{ color: var(--green); }}
  .trade-label .price {{ font-weight: 600; }}
  .explain-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; padding: 0 16px 16px 16px; }}
  .explain-card {{ background: var(--bg); border: 1px solid var(--border); padding: 12px; }}
  .explain-card .icon {{ font-size: 18px; }}
  .explain-card .title {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--red); margin: 6px 0 2px 0; }}
  .explain-card .tag {{ font-size: 10px; color: var(--text-dim); margin-bottom: 6px; }}
  .explain-card .body {{ font-size: 11px; line-height: 1.5; color: var(--text); }}
</style></head>
<body>

<h1>HELIOS <span>//</span> STRATEGY VAULT</h1>
<div class="subtitle">live local dashboard · click to respond, no CLI needed</div>

<div class="stats-row">
  <div class="stat-box"><div class="label">Strategies Vaulted</div><div class="value">{len(vault)}</div></div>
  <div class="stat-box"><div class="label">Pending Signals</div><div class="value red">{len(pending)}</div></div>
  <div class="stat-box"><div class="label">Closed Signals</div><div class="value">{len(closed)}</div></div>
  <div class="stat-box"><div class="label">Live Win Rate</div>
    <div class="value {'green' if live_win_rate and live_win_rate >= 50 else 'red'}">{live_win_rate if live_win_rate is not None else '--'}{'%' if live_win_rate is not None else ''}</div>
  </div>
</div>

<div class="panel">
  <div class="panel-header">Pending Signals</div>
  <div id="signals-table"></div>
</div>

<div class="panel" id="inspector">
  <div class="panel-header">
    <span id="insp-title">Inspector</span>
    <span class="close-insp" onclick="closeInspector()">close &times;</span>
  </div>
  <div id="insp-body"></div>
</div>

<div class="panel">
  <div class="panel-header">
    <span>Portfolio Builder <span class="dim" style="font-size:10px">check strategies below, then build</span></span>
    <button class="btn" style="margin:0" onclick="buildPortfolio()">Build Portfolio</button>
  </div>
  <div id="portfolio-result"></div>
</div>

<div class="panel">
  <div class="panel-header">Strategy Vault <span class="dim" style="font-size:10px">click a row for full backtest details, check to add to portfolio</span></div>
  <div id="vault-table"></div>
</div>

<script>
const vault = {vault_json};
let signals = {signals_json};
const labels = {labels_json};
const mechanisms = {mechanisms_json};
let activeIds = {active_json};
const explanations = {explanations_json};

function calcRR(entry, stop, target) {{
  const risk = Math.abs(entry - stop);
  const reward = Math.abs(target - entry);
  return risk ? (reward / risk).toFixed(2) : '0.00';
}}

async function respond(signalId, taken, outcome) {{
  await fetch('/api/respond', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{signal_id: signalId, taken: taken, outcome: outcome}})
  }});
  location.reload();
}}

function renderSignals() {{
  const el = document.getElementById('signals-table');
  const pending = signals.filter(s => s.taken === null || s.outcome === null);
  if (!pending.length) {{
    el.innerHTML = '<div class="empty">No pending signals right now.</div>';
    return;
  }}
  let cards = pending.map(s => {{
    const dirClass = s.direction === 'BUY' ? 'buy' : 'sell';
    const rr = calcRR(s.entry, s.stop, s.target);
    const lot = s._lot ? s._lot.lots : '--';
    const takenYesActive = s.taken === true ? 'active-yes' : '';
    const takenNoActive = s.taken === false ? 'active-no' : '';
    const winActive = s.outcome === 'WIN' ? 'active' : '';
    const lossActive = s.outcome === 'LOSS' ? 'active' : '';
    const beActive = s.outcome === 'BREAKEVEN' ? 'active' : '';
    return `<div class="insp-box" style="margin-bottom:12px">
      <div style="display:flex; justify-content:space-between; align-items:center">
        <div>
          <span class="${{dirClass}}" style="font-weight:600">${{s.direction}}</span>
          <span> ${{s.symbol}} <span class="dim">${{s.timeframe}}</span> -- ${{s._label}}</span>
          <span class="dim"> -- RR 1:${{rr}} -- ${{lot}} lots</span>
        </div>
        <div class="dim" style="font-size:10px">${{s.id}}</div>
      </div>
      ${{tradeSetupDiagram(s.direction, s.entry, s.stop, s.target)}}
      <div class="btn-group">
        <button class="btn ${{takenYesActive}}" onclick="respond('${{s.id}}', true, ${{s.outcome ? `'${{s.outcome}}'` : 'null'}})">Taken</button>
        <button class="btn ${{takenNoActive}}" onclick="respond('${{s.id}}', false, ${{s.outcome ? `'${{s.outcome}}'` : 'null'}})">Skip</button>
        <button class="btn win ${{winActive}}" onclick="respond('${{s.id}}', ${{s.taken}}, 'WIN')">Win</button>
        <button class="btn loss ${{lossActive}}" onclick="respond('${{s.id}}', ${{s.taken}}, 'LOSS')">Loss</button>
        <button class="btn be ${{beActive}}" onclick="respond('${{s.id}}', ${{s.taken}}, 'BREAKEVEN')">BE</button>
      </div>
    </div>`;
  }}).join('');
  el.innerHTML = cards;
}}

function renderVault() {{
  const el = document.getElementById('vault-table');
  if (!vault.length) {{
    el.innerHTML = '<div class="empty">No strategies vaulted yet.</div>';
    return;
  }}
  let rows = vault.map(g => {{
    const score = g.score || {{}};
    const test = score.test || {{}};
    const isLive = activeIds.includes(g.id);
    return `<tr class="vault-row" onclick="openInspector('${{g.id}}')">
      <td onclick="event.stopPropagation()"><input type="checkbox" class="portfolio-check" value="${{g.id}}"></td>
      <td class="dim">${{g.id}}</td>
      <td>${{g.symbol}} <span class="dim">${{g.timeframe}}</span></td>
      <td>${{labels[g.id] || g.signal_indicator}}</td>
      <td class="fitness">${{score.fitness ?? '--'}}</td>
      <td>${{test.return_pct ?? '--'}}%</td>
      <td>${{test.max_dd_pct ?? '--'}}%</td>
      <td>${{test.win_rate ?? '--'}}%</td>
      <td class="dim">${{test.trades ?? '--'}}</td>
      <td onclick="event.stopPropagation()">
        <button class="btn ${{isLive ? 'active-yes' : ''}}" onclick="toggleActive('${{g.id}}')">${{isLive ? 'LIVE' : 'off'}}</button>
      </td>
    </tr>`;
  }}).join('');
  el.innerHTML = `<table><tr>
    <th></th><th>ID</th><th>Symbol</th><th>Strategy</th><th>Fitness</th>
    <th>Test Ret</th><th>Test DD</th><th>Win Rate</th><th>Trades</th><th>Live?</th>
  </tr>${{rows}}</table>`;
}}

async function toggleActive(genomeId) {{
  const endpoint = activeIds.includes(genomeId) ? '/api/deactivate' : '/api/activate';
  const resp = await fetch(endpoint, {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{genome_id: genomeId}})
  }});
  const r = await resp.json();
  activeIds = r.active;
  renderVault();
}}

async function buildPortfolio() {{
  const ids = [...document.querySelectorAll('.portfolio-check:checked')].map(c => c.value);
  const el = document.getElementById('portfolio-result');
  if (ids.length < 2) {{
    el.innerHTML = '<div class="empty">Check at least 2 strategies first.</div>';
    return;
  }}
  const resp = await fetch('/api/portfolio', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{genome_ids: ids}})
  }});
  const r = await resp.json();
  const gradeColor = ['A','B'].includes(r.overall_grade) ? 'green' : ['C'].includes(r.overall_grade) ? '' : 'red';
  el.innerHTML = `
    <div class="insp-grid">
      <div class="insp-box">
        <div class="insp-label">Overall Diversity Grade</div>
        <div class="value ${{gradeColor}}" style="font-size:32px">${{r.overall_grade}}</div>
        <div class="dim">${{r.members}} strategies, score ${{r.overall_score}}/100</div>
      </div>
      <div class="insp-box">
        <div class="insp-label">Concentration (lower = more spread out)</div>
        <div class="insp-stat-row"><span class="dim">Symbol</span><span>${{r.symbol_concentration_pct}}%</span></div>
        <div class="insp-stat-row"><span class="dim">Timeframe</span><span>${{r.timeframe_concentration_pct}}%</span></div>
        <div class="insp-stat-row"><span class="dim">Indicator</span><span>${{r.indicator_concentration_pct}}%</span></div>
        <div class="insp-stat-row"><span class="dim">Avg pairwise correlation</span><span>${{r.avg_pairwise_correlation ?? '--'}}</span></div>
      </div>
      <div class="insp-box">
        <div class="insp-label">Combined</div>
        <div class="insp-stat-row"><span class="dim">Avg test return</span><span>${{r.combined_avg_test_return_pct}}%</span></div>
        <div class="insp-stat-row"><span class="dim">Worst test drawdown</span><span>${{r.combined_worst_test_dd_pct}}%</span></div>
      </div>
    </div>
  `;
}}

function closeInspector() {{
  document.getElementById('inspector').classList.remove('open');
}}

function tradeSetupDiagram(direction, entry, stop, target) {{
  // For BUY: stop is below entry, target is above (risk zone on the left, reward on the right).
  // For SELL: mirrored (reward on the left, risk on the right).
  const isBuy = direction === 'BUY';
  const low = isBuy ? stop : target;
  const high = isBuy ? target : stop;
  const range = high - low || 1;
  const entryPct = Math.max(0, Math.min(100, ((entry - low) / range) * 100));

  const riskWidth = isBuy ? entryPct : (100 - entryPct);
  const rewardWidth = 100 - riskWidth;
  const riskZone = `<div class="risk-zone" style="width:${{riskWidth}}%"></div>`;
  const rewardZone = `<div class="reward-zone" style="width:${{rewardWidth}}%"></div>`;
  const zones = isBuy ? riskZone + rewardZone : rewardZone + riskZone;

  return `
    <div class="trade-diagram">
      <div class="trade-bar">${{zones}}</div>
      <div class="trade-label stop" style="left:${{isBuy ? 0 : 100}}%; top:28px">STOP<br><span class="price">${{stop}}</span></div>
      <div class="trade-label entry" style="left:${{entryPct}}%; top:28px">ENTRY<br><span class="price">${{entry}}</span></div>
      <div class="trade-label target" style="left:${{isBuy ? 100 : 0}}%; top:28px">TARGET<br><span class="price">${{target}}</span></div>
    </div>
  `;
}}

let equityChart = null;

function drawEquityCurve(canvas, trainCurve, testCurve) {{
  if (equityChart) {{
    equityChart.destroy();
  }}
  const combined = trainCurve.concat(testCurve.slice(1));  // avoid duplicating the split point
  const labels = combined.map((_, i) => i);
  const trainData = trainCurve.map(v => v);
  const testData = new Array(trainCurve.length - 1).fill(null).concat(testCurve);

  equityChart = new Chart(canvas, {{
    type: 'line',
    data: {{
      labels: labels,
      datasets: [
        {{
          label: 'Train (in-sample)',
          data: trainData,
          borderColor: '#8a8785',
          backgroundColor: 'rgba(138,135,133,0.08)',
          borderWidth: 1.5,
          pointRadius: 0,
          fill: true,
          tension: 0.15,
        }},
        {{
          label: 'Test (out-of-sample)',
          data: testData,
          borderColor: '#e8384f',
          backgroundColor: 'rgba(232,56,79,0.10)',
          borderWidth: 1.5,
          pointRadius: 0,
          fill: true,
          tension: 0.15,
        }},
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{
          labels: {{ color: '#8a8785', font: {{ family: 'monospace', size: 10 }}, boxWidth: 12 }}
        }},
        tooltip: {{
          backgroundColor: '#111114',
          titleColor: '#8a8785',
          bodyColor: '#e4e2e0',
          borderColor: '#2a1418',
          borderWidth: 1,
          callbacks: {{
            label: (ctx) => `${{ctx.dataset.label}}: ${{((ctx.raw - 1) * 100).toFixed(2)}}%`
          }}
        }}
      }},
      scales: {{
        x: {{
          grid: {{ color: '#1a1a1d' }},
          ticks: {{ color: '#8a8785', font: {{ family: 'monospace', size: 9 }}, maxTicksLimit: 8 }}
        }},
        y: {{
          grid: {{ color: '#1a1a1d' }},
          ticks: {{
            color: '#8a8785', font: {{ family: 'monospace', size: 9 }},
            callback: (v) => ((v - 1) * 100).toFixed(1) + '%'
          }}
        }}
      }}
    }}
  }});
}}


function openInspector(genomeId) {{
  const g = vault.find(v => v.id === genomeId);
  if (!g) return;
  const score = g.score || {{}};
  const train = score.train || {{}};
  const test = score.test || {{}};
  const ex = explanations[g.id] || {{
    entry: {{title:'--', text:'No explanation available.'}},
    bias: {{title:'--', text:''}},
    filter: {{title:'--', text:''}},
    management: {{title:'--', text:''}}
  }};

  document.getElementById('insp-title').textContent =
    `Inspector // ${{g.symbol}} ${{g.timeframe}} // ${{g.id}}`;

  document.getElementById('insp-body').innerHTML = `
    <div class="insp-grid">
      <div class="insp-box">
        <div class="insp-label">Passport</div>
        <div class="insp-tag">${{labels[g.id] || g.signal_indicator}}</div>
        <div class="insp-tag">${{mechanisms[g.id] || g.exec_mode}}</div>
        <div class="insp-tag">Bias: ${{g.bias}}</div>
        <div class="insp-tag">Filter: ${{g.filter}}</div>
        <div class="insp-tag">RR 1:${{g.rr}}</div>
        <div style="margin-top:12px" class="insp-label">Fitness</div>
        <div class="fitness" style="font-size:20px">${{score.fitness ?? '--'}}</div>
      </div>
      <div class="insp-box">
        <div class="insp-label">Backtest -- Train (in-sample) vs Test (out-of-sample)</div>
        <div class="insp-stat-row"><span class="dim">Return</span><span>${{train.return_pct ?? '--'}}% <span class="dim">/</span> ${{test.return_pct ?? '--'}}%</span></div>
        <div class="insp-stat-row"><span class="dim">Max Drawdown</span><span>${{train.max_dd_pct ?? '--'}}% <span class="dim">/</span> ${{test.max_dd_pct ?? '--'}}%</span></div>
        <div class="insp-stat-row"><span class="dim">Win Rate</span><span>${{train.win_rate ?? '--'}}% <span class="dim">/</span> ${{test.win_rate ?? '--'}}%</span></div>
        <div class="insp-stat-row"><span class="dim">Trades</span><span>${{train.trades ?? '--'}} <span class="dim">/</span> ${{test.trades ?? '--'}}</span></div>
      </div>
    </div>
    <div class="explain-grid">
      <div class="explain-card">
        <div class="card-num">1. ENTRY TRIGGER</div>
        <div class="card-title">${{ex.entry.title}}</div>
        <div class="card-text">${{ex.entry.text}}</div>
      </div>
      <div class="explain-card">
        <div class="card-num">2. TREND BIAS</div>
        <div class="card-title">${{ex.bias.title}}</div>
        <div class="card-text">${{ex.bias.text}}</div>
      </div>
      <div class="explain-card">
        <div class="card-num">3. FILTER</div>
        <div class="card-title">${{ex.filter.title}}</div>
        <div class="card-text">${{ex.filter.text}}</div>
      </div>
      <div class="explain-card">
        <div class="card-num">4. TRADE MANAGEMENT</div>
        <div class="card-title">${{ex.management.title}}</div>
        <div class="card-text">${{ex.management.text}}</div>
      </div>
    </div>
    <div class="insp-box" style="margin:0 16px 16px 16px">
      <div class="insp-label">Equity Curve <span class="dim">(gray = train/in-sample, red = test/out-of-sample -- the honest part)</span></div>
      <canvas id="equity-canvas" width="900" height="180" style="width:100%; height:180px;"></canvas>
    </div>
  `;

  document.getElementById('inspector').classList.add('open');
  const canvas = document.getElementById('equity-canvas');
  drawEquityCurve(canvas, train.equity_curve || [], test.equity_curve || []);
  document.getElementById('inspector').scrollIntoView({{behavior: 'smooth', block: 'start'}});
}}

renderSignals();
renderVault();
</script>
</body></html>"""


@app.route("/api/activate", methods=["POST"])
def api_activate():
    genome_id = request.get_json()["genome_id"]
    result = activate(genome_id)
    return jsonify({"active": result})


@app.route("/api/deactivate", methods=["POST"])
def api_deactivate():
    genome_id = request.get_json()["genome_id"]
    result = deactivate(genome_id)
    return jsonify({"active": result})


@app.route("/api/portfolio", methods=["POST"])
def api_portfolio():
    body = request.get_json()
    genome_ids = set(body.get("genome_ids", []))
    vault = _load_json(VAULT_PATH, [])
    selected = [g for g in vault if g["id"] in genome_ids]
    result = analyze_portfolio(selected)
    return jsonify(result)


@app.route("/api/respond", methods=["POST"])
def api_respond():
    body = request.get_json()
    signal_id = body["signal_id"]
    taken = body.get("taken")
    outcome = body.get("outcome")
    if taken is not None:
        mark_taken(signal_id, bool(taken))
    if outcome:
        report_outcome(signal_id, outcome)
    return jsonify({"ok": True})


def build_and_open():
    url = f"http://127.0.0.1:{PORT}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Dashboard running at {url} -- Ctrl+C to stop.")
    app.run(port=PORT, debug=False)
