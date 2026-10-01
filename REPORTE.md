# Fase 0 — Fade de velas extremas 24 h después (Hyperliquid)

_Generado por `python run.py` el 2026-10-01 21:33 UTC._

## 1. Veredicto

**DESCARTAR.** El rendimiento neto en k = 24 no sobrevive en ningún cuartil de liquidez ni en ningún umbral: el rendimiento bruto medio del fade en k = 24 (+6.8, +7.0, +8.0, +10.9, +11.1, +13.5 pb para los umbrales 3, 3.5, 4, 4.5, 5, 6) es menor que el costo mínimo de ida y vuelta (13 pb en el cuartil más líquido), y la media neta en Q1 es negativa en todos los umbrales (mejor caso: umbral 4.5, neto -5.0 pb, IC [-19.3, +11.2]). El pico en k = 24 (D) tampoco sobrevive al criterio: su IC 95 % incluye cero en los 6 umbrales.

**Matiz que no cambia el veredicto.** D es positivo en los 6 umbrales y crece con el umbral, k = 24 es el máximo de la curva en 6 de 6 umbrales, y el placebo es plano. La muestra no refuta el mecanismo de la ventana de 24 h: lo deja sin potencia (ver abajo). Pero aun si el efecto fuera real con el tamaño observado (≈ 4-11 pb), no cubre las comisiones, así que más datos no cambiarían la decisión operativa. La única señal exploratoria con IC que excluye cero es D en eventos verdes (fade corto) para los umbrales 3.0 y 3.5 (sección 4.3), y D en Q2 para umbrales ≥ 4.0 (sección 4.4): son 2 de muchas comparaciones y sus rendimientos netos siguen siendo ≤ 0 o con IC que incluye cero.

**¿Alcanza la muestra?** En el umbral con más eventos (≥ 100), 3 (n = 24,002, 953 días), D = +4.1 pb con IC 95 % [-3.5, +11.0] pb. Si el efecto real fuera del tamaño del D observado, harían falta ≈ 74,610 eventos del mismo tipo para que el IC lo excluyera (escala 1/√n), es decir ≈ 3.1× la historia actual en días. Sobre la pregunta mecanicista aislada (¿existe el pico en 24 h?) el estudio es INCONCLUSO con esa necesidad de muestra; sobre la pregunta operativa (¿se puede operar con beneficio neto?) la respuesta es no.

Tabla de D = fade_24 − promedio(fade_22, fade_23, fade_25, fade_26) (incluye monedas deslistadas; pb = puntos básicos, 1 pb = 0.01 %):

| umbral | eventos | días | D (pb) | IC 95 % (pb) | excluye 0 |
|---|---|---|---|---|---|
| 3 | 24,002 | 953 | +4.1 | [-3.5, +11.0] | no |
| 3.5 | 14,580 | 869 | +4.0 | [-3.5, +11.9] | no |
| 4 | 9,317 | 757 | +4.8 | [-3.6, +14.1] | no |
| 4.5 | 6,174 | 652 | +7.7 | [-2.3, +20.8] | no |
| 5 | 4,221 | 566 | +8.3 | [-3.9, +23.4] | no |
| 6 | 2,198 | 443 | +11.3 | [-4.1, +29.8] | no |

Sin deslistadas:

| umbral | eventos | D (pb) | IC 95 % (pb) |
|---|---|---|---|
| 3 | 19,121 | +3.6 | [-5.3, +11.8] |
| 3.5 | 11,588 | +3.0 | [-6.1, +12.4] |
| 4 | 7,368 | +3.1 | [-7.2, +14.5] |
| 4.5 | 4,877 | +5.3 | [-6.2, +20.9] |
| 5 | 3,284 | +6.4 | [-7.8, +25.5] |
| 6 | 1,668 | +10.4 | [-7.6, +33.8] |

## 2. Muestra

| métrica | valor |
|---|---|
| monedas en el universo (`meta`) | 234 |
| monedas con velas | 234 |
| de ellas marcadas `isDelisted` | 56 |
| velas 1 h totales | 1,147,017 |
| velas por moneda (mediana / máx) | 5001 / 5,003 |
| rango de fechas, monedas activas | 2026-03-07 10:00 UTC → 2026-10-01 20:00 UTC (208 días) |
| rango de fechas, monedas deslistadas | 2023-10-07 00:00 UTC → 2026-08-26 10:00 UTC |
| monedas con huecos | 0 |
| horas faltantes en total | 0 |
| velas que pasan todos los filtros | 1,053,881 |

