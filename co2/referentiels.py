"""Référentiels externes : facteurs d'émission ADEME, géographie, réseau de sites.

Chaque table est construite à partir d'une source publique téléchargée dans
data/external, jamais saisie à la main, pour que les valeurs restent traçables.
"""
from __future__ import annotations

import json
import time
from functools import lru_cache

import numpy as np
import pandas as pd
import requests

from . import config as C
from .geo import haversine_km

# ---------------------------------------------------------------------------
# Facteurs d'émission (Base Carbone ADEME)
# ---------------------------------------------------------------------------
# code interne -> (mode, libellé, identifiant Base Carbone)
FACTEURS_BASE_CARBONE = {
    "ROUTE_ART_40T_DIESEL": ("route", "Articulé 34 à 40 t, gazole B7", 43643),
    "ROUTE_ART_40T_GNC": ("route", "Articulé 34 à 40 t, GNC", 43644),
    "ROUTE_ART_40T_GNL": ("route", "Articulé 34 à 40 t, GNL", 43645),
    "ROUTE_RIG_20T_DIESEL": ("route", "Porteur 12 à 20 t, gazole B7", 43716),
    "ROUTE_RIG_12T_DIESEL": ("route", "Porteur 7,5 à 12 t, gazole B7", 43724),
    "ROUTE_RIG_7T_DIESEL": ("route", "Porteur 3,5 à 7,5 t, gazole B7", 43722),
    "ROUTE_RIG_7T_ELEC": ("route", "Porteur 3,5 à 7,5 t, électrique", 28030),
    "VUL_DIESEL": ("vul", "Utilitaire < 3,5 t, gazole B7", 43735),
    "VUL_ESSENCE": ("vul", "Utilitaire < 3,5 t, essence", 43736),
    "VUL_GNC": ("vul", "Utilitaire < 3,5 t, GNC", 43737),
    "FER_ELEC": ("fer", "Train, traction électrique, chargement moyen", 43734),
    "FER_MOYEN": ("fer", "Train, motorisation moyenne, chargement moyen", 43728),
    "MER_PC_ASIE_EUN": ("mer", "Porte-conteneur dry, Asie - Europe du Nord", 28203),
    "MER_PC_ASIE_MED": ("mer", "Porte-conteneur dry, Asie - Méditerranée", 28201),
    "MER_PC_EUR_AFR": ("mer", "Porte-conteneur dry, Europe - Afrique", 28205),
    "MER_PC_TRANSAT": ("mer", "Porte-conteneur dry, trans-Atlantique", 28195),
    "MER_PC_MOYEN": ("mer", "Porte-conteneur dry, valeur moyenne", 28193),
    "AIR_CARGO_5000P": ("air", "Avion cargo > 100 t, plus de 5 000 km, avec traînées", 43670),
    "AIR_CARGO_2000_5000": ("air", "Avion cargo > 100 t, 2 000 à 5 000 km, avec traînées", 43662),
    "AIR_CARGO_1000_2000": ("air", "Avion cargo > 100 t, 1 000 à 2 000 km, avec traînées", 43668),
}
ELECTRICITE_FR_ID = 43642          # mix moyen France 2024, kgCO2e/kWh
VELO_KWH_PAR_KM = 0.015            # vélo cargo à assistance électrique
VELO_CHARGE_MOYENNE_T = 0.08       # 80 kg transportés en moyenne


def lire_base_carbone() -> pd.DataFrame:
    """Lit l'export brut de la Base Carbone (latin-1, ';', virgule décimale, guillemets cassés)."""
    df = pd.read_csv(C.EXTERNAL / "base_carbone_ademe.csv", sep=";", encoding="latin-1",
                     dtype=str, engine="python", on_bad_lines="skip")
    df = df[df["Type Ligne"] == "Elément"].copy()
    df["id"] = pd.to_numeric(df["Identifiant de l'élément"], errors="coerce").astype("Int64")
    df["valeur"] = pd.to_numeric(df["Total poste non décomposé"].str.replace(",", ".", regex=False),
                                 errors="coerce")
    return df


