"""Verifica que en k = 24 la vela de entrada es la hora durante la cual la vela del
evento sale de la ventana movil de 24 h del "cambio 24h" de los exchanges."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from events import HOUR_MS, LAGS  # noqa: E402


def window_start(now_ms):
    """Inicio de la ventana de 24 h que un exchange usa para el 'cambio 24h' en now_ms."""
    return now_ms - 24 * HOUR_MS


def test_lag24_entry_candle_is_exit_hour():
    t_event = 1_780_000_000_000  # open de la vela del evento (ms UTC)
    event_open, event_close = t_event, t_event + HOUR_MS
    k = 24
    entry_open = t_event + k * HOUR_MS
    entry_close = entry_open + HOUR_MS
    # Al abrir la vela de entrada, el inicio de la ventana coincide con el open del evento:
    # la vela del evento aun esta (parcialmente) dentro.
    assert window_start(entry_open) == event_open
    # Al cerrar la vela de entrada, la ventana empieza en el close del evento: ya salio.
    assert window_start(entry_close) == event_close
    # Durante toda la vela de entrada, el inicio de la ventana recorre la vela del evento.
    for frac in np.linspace(0, 1, 11)[:-1]:
        now = entry_open + int(frac * HOUR_MS)
        assert event_open <= window_start(now) < event_close
    # En k = 23 la vela del evento sigue completamente dentro; en k = 25 ya salio del todo.
    assert window_start(t_event + 23 * HOUR_MS + HOUR_MS) == event_open
    assert window_start(t_event + 25 * HOUR_MS) > event_close - 1


def test_fade_index_arithmetic_on_grid():
    """fade_k calculado por build_coin_events usa la vela que abre en t + k horas."""
    import polars as pl
    from events import build_coin_events
    n = 120
    rng = np.random.default_rng(0)
    t = np.arange(n) * HOUR_MS + 1_780_000_000_000
    o = rng.uniform(90, 110, n)
    c = o * np.exp(rng.normal(0, 0.01, n))
    df = pl.DataFrame({"t": t, "T": t + HOUR_MS - 1, "o": o, "h": np.maximum(o, c),
                       "l": np.minimum(o, c), "c": c, "v": np.ones(n), "n": np.ones(n, dtype=int)})
    panel = build_coin_events("X", df, False)
    r = np.full(n, np.nan)
    r[1:] = np.log(c[1:] / c[:-1])
    for i in (30, 55, 80):
        row = panel.row(i, named=True)
        assert row["t"] == t[i]
        for k in LAGS:
            assert t[i + k] == t[i] + k * HOUR_MS
            expected = -np.sign(r[i]) * np.log(c[i + k] / o[i + k])
            assert np.isclose(row[f"fade_{k}"], expected), (i, k)
    # z_excl: la vela t no participa en media/desv
    i = 60
    w = r[i - 24:i]
    z = (r[i] - w.mean()) / w.std(ddof=1)
    assert np.isclose(panel["z_excl"][i], z)
    w2 = r[i - 23:i + 1]
    z2 = (r[i] - w2.mean()) / w2.std(ddof=1)
    assert np.isclose(panel["z_incl"][i], z2)


if __name__ == "__main__":
    test_lag24_entry_candle_is_exit_hour()
    test_fade_index_arithmetic_on_grid()
    print("tests OK")
