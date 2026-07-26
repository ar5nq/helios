"""
CLI entry point.

Examples:
  python run.py breed --symbol EURUSD --timeframe H1 --generations 5
  python run.py signal --genome B8CE8E --symbol EURUSD --timeframe H1 --direction BUY --entry 1.1050 --stop 1.1010 --target 1.1130
  python run.py news
"""
import argparse
import json
import os

from engine.campaign import run_campaign
from signals.signal_engine import emit_signal, genome_live_stats, list_signals, mark_taken, report_outcome
from news.calendar_feed import fetch_week, high_impact_today, upcoming_by_color, format_alert, SYMBOL_TO_CURRENCIES
from engine.risk import calculate_lot_size, save_account, load_account
from engine.dashboard_server import build_and_open
from engine.active_strategies import get_active, activate, deactivate
from engine.genome import explain_genome


def _calc_rr(entry: float, stop: float, target: float) -> float:
    risk = abs(entry - stop)
    reward = abs(target - entry)
    return round(reward / risk, 2) if risk else 0.0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    breed = sub.add_parser("breed")
    breed.add_argument("--symbol", required=True)
    breed.add_argument("--timeframe", required=True)
    breed.add_argument("--population", type=int, default=40)
    breed.add_argument("--generations", type=int, default=5)
    breed.add_argument("--min-test-trades", type=int, default=25,
                        help="minimum out-of-sample trades to promote a strategy. "
                             "Lower this for inherently low-frequency indicators like ORB "
                             "(once-per-day max) which can't naturally clear 25 on M5/M15.")

    signal = sub.add_parser("signal")
    signal.add_argument("--genome", required=True)
    signal.add_argument("--symbol", required=True)
    signal.add_argument("--timeframe", required=True)
    signal.add_argument("--direction", required=True, choices=["BUY", "SELL"])
    signal.add_argument("--entry", type=float, required=True)
    signal.add_argument("--stop", type=float, required=True)
    signal.add_argument("--target", type=float, required=True)

    news = sub.add_parser("news")
    news.add_argument("--today", action="store_true",
                       help="only show today's events (default: rest of this week)")
    news.add_argument("--color", choices=["red", "orange", "yellow"], default="red",
                       help="red=High only (default), orange=Medium+High, yellow=Low+Medium+High")
    news.add_argument("--symbol", help="only show news relevant to this symbol, e.g. NAS100")

    signals_cmd = sub.add_parser("signals", help="list pending signals waiting for your response")
    signals_cmd.add_argument("--all", action="store_true", help="show every signal, not just pending ones")

    respond = sub.add_parser("respond", help="record what happened to a signal")
    respond.add_argument("signal_id")
    respond.add_argument("--taken", choices=["yes", "no"],
                          help="did you actually take this trade?")
    respond.add_argument("--outcome", choices=["win", "loss", "be"],
                          help="how did it turn out -- win, loss, or breakeven (be)? "
                               "You can report this even if you skipped the trade (--taken no).")

    lotsize = sub.add_parser("lotsize", help="calculate position size from account risk")
    lotsize.add_argument("signal_id", nargs="?",
                          help="pull entry/stop straight from this signal instead of typing them")
    lotsize.add_argument("--account", type=float, help="account size (uses saved default if omitted)")
    lotsize.add_argument("--risk", type=float, help="%% of account to risk (uses saved default if omitted)")
    lotsize.add_argument("--entry", type=float, help="only needed if not giving a signal_id")
    lotsize.add_argument("--stop", type=float, help="only needed if not giving a signal_id")
    lotsize.add_argument("--point-value", type=float,
                          help="$ per 1.0 price-unit move per 1.0 lot (uses saved default for the symbol if omitted)")

    account = sub.add_parser("account", help="save your account size / default risk so lotsize doesn't need retyping")
    account.add_argument("--size", type=float, help="account size, e.g. 5000")
    account.add_argument("--risk", type=float, help="default %% risk per trade, e.g. 1.0")
    account.add_argument("--point-value", nargs=2, metavar=("SYMBOL", "VALUE"), action="append",
                          help="set point value for a symbol, e.g. --point-value NAS100 1.0 (repeatable)")

    sub.add_parser("dashboard", help="generate and open the local vault/signals dashboard")

    activate_cmd = sub.add_parser("activate", help="turn ON live signals for a strategy")
    activate_cmd.add_argument("genome_id")

    deactivate_cmd = sub.add_parser("deactivate", help="turn OFF live signals for a strategy")
    deactivate_cmd.add_argument("genome_id")

    sub.add_parser("active", help="list which strategies are currently live")

    explain_cmd = sub.add_parser("explain", help="plain-English breakdown of a strategy")
    explain_cmd.add_argument("genome_id")

    args = parser.parse_args()

    if args.cmd == "breed":
        result = run_campaign(args.symbol, args.timeframe, args.population, args.generations,
                               min_test_trades=args.min_test_trades)
        print(json.dumps(result, indent=2))

    elif args.cmd == "signal":
        s = emit_signal(args.genome, args.symbol, args.timeframe, args.direction,
                         args.entry, args.stop, args.target)
        print(json.dumps(s, indent=2))

    elif args.cmd == "news":
        events = fetch_week()
        currencies = None
        if args.symbol:
            currencies = SYMBOL_TO_CURRENCIES.get(args.symbol.upper())
            if currencies is None:
                print(f"Unknown symbol '{args.symbol}'. Known: {', '.join(SYMBOL_TO_CURRENCIES)}")
                return

        if args.today:
            alerts = high_impact_today(events, currencies=currencies)
            label = "today"
        else:
            alerts = upcoming_by_color(events, color=args.color, currencies=currencies)
            label = f"this week ({args.color} and above)"
        if args.symbol:
            label += f" for {args.symbol.upper()}"

        if not alerts:
            print(f"No matching events {label}.")
        for e in alerts:
            print(format_alert(e))

    elif args.cmd == "signals":
        sigs = list_signals(pending_only=not args.all)
        if not sigs:
            print("No pending signals." if not args.all else "No signals logged yet.")
        for s in sigs:
            taken_str = {True: "TAKEN", False: "SKIPPED", None: "?"}[s["taken"]]
            outcome_str = s["outcome"] or "?"
            rr = _calc_rr(s["entry"], s["stop"], s["target"])
            print(f"[{s['id']}] {s['direction']} {s['symbol']} ({s['timeframe']}) "
                  f"entry={s['entry']} stop={s['stop']} target={s['target']} RR=1:{rr} "
                  f"| genome={s['genome_id']} | taken={taken_str} outcome={outcome_str}")
            if s.get("note"):
                print(f"    note: {s['note']}")

    elif args.cmd == "respond":
        if not args.taken and not args.outcome:
            print("Give at least --taken yes/no or --outcome win/loss/be")
            return
        if args.taken:
            mark_taken(args.signal_id, args.taken == "yes")
        if args.outcome:
            outcome_map = {"win": "WIN", "loss": "LOSS", "be": "BREAKEVEN"}
            report_outcome(args.signal_id, outcome_map[args.outcome])
        print(f"Updated signal {args.signal_id}.")

    elif args.cmd == "lotsize":
        saved = load_account()

        entry, stop, symbol = args.entry, args.stop, None
        if args.signal_id:
            sigs = list_signals(pending_only=False)
            match = next((s for s in sigs if s["id"] == args.signal_id), None)
            if not match:
                print(f"No signal found with id {args.signal_id}")
                return
            entry, stop, symbol = match["entry"], match["stop"], match["symbol"]

        if entry is None or stop is None:
            print("Give a signal_id, or both --entry and --stop.")
            return

        account_size = args.account or saved.get("account_size")
        risk_percent = args.risk or saved.get("default_risk_percent")
        if account_size is None or risk_percent is None:
            print("No account settings saved yet. Run: python run.py account --size 5000 --risk 1")
            return

        point_value = args.point_value
        if point_value is None and symbol:
            point_value = saved.get("point_values", {}).get(symbol)
        point_value = point_value or 1.0

        result = calculate_lot_size(account_size, risk_percent, entry, stop, point_value)
        print(json.dumps(result, indent=2))

    elif args.cmd == "account":
        current = load_account()
        size = args.size if args.size is not None else current.get("account_size")
        risk = args.risk if args.risk is not None else current.get("default_risk_percent")
        point_values = dict(current.get("point_values", {}))
        if args.point_value:
            for sym, val in args.point_value:
                point_values[sym.upper()] = float(val)

        if size is None or risk is None:
            print("First time setup needs both: python run.py account --size 5000 --risk 1")
            return

        saved = save_account(size, risk, point_values)
        print(json.dumps(saved, indent=2))

    elif args.cmd == "dashboard":
        build_and_open()

    elif args.cmd == "activate":
        result = activate(args.genome_id)
        print(f"Activated. Currently live: {result}")

    elif args.cmd == "deactivate":
        result = deactivate(args.genome_id)
        print(f"Deactivated. Currently live: {result}")

    elif args.cmd == "active":
        result = get_active()
        if not result:
            print("No strategies activated -- the live runner will stay silent until you activate some.")
        else:
            print("Live strategies:", result)

    elif args.cmd == "explain":
        vault_path = os.path.join("data", "vault.json")
        if not os.path.exists(vault_path):
            print("No vault found yet -- breed some strategies first.")
            return
        with open(vault_path) as f:
            vault = json.load(f)
        match = next((g for g in vault if g["id"] == args.genome_id), None)
        if not match:
            print(f"No strategy found with id {args.genome_id}")
            return
        print(explain_genome(match))


if __name__ == "__main__":
    main()
