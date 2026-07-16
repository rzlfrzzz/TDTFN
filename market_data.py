"""
Ambil data market BTC + global crypto dari CoinMarketCap Pro API.
"""

import time

import requests

from config import COINMARKETCAP_API_KEY

BASE_URL = "https://pro-api.coinmarketcap.com"

QUOTE_URL = f"{BASE_URL}/v1/cryptocurrency/quotes/latest"
GLOBAL_METRICS_URL = f"{BASE_URL}/v1/global-metrics/quotes/latest"
FEAR_GREED_URL = f"{BASE_URL}/v3/fear-and-greed/latest"
ALTCOIN_SEASON_URL = f"{BASE_URL}/v1/altcoin-season-index/latest"
LISTINGS_URL = f"{BASE_URL}/v1/cryptocurrency/listings/latest"

# Stablecoin diexclude dari top gainers/losers karena pergerakan harganya
# (biasanya < 1%) cuma noise, bukan sinyal market yang relevan.
STABLECOIN_SYMBOLS = {
    "USDT", "USDC", "DAI", "TUSD", "BUSD", "FDUSD", "USDE",
    "PYUSD", "USDP", "GUSD", "USDD", "FRAX", "USD1",
}

HEADERS = {
    "X-CMC_PRO_API_KEY": COINMARKETCAP_API_KEY,
    "Accept": "application/json",
}

REQUEST_TIMEOUT = 10


def _safe_float(value, default=0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)
MAX_RETRIES = 2  # total percobaan = 1 request awal + 2 retry
RETRY_BACKOFF_SECONDS = 1.5


def _get_json(url: str, params: dict | None = None, endpoint_label: str = "") -> dict | None:
    """
    Helper request ke CMC.
    Return payload JSON atau None kalau gagal.

    Auto-retry (dengan backoff singkat) khusus untuk error transient
    (429 rate limit, 5xx server error) supaya data tidak silently hilang
    gara-gara hiccup sesaat. Error permanen (401/403/parse error) langsung
    return None tanpa retry.
    """
    label = endpoint_label or url

    if not COINMARKETCAP_API_KEY:
        print(f"[market_data] COINMARKETCAP_API_KEY belum di-set ({label}).")
        return None

    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                params=params or {},
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == 401:
                print(f"[market_data] CMC API key tidak valid/expired (401) - {label}.")
                return None

            if resp.status_code == 403:
                print(f"[market_data] Akses endpoint CMC ditolak (403) - {label}. Cek plan API.")
                return None

            if resp.status_code in RETRYABLE_STATUS_CODES:
                last_error = f"HTTP {resp.status_code}"
                if attempt < MAX_RETRIES:
                    print(
                        f"[market_data] {last_error} di {label} (percobaan {attempt + 1}/"
                        f"{MAX_RETRIES + 1}), retry dalam {RETRY_BACKOFF_SECONDS}s..."
                    )
                    time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                    continue
                print(f"[market_data] {last_error} di {label}, sudah habis retry.")
                return None

            resp.raise_for_status()

            payload = resp.json()

            status = payload.get("status", {})
            if status.get("error_code") not in (None, 0):
                print(f"[market_data] CMC error ({label}): {status.get('error_message')}")
                return None

            return payload

        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                print(
                    f"[market_data] Gagal request CMC ({label}): {e} "
                    f"(percobaan {attempt + 1}/{MAX_RETRIES + 1}), retry..."
                )
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            print(f"[market_data] Gagal request CMC ({label}) setelah retry: {e}")
            return None

    print(f"[market_data] Gagal ambil data dari {label}: {last_error}")
    return None


