"""
Self-test for Phemex CCXT market data.

Run:
  PT_DEBUG=1 python pt_selftest_phemex.py
"""

import sys
import time

from broker_ccxt_phemex import CCXTPhemexBroker, map_timeframe
import pt_hub  # noqa: F401
import pt_thinker  # noqa: F401
import pt_trader  # noqa: F401
import pt_trainer  # noqa: F401


def main() -> int:
    broker = CCXTPhemexBroker()
    diag = broker.diagnose_marketdata(symbol="BTC/USDT", timeframe="1h", limit=10)
    print(f"diagnose_marketdata: {diag}")

    timeframes = ["15min", "1hour"]

    failures = []
    for cycle in range(3):
        for tf in timeframes:
            candles = broker.get_ohlcv("BTC", tf, limit=20, quote="USDT")
            count = len(candles)
            first_ts = candles[0]["ts"] if candles else None
            last_ts = candles[-1]["ts"] if candles else None
            mapped = map_timeframe(tf)
            print(
                f"cycle={cycle+1} symbol=BTC mapped_tf={mapped} limit=20 "
                f"count={count} first_ts={first_ts} last_ts={last_ts}"
            )
            if count == 0:
                failures.append(f"{tf}@cycle{cycle+1}")
        time.sleep(0.5)

    if failures:
        print(f"Self-test failed: no candles for timeframes: {', '.join(failures)}")
        return 2

    print("Self-test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
