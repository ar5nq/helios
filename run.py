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
from signals.signal_engine import emit_signal, genome_live_stats
from news.calendar_feed import fetch_week, high_impact_today, format_alert


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

    sub.add_parser("news")

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
        alerts = high_impact_today(events)
        if not alerts:
            print("No high-impact events today.")
        for e in alerts:
            print(format_alert(e))


if __name__ == "__main__":
    main()