def fetch_btc_snapshot() -> dict | None:
    """
    Ambil snapshot BTC terkini.

    Return dict atau None kalau gagal.
    """
    # BTC CoinMarketCap ID = 1.
    # Lebih aman pakai id daripada symbol.
    params = {
        "id": "1",
        "convert": "USD",
    }

    payload = _get_json(QUOTE_URL, params=params, endpoint_label="BTC quote")
    if not payload:
        return None

    try:
        btc = payload["data"]["1"]
        quote = btc["quote"]["USD"]

        market_cap = _safe_float(quote.get("market_cap"))
        volume_24h = _safe_float(quote.get("volume_24h"))

        volume_to_market_cap = 0.0
        if market_cap > 0:
            volume_to_market_cap = (volume_24h / market_cap) * 100

        return {
            "id": btc.get("id"),
            "name": btc.get("name"),
            "symbol": btc.get("symbol"),
            "cmc_rank": _safe_int(btc.get("cmc_rank")),

            "price": _safe_float(quote.get("price")),
            "change_1h": _safe_float(quote.get("percent_change_1h")),
            "change_24h": _safe_float(quote.get("percent_change_24h")),
            "change_7d": _safe_float(quote.get("percent_change_7d")),
            "change_30d": _safe_float(quote.get("percent_change_30d")),
            "change_60d": _safe_float(quote.get("percent_change_60d")),
            "change_90d": _safe_float(quote.get("percent_change_90d")),

            "market_cap": market_cap,
            "volume_24h": volume_24h,
            "volume_change_24h": _safe_float(quote.get("volume_change_24h")),
            "volume_to_market_cap": volume_to_market_cap,

            "btc_dominance_from_quote": _safe_float(quote.get("market_cap_dominance")),
            "fully_diluted_market_cap": _safe_float(quote.get("fully_diluted_market_cap")),

            "circulating_supply": _safe_float(btc.get("circulating_supply")),
            "total_supply": _safe_float(btc.get("total_supply")),
            "max_supply": _safe_float(btc.get("max_supply")),

            "last_updated": quote.get("last_updated") or btc.get("last_updated"),
        }

    except Exception as e:
        print(f"[market_data] Gagal parse data BTC: {e}")
        return None


def fetch_global_metrics() -> dict | None:
    """
    Ambil data global crypto market:
    total market cap, total volume, BTC dominance, ETH dominance.
    """
    payload = _get_json(GLOBAL_METRICS_URL, params={"convert": "USD"}, endpoint_label="Global Metrics")
    if not payload:
        return None

    try:
        data = payload["data"]
        quote = data.get("quote", {}).get("USD", {})

        return {
            "total_market_cap": _safe_float(quote.get("total_market_cap") or data.get("total_market_cap")),
            "total_volume_24h": _safe_float(quote.get("total_volume_24h") or data.get("total_volume_24h")),
            "btc_dominance": _safe_float(data.get("btc_dominance")),
            "eth_dominance": _safe_float(data.get("eth_dominance")),
            "active_cryptocurrencies": _safe_int(data.get("active_cryptocurrencies")),
            "active_exchanges": _safe_int(data.get("active_exchanges")),
            "last_updated": data.get("last_updated"),
        }

    except Exception as e:
        print(f"[market_data] Gagal parse global metrics: {e}")
        return None


def fetch_fear_greed() -> dict | None:
    """
    Ambil CMC Fear & Greed Index terbaru.
    """
    payload = _get_json(FEAR_GREED_URL, endpoint_label="Fear & Greed Index")
    if not payload:
        return None

    try:
        data = payload["data"]

        return {
            "fear_greed_value": _safe_int(data.get("value")),
            "fear_greed_classification": data.get("value_classification"),
            "fear_greed_update_time": data.get("update_time"),
        }

    except Exception as e:
        print(f"[market_data] Gagal parse Fear & Greed: {e}")
        return None


def fetch_altcoin_season() -> dict | None:
    """
    Ambil Altcoin Season Index terbaru.
    """
    payload = _get_json(ALTCOIN_SEASON_URL, endpoint_label="Altcoin Season Index")
    if not payload:
        return None

    try:
        data = payload["data"]

        return {
            "altcoin_season_index": _safe_int(data.get("altcoin_index")),
            "altcoin_marketcap": _safe_float(data.get("altcoin_marketcap")),
            "altcoin_snapshot_time": data.get("snapshot_time"),
            "altcoin_yearly_high": _safe_int(data.get("yearly_high")),
            "altcoin_yearly_low": _safe_int(data.get("yearly_low")),
        }

    except Exception as e:
        print(f"[market_data] Gagal parse Altcoin Season Index: {e}")
        return None


