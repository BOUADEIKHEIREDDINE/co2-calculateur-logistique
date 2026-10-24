"""Orchestration des étapes du data wrangling, du fichier brut à la table Curated."""
from __future__ import annotations

import json
import logging
import time

import numpy as np
import pandas as pd

from . import config as C
from . import (decouverte, enrichissement, features, figures, ingestion, nettoyage, publication, simulation,
               telechargement, validation)
from .geo import haversine_km
from .modele import ClassifieurVehicule, ModeInternational, RegresseurEmission

log = logging.getLogger("co2")


class Chrono:
    def __init__(self):
        self.etapes = []

    def __call__(self, nom):
        chrono = self

        class _Ctx:
            def __enter__(self):
                self.t = time.perf_counter()
                log.info("▶ %s", nom)

            def __exit__(self, *a):
                d = time.perf_counter() - self.t
                chrono.etapes.append((nom, round(d, 1)))
                log.info("  %s terminé en %.1f s", nom, d)
        return _Ctx()


def executer(regenerer_sources: bool = False) -> dict:
    C.REPORTS.mkdir(exist_ok=True)
    C.FIGURES.mkdir(parents=True, exist_ok=True)
    chrono = Chrono()

    telechargement.telecharger()
    if regenerer_sources or not (C.SOURCES / "sap_export_colis.csv").exists():
        with chrono("0. Génération des extractions internes fictives"):
            simulation.generer()

    with chrono("1-2. Ingestion et découverte"):
        raw = ingestion.ingerer()
        decouverte.rapport(raw)

    with chrono("3. Structuration et nettoyage"):
        rc = nettoyage.nettoyer(raw)
        j = nettoyage.Journal()
        j.lignes = rc["journal_nettoyage"].to_dict("records")

    with chrono("4. Enrichissement"):
        colis = enrichissement.imputer_poids(rc["colis"], j)
        colis = enrichissement.geocoder(colis, rc["sites"], rc["flashages"], j)
        topo = enrichissement.apprendre_topologie(rc["flashages"], rc["sites"])
        mode_intl = ModeInternational().ajuster(colis, rc["flashages"])
        et = enrichissement.reconstituer(colis, rc["flashages"], rc["sites"], topo, mode_intl, j)
        et = enrichissement.distances(et, colis, rc["sites"], j)
        C.ENRICHED.mkdir(parents=True, exist_ok=True)
        colis.to_parquet(C.ENRICHED / "colis.parquet", index=False)
        et.to_parquet(C.ENRICHED / "etapes.parquet", index=False)
        pd.Series(topo, name="tri_rattachement").rename_axis("site_code").reset_index().to_csv(
            C.ENRICHED / "topologie_apprise.csv", index=False)

    with chrono("5. Mapping, feature engineering et modèles"):
        et = features.preparer_etapes(et, colis, rc["transporteurs"])
        clf = ClassifieurVehicule().ajuster(et)
        et = features.attribuer_vehicules(et, clf, j)
        et = features.calculer_emissions(et)
        colis = features.agreger_colis(et, colis, rc["flashages"])
        colis["distance_directe_km"] = haversine_km(colis.lat_orig, colis.lon_orig,
                                                    colis.lat_dest, colis.lon_dest).round(1)
        propres = colis[(colis.taux_observation >= 0.75) & (colis.statut == "livre")]
        reg = RegresseurEmission().ajuster(propres)
        reg.sauver()
        pred = reg.predire(colis)
        colis["emission_ml_g"] = pred["median"].round(2)
        colis["emission_ml_bas_g"] = pred["bas"].round(2)
        colis["emission_ml_haut_g"] = pred["haut"].round(2)
        colis["ecart_ml_pct"] = (100 * (colis.emission_estimee_g - colis.emission_ml_g) / colis.emission_ml_g).round(1)
        colis["a_verifier"] = ~colis.emission_estimee_g.between(colis.emission_ml_bas_g * 0.5,
                                                                colis.emission_ml_haut_g * 2)
        colis["methode_emission"] = np.where(colis.taux_observation == 1, "trajet observé",
                                             "trajet reconstitué")
        j.note("colis", "écart fort entre reconstitution et modèle", colis.a_verifier.sum(),
               "signalés pour revue (hors de [bas/2 ; haut x 2])")
        metriques = {"Mode des colis internationaux (porte d'entrée non flashée)": mode_intl.metriques,
                     "Véhicule d'une étape sans transporteur": clf.metriques,
                     "Émission d'un colis à partir de la commande": reg.metriques}

    with chrono("6. Validation"):
        evaluation = None
        if validation.verite_disponible():
            evaluation = validation.evaluer(colis, et, j.table())
        validation.rapport(colis, et, j.table(), metriques, evaluation)

    with chrono("7. Publication"):
        sortie = publication.publier(colis, et)
        j.table().to_csv(C.REPORTS / "journal_traitements.csv", index=False)

    (C.REPORTS / "resume_pipeline.json").write_text(json.dumps({"evaluation": evaluation}, default=str),
                                                    encoding="utf-8")
    with chrono("8. Figures"):
        figures.generer(sortie["curated"])

    resume = {"etapes": chrono.etapes, "metriques_modeles": metriques, "evaluation": evaluation,
              "colis": int(len(colis)), "etapes_transport": int(len(et)),
              "emission_totale_t": round(colis.emission_estimee_g.sum() / 1e6, 2)}
    (C.REPORTS / "resume_pipeline.json").write_text(json.dumps(resume, indent=2, ensure_ascii=False, default=str),
                                                    encoding="utf-8")
    return {"colis": sortie["curated"], "etapes": et, "resume": resume}
