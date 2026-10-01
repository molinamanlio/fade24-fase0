"""Etapa 2: validacion de velas y construccion de eventos."""
import json
import os

import numpy as np
import polars as pl

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
CANDLES = os.path.join(DATA, "candles")
RESULTADOS = os.path.join(os.path.dirname(__file__), "..", "resultados")
HOUR_MS = 3_600_000
N_WIN = 24            # ventana de la z
LAGS = list(range(18, 31))
PRE = 24              # ventana [t-24, t+30] exigida sin huecos ni volumen cero
POST = 30
LISTING_H = 72
THRESHOLDS = [3.0, 3.5, 4.0, 4.5, 5.0, 6.0]


def load_meta():
    with open(os.path.join(DATA, "meta.json")) as f:
        return json.load(f)


def load_coin(coin):
    path = os.path.join(CANDLES, f"{coin}.parquet")
    if not os.path.exists(path):
        return None
    df = pl.read_parquet(path)
    return df if df.height > 0 else None


def validate(df):
    """Devuelve (n_velas, t_min, t_max, n_huecos, horas_faltantes)."""
    t = df["t"].to_numpy()
    if len(t) < 2:
        return len(t), int(t[0]) if len(t) else None, int(t[-1]) if len(t) else None, 0, 0
    d = np.diff(t)
    gaps = d != HOUR_MS
    missing = int(((d[gaps] // HOUR_MS) - 1).sum())
    return len(t), int(t[0]), int(t[-1]), int(gaps.sum()), missing


def to_grid(df):
    """Reindexa a una rejilla horaria completa; huecos quedan como null."""
    t0, t1 = int(df["t"][0]), int(df["t"][-1])
    grid = pl.DataFrame({"t": np.arange(t0, t1 + HOUR_MS, HOUR_MS, dtype=np.int64)})
    return grid.join(df, on="t", how="left").sort("t")


def build_coin_events(coin, df, delisted):
    g = to_grid(df)
    t = g["t"].to_numpy()
    o = g["o"].to_numpy().astype(float)
    c = g["c"].to_numpy().astype(float)
    v = g["v"].to_numpy().astype(float)
    n = len(t)
    missing = np.isnan(c)
    r = np.full(n, np.nan)
    r[1:] = np.log(c[1:] / c[:-1])

    # Media y desv. est. (muestral, ddof=1) de r_{t-24..t-1}: vela t EXCLUIDA.
    s = pl.Series(r)
    mean_excl = s.shift(1).rolling_mean(N_WIN).to_numpy()
    std_excl = s.shift(1).rolling_std(N_WIN, ddof=1).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        z_excl = (r - mean_excl) / std_excl
    # Version del autor original: vela t INCLUIDA en las 24.
    mean_incl = s.rolling_mean(N_WIN).to_numpy()
    std_incl = s.rolling_std(N_WIN, ddof=1).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        z_incl = (r - mean_incl) / std_incl
    # std = 0 (24 retornos identicos, p.ej. precio plano sin operaciones) => z indefinida
    z_excl[~np.isfinite(z_excl)] = np.nan
    z_incl[~np.isfinite(z_incl)] = np.nan

    dollar = v * c
    dollar_prev24 = pl.Series(dollar).shift(1).rolling_mean(N_WIN).to_numpy()

    # Filtros
    bad = missing | np.isnan(v) | (v == 0)
    # ventana [t-24, t+30] sin velas malas (cumsum sobre rejilla)
    cs = np.concatenate([[0], np.cumsum(bad.astype(int))])
    idx = np.arange(n)
    lo = idx - PRE
    hi = idx + POST
    window_ok = (lo >= 0) & (hi < n)
    bad_in_window = np.full(n, True)
    ok_idx = np.where(window_ok)[0]
    bad_in_window[ok_idx] = (cs[hi[ok_idx] + 1] - cs[lo[ok_idx]]) > 0
    f_listing = t < t[0] + LISTING_H * HOUR_MS
    f_window = ~window_ok                     # ventana incompleta (inicio/fin historia)
    f_badcandle = window_ok & bad_in_window   # hueco o volumen cero dentro de la ventana
    f_nan_z = np.isnan(z_excl)

    fades = {}
    for k in LAGS:
        fk = np.full(n, np.nan)
        fk[: n - k] = -np.sign(r[: n - k]) * np.log(c[k:] / o[k:])
        fades[f"fade_{k}"] = fk

    out = pl.DataFrame(
        {
            "coin": [coin] * n,
            "delisted": [delisted] * n,
            "t": t,
            "r": r,
            "z_excl": z_excl,
            "z_incl": z_incl,
            "dollar_vol_prev24": dollar_prev24,
            "f_listing": f_listing,
            "f_window": f_window,
            "f_badcandle": f_badcandle,
            "f_nan_z": f_nan_z,
            **fades,
        }
    )
    return out


def build_all():
    meta = load_meta()
    rows, val_rows = [], []
    for u in meta:
        df = load_coin(u["name"])
        if df is None:
            val_rows.append({"coin": u["name"], "delisted": u["isDelisted"], "n_velas": 0,
                             "t_min": None, "t_max": None, "n_huecos": 0, "horas_faltantes": 0})
            continue
        nv, tmin, tmax, ng, nm = validate(df)
        val_rows.append({"coin": u["name"], "delisted": u["isDelisted"], "n_velas": nv,
                         "t_min": tmin, "t_max": tmax, "n_huecos": ng, "horas_faltantes": nm})
        if nv < PRE + POST + 2:
            continue
        rows.append(build_coin_events(u["name"], df, u["isDelisted"]))
    panel = pl.concat(rows)
    validation = pl.DataFrame(val_rows)
    return panel, validation


def candidate_mask(panel, thr):
    """Candidato: |z_excl| >= umbral y z definida (desv. est. previa > 0, sin huecos).
    Ojo: en polars NaN >= x es True, por eso se exige is_finite()."""
    z = panel["z_excl"]
    return z.is_finite() & (z.abs() >= thr)


def filter_report(panel):
    """Cuenta cuantos candidatos elimina cada filtro (secuencialmente) por umbral."""
    recs = []
    for thr in THRESHOLDS:
        cand = panel.filter(candidate_mask(panel, thr))
        n0 = cand.height
        s1 = cand.filter(~pl.col("f_listing"))
        s2 = s1.filter(~pl.col("f_window"))
        s3 = s2.filter(~pl.col("f_badcandle"))
        s4 = s3.filter(~pl.col("delisted"))
        recs.append({
            "umbral": thr,
            "candidatos": n0,
            "elim_primeras_72h": n0 - s1.height,
            "elim_ventana_incompleta": s1.height - s2.height,
            "elim_hueco_o_vol_cero": s2.height - s3.height,
            "eventos_validos_con_deslistadas": s3.height,
            "eventos_en_deslistadas": s3.height - s4.height,
            "eventos_validos_sin_deslistadas": s4.height,
        })
    return pl.DataFrame(recs)


def valid_events(panel):
    return panel.filter(
        ~pl.col("f_listing") & ~pl.col("f_window") & ~pl.col("f_badcandle") & ~pl.col("f_nan_z")
    )


if __name__ == "__main__":
    os.makedirs(RESULTADOS, exist_ok=True)
    panel, validation = build_all()
    validation.write_csv(os.path.join(RESULTADOS, "validacion_velas.csv"))
    print(validation.describe())
    print(filter_report(panel))