def fetch_top_movers(limit: int = 5, universe: int = 200) -> dict | None:
    """
    Ambil top gainers & losers 24h dari `universe` koin teratas by market cap
    (default top 200, biar tidak kena noise micro-cap/low-liquidity yang
    gampang naik/turun ratusan persen tanpa makna). Stablecoin diexclude.

    Return {"gainers": [...], "losers": [...]} - tiap item dict berisi
    symbol/name/change_24h - atau None kalau request gagal.
    """
    params = {
        "start": "1",
        "limit": str(universe),
        "convert": "USD",
        "sort": "market_cap",
        "sort_dir": "desc",
    }
    payload = _get_json(LISTINGS_URL, params=params, endpoint_label="Top Movers Listings")
    if not payload:
        return None

    try:
        coins = []
        for item in payload.get("data", []):
            symbol = str(item.get("symbol", "")).upper()
            if symbol in STABLECOIN_SYMBOLS:
                continue
            quote = item.get("quote", {}).get("USD", {})
            change = quote.get("percent_change_24h")
            if change is None:
                continue
            coins.append({
                "symbol": symbol,
                "name": item.get("name", symbol),
                "change_24h": _safe_float(change),
            })

        if not coins:
            return {"gainers": [], "losers": []}

        sorted_by_change = sorted(coins, key=lambda c: c["change_24h"], reverse=True)
        gainers = sorted_by_change[:limit]
        losers = list(reversed(sorted_by_change[-limit:]))

        return {"gainers": gainers, "losers": losers}

    except Exception as e:
        print(f"[market_data] Gagal parse Top Movers: {e}")
        return None


def fetch_market_snapshot() -> dict | None:
    """
    Gabungkan semua data market untuk dikirim ke AI / Telegram.

    Kalau BTC gagal, return None.
    Kalau data tambahan (global metrics / fear&greed / altcoin season) gagal,
    tetap lanjut dengan data BTC saja, TAPI key yang gagal itu diisi None
    (bukan dihilangkan / bukan 0) supaya lapisan tampilan (ai_narrative.py)
    bisa membedakan "nilainya memang 0" vs "datanya gagal diambil", dan
    menampilkan status tersebut secara jujur (mis. "N/A") bukan angka palsu.

    "data_warnings": list label section yang gagal diambil, dipakai untuk
    kasih catatan singkat di pesan kalau ada data yang tidak lengkap.
    """
    btc = fetch_btc_snapshot()
    if not btc:
        return None

    warnings: list[str] = []

    global_metrics = fetch_global_metrics()
    if global_metrics is None:
        warnings.append("Data Global Market")
        global_metrics = {
            "total_market_cap": None,
            "total_volume_24h": None,
            "btc_dominance": None,
            "eth_dominance": None,
        }

    fear_greed = fetch_fear_greed()
    if fear_greed is None:
        warnings.append("Fear & Greed Index")
        fear_greed = {
            "fear_greed_value": None,
            "fear_greed_classification": None,
            "fear_greed_update_time": None,
        }

    altcoin_season = fetch_altcoin_season()
    if altcoin_season is None:
        warnings.append("Altcoin Season Index")
        altcoin_season = {
            "altcoin_season_index": None,
            "altcoin_marketcap": None,
        }

    top_movers = fetch_top_movers()
    if top_movers is None:
        warnings.append("Top Gainers/Losers")
        top_movers = {"gainers": [], "losers": []}

    snapshot = {
        **btc,
        **global_metrics,
        **fear_greed,
        **altcoin_season,
        "top_gainers": top_movers["gainers"],
        "top_losers": top_movers["losers"],
        "data_warnings": warnings,
    }

    return snapshot