"""Étape 1 : découverte des sources.

Le profilage repose sur une idée simple : réduire chaque valeur à sa « forme »
(chiffres -> 9, lettres -> A). Les formes rares ou multiples révèlent les formats
concurrents (dates, unités, codes) avant même d'écrire la moindre règle.
"""
from __future__ import annotations

import re

import pandas as pd

from . import config as C


def forme(valeur) -> str:
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return "∅"
    s = re.sub(r"[0-9]", "9", str(valeur))
    s = re.sub(r"[^\W\d_]", "A", s)
    return re.sub(r"(9)\1{3,}", lambda m: f"9{{{len(m.group(0))}}}", re.sub(r"(A)\1{3,}",
                  lambda m: f"A{{{len(m.group(0))}}}", s))


def profiler(df: pd.DataFrame, echantillon: int = 50_000) -> pd.DataFrame:
    ech = df.sample(min(len(df), echantillon), random_state=C.SEED) if len(df) > echantillon else df
    lignes = []
    for col in [c for c in df.columns if not c.startswith("_")]:
        s = df[col]
        formes = ech[col].map(forme).value_counts(normalize=True)
        top = s.value_counts().head(3)
        lignes.append({
            "colonne": col,
            "manquants_pct": round(100 * s.isna().mean(), 1),
            "distincts": int(s.nunique()),
            "formes": " | ".join(f"`{f}` {p:.0%}" for f, p in formes.head(4).items()),
            "valeurs_frequentes": ", ".join(f"{v} ({n})" for v, n in top.items()),
        })
    return pd.DataFrame(lignes)


def constats(raw: dict[str, pd.DataFrame]) -> list[str]:
    """Problèmes repérés automatiquement, formulés pour le rapport."""
    sap, fl = raw["sap"], raw["flashages"]
    sites = set(raw["sites"].site_code)
    out = []
    n_dup = sap.TRACKING.duplicated().sum()
    out.append(f"SAP : {len(sap):,} lignes pour {sap.TRACKING.nunique():,} numéros de suivi, "
               f"soit {n_dup:,} lignes en double.")
    out.append("SAP : formats de date ERDAT rencontrés : " + ", ".join(
        f"`{f}` ({n:,})" for f, n in sap.ERDAT.map(forme).value_counts().items()) + ".")
    out.append("SAP : unités de poids GEWEI : " + ", ".join(
        f"{u or 'vide'} ({n:,})" for u, n in sap.GEWEI.fillna("").value_counts().items()) + ".")
    poids = pd.to_numeric(sap.BRGEW.str.replace(",", ".", regex=False), errors="coerce")
    out.append(f"SAP : {poids.isna().sum():,} poids illisibles ou vides, {(poids <= 0).sum():,} nuls ou "
               f"négatifs, {((sap.GEWEI == 'KG') & (poids > C.MAX_POIDS_KG)).sum():,} poids > "
               f"{C.MAX_POIDS_KG} « kg » (probablement des grammes).")
    out.append(f"SAP : {sap.NAME1.nunique()} libellés clients pour {sap.KUNNR.nunique()} codes clients.")
    out.append(f"SAP : {sap.LAND1_ORIG.nunique()} écritures de pays d'origine "
               f"({', '.join(sorted(sap.LAND1_ORIG.dropna().unique())[:12])}...).")
    out.append(f"SAP : codes de service VSART : {', '.join(sorted(sap.VSART.dropna().unique()))}.")
    out.append(f"Flashages : {len(fl):,} événements, {fl.firmware.value_counts().get('v1', 0):,} au format v1 "
               f"(epoch en ms, codes courts) et {fl.firmware.value_counts().get('v2', 0):,} au format v2 (ISO 8601).")
    out.append("Flashages : codes d'événements : " + ", ".join(sorted(fl.evenement.unique())) + ".")
    codes = fl.site.str.strip().str.upper()
    relais = codes.str.startswith("PR-")
    inconnus = codes[~codes.isin(sites) & ~relais].value_counts()
    out.append(f"Flashages : {relais.sum():,} dépôts en point relais ({codes[relais].nunique():,} relais, "
               f"non référencés : normal). Hors relais, {inconnus.sum():,} scans portent {len(inconnus)} codes "
               f"absents du référentiel ({', '.join(inconnus.index[:10])}...).")
    out.append(f"Flashages : formes des numéros de suivi : " + ", ".join(
        f"`{f}` ({n:,})" for f, n in fl.tracking.map(forme).value_counts().head(5).items()) + ".")
    out.append(f"Flashages : {fl.lat.isna().mean():.0%} des scans sans GPS, "
               f"{fl.transporteur.isna().mean():.0%} sans transporteur.")
    ts_naif = fl[(fl.firmware == "v2") & ~fl.horodatage.str.contains(r"[+-]\d\d:\d\d$|Z$", regex=True)]
    out.append(f"Flashages : {len(ts_naif):,} horodatages v2 sans fuseau horaire.")
    st = raw["transporteurs_sous_traitants"]
    out.append(f"Transporteurs : {len(raw['transporteurs_internes'])} flottes internes et {len(st)} lignes "
               f"sous-traitants dont {st['ID transporteur'].str.upper().duplicated().sum()} doublons ; "
               f"{st['Catégorie'].isna().sum()} sans catégorie de véhicule.")
    s = raw["sites"]
    out.append(f"Sites : {len(s)} sites, {s.lat.isna().sum()} sans coordonnées, décimales à la virgule.")
    return [re.sub(r"(?<=\d),(?=\d{3}\b)", "\u202f", ligne) for ligne in out]


def rapport(raw: dict[str, pd.DataFrame]) -> str:
    parties = ["# Rapport de découverte des sources\n",
               "Généré automatiquement par `co2.decouverte` (étape 1 du pipeline). Une *forme* remplace "
               "chaque chiffre par `9` et chaque lettre par `A` : plusieurs formes pour une même colonne "
               "signalent des formats concurrents.\n",
               "## Constats principaux\n"]
    parties += [f"* {c}" for c in constats(raw)]
    for nom, df in raw.items():
        parties.append(f"\n## Table `{nom}` ({len(df):,} lignes, {df.shape[1]} colonnes)\n")
        parties.append(profiler(df).to_markdown(index=False))
    texte = "\n".join(parties) + "\n"
    C.REPORTS.mkdir(exist_ok=True)
    (C.REPORTS / "01_decouverte.md").write_text(texte, encoding="utf-8")
    return texte
