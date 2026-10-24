"""Calculateur pour un envoi qui n'existe pas encore.

Le trajet type est construit avec la topologie apprise par le pipeline, chaque
étape reçoit le facteur moyen réellement observé sur l'année pour ce type
d'étape et ce service (mix de flotte compris), et le modèle donne une
fourchette à 80 % à partir de l'historique.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from . import config as C
from . import referentiels as R
from .enrichissement import Geocodeur, coefficient_detour
from .geo import distance_mer_km, haversine_km
from .modele import RegresseurEmission

LIBELLES_ETAPE = {
    "PRE_ACHEMINEMENT": "Transport jusqu'à l'aéroport ou au port de départ",
    "INTERNATIONAL_AIR": "Vol international",
    "INTERNATIONAL_MER": "Traversée en porte-conteneurs",
    "INTERNATIONAL": "Transport routier jusqu'à la frontière",
    "POST_ENTREE": "Douane vers plateforme de tri",
    "COLLECTE": "Collecte au point relais de dépôt",
    "ENLEVEMENT": "Enlèvement à l'entrepôt",
    "CAPILLAIRE_ORIGINE": "Agence de départ vers plateforme de tri",
    "LIGNE": "Trajet entre plateformes de tri",
    "CAPILLAIRE": "Plateforme de tri vers agence locale",
    "DERNIER_KM": "Livraison finale",
}
SERVICES_LIBELLES = {"standard": "Standard", "express": "Express 24 h", "ecologique": "Écologique",
                     "international": "International"}
PORTS = {"CN": "ENT-LEH", "HK": "ENT-LEH", "KR": "ENT-LEH", "US": "ENT-LEH", "CA": "ENT-LEH", "MA": "ENT-FOS"}


class Calculateur:
    def __init__(self):
        self.geo = Geocodeur()
        self.sites = pd.read_parquet(C.RAW_CLEAN / "sites.parquet").set_index("site_code")
        topo = pd.read_csv(C.ENRICHED / "topologie_apprise.csv")
        self.topo = dict(zip(topo.site_code, topo.tri_rattachement))
        osrm = pd.read_csv(R.CACHE_OSRM)
        self.route = dict(zip(zip(osrm.de, osrm.vers), osrm.distance_route_km))
        self.detour = coefficient_detour()
        et = pd.read_parquet(C.CURATED / "etapes_co2.parquet")
        colis = pd.read_parquet(C.CURATED / "colis_co2.parquet", columns=["tracking_id", "service", "pays_origine"])
        et = et.merge(colis, on="tracking_id")
        g = et.groupby(["type_etape", "service"])
        self.facteur = (g.emission_g.sum() / g.tonne_km.sum() / 1000).to_dict()
        # fourchette : facteurs observés du 10e au 90e centile selon le véhicule réellement affecté
        connus = et[et.source_vehicule == "transporteur"].groupby(["type_etape", "service"]).facteur_kgco2e_tkm
        self.f_bas, self.f_haut = connus.quantile(0.1).to_dict(), connus.quantile(0.9).to_dict()
        # distance minimale d'une tournée (adresse en centre-ville de l'agence)
        tournee = et[et.type_etape.isin(["DERNIER_KM", "COLLECTE"]) & (et.distance_vol_oiseau_km < 5)]
        self.tournee_min = float(tournee.distance_km.median())
        # allongement des lignes selon le service (passage éventuel par le hub national)
        lignes = et[et.type_etape == "LIGNE"].groupby("tracking_id").agg(
            de=("de", "first"), vers=("vers", "last"), d=("distance_km", "sum"), service=("service", "first"))
        lignes["direct"] = [self.route.get((a, b), np.nan) for a, b in zip(lignes.de, lignes.vers)]
        lignes = lignes[lignes.direct > 0]
        self.allongement = (lignes.d.groupby(lignes.service).sum() / lignes.direct.groupby(lignes.service).sum()).to_dict()
        self.facteur_type = (et.groupby("type_etape").emission_g.sum()
                             / et.groupby("type_etape").tonne_km.sum() / 1000).to_dict()
        self.part_air = (et[et.type_etape.isin(["INTERNATIONAL", "INTERNATIONAL_AIR"])]
                         .assign(air=lambda d: d.mode_transport.eq("Avion"))
                         .groupby("pays_origine").air.mean().to_dict())
        self.facteurs_ref = R.table_facteurs().set_index("code_vehicule")
        self.modele = RegresseurEmission.charger()
        self.agences = {r.departement: c for c, r in self.sites[self.sites.index.str.startswith("AG-")].iterrows()}

    # -- géographie -------------------------------------------------------------
    def point(self, code: str) -> tuple[float, float]:
        return float(self.sites.at[code, "lat"]), float(self.sites.at[code, "lon"])

    def distance_route(self, a: str, b: str, pa, pb) -> float:
        if (a, b) in self.route:
            return self.route[(a, b)]
        return float(haversine_km(pa[0], pa[1], pb[0], pb[1]) * self.detour)

    def localiser(self, ville: str, pays: str = "FR") -> dict:
        if pays == "FR":
            lat, lon, dep, nom, methode = self.geo.france(ville)
        else:
            lat, lon, nom, methode = self.geo.etranger(ville, pays)
            dep = None
        if methode == "echec" or pd.isna(lat):
            raise ValueError(f"Ville introuvable : {ville} ({pays})")
        return {"ville": nom, "pays": pays, "departement": dep, "lat": float(lat), "lon": float(lon)}

    # -- trajet type ------------------------------------------------------------
    def trajet(self, origine: dict, destination: dict, service: str, livraison: str,
               entrepot: str | None = None, mode_international: str | None = None) -> list[dict]:
        etapes = []

        def ajoute(type_etape, de, vers, pa, pb, dist, mode):
            etapes.append({"type_etape": type_etape, "de": de, "vers": vers, "lat_de": pa[0], "lon_de": pa[1],
                           "lat_vers": pb[0], "lon_vers": pb[1], "distance_km": round(dist, 1), "mode": mode})

        po = (origine["lat"], origine["lon"])
        if origine["pays"] != "FR":
            pays = origine["pays"]
            if pays in {"ES", "IT", "DE", "PL", "BE", "NL"} or mode_international == "route":
                from .enrichissement import ENTREE_DE_PAYS_EUROPE
                ent = ENTREE_DE_PAYS_EUROPE.get(pays, "ENT-STR")
                pe = self.point(ent)
                ajoute("INTERNATIONAL", origine["ville"], self.sites.at[ent, "libelle"], po, pe,
                       haversine_km(*po, *pe) * self.detour, "Camion")
            elif (mode_international or ("air" if service == "express" else None)) == "mer":
                ent = PORTS.get(pays, "ENT-LEH")
                pe = self.point(ent)
                ajoute("INTERNATIONAL_MER", origine["ville"], self.sites.at[ent, "libelle"], po, pe,
                       distance_mer_km(round(po[0], 2), round(po[1], 2), round(pe[0], 2), round(pe[1], 2)), "Bateau")
            else:
                ent = "ENT-CDG"
                pe = self.point(ent)
                ajoute("INTERNATIONAL_AIR", origine["ville"], self.sites.at[ent, "libelle"], po, pe,
                       haversine_km(*po, *pe) + C.AIR_KM_SUPPLEMENTAIRES, "Avion")
            tri_o = self.topo[ent]
            ajoute("POST_ENTREE", self.sites.at[ent, "libelle"], self.sites.at[tri_o, "libelle"], pe,
                   self.point(tri_o), self.distance_route(ent, tri_o, pe, self.point(tri_o)), "Camion")
        elif entrepot:
            tri_o = self.topo[entrepot]
            pw = self.point(entrepot)
            ajoute("ENLEVEMENT", self.sites.at[entrepot, "libelle"], self.sites.at[tri_o, "libelle"], pw,
                   self.point(tri_o), self.distance_route(entrepot, tri_o, pw, self.point(tri_o)), "Camion")
        else:
            ag_o = self.agences[origine["departement"]]
            pa = self.point(ag_o)
            ajoute("COLLECTE", f"Point relais à {origine['ville']}", self.sites.at[ag_o, "libelle"], po, pa,
                   max(haversine_km(*po, *pa) * self.detour * C.TOURNEE_FACTEUR, self.tournee_min), "Camionnette")
            tri_o = self.topo[ag_o]
            ajoute("CAPILLAIRE_ORIGINE", self.sites.at[ag_o, "libelle"], self.sites.at[tri_o, "libelle"], pa,
                   self.point(tri_o), self.distance_route(ag_o, tri_o, pa, self.point(tri_o)), "Camion")

        ag_d = self.agences[destination["departement"]]
        tri_d = self.topo[ag_d]
        if tri_o != tri_d:
            mode = "Camion / train" if service == "ecologique" else "Camion"
            direct = self.distance_route(tri_o, tri_d, self.point(tri_o), self.point(tri_d))
            ajoute("LIGNE", self.sites.at[tri_o, "libelle"], self.sites.at[tri_d, "libelle"], self.point(tri_o),
                   self.point(tri_d), direct * self.allongement.get(service, 1.0), mode)
        ajoute("CAPILLAIRE", self.sites.at[tri_d, "libelle"], self.sites.at[ag_d, "libelle"], self.point(tri_d),
               self.point(ag_d), self.distance_route(tri_d, ag_d, self.point(tri_d), self.point(ag_d)), "Camion")
        pd_ = (destination["lat"], destination["lon"])
        pr = livraison == "point_relais"
        mode = "Vélo / camionnette électrique" if service == "ecologique" else "Camionnette"
        ajoute("DERNIER_KM", self.sites.at[ag_d, "libelle"],
               f"{'Point relais' if pr else 'Domicile'} à {destination['ville']}", self.point(ag_d), pd_,
               max(haversine_km(*self.point(ag_d), *pd_) * self.detour * C.TOURNEE_FACTEUR, self.tournee_min)
               * (0.6 if pr else 1.0), mode)
        return etapes

    def facteur_etape(self, type_etape: str, service: str, mode: str, distance: float) -> float:
        if type_etape == "INTERNATIONAL_AIR":
            return float(self.facteurs_ref.at[R.facteur_air(distance), "kgco2e_tkm"])
        if type_etape == "INTERNATIONAL_MER":
            return float(self.facteurs_ref.at["MER_PC_ASIE_EUN", "kgco2e_tkm"])
        if type_etape == "INTERNATIONAL":
            return float(self.facteurs_ref.at["ROUTE_ART_40T_DIESEL", "kgco2e_tkm"])
        return float(self.facteur.get((type_etape, service), self.facteur_type.get(type_etape)))

    # -- estimation -------------------------------------------------------------
    def estimer(self, origine: dict, destination: dict, poids_kg: float, service: str, livraison: str,
                entrepot: str | None = None, client: str | None = None, mode_international: str | None = None,
                volume_m3: float | None = None) -> dict:
        etapes = self.trajet(origine, destination, service, livraison, entrepot, mode_international)
        for e in etapes:
            f = self.facteur_etape(e["type_etape"], service, e["mode"], e["distance_km"])
            cle = (e["type_etape"], service)
            tkm = poids_kg / 1000 * e["distance_km"]
            e["facteur_kgco2e_tkm"] = f
            e["emission_g"] = tkm * f * 1000
            e["bas_g"] = tkm * min(f, self.f_bas.get(cle, f * 0.9)) * 1000
            e["haut_g"] = tkm * max(f, self.f_haut.get(cle, f * 1.1)) * 1000
            e["etape"] = LIBELLES_ETAPE[e["type_etape"]]
        df = pd.DataFrame(etapes)
        total = float(df.emission_g.sum())
        x = pd.DataFrame([{"client": client or "INCONNU", "categorie": "Mode", "service": service,
                           "livraison": livraison, "pays_origine": origine["pays"], "poids_kg": poids_kg,
                           "volume_m3": volume_m3 if volume_m3 else np.nan,
                           "lat_orig": origine["lat"], "lon_orig": origine["lon"],
                           "lat_dest": destination["lat"], "lon_dest": destination["lon"],
                           "site_expedition": entrepot, "date_commande": pd.Timestamp.today()}])
        p = self.modele.predire(x).iloc[0]
        return {"etapes": df, "total_g": total, "bas_g": float(df.bas_g.sum()), "haut_g": float(df.haut_g.sum()),
                "modele_g": float(p["median"]), "distance_km": float(df.distance_km.sum()),
                "km_voiture": total / 1000 / C.VOITURE_KG_PAR_KM}

    def comparer(self, origine: dict, destination: dict, poids_kg: float, entrepot: str | None = None,
                 client: str | None = None) -> pd.DataFrame:
        lignes = []
        services = ["international", "express"] if origine["pays"] != "FR" else ["standard", "express", "ecologique"]
        for s in services:
            for liv in ("domicile", "point_relais"):
                modes = [None]
                if origine["pays"] != "FR" and s == "international" and origine["pays"] not in {"ES", "IT", "DE", "PL", "BE", "NL"}:
                    modes = ["air", "mer"]
                for m in modes:
                    r = self.estimer(origine, destination, poids_kg, s, liv, entrepot, client, m)
                    libelle = SERVICES_LIBELLES[s] + (" (bateau)" if m == "mer" else " (avion)" if m == "air" else "")
                    lignes.append({"service": libelle, "livraison": "Point relais" if liv == "point_relais" else "Domicile",
                                   "emission_g": r["total_g"], "bas_g": r["bas_g"], "haut_g": r["haut_g"]})
        return pd.DataFrame(lignes).sort_values("emission_g").reset_index(drop=True)


@lru_cache(maxsize=1)
def calculateur() -> Calculateur:
    return Calculateur()
