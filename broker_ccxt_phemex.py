import logging
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import ccxt
except Exception:  # pragma: no cover - fallback for missing dependency
    ccxt = None

LOGGER = logging.getLogger(__name__)


TIMEFRAME_MAP = {
    "1m": "1m",
    "m1": "1m",
    "1min": "1m",
    "5m": "5m",
    "m5": "5m",
    "5min": "5m",
    "15m": "15m",
    "m15": "15m",
    "15min": "15m",
    "30m": "30m",
    "m30": "30m",
    "30min": "30m",
    "1h": "1h",
    "h1": "1h",
    "1hour": "1h",
    "2h": "2h",
    "h2": "2h",
    "2hour": "2h",
    "4h": "4h",
    "h4": "4h",
    "4hour": "4h",
    "8h": "8h",
    "h8": "8h",
    "8hour": "8h",
    "12h": "12h",
    "h12": "12h",
    "12hour": "12h",
    "1d": "1d",
    "d1": "1d",
    "1day": "1d",
    "1w": "1w",
    "w1": "1w",
    "1week": "1w",
}


def normalize_symbol(symbol: str, quote: str = "USDT") -> str:
    sym = (symbol or "").strip().upper()
    quote = (quote or "USDT").strip().upper()
    if not sym:
        return f"UNKNOWN/{quote}"
    if "/" in sym:
        return sym
    if "-" in sym:
        base = sym.split("-")[0].strip()
        return f"{base}/{quote}"
    return f"{sym}/{quote}"


def map_timeframe(timeframe: str) -> str:
    tf = (timeframe or "").strip().lower()
    if tf in TIMEFRAME_MAP:
        mapped = TIMEFRAME_MAP[tf]
        if mapped in ("8h", "12h"):
            LOGGER.warning("Timeframe '%s' not supported; falling back to 4h.", timeframe)
            return "4h"
        return mapped
    LOGGER.warning("Unknown timeframe '%s'; defaulting to 1m.", timeframe)
    return "1m"