def table_facteurs() -> pd.DataFrame:
    """Table référentielle des facteurs, en kgCO2e par tonne.km."""
    bc = lire_base_carbone().drop_duplicates("id").set_index("id")
    lignes = []
    for code, (mode, libelle, ident) in FACTEURS_BASE_CARBONE.items():
        ligne = bc.loc[ident]
        lignes.append({
            "code_vehicule": code, "mode": mode, "libelle": libelle,
            "kgco2e_tkm": float(ligne["valeur"]), "unite_source": ligne["Unité français"],
            "base_carbone_id": ident, "statut_source": ligne["Statut de l'élément"],
            "origine": "Base Carbone ADEME",
        })
    f = pd.DataFrame(lignes)

    # Deux facteurs absents de la Base Carbone, dérivés de valeurs qui y figurent
    diesel_vul = f.loc[f.code_vehicule == "VUL_DIESEL", "kgco2e_tkm"].item()
    ratio_elec = (f.loc[f.code_vehicule == "ROUTE_RIG_7T_ELEC", "kgco2e_tkm"].item()
                  / f.loc[f.code_vehicule == "ROUTE_RIG_7T_DIESEL", "kgco2e_tkm"].item())
    elec = float(bc.loc[ELECTRICITE_FR_ID, "valeur"])
    derives = pd.DataFrame([
        {"code_vehicule": "VUL_ELEC", "mode": "vul", "libelle": "Utilitaire < 3,5 t, électrique",
         "kgco2e_tkm": round(diesel_vul * ratio_elec, 4), "unite_source": "kgCO2e/t.km",
         "base_carbone_id": 43735, "statut_source": "Dérivé",
         "origine": f"VUL gazole x ratio électrique/gazole des porteurs 3,5-7,5 t ({ratio_elec:.3f})"},
        {"code_vehicule": "VELO_CARGO", "mode": "velo", "libelle": "Vélo cargo à assistance électrique",
         "kgco2e_tkm": round(elec * VELO_KWH_PAR_KM / VELO_CHARGE_MOYENNE_T, 4),
         "unite_source": "kgCO2e/t.km", "base_carbone_id": ELECTRICITE_FR_ID, "statut_source": "Dérivé",
         "origine": f"Mix électrique France 2024 ({elec} kgCO2e/kWh) x {VELO_KWH_PAR_KM} kWh/km "
                    f"/ {VELO_CHARGE_MOYENNE_T} t de charge"},
    ])
    return pd.concat([f, derives], ignore_index=True)


def facteur_air(distance_km: float) -> str:
    if distance_km > 5000:
        return "AIR_CARGO_5000P"
    if distance_km > 2000:
        return "AIR_CARGO_2000_5000"
    return "AIR_CARGO_1000_2000"


def facteur_mer(pays_origine: str, port_arrivee: str) -> str:
    if pays_origine in {"CN", "HK", "KR"}:
        return "MER_PC_ASIE_MED" if port_arrivee == "ENT-FOS" else "MER_PC_ASIE_EUN"
    if pays_origine == "MA":
        return "MER_PC_EUR_AFR"
    if pays_origine in {"US", "CA"}:
        return "MER_PC_TRANSAT"
    return "MER_PC_MOYEN"


# ---------------------------------------------------------------------------
# Géographie (GeoNames, OpenFlights)
# ---------------------------------------------------------------------------
GEONAMES_COLS = ["geonameid", "name", "asciiname", "alternatenames", "lat", "lon", "feature_class",
                 "feature_code", "pays", "cc2", "admin1", "admin2", "admin3", "admin4", "population",
                 "elevation", "dem", "timezone", "modification"]


@lru_cache(maxsize=1)
def villes() -> pd.DataFrame:
    """Villes de plus de 5 000 habitants (GeoNames, licence CC BY 4.0)."""
    df = pd.read_csv(C.EXTERNAL / "cities5000.txt", sep="\t", header=None, names=GEONAMES_COLS,
                     dtype={"admin1": str, "admin2": str, "admin3": str, "admin4": str}, keep_default_na=False, na_values=[""],
                     quoting=3)
    # arrondissements (Paris 15 Vaugirard, Lyon 05...) : doublons de la ville elle-même
    df = df[(df.feature_code != "PPLX") & ~df.name.str.match(r"^(Paris|Lyon|Marseille) \d\d")]
    return df[["geonameid", "name", "lat", "lon", "pays", "admin1", "admin2", "population", "timezone"]]


@lru_cache(maxsize=1)
def villes_france() -> pd.DataFrame:
    v = villes()
    v = v[(v.pays == "FR") & v.admin2.notna()].copy()
    v = v[~v.admin2.str.startswith("97")]                      # métropole et Corse uniquement
    v["departement"] = v.admin2.str.zfill(2)
    return v.reset_index(drop=True)


def localiser(ville: str, pays: str) -> tuple[float, float]:
    """(lat, lon) de la ville la plus peuplée portant ce nom dans ce pays."""
    v = villes()
    m = v[(v.name == ville) & (v.pays == pays)]
    if m.empty:
        raise KeyError(f"{ville} ({pays}) absente de GeoNames")
    r = m.sort_values("population", ascending=False).iloc[0]
    return float(r.lat), float(r.lon)


@lru_cache(maxsize=1)
def aeroports() -> pd.DataFrame:
    cols = ["id", "nom", "ville", "pays_nom", "iata", "icao", "lat", "lon", "alt", "utc",
            "dst", "tz", "type", "source"]
    df = pd.read_csv(C.EXTERNAL / "airports_openflights.dat", header=None, names=cols,
                     na_values="\\N", keep_default_na=False)
    return df[df.iata.notna()].set_index("iata")


