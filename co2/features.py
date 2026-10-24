"""Étape 5 : mapping et feature engineering.

Attribue un véhicule et un facteur d'émission à chaque étape, calcule les
émissions, puis agrège au niveau du colis pour produire la table « Curated »
avec les colonnes demandées dans le cahier des charges.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import referentiels as R
from .modele import ClassifieurVehicule
from .nettoyage import Journal

ZONES = {"FR": "France", "ES": "Europe", "IT": "Europe", "DE": "Europe", "PL": "Europe", "BE": "Europe",
         "NL": "Europe", "CN": "Asie", "HK": "Asie", "KR": "Asie", "TR": "Europe", "MA": "Afrique",
         "US": "Amerique", "CA": "Amerique"}
MODE_DE_VEHICULE = {"ROUTE": "Camion", "VUL": "Camionnette", "VELO": "Vélo", "FER": "Train", "AIR": "Avion",
                    "MER": "Bateau"}


def preparer_etapes(et: pd.DataFrame, colis: pd.DataFrame, transporteurs: pd.DataFrame) -> pd.DataFrame:
    c = colis.set_index("tracking_id")
    et = et.copy()
    for col in ("service", "livraison", "client", "poids_kg", "pays_origine"):
        et[col] = et.tracking_id.map(c[col])
    et["zone_origine"] = et.pays_origine.map(ZONES)
    pop = R.villes_france().drop_duplicates("name").set_index("name").population
    et["population_dest"] = et.tracking_id.map(c.ville_destination).map(pop)
    et["mois"] = et.tracking_id.map(c.date_commande).dt.month
    et["vitesse_kmh"] = (et.distance_km / et.duree_h).where(et.duree_h > 0.05)
    et["vehicule_observe"] = et.transporteur_id.map(transporteurs.set_index("transporteur_id").code_vehicule)
    return et


def attribuer_vehicules(et: pd.DataFrame, clf: ClassifieurVehicule, j: Journal) -> pd.DataFrame:
    et = et.copy()
    veh = et.vehicule_observe.copy()
    source = pd.Series(np.where(veh.notna(), "transporteur", None), index=et.index, dtype=object)

    # Étapes internationales : le mode est fixé par la porte d'entrée, la classe par la distance ou la ligne
    air = et.type_etape.eq("INTERNATIONAL_AIR") | (et.type_etape.eq("INTERNATIONAL") & et.vers.eq("ENT-CDG"))
    veh[air] = [R.facteur_air(d) for d in et.distance_km[air]]
    mer = et.type_etape.eq("INTERNATIONAL_MER") | (et.type_etape.eq("INTERNATIONAL")
                                                     & et.vers.isin(["ENT-LEH", "ENT-RTM", "ENT-FOS"]))
    veh[mer] = [R.facteur_mer(p, v) for p, v in zip(et.pays_origine[mer], et.vers[mer])]
    pre = et.type_etape.eq("PRE_ACHEMINEMENT")
    veh[pre] = "ROUTE_ART_40T_DIESEL"
    source[(air | mer | pre) & source.isna()] = "regle_metier"
    source[(air | mer) & et.vehicule_observe.notna()] = "transporteur"

    inconnu = veh.isna()
    pred, confiance, proba = clf.predire(et[inconnu])
    # facteur attendu : moyenne des facteurs pondérée par les probabilités du modèle. Choisir la
    # seule classe la plus probable biaiserait le total (les véhicules rares ne seraient jamais tirés).
    f = R.table_facteurs().set_index("code_vehicule").kgco2e_tkm
    rapport_fer = (et.distance_vol_oiseau_km * C.DETOUR_FER / et.distance_km).where(et.distance_km > 0, 1.0)
    poids = pd.DataFrame({v: f[v] * (rapport_fer[inconnu] if v.startswith("FER") else 1.0) for v in proba.columns})
    et["facteur_attendu"] = np.nan
    et.loc[inconnu, "facteur_attendu"] = (proba * poids).sum(axis=1)
    veh[inconnu] = pred
    source[inconnu] = "modele_ml"
    et["vehicule"] = veh
    et["source_vehicule"] = source
    et["confiance_vehicule"] = np.nan
    et.loc[inconnu, "confiance_vehicule"] = confiance
    j.note("etapes", "véhicule connu par le transporteur", (source == "transporteur").sum(), "facteur direct")
    j.note("etapes", "véhicule fixé par règle métier (international)", (source == "regle_metier").sum(),
           "aérien selon distance, maritime selon la ligne, pré-acheminement routier")
    j.note("etapes", "véhicule prédit par le modèle", inconnu.sum(),
           f"transporteur inconnu ; confiance médiane {np.median(confiance):.0%}")
    return et


def calculer_emissions(et: pd.DataFrame) -> pd.DataFrame:
    f = R.table_facteurs().set_index("code_vehicule")
    et = et.copy()
    impute = et.facteur_attendu.notna()
    fer = et.vehicule.str.startswith("FER") & ~impute
    et.loc[fer, "distance_km"] = (et.distance_vol_oiseau_km[fer] * C.DETOUR_FER).round(2)
    et.loc[fer, "methode_distance"] = "vol_oiseau_x_1.30_fer"
    et["mode_transport"] = et.vehicule.str.split("_").str[0].map(MODE_DE_VEHICULE)
    et["facteur_kgco2e_tkm"] = et.facteur_attendu.where(impute, et.vehicule.map(f.kgco2e_tkm))
    et["base_carbone_id"] = et.vehicule.map(f.base_carbone_id)
    et["tonne_km"] = et.poids_kg / 1000 * et.distance_km
    et["emission_g"] = et.tonne_km * et.facteur_kgco2e_tkm * 1000
    return et


def agreger_colis(et: pd.DataFrame, colis: pd.DataFrame, scans: pd.DataFrame) -> pd.DataFrame:
    g = et.groupby("tracking_id")
    plateformes = et[et.vers.str.match(r"^(TRI|ENT|AG)-")].groupby("tracking_id").vers.nunique()
    observe = (et.source_vehicule.ne("modele_ml") & ~et.de_infere & ~et.vers_infere)
    dist_mode = et.groupby(["tracking_id", "mode_transport"]).distance_km.sum().reset_index()
    principal = dist_mode.sort_values("distance_km").drop_duplicates("tracking_id", keep="last")
    em_mode = et.pivot_table(index="tracking_id", columns="mode_transport", values="emission_g",
                             aggfunc="sum", fill_value=0)
    em_mode.columns = [f"emission_{m.lower()}_g".replace("é", "e") for m in em_mode.columns]
    sc = scans.groupby("tracking_id").horodatage_utc.agg(["min", "max"])
    livre = scans[scans.evenement.isin(["LIVRE", "LIVRE_RELAIS"])].groupby("tracking_id").size()
    suspect = scans.groupby("tracking_id").horodatage_suspect.any()

    df = colis.copy()
    t = df.tracking_id
    df["date_first_scan"] = t.map(sc["min"]).dt.tz_convert("Europe/Paris").dt.tz_localize(None)
    df["date_last_scan"] = t.map(sc["max"]).dt.tz_convert("Europe/Paris").dt.tz_localize(None)
    df["statut"] = np.where(t.map(livre).fillna(0) > 0, "livre", "en_transit_ou_non_flashe")
    df["delai_livraison_h"] = ((df.date_last_scan - df.date_commande).dt.total_seconds() / 3600).where(
        df.statut == "livre")
    df["chronologie_suspecte"] = t.map(suspect).fillna(False).astype(bool)
    df["nb_plateformes"] = t.map(plateformes).fillna(0).astype(int)
    df["nb_etapes"] = t.map(g.size()).fillna(0).astype(int)
    df["nb_etapes_inferees"] = t.map(g.apply(lambda x: (x.de_infere | x.vers_infere).sum())).fillna(0).astype(int)
    df["nb_vehicules_predits"] = t.map(g.source_vehicule.apply(lambda s: (s == "modele_ml").sum())).fillna(0).astype(int)
    df["taux_observation"] = t.map(observe.groupby(et.tracking_id).mean()).round(3)
    df["distance_estimee_km"] = t.map(g.distance_km.sum()).round(1)
    df["tonne_km"] = t.map(g.tonne_km.sum())
    df["mode_transport"] = t.map(principal.set_index("tracking_id").mode_transport)
    df["emission_estimee_g"] = t.map(g.emission_g.sum()).round(2)
    df["facteur_emission_moyen_g_tkm"] = (df.emission_estimee_g / df.tonne_km).round(1)
    for col in em_mode.columns:
        df[col] = t.map(em_mode[col]).fillna(0).round(2)
    dk = et[et.type_etape == "DERNIER_KM"].set_index("tracking_id")
    df["vehicule_dernier_km"] = t.map(dk.vehicule)
    df["emission_dernier_km_g"] = t.map(dk.emission_g).round(2)
    return df
