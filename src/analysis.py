"""Etapa 3: analisis de la curva por rezago, prueba de 24 h, cortes, placebo, costos
y simulacion sin solapamiento."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from events import HOUR_MS, LAGS, THRESHOLDS, valid_events

ROOT = os.path.join(os.path.dirname(__file__), "..")
RESULTADOS = os.path.join(ROOT, "resultados")
GRAFICAS = os.path.join(ROOT, "graficas")
DAY_MS = 24 * HOUR_MS
B = 2000
SEED = 20261001
FEE_SIDE = 0.00045                       # taker 0.045 % por lado
SLIP_SIDE = [0.0002, 0.0005, 0.0010, 0.0020]  # Q1 (mas liquido) .. Q4 (menos liquido)
FADE_COLS = [f"fade_{k}" for k in LAGS]
D_NEIGH = ["fade_22", "fade_23", "fade_25", "fade_26"]

# paleta (dataviz reference palette, modo claro)
C_FADE, C_PLACEBO, C_INK, C_MUTED, C_GRID, C_SURF = (
    "#2a78d6", "#eb6834", "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb")


# ----------------------------------------------------------------------------- bootstrap
def cluster_bootstrap(X, days, rng, B=B):
    """Media por columna de X (n x m) e IC 95 % por bootstrap de conglomerados (dias UTC).
    Remuestrea dias con reemplazo; la media bootstrap es la media ponderada de los
    eventos de los dias sorteados."""
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    n, m = X.shape
    if n == 0:
        return np.full(m, np.nan), np.full(m, np.nan), np.full(m, np.nan), 0
    uniq, inv = np.unique(days, return_inverse=True)
    D = len(uniq)
    sums = np.zeros((D, m))
    np.add.at(sums, inv, X)
    counts = np.bincount(inv, minlength=D).astype(float)
    idx = rng.integers(0, D, size=(B, D))
    bs = sums[idx].sum(axis=1)                       # B x m
    bc = counts[idx].sum(axis=1)[:, None]            # B x 1
    means_b = bs / bc
    lo = np.percentile(means_b, 2.5, axis=0)
    hi = np.percentile(means_b, 97.5, axis=0)
    return X.mean(axis=0), lo, hi, D


def with_D(df):
    return df.with_columns(
        (pl.col("fade_24") - pl.mean_horizontal(D_NEIGH)).alias("D")
    )


def days_of(df):
    return (df["t"].to_numpy() // DAY_MS).astype(np.int64)


# ----------------------------------------------------------------------------- tablas
def curve_table(ev, rng, label_cols):
    """Curva por rezago + D para un subconjunto de eventos."""
    cols = FADE_COLS + ["D"]
    mean, lo, hi, D = cluster_bootstrap(ev.select(cols).to_numpy(), days_of(ev), rng)
    rows = []
    for j, k in enumerate(LAGS):
        rows.append({**label_cols, "k": k, "n_eventos": ev.height, "n_dias": D,
                     "media": mean[j], "ic_lo": lo[j], "ic_hi": hi[j]})
    d_row = {**label_cols, "n_eventos": ev.height, "n_dias": D,
             "D": mean[-1], "ic_lo": lo[-1], "ic_hi": hi[-1]}
    return rows, d_row


def liquidity_cutpoints(ev3):
    v = ev3["dollar_vol_prev24"].drop_nulls().to_numpy()
    return np.quantile(v, [0.25, 0.5, 0.75])


def assign_quartile(ev, cuts):
    """Q1 = mas liquido (volumen en USD mas alto) ... Q4 = menos liquido."""
    v = ev["dollar_vol_prev24"].to_numpy()
    q = 4 - np.searchsorted(cuts, v, side="right")   # v > cuts[2] -> Q1
    return ev.with_columns(pl.Series("cuartil", q.astype(int)))


def add_net(ev):
    slip = np.array(SLIP_SIDE)[ev["cuartil"].to_numpy() - 1]
    cost = 2 * FEE_SIDE + 2 * slip
    return ev.with_columns(
        pl.Series("costo_rt", cost),
        (pl.col("fade_24") - pl.Series("c", cost)).alias("neto_24"),
    )


def placebo_events(valid, ev_thr, rng):
    """Mismo numero de eventos por moneda, timestamps aleatorios entre las velas
    validas de la moneda, direccion aleatoria."""
    counts = ev_thr.group_by("coin").len().sort("coin")
    parts = []
    raw_cols = [f"raw_{k}" for k in LAGS]
    for coin, n in counts.iter_rows():
        pool = valid.filter(pl.col("coin") == coin)
        take = rng.integers(0, pool.height, size=n)
        sub = pool[take.tolist()]
        sign = rng.choice([-1.0, 1.0], size=n)
        # fade_k = -sign(r_t) * raw_k  =>  raw_k = -sign(r_t) * fade_k
        sr = -np.sign(sub["r"].to_numpy())
        M = sub.select(FADE_COLS).to_numpy() * sr[:, None] * sign[:, None]
        parts.append(pl.DataFrame({"t": sub["t"], **{c: M[:, j] for j, c in enumerate(raw_cols)}}))
    pdf = pl.concat(parts)
    pdf = pdf.rename({f"raw_{k}": f"fade_{k}" for k in LAGS})
    return with_D(pdf)


def simulate(ev4):
    """Una posicion por moneda a la vez (ocupada desde la senal t hasta la salida
    t+25 h), tamano fijo, umbral 4.0, neto de costos."""
    ev4 = ev4.sort("t")
    busy = {}
    trades = []
    for row in ev4.iter_rows(named=True):
        t = row["t"]
        if busy.get(row["coin"], -1) > t:
            continue
        busy[row["coin"]] = t + 25 * HOUR_MS
        trades.append({"coin": row["coin"], "t_evento": t, "t_entrada": t + 24 * HOUR_MS,
                       "direccion": "corto" if row["r"] > 0 else "largo",
                       "cuartil": row["cuartil"], "bruto": row["fade_24"],
                       "costo_rt": row["costo_rt"], "neto": row["neto_24"]})
    tr = pl.DataFrame(trades).sort("t_entrada")
    net = tr["neto"].to_numpy()
    eq = np.cumsum(net)
    dd = eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    metrics = {
        "eventos_umbral_4": ev4.height,
        "operaciones": int(tr.height),
        "omitidas_por_solapamiento": int(ev4.height - tr.height),
        "rendimiento_medio_bruto": float(tr["bruto"].mean()),
        "rendimiento_medio_neto": float(net.mean()),
        "rendimiento_total_neto": float(eq[-1]),
        "tasa_acierto_neta": float((net > 0).mean()),
        "peor_operacion_neta": float(net.min()),
        "mejor_operacion_neta": float(net.max()),
        "drawdown_maximo": float(dd.min()),
    }
    return tr, metrics, eq


# ----------------------------------------------------------------------------- graficas
def plot_curve(thr, curve, plac, path):
    c = curve.filter(pl.col("umbral") == thr).sort("k")
    p = plac.filter(pl.col("umbral") == thr).sort("k")
    k = c["k"].to_numpy()
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=150)
    fig.patch.set_facecolor(C_SURF)
    ax.set_facecolor(C_SURF)
    ax.axhline(0, color=C_MUTED, lw=0.8)
    ax.axvline(24, color=C_INK, lw=1, ls="--")
    ax.fill_between(p["k"], p["ic_lo"] * 1e4, p["ic_hi"] * 1e4, color=C_PLACEBO, alpha=0.12, lw=0)
    ax.plot(p["k"], p["media"] * 1e4, color=C_PLACEBO, lw=2, marker="o", ms=4, label="placebo")
    ax.fill_between(k, c["ic_lo"] * 1e4, c["ic_hi"] * 1e4, color=C_FADE, alpha=0.18, lw=0)
    ax.plot(k, c["media"] * 1e4, color=C_FADE, lw=2, marker="o", ms=4,
            label=f"fade |z_excl| ≥ {thr:g}")
    n = int(c["n_eventos"][0])
    ax.set_title(f"Rendimiento medio del fade por rezago · umbral {thr:g} · n = {n:,} eventos",
                 color=C_INK, fontsize=11, loc="left")
    ax.set_xlabel("rezago k (horas después de la vela extrema)", color=C_MUTED)
    ax.set_ylabel("rendimiento medio (pb)", color=C_MUTED)
    ax.set_xticks(k)
    ax.tick_params(colors=C_MUTED)
    ax.grid(axis="y", color=C_GRID, lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(C_GRID)
    ax.text(24.1, ax.get_ylim()[1], "k = 24", color=C_INK, fontsize=9, va="top")
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    fig.text(0.01, 0.005, "banda = IC 95 % bootstrap agrupado por día UTC (2,000 remuestreos)",
             color=C_MUTED, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, facecolor=C_SURF)
    plt.close(fig)


def plot_equity(eq, tr, path):
    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    fig.patch.set_facecolor(C_SURF)
    ax.set_facecolor(C_SURF)
    ax.plot(np.arange(1, len(eq) + 1), eq * 100, color=C_FADE, lw=2)
    ax.axhline(0, color=C_MUTED, lw=0.8)
    ax.set_title("Simulación sin solapamiento · umbral 4.0 · neto de costos · tamaño fijo",
                 color=C_INK, fontsize=11, loc="left")
    ax.set_xlabel("operación #", color=C_MUTED)
    ax.set_ylabel("rendimiento acumulado (% del tamaño fijo)", color=C_MUTED)
    ax.tick_params(colors=C_MUTED)
    ax.grid(axis="y", color=C_GRID, lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, facecolor=C_SURF)
    plt.close(fig)


# ----------------------------------------------------------------------------- main
def run(panel, validation, filter_tbl):
    os.makedirs(RESULTADOS, exist_ok=True)
    os.makedirs(GRAFICAS, exist_ok=True)
    rng = np.random.default_rng(SEED)
    valid = with_D(valid_events(panel))

    ev3 = valid.filter(pl.col("z_excl").abs() >= 3.0)
    cuts = liquidity_cutpoints(ev3)
    valid = add_net(assign_quartile(valid, cuts))

    curve_rows, d_rows, dir_rows, liq_rows, plac_rows, incl_rows = [], [], [], [], [], []
    for thr in THRESHOLDS:
        ev = valid.filter(pl.col("z_excl").abs() >= thr)
        for incl, sub in (("con", ev), ("sin", ev.filter(~pl.col("delisted")))):
            if sub.height == 0:
                continue
            cr, dr = curve_table(sub, rng, {"umbral": thr, "deslistadas": incl})
            curve_rows += cr
            d_rows.append(dr)
        # direccion
        for name, sub in (("verde (fade corto)", ev.filter(pl.col("r") > 0)),
                          ("roja (fade largo)", ev.filter(pl.col("r") < 0))):
            if sub.height == 0:
                continue
            cr, dr = curve_table(sub, rng, {"umbral": thr, "direccion": name})
            best = max(cr, key=lambda r: r["media"])
            m24 = next(r for r in cr if r["k"] == 24)
            dir_rows.append({**dr, "fade24_media": m24["media"], "fade24_ic_lo": m24["ic_lo"],
                             "fade24_ic_hi": m24["ic_hi"], "k_max": best["k"], "max_media": best["media"]})
        # liquidez + costos
        for q in (1, 2, 3, 4):
            sub = ev.filter(pl.col("cuartil") == q)
            if sub.height == 0:
                continue
            M = sub.select(["fade_24", "neto_24", "D"]).to_numpy()
            mean, lo, hi, D = cluster_bootstrap(M, days_of(sub), rng)
            liq_rows.append({"umbral": thr, "cuartil": f"Q{q}", "n_eventos": sub.height, "n_dias": D,
                             "vol_usd_prev24_mediana": float(sub["dollar_vol_prev24"].median()),
                             "costo_rt": 2 * FEE_SIDE + 2 * SLIP_SIDE[q - 1],
                             "fade24_bruto": mean[0], "bruto_ic_lo": lo[0], "bruto_ic_hi": hi[0],
                             "fade24_neto": mean[1], "neto_ic_lo": lo[1], "neto_ic_hi": hi[1],
                             "D": mean[2], "D_ic_lo": lo[2], "D_ic_hi": hi[2]})
        M = ev.select(["neto_24"]).to_numpy()
        mean, lo, hi, D = cluster_bootstrap(M, days_of(ev), rng)
        liq_rows.append({"umbral": thr, "cuartil": "todos", "n_eventos": ev.height, "n_dias": D,
                         "vol_usd_prev24_mediana": float(ev["dollar_vol_prev24"].median()),
                         "costo_rt": float(ev["costo_rt"].mean()),
                         "fade24_bruto": float(ev["fade_24"].mean()), "bruto_ic_lo": None, "bruto_ic_hi": None,
                         "fade24_neto": mean[0], "neto_ic_lo": lo[0], "neto_ic_hi": hi[0],
                         "D": None, "D_ic_lo": None, "D_ic_hi": None})
        # placebo
        pev = placebo_events(valid, ev, rng)
        cr, dr = curve_table(pev, rng, {"umbral": thr})
        plac_rows += cr
        # z_incl vs z_excl
        incl_rows.append({"umbral": thr, "eventos_z_excl": ev.height,
                          "eventos_z_incl": valid.filter(pl.col("z_incl").abs() >= thr).height})

    curve = pl.DataFrame(curve_rows)
    dtab = pl.DataFrame(d_rows)
    plac = pl.DataFrame(plac_rows)
    curve.write_csv(os.path.join(RESULTADOS, "curva_rezagos.csv"))
    dtab.write_csv(os.path.join(RESULTADOS, "prueba_D.csv"))
    pl.DataFrame(dir_rows).write_csv(os.path.join(RESULTADOS, "por_direccion.csv"))
    pl.DataFrame(liq_rows).write_csv(os.path.join(RESULTADOS, "por_liquidez_y_costos.csv"))
    plac.write_csv(os.path.join(RESULTADOS, "placebo.csv"))
    zmax_theory = 23 / np.sqrt(24)
    incl_tbl = pl.DataFrame(incl_rows).with_columns(
        pl.lit(float(valid["z_incl"].abs().max())).alias("max_abs_z_incl_observado"),
        pl.lit(float(valid["z_excl"].abs().max())).alias("max_abs_z_excl_observado"),
        pl.lit(zmax_theory).alias("max_teorico_z_incl"),
    )
    incl_tbl.write_csv(os.path.join(RESULTADOS, "z_incl_vs_z_excl.csv"))
    filter_tbl.write_csv(os.path.join(RESULTADOS, "filtros.csv"))
    validation.write_csv(os.path.join(RESULTADOS, "validacion_velas.csv"))

    # simulacion
    ev4 = valid.filter(pl.col("z_excl").abs() >= 4.0)
    tr, metrics, eq = simulate(ev4)
    tr.write_csv(os.path.join(RESULTADOS, "simulacion_operaciones.csv"))
    _, metrics_q1, _ = simulate(ev4.filter(pl.col("cuartil") == 1))
    pl.DataFrame([{"universo": "todos los cuartiles", **metrics},
                  {"universo": "solo Q1 (mas liquido)", **metrics_q1}]).write_csv(
        os.path.join(RESULTADOS, "simulacion.csv"))
    plot_equity(eq, tr, os.path.join(GRAFICAS, "simulacion_equity.png"))

    # graficas por umbral (con deslistadas = analisis principal)
    cmain = curve.filter(pl.col("deslistadas") == "con")
    for thr in THRESHOLDS:
        plot_curve(thr, cmain, plac, os.path.join(GRAFICAS, f"curva_rezagos_{thr:g}.png"))

    # muestra
    v = validation.filter(pl.col("n_velas") > 0)
    va = v.filter(~pl.col("delisted"))
    vd = v.filter(pl.col("delisted"))
    sample = {
        "activas_t_min_ms": int(va["t_min"].min()),
        "activas_t_max_ms": int(va["t_max"].max()),
        "activas_dias_historia": (int(va["t_max"].max()) - int(va["t_min"].min())) / DAY_MS,
        "deslistadas_t_min_ms": int(vd["t_min"].min()) if vd.height else None,
        "deslistadas_t_max_ms": int(vd["t_max"].max()) if vd.height else None,
        "monedas_universo": validation.height,
        "monedas_con_datos": v.height,
        "monedas_deslistadas_con_datos": int(v["delisted"].sum()),
        "velas_total": int(v["n_velas"].sum()),
        "velas_por_moneda_mediana": float(v["n_velas"].median()),
        "velas_por_moneda_max": int(v["n_velas"].max()),
        "monedas_con_huecos": int((v["n_huecos"] > 0).sum()),
        "horas_faltantes_total": int(v["horas_faltantes"].sum()),
        "t_min_ms": int(v["t_min"].min()),
        "t_max_ms": int(v["t_max"].max()),
        "dias_historia": (int(v["t_max"].max()) - int(v["t_min"].min())) / DAY_MS,
        "velas_validas_para_eventos": valid.height,
        "cortes_liquidez_usd": [float(x) for x in cuts],
    }
    with open(os.path.join(RESULTADOS, "muestra.json"), "w") as f:
        json.dump(sample, f, indent=1)
    return dict(curve=curve, D=dtab, dir=pl.DataFrame(dir_rows), liq=pl.DataFrame(liq_rows),
                placebo=plac, sim=metrics, sim_q1=metrics_q1, sample=sample, incl=incl_tbl)
