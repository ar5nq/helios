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

from .genome import genome_label, genome_mechanism
from .portfolio import analyze_portfolio
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
    for s in signals:
        s["_lot"] = _lot_size_for(s)
        s["_label"] = labels.get(s["genome_id"], s["genome_id"])

    vault_json = json.dumps(vault)
    signals_json = json.dumps(signals)
    labels_json = json.dumps(labels)
    mechanisms_json = json.dumps(mechanisms)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Helios // Strategy Vault</title>
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
  let rows = pending.map(s => {{
    const dirClass = s.direction === 'BUY' ? 'buy' : 'sell';
    const rr = calcRR(s.entry, s.stop, s.target);
    const lot = s._lot ? s._lot.lots : '--';
    const takenYesActive = s.taken === true ? 'active-yes' : '';
    const takenNoActive = s.taken === false ? 'active-no' : '';
    const winActive = s.outcome === 'WIN' ? 'active' : '';
    const lossActive = s.outcome === 'LOSS' ? 'active' : '';
    const beActive = s.outcome === 'BREAKEVEN' ? 'active' : '';
    return `<tr>
      <td class="dim">${{s.id}}</td>
      <td class="${{dirClass}}">${{s.direction}}</td>
      <td>${{s.symbol}} <span class="dim">${{s.timeframe}}</span></td>
      <td class="dim">${{s._label}}</td>
      <td>${{s.entry}} / ${{s.stop}} / ${{s.target}}</td>
      <td>1:${{rr}}</td>
      <td>${{lot}}</td>
      <td>
        <div class="btn-group">
          <button class="btn ${{takenYesActive}}" onclick="respond('${{s.id}}', true, ${{s.outcome ? `'${{s.outcome}}'` : 'null'}})">Taken</button>
          <button class="btn ${{takenNoActive}}" onclick="respond('${{s.id}}', false, ${{s.outcome ? `'${{s.outcome}}'` : 'null'}})">Skip</button>
        </div>
        <div class="btn-group">
          <button class="btn win ${{winActive}}" onclick="respond('${{s.id}}', ${{s.taken}}, 'WIN')">Win</button>
          <button class="btn loss ${{lossActive}}" onclick="respond('${{s.id}}', ${{s.taken}}, 'LOSS')">Loss</button>
          <button class="btn be ${{beActive}}" onclick="respond('${{s.id}}', ${{s.taken}}, 'BREAKEVEN')">BE</button>
        </div>
      </td>
    </tr>`;
  }}).join('');
  el.innerHTML = `<table><tr>
    <th>ID</th><th>Dir</th><th>Symbol</th><th>Strategy</th><th>Entry/Stop/Target</th>
    <th>RR</th><th>Lots</th><th>Respond</th>
  </tr>${{rows}}</table>`;
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
    </tr>`;
  }}).join('');
  el.innerHTML = `<table><tr>
    <th></th><th>ID</th><th>Symbol</th><th>Strategy</th><th>Fitness</th>
    <th>Test Ret</th><th>Test DD</th><th>Win Rate</th><th>Trades</th>
  </tr>${{rows}}</table>`;
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

function drawEquityCurve(canvas, trainCurve, testCurve) {{
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  const all = trainCurve.concat(testCurve);
  if (!all.length) return;
  const min = Math.min(...all), max = Math.max(...all);
  const range = (max - min) || 1;
  const totalPoints = all.length;
  const stepX = w / Math.max(1, totalPoints - 1);
  const toY = (v) => h - ((v - min) / range) * (h - 10) - 5;

  function drawSeries(curve, offset, color) {{
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    curve.forEach((v, i) => {{
      const x = (offset + i) * stepX;
      const y = toY(v);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }});
    ctx.stroke();
  }}

  drawSeries(trainCurve, 0, '#8a8785');
  drawSeries(testCurve, trainCurve.length - 1, '#e8384f');

  // split marker
  const splitX = (trainCurve.length - 1) * stepX;
  ctx.beginPath();
  ctx.strokeStyle = '#2a1418';
  ctx.setLineDash([3, 3]);
  ctx.moveTo(splitX, 0);
  ctx.lineTo(splitX, h);
  ctx.stroke();
  ctx.setLineDash([]);
}}

function openInspector(genomeId) {{
  const g = vault.find(v => v.id === genomeId);
  if (!g) return;
  const score = g.score || {{}};
  const train = score.train || {{}};
  const test = score.test || {{}};

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
