"""Étape 2 : ingestion des sources hétérogènes, sans transformation métier.

Chaque lecteur rend les données telles qu'elles arrivent (tout en texte) avec deux
colonnes de traçabilité : le fichier d'origine et le numéro de ligne. Les tables
sont ensuite figées en Parquet dans data/raw pour que les étapes suivantes ne
relisent jamais les fichiers sources.
"""
from __future__ import annotations

import json

import pandas as pd

from . import config as C

RAW = C.DATA / "raw"


def lire_sap() -> pd.DataFrame:
    """Export SAP : CSV Windows-1252, séparateur ';', décimales à la virgule."""
    chemin = C.SOURCES / "sap_export_colis.csv"
    df = pd.read_csv(chemin, sep=";", encoding="cp1252", dtype=str, keep_default_na=False)
    df = df.replace({"": None})
    df["_fichier"] = chemin.name
    df["_ligne"] = range(2, len(df) + 2)
    return df


def lire_flashages() -> pd.DataFrame:
    """Logs JSON Lines des scanners. Deux générations de firmware cohabitent :

    v1 : {"trk", "evt" (code court), "site", "ts" (epoch ms UTC), "gps": "lat,lon", "carrier"}
    v2 : {"tracking_id", "event_type", "site_code", "timestamp" (ISO 8601), "geo": {lat, lon}, "carrier_id"}
    """
    lignes = []
    for chemin in sorted((C.SOURCES / "flashages").glob("flashages_*.jsonl")):
        with open(chemin, encoding="utf-8") as f:
            for n, brut in enumerate(f, 1):
                d = json.loads(brut)
                if "trk" in d:
                    lat, lon = (d["gps"].split(",") + [None])[:2] if d.get("gps") else (None, None)
                    lignes.append(("v1", d["trk"], d["evt"], d["site"], str(d["ts"]), lat, lon,
                                   d.get("carrier"), chemin.name, n))
                else:
                    geo = d.get("geo") or {}
                    lignes.append(("v2", d["tracking_id"], d["event_type"], d["site_code"], d["timestamp"],
                                   geo.get("lat"), geo.get("lon"), d.get("carrier_id"), chemin.name, n))
    cols = ["firmware", "tracking", "evenement", "site", "horodatage", "lat", "lon", "transporteur",
            "_fichier", "_ligne"]
    df = pd.DataFrame(lignes, columns=cols)
    for c in ("lat", "lon"):
        df[c] = df[c].astype("string")
    return df


def lire_transporteurs() -> dict[str, pd.DataFrame]:
    """Annuaire Excel : deux onglets aux colonnes différentes."""
    chemin = C.SOURCES / "transporteurs.xlsx"
    onglets = pd.read_excel(chemin, sheet_name=None, dtype=str)
    for nom, df in onglets.items():
        df["_fichier"] = f"{chemin.name}#{nom}"
        df["_ligne"] = range(2, len(df) + 2)
    return onglets


def lire_sites() -> tuple[pd.DataFrame, pd.DataFrame]:
    sites = pd.read_csv(C.SOURCES / "sites_reseau.csv", sep=";", encoding="utf-8-sig", dtype=str)
    alias = pd.read_csv(C.SOURCES / "sites_alias_wms.csv", dtype=str)
    return sites, alias


def ingerer() -> dict[str, pd.DataFrame]:
    """Charge toutes les sources et les fige en Parquet (couche brute)."""
    RAW.mkdir(parents=True, exist_ok=True)
    tables = {"sap": lire_sap(), "flashages": lire_flashages()}
    for nom, df in lire_transporteurs().items():
        cle = "transporteurs_internes" if "interne" in nom.lower() else "transporteurs_sous_traitants"
        tables[cle] = df
    tables["sites"], tables["sites_alias"] = lire_sites()
    for nom, df in tables.items():
        df.to_parquet(RAW / f"{nom}.parquet", index=False)
    return tables


def charger_raw() -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_parquet(p) for p in RAW.glob("*.parquet")}
