"""Exécute le pipeline complet : python run_pipeline.py [--regenerer-sources]"""
import argparse
import logging
import sys

from co2 import config as C
from co2.pipeline import executer

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Pipeline de data wrangling du calculateur CO2 FastColis")
    p.add_argument("--regenerer-sources", action="store_true",
                   help="régénère les extractions internes fictives (SAP, flashages, transporteurs)")
    args = p.parse_args()
    C.REPORTS.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(C.REPORTS / "pipeline.log", mode="w", encoding="utf-8")])
    r = executer(args.regenerer_sources)["resume"]
    print(f"\n{r['colis']} colis, {r['etapes_transport']} étapes, {r['emission_totale_t']} t CO2e au total")
    if r["evaluation"]:
        e = r["evaluation"]["emission_reconstituee"]
        print(f"Erreur médiane sur l'émission d'un colis : {e['erreur_mediane_pct']} % "
              f"(biais total {e['biais_total_pct']} %)")