La API devuelve como máximo ~5,000 velas por moneda, por eso el histórico de las monedas activas es de ~208 días y menos para las listadas después. **Las monedas deslistadas son distintas:** sus 5,000 velas terminan en la fecha de deslistado, así que cubren periodos anteriores (2023-2026) que no se solapan con el de las activas. Incluirlas añade días calendario independientes (ver columna 'días' en la tabla de D) pero mezcla regímenes de mercado y monedas que acabaron deslistadas (sesgo de supervivencia inverso). El detalle por moneda está en `resultados/validacion_velas.csv`.

## 3. Etapa 2 — Eventos y filtros

Definiciones aplicadas literalmente: r_t = ln(close_t/close_{t−1}); z_excl(t) usa media y desviación estándar muestral (ddof = 1) de r_{t−24..t−1} (vela t excluida); evento si |z_excl| ≥ umbral; fade_k = −signo(r_t)·ln(close_{t+k}/open_{t+k}) con k = 18..30 sobre una rejilla horaria completa (los huecos se reindexan como nulos, de modo que t + k siempre son horas de reloj, no filas). El test `tests/test_lag24.py` verifica que en k = 24 la vela de entrada es exactamente la hora en que la vela del evento sale de la ventana de 24 h.

Filtros aplicados en secuencia (cuántos candidatos elimina cada uno):

| umbral | candidatos | −primeras 72 h | −ventana incompleta (inicio/fin de historia) | −hueco o volumen 0 en [t−24, t+30] | eventos válidos | de ellos en deslistadas |
|---|---|---|---|---|---|---|
| 3 | 26,574 | 213 | 128 | 2231 | 24,002 | 4881 |
| 3.5 | 16,285 | 119 | 75 | 1511 | 14,580 | 2992 |
| 4 | 10,525 | 81 | 46 | 1081 | 9,317 | 1949 |
| 4.5 | 7,070 | 63 | 30 | 803 | 6,174 | 1297 |
| 5 | 4,929 | 54 | 22 | 632 | 4,221 | 937 |
| 6 | 2,664 | 34 | 13 | 419 | 2,198 | 530 |

**z_incl vs z_excl.** Con la vela t incluida en las 24 (versión del autor original), la desigualdad de Samuelson acota |z_incl| ≤ (n−1)/√n = 23/√24 ≈ 4.69; el máximo observado es 4.68, frente a 66.4 con z_excl. Por eso los umbrales 5.0 y 6.0 son inalcanzables con z_incl y la comparación de conteos es:

| umbral | eventos z_excl | eventos z_incl |
|---|---|---|
| 3 | 24,002 | 9,704 |
| 3.5 | 14,580 | 3,403 |
| 4 | 9,317 | 844 |
| 4.5 | 6,174 | 78 |
| 5 | 4,221 | 0 |
| 6 | 2,198 | 0 |

## 4. Etapa 3 — Resultados

Todos los IC son al 95 % por bootstrap de conglomerados por día calendario UTC (2,000 remuestreos). Las gráficas `graficas/curva_rezagos_<umbral>.png` muestran la curva con su banda, la línea en k = 24 y el placebo.

### 4.1 Curva por rezago (media del fade en pb, con deslistadas)

| umbral | n | k=18 | k=19 | k=20 | k=21 | k=22 | k=23 | k=24 | k=25 | k=26 | k=27 | k=28 | k=29 | k=30 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | 24,002 | -1.6 | +1.1 | -5.3 | +3.4 | +2.5 | +3.8 | +6.8 | +2.3 | +2.4 | +1.4 | **-3.6** | -0.6 | +3.4 |
| 3.5 | 14,580 | -2.3 | +0.7 | -6.2 | +2.6 | +2.7 | +3.2 | **+7.0** | +3.8 | +2.1 | +1.9 | -2.9 | -1.0 | +3.7 |
| 4 | 9,317 | -3.3 | -0.2 | **-8.0** | +3.0 | +3.2 | +3.3 | +8.0 | +4.6 | +1.6 | +3.1 | -2.9 | -0.4 | +3.8 |
| 4.5 | 6,174 | -3.4 | +0.0 | **-10.0** | +3.1 | +2.1 | +3.6 | **+10.9** | +4.7 | +2.2 | +4.0 | -1.3 | +1.1 | +3.8 |
| 5 | 4,221 | -4.0 | -1.0 | **-11.2** | +0.9 | +1.7 | +4.4 | +11.1 | +3.9 | +1.4 | +4.4 | -1.1 | +3.1 | +3.1 |
| 6 | 2,198 | -1.5 | +1.9 | **-12.4** | +0.9 | +1.2 | +2.9 | +13.5 | +5.3 | -0.5 | +6.3 | -2.0 | +6.0 | -1.0 |

