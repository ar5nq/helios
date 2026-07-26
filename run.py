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
            print(f"[{s['id']}] {s['direction']} {s['symbol']} ({s['timeframe']}) "
                  f"entry={s['entry']} stop={s['stop']} target={s['target']} "
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


if __name__ == "__main__":
    main()
