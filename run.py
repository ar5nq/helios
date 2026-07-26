"""
CLI entry point.

Examples:
  python run.py breed --symbol EURUSD --timeframe H1 --generations 5
  python run.py signal --genome B8CE8E --symbol EURUSD --timeframe H1 --direction BUY --entry 1.1050 --stop 1.1010 --target 1.1130
  python run.py news
"""
import argparse
import json

from engine.campaign import run_campaign
from signals.signal_engine import emit_signal, genome_live_stats, list_signals, mark_taken, report_outcome
from news.calendar_feed import fetch_week, high_impact_today, upcoming_by_color, format_alert, SYMBOL_TO_CURRENCIES
from engine.risk import calculate_lot_size
from engine.dashboard import build_and_open


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
    lotsize.add_argument("--account", type=float, required=True, help="account size, e.g. 5000")
    lotsize.add_argument("--risk", type=float, required=True, help="% of account to risk, e.g. 1.0")
    lotsize.add_argument("--entry", type=float, required=True)
    lotsize.add_argument("--stop", type=float, required=True)
    lotsize.add_argument("--point-value", type=float, default=1.0,
                          help="$ per 1.0 price-unit move per 1.0 lot for YOUR broker (check contract specs)")

    sub.add_parser("dashboard", help="generate and open the local vault/signals dashboard")

    args = parser.parse_args()

    if args.cmd == "breed":
        result = run_campaign(args.symbol, args.timeframe, args.population, args.generations)
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
        result = calculate_lot_size(args.account, args.risk, args.entry, args.stop, args.point_value)
        print(json.dumps(result, indent=2))

    elif args.cmd == "dashboard":
        path = build_and_open()
        print(f"Dashboard generated at {path} and opened in your browser.")


if __name__ == "__main__":
    main()
