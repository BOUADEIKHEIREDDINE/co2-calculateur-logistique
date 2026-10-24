"""Étape 6 : validation.

Deux niveaux :

1. des règles de cohérence, applicables à de vraies données (bornes, sommes,
   inégalité triangulaire, vitesses, unicité...) ;
2. une évaluation contre la vérité terrain de la simulation, possible ici parce
   que les données internes sont fictives : on mesure l'erreur réelle des
   émissions estimées et le taux de détection de chaque défaut injecté.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import referentiels as R
from .geo import haversine_km
from .nettoyage import fr

BORNES_FACTEURS = {"route": (0.03, 1.5), "vul": (0.05, 1.5), "velo": (0.001, 0.1), "fer": (0.001, 0.06),
                   "mer": (0.001, 0.06), "air": (0.4, 6.0)}
VITESSE_MAX = {"Camion": 110, "Camionnette": 90, "Vélo": 30, "Train": 160, "Avion": 950, "Bateau": 50}


def regles(colis: pd.DataFrame, et: pd.DataFrame) -> pd.DataFrame:
    r = []

    def ajoute(nom, description, ko, total):
        r.append({"regle": nom, "description": description, "anomalies": int(ko), "controles": int(total),
                  "statut": "OK" if ko == 0 else ("ALERTE" if ko / max(total, 1) < 0.01 else "ECHEC")})

    ajoute("unicite_tracking", "un numéro de suivi par colis", colis.tracking_id.duplicated().sum(), len(colis))
    ajoute("poids_borne", f"poids dans ]0 ; {C.MAX_POIDS_KG}] kg",
           (~colis.poids_kg.between(0.001, C.MAX_POIDS_KG)).sum(), len(colis))
    ajoute("volume_borne", "volume < 0,5 m3 quand il est connu", (colis.volume_m3 > 0.5).sum(),
           colis.volume_m3.notna().sum())
    direct = haversine_km(colis.lat_orig, colis.lon_orig, colis.lat_dest, colis.lon_dest)
    ajoute("inegalite_triangulaire", "distance parcourue >= distance à vol d'oiseau origine-destination",
           (colis.distance_estimee_km < 0.95 * direct).sum(), len(colis))
    ajoute("distance_positive", "aucune étape de distance négative ou > 25 000 km",
           ((et.distance_km < 0) | (et.distance_km > 25_000)).sum(), len(et))
    somme = et.groupby("tracking_id").emission_g.sum()
    ecart = (colis.set_index("tracking_id").emission_estimee_g - somme).abs()
    ajoute("total_egal_sous_totaux", "émission du colis = somme des émissions de ses étapes", (ecart > 0.01).sum(),
           len(colis))
    ajoute("facteur_reference", "chaque étape a un facteur du référentiel", et.facteur_kgco2e_tkm.isna().sum(), len(et))
    f = R.table_facteurs()
    hors = [not (BORNES_FACTEURS[m][0] <= v <= BORNES_FACTEURS[m][1]) for m, v in zip(f["mode"], f.kgco2e_tkm)]
    ajoute("facteurs_plausibles", "facteurs ADEME dans les bornes attendues par mode", sum(hors), len(f))
    v = et[et.duree_h > 0.25]
    trop = (v.distance_km / v.duree_h) > v.mode_transport.map(VITESSE_MAX)
    ajoute("vitesse_plausible", "vitesse moyenne entre deux scans compatible avec le mode", trop.sum(), len(v))
    periode = colis.date_commande.between(C.PERIODE_DEBUT, pd.Timestamp(C.PERIODE_FIN) + pd.Timedelta(days=1))
    ajoute("date_dans_periode", "commande dans la période étudiée", (~periode).sum(), len(colis))
    d = colis.delai_livraison_h.dropna()
    ajoute("delai_plausible", "délai de livraison entre 0 et 60 jours", (~d.between(0, 60 * 24)).sum(), len(d))
    ajoute("emission_positive", "émission strictement positive", (colis.emission_estimee_g <= 0).sum(), len(colis))
    ajoute("geocodage_complet", "origine et destination géolocalisées",
           colis[["lat_orig", "lat_dest"]].isna().any(axis=1).sum(), len(colis))
    return pd.DataFrame(r)


def statistiques(colis: pd.DataFrame) -> pd.DataFrame:
    cols = ["poids_kg", "volume_m3", "distance_estimee_km", "nb_plateformes", "emission_estimee_g",
            "emission_ml_g", "delai_livraison_h", "taux_observation"]
    return colis[cols].describe(percentiles=[0.1, 0.5, 0.9]).T.round(2)


# ---------------------------------------------------------------------------
# Évaluation contre la vérité terrain (données simulées uniquement)
# ---------------------------------------------------------------------------
VERITE = C.SOURCES / "_verite_terrain"


def verite_disponible() -> bool:
    return (VERITE / "colis.parquet").exists()


def evaluer(colis: pd.DataFrame, et: pd.DataFrame, journal: pd.DataFrame) -> dict:
    v = pd.read_parquet(VERITE / "colis.parquet").set_index("tracking")
    ve = pd.read_parquet(VERITE / "etapes.parquet")
    df = colis.set_index("tracking_id")
    vrai = v.emission_kg.reindex(df.index) * 1000
    res = {}

    def mesures(est, ref):
        ape = (est - ref).abs() / ref
        return {"erreur_mediane_pct": round(100 * ape.median(), 1),
                "erreur_p90_pct": round(100 * ape.quantile(0.9), 1),
                "biais_total_pct": round(100 * (est.sum() / ref.sum() - 1), 2),
                "part_a_moins_de_20pct": round(100 * (ape < 0.2).mean(), 1)}

    res["emission_reconstituee"] = mesures(df.emission_estimee_g, vrai)
    res["emission_ml"] = mesures(df.emission_ml_g, vrai)
    res["distance"] = mesures(df.distance_estimee_km, v.distance_totale_km.reindex(df.index))
    # Erreur selon la part du trajet observée
    tranches = pd.cut(df.taux_observation, [-0.01, 0.5, 0.75, 0.99, 1.0],
                      labels=["< 50 %", "50-75 %", "75-99 %", "100 %"])
    lignes = []
    for t, idx in df.groupby(tranches, observed=True).groups.items():
        lignes.append({"part_observee": t, "colis": len(idx),
                       "erreur_reconstituee_pct": round(100 * ((df.emission_estimee_g[idx] - vrai[idx]).abs()
                                                               / vrai[idx]).median(), 1),
                       "erreur_ml_pct": round(100 * ((df.emission_ml_g[idx] - vrai[idx]).abs()
                                                     / vrai[idx]).median(), 1)})
    res["erreur_par_observation"] = lignes
    par_service = []
    for s, idx in df.groupby("service").groups.items():
        par_service.append({"service": s, **mesures(df.emission_estimee_g[idx], vrai[idx])})
    res["erreur_par_service"] = par_service

    # Véhicules prédits par le modèle : comparaison étape par étape
    ve = ve.rename(columns={"tracking": "tracking_id", "vehicule": "vehicule_vrai"})
    m = et[et.source_vehicule == "modele_ml"].merge(ve[["tracking_id", "de", "vers", "vehicule_vrai"]],
                                                    on=["tracking_id", "de", "vers"])
    res["vehicules_predits"] = {"etapes_comparables": len(m),
                                "precision_pct": round(100 * (m.vehicule == m.vehicule_vrai).mean(), 1)}

    # Défauts injectés et corrections du pipeline
    d = pd.read_parquet(VERITE / "defauts_injectes.parquet")
    d["defaut"] = d.defaut.str.split(":").str[0]
    inj = d.defaut.value_counts()
    trouve = dict(zip(journal.regle, journal.lignes))
    correspondances = [
        ("ligne_en_double", "doublons de numéro de suivi", "SAP : doublons supprimés"),
        ("poids_en_grammes_unite_kg", f"poids > {C.MAX_POIDS_KG} kg avec unité KG ou vide",
         "SAP : grammes saisis en kg (inclut les grammes à unité vide)"),
        ("poids_manquant", "poids manquant imputé par le volume", "SAP : poids manquants (+ imputés par médiane)"),
        ("poids_negatif_ou_nul", "poids nul ou négatif", "SAP : poids nuls ou négatifs"),
        ("scan_en_double", "double flashage (< 5 min)", "Scans : doubles flashages"),
        ("gps_inverse", "latitude et longitude inversées", "Scans : GPS inversés"),
        ("gps_zero", "GPS à (0, 0)", "Scans : GPS à zéro"),
        ("scan_orphelin", "scans orphelins", "Scans : orphelins"),
        ("transporteur_tronque", "identifiant transporteur tronqué ou inconnu", "Scans : transporteur tronqué"),
        ("horloge_decalee", "horodatage incohérent (avant la commande ou ordre logique inversé)",
         "Scans : horloge décalée"),
        ("coordonnees_manquantes", "coordonnées manquantes", "Sites : coordonnées manquantes"),
    ]
    lignes = []
    for cle, regle, libelle in correspondances:
        n_trouve = trouve.get(regle, 0)
        if cle == "poids_manquant":
            n_trouve = trouve.get(regle, 0) + trouve.get("poids manquant imputé par la médiane", 0) \
                - trouve.get("poids nul ou négatif", 0)
        lignes.append({"defaut": libelle, "injectes": int(inj.get(cle, 0)), "traites": int(n_trouve)})
    res["defauts"] = lignes
    return res


def rapport(colis: pd.DataFrame, et: pd.DataFrame, journal: pd.DataFrame, metriques_ml: dict,
            evaluation: dict | None) -> str:
    r = regles(colis, et)
    p = ["# Rapport qualité et validation\n",
         "Généré par `co2.validation` (étape 6). Statut : OK (aucune anomalie), ALERTE (moins de 1 %), "
         "ECHEC (1 % ou plus).\n", "## Règles de cohérence\n", r.to_markdown(index=False),
         "\n## Statistiques descriptives (table Curated)\n", statistiques(colis).to_markdown(),
         "\n## Journal des traitements\n", journal.to_markdown(index=False),
         "\n## Modèles d'apprentissage\n"]
    for nom, m in metriques_ml.items():
        p.append(f"**{nom}** : " + ", ".join(f"{k} = {round(v, 3) if isinstance(v, float) else fr(v)}"
                                              for k, v in m.items()) + "\n")
    if evaluation:
        p.append("\n## Évaluation contre la vérité terrain\n")
        p.append("Les données internes étant simulées, on connaît l'émission exacte de chaque colis. "
                 "Le pipeline ne lit jamais cette vérité ; elle sert uniquement ici.\n")
        tab = pd.DataFrame({k: evaluation[k] for k in ("emission_reconstituee", "emission_ml", "distance")}).T
        p.append(tab.to_markdown())
        p.append("\n### Erreur selon la part du trajet observée\n")
        p.append(pd.DataFrame(evaluation["erreur_par_observation"]).to_markdown(index=False))
        p.append("\n### Erreur par service (émission reconstituée)\n")
        p.append(pd.DataFrame(evaluation["erreur_par_service"]).to_markdown(index=False))
        p.append(f"\n### Véhicules prédits\n\nSur {fr(evaluation['vehicules_predits']['etapes_comparables'])} "
                 f"étapes comparables, le véhicule prédit est le bon dans "
                 f"{evaluation['vehicules_predits']['precision_pct']} % des cas.\n")
        p.append("\n### Défauts injectés et traités\n")
        p.append(pd.DataFrame(evaluation["defauts"]).to_markdown(index=False))
    texte = "\n".join(p) + "\n"
    (C.REPORTS / "06_rapport_qualite.md").write_text(texte, encoding="utf-8")
    r.to_csv(C.REPORTS / "06_regles_validation.csv", index=False)
    return texte