(negrita = IC 95 % excluye cero). IC completos en `resultados/curva_rezagos.csv`.

### 4.2 Placebo (timestamps y dirección aleatorios, pb)

| umbral | n | k=18 | k=19 | k=20 | k=21 | k=22 | k=23 | k=24 | k=25 | k=26 | k=27 | k=28 | k=29 | k=30 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | 24,002 | -0.7 | -0.5 | -0.7 | -1.3 | +0.9 | +0.9 | -0.5 | -0.8 | +0.3 | -1.6 | -0.1 | +0.5 | -0.0 |
| 3.5 | 14,580 | +0.2 | +0.8 | +0.2 | +0.3 | +1.0 | -1.4 | +0.2 | +0.6 | -1.5 | +0.2 | -0.1 | -2.0 | -0.6 |
| 4 | 9,317 | +0.7 | -2.1 | +1.3 | -1.3 | -1.3 | -0.8 | +0.5 | +0.9 | -0.1 | +0.2 | +0.3 | +0.5 | +0.0 |
| 4.5 | 6,174 | -1.4 | -0.3 | +1.0 | -0.5 | +1.3 | -2.6 | +0.6 | -1.5 | +3.4 | -0.9 | -2.9 | -0.8 | +0.5 |
| 5 | 4,221 | -2.9 | -4.0 | +3.8 | -0.3 | +0.9 | -2.0 | -2.1 | +0.4 | +2.3 | +1.8 | +0.9 | -0.6 | -0.9 |
| 6 | 2,198 | +1.2 | +4.5 | +2.4 | -3.0 | -0.6 | +3.6 | +5.2 | -1.3 | -1.9 | -3.9 | -1.8 | -1.7 | +0.6 |

### 4.3 Por dirección

| umbral | dirección | n | fade_24 (pb) | IC | D (pb) | IC de D | k máx |
|---|---|---|---|---|---|---|---|
| 3 | verde (fade corto) | 12,804 | +10.2 | [+4.0, +16.5] | +7.3 | [+1.5, +13.2] | 24 |
| 3 | roja (fade largo) | 11,198 | +3.0 | [-9.8, +14.8] | +0.5 | [-12.8, +12.0] | 26 |
| 3.5 | verde (fade corto) | 7,820 | +9.6 | [+3.6, +15.8] | +6.5 | [+0.6, +12.4] | 24 |
| 3.5 | roja (fade largo) | 6,760 | +3.9 | [-9.8, +19.1] | +1.2 | [-13.3, +16.1] | 26 |
| 4 | verde (fade corto) | 4,978 | +9.3 | [+2.6, +16.0] | +5.4 | [-0.9, +12.1] | 24 |
| 4 | roja (fade largo) | 4,339 | +6.5 | [-8.4, +24.5] | +4.2 | [-11.3, +22.9] | 26 |
| 4.5 | verde (fade corto) | 3,322 | +11.4 | [+3.9, +18.8] | +6.1 | [-1.6, +13.9] | 22 |
| 4.5 | roja (fade largo) | 2,852 | +10.3 | [-7.6, +35.5] | +9.5 | [-8.8, +34.1] | 24 |
| 5 | verde (fade corto) | 2,285 | +10.0 | [+1.7, +18.4] | +4.7 | [-4.1, +13.9] | 22 |
| 5 | roja (fade largo) | 1,936 | +12.4 | [-8.9, +41.3] | +12.5 | [-9.4, +40.7] | 24 |
| 6 | verde (fade corto) | 1,236 | +14.5 | [+3.3, +25.5] | +8.4 | [-4.1, +21.7] | 22 |
| 6 | roja (fade largo) | 962 | +12.3 | [-16.6, +51.5] | +15.0 | [-15.2, +54.2] | 24 |

### 4.4 Por liquidez y costos en k = 24