class CCXTPhemexBroker:
    def __init__(
        self,
        api_key: str = "",
        secret: str = "",
        enable_rate_limit: bool = True,
        options: Optional[Dict[str, Any]] = None,
        load_markets: bool = True,
    ) -> None:
        if ccxt is None:
            raise RuntimeError("ccxt is not installed. Run: pip install -r requirements.txt")
        cfg: Dict[str, Any] = {
            "enableRateLimit": bool(enable_rate_limit),
        }
        if api_key and secret:
            cfg.update({"apiKey": api_key, "secret": secret})
        if options:
            cfg["options"] = options
        self.exchange = ccxt.phemex(cfg)
        self._markets_loaded = False
        if load_markets:
            self._ensure_markets()
        self._last_good_bid_ask: Dict[str, Dict[str, float]] = {}
        self._log_state: Dict[str, float] = {}

    def _ensure_markets(self) -> None:
        if self._markets_loaded:
            return
        try:
            self.exchange.load_markets()
            self._markets_loaded = True
        except Exception:
            pass

    def _log_rate_limited(self, key: str, msg: str, level: int = logging.WARNING, every_seconds: int = 300) -> None:
        now = time.time()
        last = self._log_state.get(key, 0.0)
        if now - last < every_seconds:
            return
        self._log_state[key] = now
        try:
            LOGGER.log(level, msg)
        except Exception:
            pass

    def get_best_bid_ask(self, coin_or_symbol: str, quote: str = "USDT") -> Tuple[Optional[float], Optional[float]]:
        symbol = normalize_symbol(coin_or_symbol, quote=quote)
        self._ensure_markets()
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            if ticker:
                bid = ticker.get("bid")
                ask = ticker.get("ask")
                if bid is not None and ask is not None:
                    bid_f = float(bid)
                    ask_f = float(ask)
                    if bid_f > 0 and ask_f > 0:
                        self._last_good_bid_ask[symbol] = {"bid": bid_f, "ask": ask_f, "ts": time.time()}
                        return bid_f, ask_f
        except Exception:
            pass

        cached = self._last_good_bid_ask.get(symbol)
        if cached:
            return float(cached.get("bid", 0.0) or 0.0), float(cached.get("ask", 0.0) or 0.0)

        last = self.get_last_price(symbol, quote=quote)
        if last is not None:
            return float(last), float(last)
        self._log_rate_limited(f"bidask-empty:{symbol}", f"No bid/ask available for {symbol}.")
        return None, None

    def get_last_price(self, coin_or_symbol: str, quote: str = "USDT") -> Optional[float]:
        symbol = normalize_symbol(coin_or_symbol, quote=quote)
        self._ensure_markets()
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            if ticker:
                last = ticker.get("last")
                if last is not None:
                    return float(last)
        except Exception:
            pass
        return None

    def get_ohlcv(
        self,
        coin_or_symbol: str,
        timeframe: str,
        limit: int,
        quote: str = "USDT",
    ) -> List[dict]:
        symbol = normalize_symbol(coin_or_symbol, quote=quote)
        tf = map_timeframe(timeframe)
        self._ensure_markets()
        try:
            limit_int = int(limit)
        except Exception:
            limit_int = 0
        if limit_int <= 0:
            limit_int = 200
        try:
            rows = self.exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit_int)
        except Exception as exc:
            self._log_rate_limited(
                f"ohlcv-error:{symbol}:{tf}",
                f"Failed to fetch OHLCV for {symbol} ({tf}) limit={limit_int}: {exc}",
            )
            return []

        candles: List[dict] = []
        for row in rows or []:
            try:
                ts_ms, o, h, l, c, v = row
                candles.append(
                    {
                        "ts": int(int(ts_ms) / 1000),
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                        "volume": float(v),
                    }
                )
            except Exception:
                continue

        candles.sort(key=lambda x: x["ts"])
        if not candles:
            self._log_rate_limited(
                f"ohlcv-empty:{symbol}:{tf}",
                f"No OHLCV data returned for {symbol} ({tf}).",
            )
        return candles

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> dict:
        norm_symbol = normalize_symbol(symbol)
        self._ensure_markets()
        params = params or {}
        try:
            order = self.exchange.create_order(
                norm_symbol,
                order_type,
                side,
                amount,
                price,
                params,
            )
            return self._normalize_order(order)
        except Exception as exc:
            return {
                "id": None,
                "status": "error",
                "error": str(exc),
                "symbol": norm_symbol,
                "side": side,
                "type": order_type,
                "amount": amount,
                "price": price,
            }

    def cancel_order(self, order_id: str, symbol: str) -> Any:
        raise NotImplementedError("cancel_order is not implemented for this project.")

    def fetch_order(self, order_id: str, symbol: str) -> Any:
        raise NotImplementedError("fetch_order is not implemented for this project.")

    def diagnose_marketdata(self, symbol: str = "BTC/USDT", timeframe: str = "1h", limit: int = 10) -> dict:
        self._ensure_markets()
        info: Dict[str, Any] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "ticker_ok": False,
            "ohlcv_count": 0,
            "first_ts": None,
            "last_ts": None,
        }
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            info["ticker_ok"] = bool(ticker)
        except Exception:
            info["ticker_ok"] = False

        candles = self.get_ohlcv(symbol, timeframe, limit, quote="USDT")
        info["ohlcv_count"] = len(candles)
        if candles:
            info["first_ts"] = candles[0]["ts"]
            info["last_ts"] = candles[-1]["ts"]
        return info

    def _normalize_order(self, order: Optional[dict]) -> dict:
        order = order or {}
        return {
            "id": order.get("id"),
            "status": order.get("status"),
            "filled": order.get("filled"),
            "amount": order.get("amount"),
            "average": order.get("average"),
            "price": order.get("price"),
            "side": order.get("side"),
            "type": order.get("type"),
            "symbol": order.get("symbol"),
            "timestamp": order.get("timestamp"),
            "info": order.get("info"),
            "trades": order.get("trades") or [],
        }
