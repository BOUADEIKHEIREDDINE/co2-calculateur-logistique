"""Étape 7 : publication.

* table Curated (Parquet pour le ML, CSV pour tout le monde) ;
* détail des étapes ;
* un bilan Excel par client grand compte, lisible sans outil ;
* agrégats légers pour l'interface.
"""
from __future__ import annotations

import pandas as pd

from . import config as C

COLONNES_CURATED = [
    # colonnes demandées dans le cahier des charges
    "tracking_id", "date_first_scan", "date_last_scan", "pays_origine", "pays_destination", "poids_kg",
    "volume_m3", "nb_plateformes", "distance_estimee_km", "mode_transport", "facteur_emission_moyen_g_tkm",
    "emission_estimee_g", "emission_ml_g",
    # contexte et traçabilité
    "client", "categorie", "service", "livraison", "date_commande", "statut", "delai_livraison_h",
    "ville_origine", "departement_origine", "ville_destination", "departement_destination",
    "lat_orig", "lon_orig", "lat_dest", "lon_dest", "distance_directe_km", "nb_etapes", "tonne_km",
    "emission_ml_bas_g", "emission_ml_haut_g", "ecart_ml_pct", "a_verifier", "methode_emission",
    "taux_observation", "nb_etapes_inferees", "nb_vehicules_predits", "vehicule_dernier_km",
    "emission_dernier_km_g", "emission_avion_g", "emission_bateau_g", "emission_camion_g",
    "emission_camionnette_g", "emission_train_g", "emission_velo_g", "poids_impute", "poids_corrige",
    "poids_volumetrique_kg", "chronologie_suspecte", "source_geo_origine", "source_geo_destination",
]

COLONNES_ETAPES = ["tracking_id", "rang", "de", "vers", "type_etape", "de_infere", "vers_infere",
                   "transporteur_id", "vehicule", "source_vehicule", "confiance_vehicule", "mode_transport",
                   "distance_vol_oiseau_km", "distance_km", "methode_distance", "duree_h", "poids_kg",
                   "tonne_km", "facteur_kgco2e_tkm", "base_carbone_id", "emission_g"]


def publier(colis: pd.DataFrame, et: pd.DataFrame) -> dict[str, pd.DataFrame]:
    C.CURATED.mkdir(parents=True, exist_ok=True)
    cur = colis[[c for c in COLONNES_CURATED if c in colis]].copy()
    cur.to_parquet(C.CURATED / "colis_co2.parquet", index=False)
    cur.to_csv(C.CURATED / "colis_co2.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig")
    etapes = et[COLONNES_ETAPES]
    etapes.to_parquet(C.CURATED / "etapes_co2.parquet", index=False)

    # Agrégats mensuels par client, utilisés par l'interface et les bilans
    cur["mois"] = cur.date_commande.dt.to_period("M").dt.to_timestamp()
    mensuel = cur.groupby(["client", "mois"]).agg(
        colis=("tracking_id", "size"), emission_kg=("emission_estimee_g", lambda s: s.sum() / 1000),
        poids_t=("poids_kg", lambda s: s.sum() / 1000), tonne_km=("tonne_km", "sum")).reset_index()
    mensuel["g_par_colis"] = mensuel.emission_kg * 1000 / mensuel.colis
    mensuel.to_parquet(C.CURATED / "bilan_mensuel_client.parquet", index=False)

    dossier = C.CURATED / "bilans_clients"
    dossier.mkdir(exist_ok=True)
    for client, d in cur.groupby("client"):
        synthese = pd.DataFrame({
            "Indicateur": ["Colis expédiés", "Émissions totales (kg CO2e)", "Moyenne par colis (g CO2e)",
                           "Médiane par colis (g CO2e)", "Part du transport aérien dans les émissions",
                           "Part du dernier kilomètre dans les émissions", "Colis dont le trajet est entièrement observé"],
            "Valeur": [len(d), round(d.emission_estimee_g.sum() / 1000, 1), round(d.emission_estimee_g.mean(), 1),
                       round(d.emission_estimee_g.median(), 1),
                       f"{d.emission_avion_g.sum() / d.emission_estimee_g.sum():.1%}" if "emission_avion_g" in d else "0 %",
                       f"{d.emission_dernier_km_g.sum() / d.emission_estimee_g.sum():.1%}",
                       f"{(d.taux_observation == 1).mean():.1%}"],
        })
        par_service = d.groupby("service").agg(colis=("tracking_id", "size"),
                                                emission_kg=("emission_estimee_g", lambda s: round(s.sum() / 1000, 2)),
                                                g_par_colis=("emission_estimee_g", lambda s: round(s.mean(), 1)))
        par_mois = mensuel[mensuel.client == client].drop(columns="client")
        detail = d.drop(columns=["mois"]).sort_values("date_commande")
        with pd.ExcelWriter(dossier / f"bilan_co2_{client.lower().replace(' ', '_')}.xlsx") as w:
            synthese.to_excel(w, sheet_name="Synthèse", index=False)
            par_service.to_excel(w, sheet_name="Par service")
            par_mois.to_excel(w, sheet_name="Par mois", index=False)
            detail.to_excel(w, sheet_name="Détail des colis", index=False)
    return {"curated": cur, "etapes": etapes, "mensuel": mensuel}
