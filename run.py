"""Punto de entrada unico: regenera resultados/, graficas/ y REPORTE.md desde data/.
Uso:  python run.py            (si data/candles esta vacio, descarga primero)
      python run.py --download (fuerza la etapa de descarga; reanudable)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import download  # noqa: E402
import events    # noqa: E402
import analysis  # noqa: E402
import report    # noqa: E402


def main():
    if "--download" in sys.argv or not os.path.isdir(download.CANDLES) or not os.listdir(download.CANDLES):
        download.main()
    print("etapa 2: construyendo eventos...")
    panel, validation = events.build_all()
    filt = events.filter_report(panel)
    print(filt)
    print("etapa 3: analisis...")
    res = analysis.run(panel, validation, filt)
    print("reporte...")
    report.write(res, filt)
    print(res["D"])
    print("listo: REPORTE.md, resultados/, graficas/")


if __name__ == "__main__":
    main()