Cuartiles por volumen medio **por hora** en USD de las 24 h previas (cortes fijados con los eventos de umbral 3.0: 5 k, 13 k, 61 k). Q1 = más líquido. Costo = comisión taker 0.045 % por lado + deslizamiento por lado de 0.02 % / 0.05 % / 0.10 % / 0.20 % (Q1→Q4).

| umbral | cuartil | n | vol USD/h mediana (prev. 24 h) | costo RT (pb) | bruto k=24 (pb) | neto k=24 (pb) | IC neto | D (pb) | IC de D |
|---|---|---|---|---|---|---|---|---|---|
| 3 | Q1 | 6,001 | 202 k | 13 | +11.3 | -1.7 | [-9.9, +6.2] | +7.8 | [-0.1, +15.9] |
| 3 | Q2 | 6,000 | 26 k | 19 | +7.4 | -11.6 | [-18.1, -5.0] | +3.8 | [-3.1, +10.6] |
| 3 | Q3 | 6,000 | 8 k | 29 | +6.1 | -22.9 | [-30.5, -15.7] | +3.5 | [-4.8, +11.4] |
| 3 | Q4 | 6,001 | 3 k | 49 | +2.5 | -46.5 | [-54.2, -39.0] | +1.3 | [-7.0, +9.4] |
| 3 | todos | 24,002 | 13 k | 28 | +6.8 | -20.7 | [-27.5, -14.2] | — | — |
| 3.5 | Q1 | 3,619 | 198 k | 13 | +9.1 | -3.9 | [-13.7, +6.3] | +3.6 | [-6.8, +14.2] |
| 3.5 | Q2 | 3,628 | 26 k | 19 | +9.7 | -9.3 | [-16.6, -1.4] | +6.8 | [-1.1, +15.2] |
| 3.5 | Q3 | 3,641 | 8 k | 29 | +6.8 | -22.2 | [-31.6, -12.9] | +4.0 | [-6.5, +13.9] |
| 3.5 | Q4 | 3,692 | 3 k | 49 | +2.4 | -46.6 | [-53.7, -39.3] | +1.8 | [-6.3, +9.8] |
| 3.5 | todos | 14,580 | 13 k | 28 | +7.0 | -20.6 | [-27.6, -12.4] | — | — |
| 4 | Q1 | 2,270 | 194 k | 13 | +6.3 | -6.7 | [-18.7, +6.1] | +1.6 | [-10.7, +14.9] |
| 4 | Q2 | 2,309 | 25 k | 19 | +15.0 | -4.0 | [-13.6, +6.9] | +12.3 | [+1.9, +24.4] |
| 4 | Q3 | 2,321 | 8 k | 29 | +8.0 | -21.0 | [-31.6, -9.4] | +4.5 | [-6.2, +16.5] |
| 4 | Q4 | 2,417 | 3 k | 49 | +3.0 | -46.0 | [-53.6, -38.4] | +1.1 | [-7.4, +9.1] |
| 4 | todos | 9,317 | 13 k | 28 | +8.0 | -19.8 | [-27.5, -10.3] | — | — |
| 4.5 | Q1 | 1,494 | 197 k | 13 | +8.0 | -5.0 | [-19.3, +11.2] | +2.0 | [-13.0, +18.6] |
| 4.5 | Q2 | 1,514 | 25 k | 19 | +18.5 | -0.5 | [-12.2, +14.0] | +15.9 | [+3.3, +30.7] |
| 4.5 | Q3 | 1,541 | 8 k | 29 | +13.7 | -15.3 | [-27.2, -0.8] | +11.7 | [-0.8, +26.9] |
| 4.5 | Q4 | 1,625 | 3 k | 49 | +3.7 | -45.3 | [-53.9, -36.6] | +1.5 | [-7.6, +11.2] |
| 4.5 | todos | 6,174 | 13 k | 28 | +10.9 | -17.1 | [-26.3, -5.1] | — | — |
| 5 | Q1 | 961 | 195 k | 13 | +2.7 | -10.3 | [-28.6, +10.1] | -2.2 | [-21.2, +18.9] |
| 5 | Q2 | 1,034 | 25 k | 19 | +21.3 | +2.3 | [-12.0, +19.0] | +19.9 | [+4.4, +38.1] |
| 5 | Q3 | 1,068 | 8 k | 29 | +18.3 | -10.7 | [-26.1, +8.1] | +15.3 | [-1.0, +34.7] |
| 5 | Q4 | 1,158 | 3 k | 49 | +2.4 | -46.6 | [-57.2, -36.0] | +0.1 | [-11.8, +12.2] |
| 5 | todos | 4,221 | 12 k | 28 | +11.1 | -17.3 | [-28.7, -2.8] | — | — |
| 6 | Q1 | 485 | 180 k | 13 | -0.8 | -13.8 | [-38.8, +10.6] | -4.0 | [-32.3, +23.0] |
| 6 | Q2 | 533 | 26 k | 19 | +23.5 | +4.5 | [-16.5, +25.2] | +23.1 | [+0.6, +46.0] |
| 6 | Q3 | 539 | 8 k | 29 | +25.2 | -3.8 | [-24.5, +22.8] | +22.2 | [-0.4, +49.8] |
| 6 | Q4 | 641 | 3 k | 49 | +6.3 | -42.7 | [-55.6, -28.2] | +3.9 | [-10.5, +19.9] |
| 6 | todos | 2,198 | 12 k | 29 | +13.5 | -15.4 | [-29.7, +3.1] | — | — |

