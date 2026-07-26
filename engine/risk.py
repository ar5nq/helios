"""
Position sizing: given your account size, how much you're willing to risk per
trade, and the signal's stop distance, works out how big a position to take.

Lot/contract conventions vary a LOT by broker and instrument, so this is
deliberately generic: you tell it how much one point of price movement is
worth per 1.0 lot for your specific broker/symbol (point_value), and it does
the rest. If you don't know your broker's point value, check your platform's
contract specifications -- it's usually listed per symbol.

Common point values people use as a starting reference (VERIFY WITH YOUR OWN
BROKER -- these vary):
  NAS100 CFD: often $1-$20 per point per 1.0 lot depending on broker
  XAUUSD: often $1-$100 per point per 1.0 lot depending on broker
  Standard forex pairs: often ~$10 per pip per 1.0 lot (standard lot)
"""


def calculate_lot_size(account_size: float, risk_percent: float,
                        entry: float, stop: float, point_value: float = 1.0) -> dict:
    """
    account_size: total account balance, e.g. 5000
    risk_percent: how much of the account you're willing to risk on this ONE
        trade, e.g. 1.0 for 1%
    entry, stop: from the signal
    point_value: $ value of 1.0 price unit movement per 1.0 lot, for YOUR
        broker/symbol -- this is the number you must get right, it's not
        something this tool can know for you
    """
    if risk_percent <= 0 or risk_percent > 100:
        raise ValueError("risk_percent must be between 0 and 100")

    risk_amount = account_size * (risk_percent / 100)
    stop_distance = abs(entry - stop)
    if stop_distance == 0:
        raise ValueError("entry and stop can't be identical")

    # risk_amount = lots * stop_distance * point_value  -->  solve for lots
    lots = risk_amount / (stop_distance * point_value)

    return {
        "account_size": account_size,
        "risk_percent": risk_percent,
        "risk_amount": round(risk_amount, 2),
        "stop_distance": round(stop_distance, 5),
        "point_value_used": point_value,
        "lots": round(lots, 2),
        "warning": ("Verify point_value against your actual broker's contract "
                    "specs before using this number -- it's the one input this "
                    "tool can't verify for you."),
    }
