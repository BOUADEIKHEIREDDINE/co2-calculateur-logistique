"""Tests des règles de nettoyage et de calcul, sur de petits cas écrits à la main."""
import numpy as np
import pandas as pd
import pytest

from co2 import config as C
from co2.decouverte import forme
from co2.enrichissement import cle_ville, type_etape
from co2.geo import haversine_km
from co2.nettoyage import (Journal, classer_vehicule, nettoyer_sap, nombre, normaliser_pays, normaliser_societe,
                           normaliser_tracking)
from co2.referentiels import facteur_air, facteur_mer


def test_forme_revele_les_formats():
    assert forme("20260314") == "9{8}"
    assert forme("14.03.2026") == "99.99.9{4}"
    assert forme(None) == "∅"


def test_haversine_paris_lyon():
    assert haversine_km(48.8566, 2.3522, 45.7640, 4.8357) == pytest.approx(392, abs=3)


def test_nombre_accepte_virgule_et_point():
    assert list(nombre(pd.Series(["1,5", "2.25", "x", None]))[:2]) == [1.5, 2.25]


def test_tracking_normalise():
    s = normaliser_tracking(pd.Series(["fc1234567890", "FC 1234 567 890", "1234567890"]))
    assert set(s) == {"FC1234567890"}


def test_societes_et_pays():
    assert normaliser_societe("AMAZON EU SARL") == normaliser_societe("amazon.fr") == "AMAZON"
    assert list(normaliser_pays(pd.Series(["fr", "France", "FRA", "Chine"]))) == ["FR", "FR", "FR", "CN"]


@pytest.mark.parametrize("libelle, energie, attendu", [
    ("Semi-remorque 40T", "Gazole", "ROUTE_ART_40T_DIESEL"),
    ("Semi 40T GNV", None, "ROUTE_ART_40T_GNC"),
    ("Porteur 7,5 t élec", "Électrique", "ROUTE_RIG_7T_ELEC"),
    ("Fourgon 12m3", "Électrique", "VUL_ELEC"),
    ("VUL 3.5T", "Gazole", "VUL_DIESEL"),
    ("Triporteur électrique", None, "VELO_CARGO"),
    ("", "Gazole", None),
])
def test_classement_vehicules(libelle, energie, attendu):
    assert classer_vehicule(libelle, energie) == attendu


def test_cle_ville_tolere_les_ecritures():
    assert cle_ville("St-Étienne") == cle_ville("SAINT ETIENNE") == cle_ville("saint-étienne")


def test_types_etape():
    assert type_etape("ORIGINE", "ENT-CDG") == "INTERNATIONAL"
    assert type_etape("TRI-IDF", "TRI-LYS") == "LIGNE"
    assert type_etape("AG-69", "DESTINATION") == "DERNIER_KM"


def test_facteurs_selon_distance_et_ligne():
    assert facteur_air(9500) == "AIR_CARGO_5000P"
    assert facteur_air(1500) == "AIR_CARGO_1000_2000"
    assert facteur_mer("CN", "ENT-FOS") == "MER_PC_ASIE_MED"


def _sap(**kw):
    base = {"VBELN": "1", "TRACKING": "FC1234567890", "KUNNR": "100100", "NAME1": "Amazon", "MATKL": "Mode",
            "BRGEW": "1,5", "GEWEI": "KG", "LAENG": "30", "BREIT": "20", "HOEHE": "10", "MEINS": "CM",
            "VSART": "01", "LIVR": "DOM", "LAND1_ORIG": "FR", "ORT01_ORIG": "Saran", "WERKS": None,
            "LAND1_DEST": "France", "ORT01_DEST": "Lyon", "REGIO_DEST": "69", "ERDAT": "20260314",
            "ERZET": "101500", "NETWR": "12,5", "WAERK": "EUR", "ZLSCH": "CB"}
    base.update(kw)
    return base


def test_sap_unites_dates_doublons():
    brut = pd.DataFrame([
        _sap(),
        _sap(TRACKING="FC0000000002", BRGEW="1500", GEWEI="G", ERDAT="14.03.2026"),
        _sap(TRACKING="FC0000000003", BRGEW="2300", GEWEI="KG", LAENG="300", BREIT="200", HOEHE="100", MEINS="MM"),
        _sap(TRACKING="FC0000000004", BRGEW="-1", VSART="Express 24h"),
        _sap(),                                                     # doublon exact
    ])
    j = Journal()
    df = nettoyer_sap(brut, j).set_index("tracking_id")
    assert len(df) == 4
    assert df.loc["FC0000000002", "poids_kg"] == 1.5
    assert df.loc["FC0000000003", "poids_kg"] == 2.3 and df.loc["FC0000000003", "poids_corrige"]
    assert df.loc["FC0000000003", "volume_m3"] == pytest.approx(0.006)
    assert np.isnan(df.loc["FC0000000004", "poids_kg"])
    assert df.loc["FC0000000004", "service"] == "express"
    assert df.loc["FC0000000002", "date_commande"] == pd.Timestamp("2026-03-14 10:15:00")
    assert (j.table().regle == "doublons de numéro de suivi").any()


@pytest.mark.skipif(not (C.CURATED / "colis_co2.parquet").exists(), reason="pipeline non exécuté")
def test_sortie_curated_coherente():
    colis = pd.read_parquet(C.CURATED / "colis_co2.parquet")
    etapes = pd.read_parquet(C.CURATED / "etapes_co2.parquet")
    assert colis.tracking_id.is_unique
    somme = etapes.groupby("tracking_id").emission_g.sum()
    assert np.allclose(colis.set_index("tracking_id").emission_estimee_g, somme.reindex(colis.tracking_id), atol=0.01)
    assert (colis.distance_estimee_km > 0).all()