### 4.5 Simulación sin solapamiento (umbral 4.0, neto de costos, tamaño fijo)

Regla: una moneda queda ocupada desde la señal (t) hasta la salida (t + 25 h); las señales que llegan mientras está ocupada se omiten. Rendimientos en fracción del tamaño fijo, no compuestos.

| métrica | todos los cuartiles | solo Q1 (más líquido) |
|---|---|---|
| eventos con |z_excl| ≥ 4.0 | 9,317 | 2,270 |
| operaciones ejecutadas | 8,028 | 1,985 |
| omitidas por solapamiento | 1289 | 285 |
| rendimiento medio bruto | +7.7 pb | +3.7 pb |
| rendimiento medio neto | -20.6 pb | -9.3 pb |
| rendimiento total neto (suma, % del tamaño fijo) | -1652.5 % | -185.0 % |
| tasa de acierto (neto > 0) | 37.5 % | 44.8 % |
| peor operación neta | -15.99 % | -15.99 % |
| mejor operación neta | +21.98 % | +13.52 % |
| drawdown máximo de la curva acumulada | -1661.3 % | -203.1 % |

Curva: `graficas/simulacion_equity.png`; operaciones: `resultados/simulacion_operaciones.csv`.

## 5. Limitaciones

- **Histórico corto.** La API solo entrega ~5,000 velas por moneda: ~208 días (2026-03-07 a 2026-10-01) para las monedas activas. Es un único régimen de mercado; cualquier efecto estacional o de régimen no es observable. Las deslistadas aportan ventanas de 2023-2026 pero son monedas que terminaron deslistadas.
- **Pocos conglomerados independientes.** Los eventos se agrupan en días de movimiento general; el bootstrap por día tiene ~208 conglomerados sin deslistadas y los IC resultantes son anchos (ver la tabla de D). Los IC de los cortes por dirección y cuartil son más anchos todavía.
- **Costos supuestos.** El deslizamiento por cuartil es un supuesto, no una medición del libro de órdenes. El rendimiento neto es muy sensible a él en los cuartiles menos líquidos.
- **Entrada al open de la vela.** Se asume ejecución exacta al open de t + k y salida al close; en la práctica la ejecución tendría latencia y el 'open' de una vela de 1 h no es un precio negociable garantizado.
- **Múltiples comparaciones.** Se evalúan 6 umbrales × 13 rezagos × cortes; algún IC que excluya cero por azar es esperable. La prueba preregistrada es D en k = 24, no el mejor rezago.
- **Deslistadas.** Las monedas marcadas `isDelisted` se incluyen en el análisis principal y se reportan aparte; sus series terminan antes y pueden tener liquidez degradada al final.
- **z_incl.** Solo se calculó para comparación; los umbrales altos no son alcanzables con esa definición.

## 6. Reproducibilidad

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run.py          # descarga (reanudable) + eventos + análisis + reporte
.venv/bin/python tests/test_lag24.py
```

Fuente de datos: exclusivamente `POST https://api.hyperliquid.xyz/info` (`meta`, `candleSnapshot`). Semilla del bootstrap/placebo: fija. Resultados en `resultados/*.csv`, gráficas en `graficas/`.
