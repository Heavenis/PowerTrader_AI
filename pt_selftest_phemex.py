"""
Self-test for Phemex CCXT market data.

Run:
  PT_DEBUG=1 python pt_selftest_phemex.py
"""

import sys

from broker_ccxt_phemex import CCXTPhemexBroker
import pt_hub  # noqa: F401
import pt_thinker  # noqa: F401
import pt_trader  # noqa: F401
import pt_trainer  # noqa: F401


def main() -> int:
    broker = CCXTPhemexBroker()
    diag = broker.diagnose_marketdata(symbol="BTC/USDT", timeframe="1h", limit=10)
    print(f"diagnose_marketdata: {diag}")

    timeframes = [
        "1min",
        "5min",
        "15min",
        "30min",
        "1hour",
        "2hour",
        "4hour",
        "8hour",
        "12hour",
        "1day",
        "1week",
    ]

    failures = []
    for tf in timeframes:
        candles = broker.get_ohlcv("BTC", tf, limit=20, quote="USDT")
        count = len(candles)
        first_ts = candles[0]["ts"] if candles else None
        last_ts = candles[-1]["ts"] if candles else None
        print(f"timeframe={tf} candles={count} first_ts={first_ts} last_ts={last_ts}")
        if count == 0:
            failures.append(tf)

    if failures:
        print(f"Self-test failed: no candles for timeframes: {', '.join(failures)}")
        return 2

    print("Self-test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