# ---------------------------------------------------------------------------
# Réseau FastColis
# ---------------------------------------------------------------------------
def reseau_sites() -> pd.DataFrame:
    """Toutes les plateformes, agences et entrepôts, géolocalisés."""
    lignes = []
    for code, (nom, ville, pays, porte) in C.PLATEFORMES_ENTREE.items():
        if ville == "CDG":
            a = aeroports().loc["CDG"]
            lat, lon, ville = float(a.lat), float(a.lon), "Roissy-en-France"
        else:
            lat, lon = localiser(ville, pays)
        lignes.append(dict(site_code=code, libelle=nom, type_site="ENTREE", ville=ville, pays=pays,
                           porte=porte, lat=lat, lon=lon))
    for code, (nom, ville) in C.PLATEFORMES_TRI.items():
        lat, lon = localiser(ville, "FR")
        lignes.append(dict(site_code=code, libelle=nom, type_site="HUB" if code == "TRI-NAT" else "TRI",
                           ville=ville, pays="FR", porte=None, lat=lat, lon=lon))
    # une agence par département : la ville la plus peuplée du département
    vf = villes_france()
    chefs = vf.sort_values("population", ascending=False).drop_duplicates("departement")
    tri = [l for l in lignes if l["type_site"] == "TRI"]
    for _, r in chefs.sort_values("departement").iterrows():
        proche = min(tri, key=lambda t: haversine_km(r.lat, r.lon, t["lat"], t["lon"]))
        lignes.append(dict(site_code=f"AG-{r.departement}", libelle=f"Agence {r['name']}",
                           type_site="AGENCE", ville=r["name"], pays="FR", porte=None,
                           lat=float(r.lat), lon=float(r.lon), departement=r.departement,
                           tri_rattachement=proche["site_code"]))
    for client, liste in C.ENTREPOTS.items():
        for i, ville in enumerate(liste, 1):
            lat, lon = localiser(ville, "FR")
            lignes.append(dict(site_code=f"WH-{client[:3]}{i}", libelle=f"Entrepôt {client.title()} {ville}",
                               type_site="ENTREPOT_CLIENT", ville=ville, pays="FR", porte=None,
                               lat=lat, lon=lon, client=client))
    df = pd.DataFrame(lignes)
    # chaque site français est rattaché à sa plateforme de tri la plus proche
    t = df[df.type_site == "TRI"]
    manque = df.tri_rattachement.isna() & (df.pays == "FR") & df.type_site.isin(["ENTREE", "ENTREPOT_CLIENT"])
    for i in df[manque].index:
        d = haversine_km(df.at[i, "lat"], df.at[i, "lon"], t.lat.values, t.lon.values)
        df.at[i, "tri_rattachement"] = t.site_code.values[int(np.argmin(d))]
    df.loc[df.site_code == "ENT-RTM", "tri_rattachement"] = "TRI-LIL"
    return df


# ---------------------------------------------------------------------------
# Distances routières réelles (OSRM, OpenStreetMap) avec cache local
# ---------------------------------------------------------------------------
OSRM_URL = "https://router.project-osrm.org/table/v1/driving/"
CACHE_OSRM = C.EXTERNAL / "osrm_distances.csv"


def distances_osrm(points: pd.DataFrame, cle: str = "site_code", taille_lot: int = 60) -> pd.DataFrame:
    """Matrice de distances routières entre points (lat, lon), mise en cache sur disque.

    Le serveur de démonstration OSRM limite la taille des requêtes : on découpe en lots.
    """
    cache = pd.read_csv(CACHE_OSRM) if CACHE_OSRM.exists() else pd.DataFrame(
        columns=["de", "vers", "distance_route_km"])
    connus = set(zip(cache.de, cache.vers))
    pts = points[[cle, "lat", "lon"]].drop_duplicates(cle).reset_index(drop=True)
    codes = pts[cle].tolist()
    a_faire = [(a, b) for a in codes for b in codes if a != b and (a, b) not in connus]
    if a_faire:
        nouveaux = []
        for i in range(0, len(pts), taille_lot):
            for j in range(0, len(pts), taille_lot):
                src, dst = pts.iloc[i:i + taille_lot], pts.iloc[j:j + taille_lot]
                bloc = pd.concat([src, dst]).reset_index(drop=True)
                coords = ";".join(f"{r.lon:.5f},{r.lat:.5f}" for r in bloc.itertuples())
                params = {"sources": ";".join(map(str, range(len(src)))),
                          "destinations": ";".join(map(str, range(len(src), len(bloc)))),
                          "annotations": "distance"}
                for essai in range(4):
                    try:
                        rep = requests.get(OSRM_URL + coords, params=params, timeout=60).json()
                        if rep.get("code") == "Ok":
                            break
                    except (requests.RequestException, json.JSONDecodeError):
                        pass
                    time.sleep(2 + 3 * essai)
                else:
                    raise RuntimeError("OSRM indisponible et cache incomplet")
                for a, ligne in zip(src[cle], rep["distances"]):
                    for b, d in zip(dst[cle], ligne):
                        if a != b and d is not None:
                            nouveaux.append((a, b, round(d / 1000, 2)))
                time.sleep(1)
        cache = pd.concat([cache, pd.DataFrame(nouveaux, columns=cache.columns)]).drop_duplicates(["de", "vers"])
        cache.to_csv(CACHE_OSRM, index=False)
    return cache
