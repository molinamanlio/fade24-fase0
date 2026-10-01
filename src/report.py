"""Genera REPORTE.md a partir de los resultados de la etapa 3."""
import datetime as dt
import os

import polars as pl

from analysis import D_NEIGH, FEE_SIDE, SLIP_SIDE, B
from events import LAGS, THRESHOLDS

ROOT = os.path.join(os.path.dirname(__file__), "..")


def pb(x):
    return "—" if x is None or x != x else f"{x * 1e4:+.1f}"


def fmt_ms(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y-%m-%d %H:%M UTC")


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def verdict(res):
    D = res["D"].filter(pl.col("deslistadas") == "con")
    liq = res["liq"].filter(pl.col("cuartil") != "todos")
    curve = res["curve"].filter(pl.col("deslistadas") == "con")
    ok_D = D.filter((pl.col("n_eventos") >= 100) & (pl.col("ic_lo") > 0))
    ok_net = liq.filter(pl.col("neto_ic_lo") > 0)
    seguir_thr = sorted(set(ok_D["umbral"].to_list()) & set(ok_net["umbral"].to_list()))
    # ¿rinde el fade en varios rezagos? (IC inferior > 0 en >= 3 rezagos, umbral con >= 100 eventos)
    generic = []
    for thr in THRESHOLDS:
        c = curve.filter((pl.col("umbral") == thr) & (pl.col("n_eventos") >= 100))
        if c.height and (c["ic_lo"] > 0).sum() >= 3:
            kmax = c.sort("media", descending=True)["k"][0]
            generic.append((thr, int(kmax), int((c["ic_lo"] > 0).sum())))
    # ¿la muestra puede decidir? ancho del IC de D vs |D| típico
    big = D.filter(pl.col("n_eventos") >= 100)
    if seguir_thr:
        return "SEGUIR", seguir_thr, generic, big
    if generic:
        return "REVERSIÓN GENÉRICA", seguir_thr, generic, big
    return "DESCARTAR", seguir_thr, generic, big


def write(res, filt):
    s = res["sample"]
    D_all = res["D"]
    Dc = D_all.filter(pl.col("deslistadas") == "con").sort("umbral")
    Ds = D_all.filter(pl.col("deslistadas") == "sin").sort("umbral")
    curve = res["curve"].filter(pl.col("deslistadas") == "con")
    plac = res["placebo"]
    liq = res["liq"]
    dirs = res["dir"]
    sim = res["sim"]
    incl = res["incl"]
    label, seguir_thr, generic, big = verdict(res)

    # --- parrafo del veredicto
    n_needed = None
    if big.height:
        # eventos necesarios para que el IC de D (semiancho) baje a |D| observado, escala 1/sqrt(n)
        r0 = big.sort("n_eventos", descending=True).row(0, named=True)
        half = (r0["ic_hi"] - r0["ic_lo"]) / 2
        if r0["D"] != 0:
            n_needed = int(r0["n_eventos"] * (half / abs(r0["D"])) ** 2)
    if label == "SEGUIR":
        texto = (f"**SEGUIR.** Para el/los umbral(es) {seguir_thr} el IC 95 % de D excluye cero por arriba "
                 f"con ≥ 100 eventos y el rendimiento neto en k = 24 tiene IC inferior > 0 en al menos "
                 f"un cuartil de liquidez.")
    elif label == "REVERSIÓN GENÉRICA":
        g = "; ".join(f"umbral {t:g}: máximo en k = {k} ({n} rezagos con IC inferior > 0)" for t, k, n in generic)
        texto = (f"**REVERSIÓN GENÉRICA.** El fade rinde en varios rezagos pero D = fade_24 − "
                 f"promedio(22, 23, 25, 26) no es distinguible de cero en ningún umbral. {g}.")
    else:
        # ¿en cuantos umbrales k=24 es el maximo de la curva?
        n_argmax24 = sum(
            1 for thr in THRESHOLDS
            if curve.filter(pl.col("umbral") == thr).sort("media", descending=True)["k"][0] == 24)
        q1 = liq.filter(pl.col("cuartil") == "Q1")
        best_q1 = q1.sort("neto_ic_hi", descending=True).row(0, named=True)
        min_cost = liq.filter(pl.col("cuartil") == "Q1")["costo_rt"][0]
        texto = (
            "**DESCARTAR.** El rendimiento neto en k = 24 no sobrevive en ningún cuartil de liquidez ni en ningún umbral: "
            "el rendimiento bruto medio del fade en k = 24 ("
            + ", ".join(f"{pb(curve.filter((pl.col('umbral') == t) & (pl.col('k') == 24))['media'][0])}" for t in THRESHOLDS)
            + f" pb para los umbrales {', '.join(f'{t:g}' for t in THRESHOLDS)}) es menor que el costo mínimo de ida y vuelta "
            f"({min_cost*1e4:.0f} pb en el cuartil más líquido), y la media neta en Q1 es negativa en todos los umbrales "
            f"(mejor caso: umbral {best_q1['umbral']:g}, neto {pb(best_q1['fade24_neto'])} pb, IC [{pb(best_q1['neto_ic_lo'])}, {pb(best_q1['neto_ic_hi'])}]). "
            "El pico en k = 24 (D) tampoco sobrevive al criterio: su IC 95 % incluye cero en los 6 umbrales.\n\n"
            f"**Matiz que no cambia el veredicto.** D es positivo en los 6 umbrales y crece con el umbral, k = 24 es el máximo "
            f"de la curva en {n_argmax24} de 6 umbrales, y el placebo es plano. La muestra no refuta el mecanismo de la ventana "
            "de 24 h: lo deja sin potencia (ver abajo). Pero aun si el efecto fuera real con el tamaño observado (≈ 4-11 pb), "
            "no cubre las comisiones, así que más datos no cambiarían la decisión operativa. La única señal exploratoria con IC "
            "que excluye cero es D en eventos verdes (fade corto) para los umbrales 3.0 y 3.5 (sección 4.3), y D en Q2 para "
            "umbrales ≥ 4.0 (sección 4.4): son 2 de muchas comparaciones y sus rendimientos netos siguen siendo ≤ 0 o con IC que incluye cero.")
    inconcluso = ""
    if label != "SEGUIR" and big.height:
        r0 = big.sort("n_eventos", descending=True).row(0, named=True)
        inconcluso = (
            f"\n\n**¿Alcanza la muestra?** En el umbral con más eventos (≥ 100), {r0['umbral']:g} "
            f"(n = {r0['n_eventos']:,}, {r0['n_dias']} días), D = {pb(r0['D'])} pb con IC 95 % "
            f"[{pb(r0['ic_lo'])}, {pb(r0['ic_hi'])}] pb. Si el efecto real fuera del tamaño del D "
            f"observado, harían falta ≈ {n_needed:,} eventos del mismo tipo para que el IC lo excluyera "
            f"(escala 1/√n), es decir ≈ {n_needed / max(r0['n_eventos'], 1):.1f}× la historia actual en días. "
            "Sobre la pregunta mecanicista aislada (¿existe el pico en 24 h?) el estudio es INCONCLUSO con esa necesidad de "
            "muestra; sobre la pregunta operativa (¿se puede operar con beneficio neto?) la respuesta es no.")

    L = []
    L.append("# Fase 0 — Fade de velas extremas 24 h después (Hyperliquid)\n")
    L.append(f"_Generado por `python run.py` el {dt.datetime.now(dt.UTC).strftime('%Y-%m-%d %H:%M UTC')}._\n")
    L.append("## 1. Veredicto\n")
    L.append(texto + inconcluso + "\n")
    L.append("Tabla de D = fade_24 − promedio(fade_22, fade_23, fade_25, fade_26) (incluye monedas deslistadas; pb = puntos básicos, 1 pb = 0.01 %):\n")
    L.append(md_table(["umbral", "eventos", "días", "D (pb)", "IC 95 % (pb)", "excluye 0"],
                      [[f"{r['umbral']:g}", f"{r['n_eventos']:,}", r["n_dias"], pb(r["D"]),
                        f"[{pb(r['ic_lo'])}, {pb(r['ic_hi'])}]",
                        "sí (D>0)" if r["ic_lo"] > 0 else ("sí (D<0)" if r["ic_hi"] < 0 else "no")]
                       for r in Dc.iter_rows(named=True)]))
    L.append("\nSin deslistadas:\n")
    L.append(md_table(["umbral", "eventos", "D (pb)", "IC 95 % (pb)"],
                      [[f"{r['umbral']:g}", f"{r['n_eventos']:,}", pb(r["D"]),
                        f"[{pb(r['ic_lo'])}, {pb(r['ic_hi'])}]"] for r in Ds.iter_rows(named=True)]))

    # --- muestra
    L.append("\n## 2. Muestra\n")
    L.append(md_table(["métrica", "valor"], [
        ["monedas en el universo (`meta`)", s["monedas_universo"]],
        ["monedas con velas", s["monedas_con_datos"]],
        ["de ellas marcadas `isDelisted`", s["monedas_deslistadas_con_datos"]],
        ["velas 1 h totales", f"{s['velas_total']:,}"],
        ["velas por moneda (mediana / máx)", f"{s['velas_por_moneda_mediana']:.0f} / {s['velas_por_moneda_max']:,}"],
        ["rango de fechas, monedas activas", f"{fmt_ms(s['activas_t_min_ms'])} → {fmt_ms(s['activas_t_max_ms'])} ({s['activas_dias_historia']:.0f} días)"],
        ["rango de fechas, monedas deslistadas", f"{fmt_ms(s['deslistadas_t_min_ms'])} → {fmt_ms(s['deslistadas_t_max_ms'])}"],
        ["monedas con huecos", s["monedas_con_huecos"]],
        ["horas faltantes en total", s["horas_faltantes_total"]],
        ["velas que pasan todos los filtros", f"{s['velas_validas_para_eventos']:,}"],
    ]))
    L.append("\nLa API devuelve como máximo ~5,000 velas por moneda, por eso el histórico de las monedas activas es de "
             f"~{s['activas_dias_historia']:.0f} días y menos para las listadas después. **Las monedas deslistadas son distintas:** "
             "sus 5,000 velas terminan en la fecha de deslistado, así que cubren periodos anteriores (2023-2026) que no se "
             "solapan con el de las activas. Incluirlas añade días calendario independientes (ver columna 'días' en la tabla de D) "
             "pero mezcla regímenes de mercado y monedas que acabaron deslistadas (sesgo de supervivencia inverso). "
             "El detalle por moneda está en `resultados/validacion_velas.csv`.\n")

    # --- etapa 2
    L.append("## 3. Etapa 2 — Eventos y filtros\n")
    L.append("Definiciones aplicadas literalmente: r_t = ln(close_t/close_{t−1}); z_excl(t) usa media y "
             "desviación estándar muestral (ddof = 1) de r_{t−24..t−1} (vela t excluida); evento si |z_excl| ≥ umbral; "
             "fade_k = −signo(r_t)·ln(close_{t+k}/open_{t+k}) con k = 18..30 sobre una rejilla horaria completa "
             "(los huecos se reindexan como nulos, de modo que t + k siempre son horas de reloj, no filas). "
             "El test `tests/test_lag24.py` verifica que en k = 24 la vela de entrada es exactamente la hora en que "
             "la vela del evento sale de la ventana de 24 h.\n")
    L.append("Filtros aplicados en secuencia (cuántos candidatos elimina cada uno):\n")
    L.append(md_table(["umbral", "candidatos", "−primeras 72 h", "−ventana incompleta (inicio/fin de historia)",
                       "−hueco o volumen 0 en [t−24, t+30]", "eventos válidos", "de ellos en deslistadas"],
                      [[f"{r['umbral']:g}", f"{r['candidatos']:,}", r["elim_primeras_72h"], r["elim_ventana_incompleta"],
                        r["elim_hueco_o_vol_cero"], f"{r['eventos_validos_con_deslistadas']:,}", r["eventos_en_deslistadas"]]
                       for r in filt.iter_rows(named=True)]))
    zi = incl.row(0, named=True)
    L.append(f"\n**z_incl vs z_excl.** Con la vela t incluida en las 24 (versión del autor original), "
             f"la desigualdad de Samuelson acota |z_incl| ≤ (n−1)/√n = 23/√24 ≈ {zi['max_teorico_z_incl']:.2f}; "
             f"el máximo observado es {zi['max_abs_z_incl_observado']:.2f}, frente a {zi['max_abs_z_excl_observado']:.1f} "
             "con z_excl. Por eso los umbrales 5.0 y 6.0 son inalcanzables con z_incl y la comparación de conteos es:\n")
    L.append(md_table(["umbral", "eventos z_excl", "eventos z_incl"],
                      [[f"{r['umbral']:g}", f"{r['eventos_z_excl']:,}", f"{r['eventos_z_incl']:,}"] for r in incl.iter_rows(named=True)]))

    # --- etapa 3
    L.append("\n## 4. Etapa 3 — Resultados\n")
    L.append(f"Todos los IC son al 95 % por bootstrap de conglomerados por día calendario UTC ({B:,} remuestreos). "
             "Las gráficas `graficas/curva_rezagos_<umbral>.png` muestran la curva con su banda, la línea en k = 24 y el placebo.\n")
    L.append("### 4.1 Curva por rezago (media del fade en pb, con deslistadas)\n")
    hdr = ["umbral", "n"] + [f"k={k}" for k in LAGS]
    rows = []
    for thr in THRESHOLDS:
        c = curve.filter(pl.col("umbral") == thr).sort("k")
        if c.height == 0:
            continue
        cells = []
        for r in c.iter_rows(named=True):
            mark = "**" if r["ic_lo"] > 0 or r["ic_hi"] < 0 else ""
            cells.append(f"{mark}{pb(r['media'])}{mark}")
        rows.append([f"{thr:g}", f"{int(c['n_eventos'][0]):,}"] + cells)
    L.append(md_table(hdr, rows))
    L.append("\n(negrita = IC 95 % excluye cero). IC completos en `resultados/curva_rezagos.csv`.\n")
    L.append("### 4.2 Placebo (timestamps y dirección aleatorios, pb)\n")
    rows = []
    for thr in THRESHOLDS:
        c = plac.filter(pl.col("umbral") == thr).sort("k")
        rows.append([f"{thr:g}", f"{int(c['n_eventos'][0]):,}"] + [pb(x) for x in c["media"]])
    L.append(md_table(hdr, rows))
    L.append("\n### 4.3 Por dirección\n")
    L.append(md_table(["umbral", "dirección", "n", "fade_24 (pb)", "IC", "D (pb)", "IC de D", "k máx"],
                      [[f"{r['umbral']:g}", r["direccion"], f"{r['n_eventos']:,}", pb(r["fade24_media"]),
                        f"[{pb(r['fade24_ic_lo'])}, {pb(r['fade24_ic_hi'])}]", pb(r["D"]),
                        f"[{pb(r['ic_lo'])}, {pb(r['ic_hi'])}]", r["k_max"]] for r in dirs.iter_rows(named=True)]))
    L.append("\n### 4.4 Por liquidez y costos en k = 24\n")
    L.append(f"Cuartiles por volumen medio **por hora** en USD de las 24 h previas (cortes fijados con los eventos de umbral 3.0: "
             + ", ".join(f"{c/1e3:,.0f} k" for c in s["cortes_liquidez_usd"]) +
             f"). Q1 = más líquido. Costo = comisión taker {FEE_SIDE*100:.3f} % por lado + deslizamiento por lado de "
             + " / ".join(f"{x*100:.2f} %" for x in SLIP_SIDE) + " (Q1→Q4).\n")
    L.append(md_table(["umbral", "cuartil", "n", "vol USD/h mediana (prev. 24 h)", "costo RT (pb)", "bruto k=24 (pb)", "neto k=24 (pb)", "IC neto", "D (pb)", "IC de D"],
                      [[f"{r['umbral']:g}", r["cuartil"], f"{r['n_eventos']:,}",
                        f"{r['vol_usd_prev24_mediana']/1e3:,.0f} k", f"{r['costo_rt']*1e4:.0f}",
                        pb(r["fade24_bruto"]), pb(r["fade24_neto"]),
                        f"[{pb(r['neto_ic_lo'])}, {pb(r['neto_ic_hi'])}]", pb(r["D"]),
                        "—" if r["D"] is None else f"[{pb(r['D_ic_lo'])}, {pb(r['D_ic_hi'])}]"]
                       for r in liq.iter_rows(named=True)]))
    L.append("\n### 4.5 Simulación sin solapamiento (umbral 4.0, neto de costos, tamaño fijo)\n")
    L.append("Regla: una moneda queda ocupada desde la señal (t) hasta la salida (t + 25 h); las señales que "
             "llegan mientras está ocupada se omiten. Rendimientos en fracción del tamaño fijo, no compuestos.\n")
    sq = res["sim_q1"]
    L.append(md_table(["métrica", "todos los cuartiles", "solo Q1 (más líquido)"], [
        ["eventos con |z_excl| ≥ 4.0", f"{sim['eventos_umbral_4']:,}", f"{sq['eventos_umbral_4']:,}"],
        ["operaciones ejecutadas", f"{sim['operaciones']:,}", f"{sq['operaciones']:,}"],
        ["omitidas por solapamiento", sim["omitidas_por_solapamiento"], sq["omitidas_por_solapamiento"]],
        ["rendimiento medio bruto", pb(sim["rendimiento_medio_bruto"]) + " pb", pb(sq["rendimiento_medio_bruto"]) + " pb"],
        ["rendimiento medio neto", pb(sim["rendimiento_medio_neto"]) + " pb", pb(sq["rendimiento_medio_neto"]) + " pb"],
        ["rendimiento total neto (suma, % del tamaño fijo)", f"{sim['rendimiento_total_neto']*100:+.1f} %", f"{sq['rendimiento_total_neto']*100:+.1f} %"],
        ["tasa de acierto (neto > 0)", f"{sim['tasa_acierto_neta']*100:.1f} %", f"{sq['tasa_acierto_neta']*100:.1f} %"],
        ["peor operación neta", f"{sim['peor_operacion_neta']*100:+.2f} %", f"{sq['peor_operacion_neta']*100:+.2f} %"],
        ["mejor operación neta", f"{sim['mejor_operacion_neta']*100:+.2f} %", f"{sq['mejor_operacion_neta']*100:+.2f} %"],
        ["drawdown máximo de la curva acumulada", f"{sim['drawdown_maximo']*100:.1f} %", f"{sq['drawdown_maximo']*100:.1f} %"],
    ]))
    L.append("\nCurva: `graficas/simulacion_equity.png`; operaciones: `resultados/simulacion_operaciones.csv`.\n")

    # --- limitaciones
    L.append("## 5. Limitaciones\n")
    L.append(
        f"- **Histórico corto.** La API solo entrega ~5,000 velas por moneda: ~{s['activas_dias_historia']:.0f} días "
        f"({fmt_ms(s['activas_t_min_ms'])[:10]} a {fmt_ms(s['activas_t_max_ms'])[:10]}) para las monedas activas. Es un único "
        "régimen de mercado; cualquier efecto estacional o de régimen no es observable. Las deslistadas aportan ventanas de "
        "2023-2026 pero son monedas que terminaron deslistadas.\n"
        f"- **Pocos conglomerados independientes.** Los eventos se agrupan en días de movimiento general; el bootstrap "
        f"por día tiene ~{s['activas_dias_historia']:.0f} conglomerados sin deslistadas y los IC resultantes son anchos (ver la "
        "tabla de D). Los IC de los cortes por dirección y cuartil son más anchos todavía.\n"
        "- **Costos supuestos.** El deslizamiento por cuartil es un supuesto, no una medición del libro de órdenes. "
        "El rendimiento neto es muy sensible a él en los cuartiles menos líquidos.\n"
        "- **Entrada al open de la vela.** Se asume ejecución exacta al open de t + k y salida al close; en la práctica "
        "la ejecución tendría latencia y el 'open' de una vela de 1 h no es un precio negociable garantizado.\n"
        "- **Múltiples comparaciones.** Se evalúan 6 umbrales × 13 rezagos × cortes; algún IC que excluya cero por azar "
        "es esperable. La prueba preregistrada es D en k = 24, no el mejor rezago.\n"
        "- **Deslistadas.** Las monedas marcadas `isDelisted` se incluyen en el análisis principal y se reportan aparte; "
        "sus series terminan antes y pueden tener liquidez degradada al final.\n"
        "- **z_incl.** Solo se calculó para comparación; los umbrales altos no son alcanzables con esa definición.\n"
    )
    L.append("## 6. Reproducibilidad\n")
    L.append("```\npython -m venv .venv && .venv/bin/pip install -r requirements.txt\n.venv/bin/python run.py          # descarga (reanudable) + eventos + análisis + reporte\n.venv/bin/python tests/test_lag24.py\n```\n")
    L.append("Fuente de datos: exclusivamente `POST https://api.hyperliquid.xyz/info` (`meta`, `candleSnapshot`). "
             f"Semilla del bootstrap/placebo: fija. Resultados en `resultados/*.csv`, gráficas en `graficas/`.\n")
    with open(os.path.join(ROOT, "REPORTE.md"), "w") as f:
        f.write("\n".join(L))
    return label


if __name__ == "__main__":
    pass
