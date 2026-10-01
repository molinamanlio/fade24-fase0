"""Etapa 1: descarga de velas 1h de Hyperliquid (solo lectura, reanudable)."""
import json
import os
import time
import sys

import polars as pl
import requests

API = "https://api.hyperliquid.xyz/info"
DATA = os.path.join(os.path.dirname(__file__), "..", "data")
CANDLES = os.path.join(DATA, "candles")
HOUR_MS = 3_600_000
PAUSE_S = 0.25


def post(payload, max_retries=8):
    backoff = 1.0
    for attempt in range(max_retries):
        try:
            r = requests.post(API, json=payload, timeout=30)
        except requests.RequestException as e:
            print(f"  error de red ({e}); reintento en {backoff:.0f}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  HTTP {r.status_code}; reintento en {backoff:.0f}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        r.raise_for_status()
    raise RuntimeError(f"fallo persistente en {payload}")


def fetch_meta():
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, "meta.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    meta = post({"type": "meta"})
    universe = [
        {
            "name": u["name"],
            "szDecimals": u["szDecimals"],
            "isDelisted": bool(u.get("isDelisted", False)),
            "maxLeverage": u.get("maxLeverage"),
        }
        for u in meta["universe"]
    ]
    with open(path, "w") as f:
        json.dump(universe, f, indent=1)
    return universe


def fetch_candles(coin):
    """Pide el rango completo; la API recorta a las ~5,000 velas mas recientes."""
    now_ms = int(time.time() * 1000)
    rows = post(
        {
            "type": "candleSnapshot",
            "req": {"coin": coin, "interval": "1h", "startTime": 0, "endTime": now_ms},
        }
    )
    if not rows:
        return pl.DataFrame(
            schema={"t": pl.Int64, "T": pl.Int64, "o": pl.Float64, "h": pl.Float64,
                    "l": pl.Float64, "c": pl.Float64, "v": pl.Float64, "n": pl.Int64}
        )
    df = pl.DataFrame(rows).select(
        pl.col("t").cast(pl.Int64),
        pl.col("T").cast(pl.Int64),
        pl.col("o").cast(pl.Float64),
        pl.col("h").cast(pl.Float64),
        pl.col("l").cast(pl.Float64),
        pl.col("c").cast(pl.Float64),
        pl.col("v").cast(pl.Float64),
        pl.col("n").cast(pl.Int64),
    ).sort("t").unique(subset="t", keep="last").sort("t")
    # Descarta la vela en curso (aun no cerrada) para no mezclar datos parciales.
    df = df.filter(pl.col("T") < now_ms)
    return df


def main():
    os.makedirs(CANDLES, exist_ok=True)
    universe = fetch_meta()
    print(f"universo: {len(universe)} perps, "
          f"{sum(u['isDelisted'] for u in universe)} marcados como deslistados")
    for i, u in enumerate(universe):
        coin = u["name"]
        path = os.path.join(CANDLES, f"{coin}.parquet")
        if os.path.exists(path):
            continue
        df = fetch_candles(coin)
        df.write_parquet(path)
        print(f"[{i+1}/{len(universe)}] {coin}: {df.height} velas")
        time.sleep(PAUSE_S)


if __name__ == "__main__":
    main()
