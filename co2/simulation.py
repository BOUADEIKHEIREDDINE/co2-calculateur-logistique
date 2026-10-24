"""Génération des extractions internes FastColis (données fictives).

Le cours autorise des fichiers fictifs pour les données internes (SAP, flashages,
transporteurs). Pour qu'ils servent vraiment à évaluer le pipeline, la simulation
procède en deux temps :

1. elle fait circuler chaque colis dans un réseau réaliste (sites géolocalisés,
   distances routières OSRM, routes maritimes, facteurs ADEME) et enregistre la
   vérité terrain : trajet réel, véhicules, émissions exactes ;
2. elle dégrade ces données comme le feraient de vrais systèmes : scans manquants
   ou en double, deux versions de firmware des scanners, unités mélangées, codes
   de site historiques, transporteurs non renseignés, GPS inversés...

Le pipeline ne lit jamais la vérité terrain : elle ne sert qu'à mesurer la qualité
de ses estimations (étape de validation et évaluation du modèle).
"""
from __future__ import annotations

import json
import string
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C
from . import referentiels as R
from .geo import distance_mer_km, haversine_km

VERITE = C.SOURCES / "_verite_terrain"
PARIS = "Europe/Paris"
FUSEAUX_SECOURS = {"IST": "Europe/Istanbul"}   # fuseaux absents d'OpenFlights


@dataclass
class Etape:
    de: str
    vers: str
    mode: str
    vehicule: str
    distance_km: float
    transporteur: str | None = None
    duree_h: float = 0.0


@dataclass
class Colis:
    tracking: str
    client: str
    service: str
    livraison: str
    poids_kg: float
    dims_cm: tuple
    cree_le: pd.Timestamp
    origine: dict
    destination: dict
    etapes: list = field(default_factory=list)
    scans: list = field(default_factory=list)


class Reseau:
    """Le réseau physique et ses distances réelles."""

    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.sites = R.reseau_sites().set_index("site_code")
        osrm = R.distances_osrm(self.sites.reset_index())
        self.route = {(a, b): d for a, b, d in osrm.itertuples(index=False)}
        hav = haversine_km(self.sites.lat.values[:, None], self.sites.lon.values[:, None],
                           self.sites.lat.values[None, :], self.sites.lon.values[None, :])
        codes = self.sites.index.to_numpy()
        ratios = [self.route[(codes[i], codes[j])] / hav[i, j]
                  for i in range(len(codes)) for j in range(len(codes))
                  if i != j and hav[i, j] > 20 and (codes[i], codes[j]) in self.route]
        self.detours = np.array(ratios)          # distribution empirique des détours routiers
        self.villes_fr = R.villes_france()
        self.poids_villes = self.villes_fr.population / self.villes_fr.population.sum()
        self.agences = self.sites[self.sites.type_site == "AGENCE"].reset_index().set_index("departement")
        self.aeroports = R.aeroports()
        self._cache_etr: dict = {}
        self._cache_sites = {c: {"code": c, "lat": float(r.lat), "lon": float(r.lon), "pays": r.pays,
                                 "ville": r.ville} for c, r in self.sites.iterrows()}

    def dist_route(self, a: dict, b: dict) -> float:
        cle = (a.get("code"), b.get("code"))
        if cle in self.route:
            return self.route[cle]
        h = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
        return float(h * self.rng.choice(self.detours)) if h > 0.5 else float(h * 1.3 + 0.3)

    def point_site(self, code: str) -> dict:
        return dict(self._cache_sites[code])

    def ville_aleatoire(self) -> dict:
        r = self.villes_fr.iloc[self.rng.choice(len(self.villes_fr), p=self.poids_villes)]
        # adresse à quelques km du centre-ville
        rayon = min(6.0, 1.0 + np.sqrt(r.population) / 120)
        ang, dist = self.rng.uniform(0, 2 * np.pi), rayon * np.sqrt(self.rng.uniform())
        return {"code": None, "ville": r["name"], "pays": "FR", "departement": r.departement,
                "population": int(r.population), "tz": PARIS,
                "lat": float(r.lat + dist / 111 * np.cos(ang)),
                "lon": float(r.lon + dist / (111 * np.cos(np.radians(r.lat))) * np.sin(ang))}

    def ville_etrangere(self, nom: str, pays: str) -> dict:
        if (nom, pays) in self._cache_etr:
            return dict(self._cache_etr[(nom, pays)])
        v = R.villes()
        r = v[(v.name == nom) & (v.pays == pays)].sort_values("population").iloc[-1]
        self._cache_etr[(nom, pays)] = {"code": None, "ville": nom, "pays": pays, "lat": float(r.lat),
                                        "lon": float(r.lon), "tz": r.timezone}
        return dict(self._cache_etr[(nom, pays)])

    def aeroport(self, iata: str) -> dict:
        a = self.aeroports.loc[iata]
        return {"code": f"PART-{iata}", "ville": a.ville, "pays": None, "lat": float(a.lat),
                "lon": float(a.lon), "tz": a.tz if isinstance(a.tz, str) else FUSEAUX_SECOURS[iata]}


# ---------------------------------------------------------------------------
# Transporteurs : flotte interne et sous-traitants
# ---------------------------------------------------------------------------
LIBELLES_VEHICULE = {
    "ROUTE_ART_40T_DIESEL": ["Semi-remorque 40T", "Articulé 40 t", "SEMI 44T gazole", "Tracteur + semi"],
    "ROUTE_ART_40T_GNC": ["Semi 40T GNV", "Articulé 40t gaz"],
    "ROUTE_ART_40T_GNL": ["Semi 40T GNL", "Articulé GNL"],
    "ROUTE_RIG_20T_DIESEL": ["Porteur 19T", "PL 19 t", "Porteur 20T"],
    "ROUTE_RIG_12T_DIESEL": ["Porteur 12T", "PL 12t"],
    "ROUTE_RIG_7T_ELEC": ["Porteur 7.5T électrique", "Porteur 7,5 t élec"],
    "VUL_DIESEL": ["VUL 3.5T", "Fourgon 12m3", "Utilitaire 3,5 t"],
    "VUL_ELEC": ["VUL électrique", "Fourgon élec 3.5T", "e-Fourgon"],
    "VUL_GNC": ["Fourgon GNV"],
    "VELO_CARGO": ["Vélo cargo", "Triporteur électrique", "Vélo-cargo"],
    "FER_ELEC": ["Caisse mobile rail-route", "Wagon combiné"],
    "AIR_CARGO_5000P": ["Fret aérien long-courrier"],
    "AIR_CARGO_2000_5000": ["Fret aérien moyen-courrier"],
    "MER_PC_ASIE_EUN": ["Conteneur 40'"], "MER_PC_ASIE_MED": ["Conteneur 40'"],
    "MER_PC_EUR_AFR": ["Conteneur 20'"], "MER_PC_TRANSAT": ["Conteneur 40'"],
}
ENERGIE = {"DIESEL": "Gazole", "GNC": "GNV", "GNL": "GNL", "ELEC": "Électrique", "CARGO": "Électrique"}


def generer_transporteurs(rng) -> pd.DataFrame:
    lignes, n = [], {"FC": 0, "ST": 0}
    plan = [  # (code véhicule, nb flottes internes, nb sous-traitants)
        ("ROUTE_ART_40T_DIESEL", 6, 10), ("ROUTE_ART_40T_GNC", 3, 2), ("ROUTE_ART_40T_GNL", 1, 2),
        ("ROUTE_RIG_20T_DIESEL", 6, 6), ("ROUTE_RIG_12T_DIESEL", 3, 4), ("ROUTE_RIG_7T_ELEC", 3, 0),
        ("VUL_DIESEL", 10, 18), ("VUL_ELEC", 8, 3), ("VUL_GNC", 1, 2), ("VELO_CARGO", 3, 3),
        ("FER_ELEC", 0, 2), ("AIR_CARGO_5000P", 0, 4), ("AIR_CARGO_2000_5000", 0, 2),
        ("MER_PC_ASIE_EUN", 0, 2), ("MER_PC_ASIE_MED", 0, 1), ("MER_PC_EUR_AFR", 0, 1),
        ("MER_PC_TRANSAT", 0, 1),
    ]
    noms_st = ["Transports Martin", "Logi Sud", "TransEurope", "Express Ouest", "Rapid'Colis",
               "Groupe Duval", "Nord Fret", "Alpes Logistique", "Atlantique TP", "Courses Urbaines",
               "Cyclo Fret", "Green Last Mile", "Sky Cargo Partners", "Asia Air Freight",
               "Ocean Box Lines", "Medi Container", "Rail Combi", "Euro Messagerie"]
    for code, n_int, n_st in plan:
        for interne, nb in ((True, n_int), (False, n_st)):
            for _ in range(nb):
                prefixe = "FC" if interne else "ST"
                n[prefixe] += 1
                lignes.append({
                    "transporteur_id": f"{prefixe}-{n[prefixe]:03d}",
                    "interne": interne,
                    "vehicule_vrai": code,
                    "raison_sociale": "FastColis" if interne else rng.choice(noms_st),
                })
    return pd.DataFrame(lignes)


# ---------------------------------------------------------------------------
# Circulation des colis
# ---------------------------------------------------------------------------
def _tirer(rng, options: dict):
    cles = list(options)
    p = np.array(list(options.values()), dtype=float)
    return cles[rng.choice(len(cles), p=p / p.sum())]


def _date_commande(rng, n: int) -> pd.DatetimeIndex:
    jours = pd.date_range(C.PERIODE_DEBUT, C.PERIODE_FIN, freq="D")
    poids = np.ones(len(jours))
    poids[(jours.month == 11) & (jours.day >= 20)] *= 2.2        # Black Friday
    poids[(jours.month == 12) & (jours.day <= 20)] *= 1.9        # Noël
    poids[jours.month.isin([7, 8])] *= 0.8
    poids[jours.dayofweek == 6] *= 0.35
    j = rng.choice(len(jours), size=n, p=poids / poids.sum())
    heures = rng.normal(14, 4.5, n).clip(0, 23.9)
    return pd.DatetimeIndex(jours[j]) + pd.to_timedelta(heures, unit="h")


class Simulateur:
    def __init__(self, seed: int = C.SEED):
        self.rng = np.random.default_rng(seed)
        self.net = Reseau(self.rng)
        self.transporteurs = generer_transporteurs(self.rng)
        self.par_vehicule = self.transporteurs.groupby("vehicule_vrai").transporteur_id.apply(list).to_dict()
        self.interne = dict(zip(self.transporteurs.transporteur_id, self.transporteurs.interne))

    # -- choix des véhicules --------------------------------------------------
    def transporteur(self, vehicule: str) -> str:
        return str(self.rng.choice(self.par_vehicule[vehicule]))

    def etape(self, a: dict, b: dict, mode: str, vehicule: str, distance: float | None = None) -> Etape:
        if distance is None:
            distance = self.net.dist_route(a, b)
        vitesse = C.VITESSES_KMH["route_longue" if distance > 150 else "route_courte"] if mode == "route" \
            else C.VITESSES_KMH[mode]
        return Etape(a.get("code") or a["ville"], b.get("code") or b["ville"], mode, vehicule,
                     round(distance, 2), self.transporteur(vehicule), distance / vitesse)

    def linehaul(self, service: str, distance: float) -> tuple[str, str]:
        if service == "ecologique" and distance > 450 and self.rng.random() < 0.7:
            return "fer", "FER_ELEC"
        if service == "express":
            return "route", "ROUTE_ART_40T_DIESEL"
        if service == "ecologique":
            return "route", _tirer(self.rng, {"ROUTE_ART_40T_GNC": 0.6, "ROUTE_ART_40T_GNL": 0.2,
                                              "ROUTE_ART_40T_DIESEL": 0.2})
        return "route", _tirer(self.rng, {"ROUTE_ART_40T_DIESEL": 0.78, "ROUTE_ART_40T_GNC": 0.14,
                                          "ROUTE_ART_40T_GNL": 0.08})

    def capillaire(self, service: str) -> str:
        if service == "ecologique":
            return _tirer(self.rng, {"ROUTE_RIG_7T_ELEC": 0.55, "ROUTE_RIG_20T_DIESEL": 0.3,
                                     "ROUTE_RIG_12T_DIESEL": 0.15})
        return _tirer(self.rng, {"ROUTE_RIG_20T_DIESEL": 0.6, "ROUTE_RIG_12T_DIESEL": 0.3,
                                 "ROUTE_RIG_7T_ELEC": 0.1})

    def dernier_km(self, service: str, dest: dict) -> str:
        grande_ville = dest.get("population", 0) > 150_000
        if service == "ecologique":
            if grande_ville and self.rng.random() < 0.6:
                return "VELO_CARGO"
            return _tirer(self.rng, {"VUL_ELEC": 0.65, "VUL_DIESEL": 0.3, "VUL_GNC": 0.05})
        if grande_ville and self.rng.random() < 0.08:
            return "VELO_CARGO"
        return _tirer(self.rng, {"VUL_DIESEL": 0.68, "VUL_ELEC": 0.25, "VUL_GNC": 0.07})

    # -- un colis ---------------------------------------------------------------
    def origine(self, client: str, typ: str) -> tuple[dict, str]:
        rng = self.rng
        if typ == "INTL" or (client == "AMAZON" and rng.random() < 0.08) \
                or (client == "CDISCOUNT" and rng.random() < 0.06):
            if typ == "INTL":
                ville = _tirer(rng, {"Shenzhen": 0.6, "Shanghai": 0.25, "Hong Kong": 0.15})
            elif client == "AMAZON":
                ville = _tirer(rng, {"Shenzhen": 0.4, "Shanghai": 0.15, "Seoul": 0.1,
                                     "New York City": 0.15, "Istanbul": 0.1, "Montréal": 0.1})
            else:
                ville = _tirer(rng, {"Casablanca": 0.45, "Istanbul": 0.35, "Shenzhen": 0.2})
            pays = C.ORIGINES_INTERNATIONALES[ville][0]
            return self.net.ville_etrangere(ville, pays), "international"
        if client == "VINTED" and rng.random() < 0.08:
            ville = rng.choice(list(C.ORIGINES_EUROPE))
            return self.net.ville_etrangere(ville, C.ORIGINES_EUROPE[ville][0]), "international"
        if client == "ZALANDO" and rng.random() < 0.5:
            return self.net.ville_etrangere("Mönchengladbach", "DE"), "international"
        if client == "VINTED":
            return self.net.ville_aleatoire(), "domestique"
        code = rng.choice([c for c in self.net.sites.index if c.startswith(f"WH-{client[:3]}")])
        return self.net.point_site(code), "domestique"

    def acheminer(self, c: Colis, perimetre: str) -> None:
        rng, net = self.rng, self.net
        o, d = c.origine, c.destination
        e = []
        if perimetre == "international":
            if o["pays"] in {"ES", "IT", "DE", "PL", "BE", "NL"}:
                entree = net.point_site(C.ORIGINES_EUROPE[o["ville"]][1])
                e.append(self.etape(o, entree, "route", _tirer(rng, {"ROUTE_ART_40T_DIESEL": 0.85,
                                                                     "ROUTE_RIG_20T_DIESEL": 0.15})))
            else:
                iata = C.ORIGINES_INTERNATIONALES[o["ville"]][1]
                pays = o["pays"]
                p_air = {"CN": 0.85, "HK": 0.95, "KR": 0.9, "US": 0.9, "CA": 0.9, "MA": 0.5, "TR": 0.4}[pays]
                if c.service == "express":
                    p_air = 1.0
                mode = "air" if rng.random() < p_air else ("route" if pays == "TR" else "mer")
                if mode == "air":
                    hub = net.aeroport(iata)
                    e.append(self.etape(o, hub, "route", "ROUTE_ART_40T_DIESEL"))
                    entree = net.point_site("ENT-CDG")
                    gcd = float(haversine_km(hub["lat"], hub["lon"], entree["lat"], entree["lon"]))
                    dist = gcd + C.AIR_KM_SUPPLEMENTAIRES
                    e.append(self.etape(hub, entree, "air", R.facteur_air(dist), dist))
                elif mode == "route":
                    entree = net.point_site("ENT-STR")
                    e.append(self.etape(o, entree, "route", "ROUTE_ART_40T_DIESEL"))
                else:
                    port = "ENT-FOS" if pays == "MA" else _tirer(rng, {"ENT-LEH": 0.4, "ENT-RTM": 0.45,
                                                                      "ENT-FOS": 0.15})
                    entree = net.point_site(port)
                    hub = {**net.aeroport(iata), "code": f"PORT-{iata}"}
                    e.append(self.etape(o, hub, "route", "ROUTE_ART_40T_DIESEL"))
                    dist = distance_mer_km(hub["lat"], hub["lon"], entree["lat"], entree["lon"])
                    e.append(self.etape(hub, entree, "mer", R.facteur_mer(pays, port), dist))
            tri_o = net.sites.loc[entree["code"], "tri_rattachement"]
            e.append(self.etape(entree, net.point_site(tri_o), "route", "ROUTE_ART_40T_DIESEL"))
        elif o.get("code"):                                   # entrepôt client
            tri_o = net.sites.loc[o["code"], "tri_rattachement"]
            e.append(self.etape(o, net.point_site(tri_o), "route",
                                _tirer(rng, {"ROUTE_ART_40T_DIESEL": 0.8, "ROUTE_ART_40T_GNC": 0.2})))
        else:                                                 # particulier : dépôt en point relais
            ag_o = net.agences.loc[o["departement"]]
            ag_o = net.point_site(ag_o.site_code)
            e.append(self.etape(o, ag_o, "vul", "VUL_DIESEL",
                                net.dist_route(o, ag_o) * C.TOURNEE_FACTEUR))
            tri_o = net.sites.loc[ag_o["code"], "tri_rattachement"]
            e.append(self.etape(ag_o, net.point_site(tri_o), "route", self.capillaire(c.service)))

        ag_d = net.point_site(net.agences.loc[d["departement"]].site_code)
        tri_d = net.sites.loc[ag_d["code"], "tri_rattachement"]
        if tri_o != tri_d:
            direct = net.route[(tri_o, tri_d)]
            via_hub = c.service == "standard" and direct > 250 and rng.random() < 0.45
            etapes_lh = [(tri_o, "TRI-NAT"), ("TRI-NAT", tri_d)] if via_hub else [(tri_o, tri_d)]
            for a, b in etapes_lh:
                pa, pb = net.point_site(a), net.point_site(b)
                mode, veh = self.linehaul(c.service, net.route[(a, b)])
                dist = net.route[(a, b)] * (C.DETOUR_FER / 1.29 if mode == "fer" else 1.0)
                e.append(self.etape(pa, pb, mode, veh, dist))
        e.append(self.etape(net.point_site(tri_d), ag_d, "route", self.capillaire(c.service)))
        veh = self.dernier_km(c.service, d)
        mode = "velo" if veh == "VELO_CARGO" else "vul"
        facteur = C.TOURNEE_FACTEUR * (0.6 if c.livraison == "point_relais" else 1.0)
        e.append(self.etape(ag_d, d, mode, veh, net.dist_route(ag_d, d) * facteur))
        c.etapes = e

    def horodater(self, c: Colis) -> None:
        """Crée les scans réels (avant dégradation) le long du trajet."""
        rng = self.rng
        t = c.cree_le + pd.Timedelta(hours=float(rng.uniform(2, 20 if c.service != "express" else 8)))
        scans = []
        o = c.origine
        if not o.get("code") and o["pays"] == "FR":
            scans.append(("DEPOT_RELAIS", f"PR-{o['departement']}{rng.integers(100, 999)}", t, o, None))
        elif (o.get("code") or "").startswith("WH-"):
            scans.append(("PRISE_EN_CHARGE", o["code"], t, o, None))
        for i, et in enumerate(c.etapes):
            t = t + pd.Timedelta(hours=et.duree_h * float(rng.uniform(0.9, 1.4)))
            if et.mode == "mer":
                t += pd.Timedelta(days=float(rng.uniform(2, 6)))    # attente au port, dédouanement
            if et.mode == "air":
                t += pd.Timedelta(hours=float(rng.uniform(6, 30)))
            fin = et.vers
            if fin.startswith("PART-") or fin.startswith("PORT-"):
                scans.append(("HUB_PARTENAIRE", fin, t, None, et.transporteur))
                t += pd.Timedelta(hours=float(rng.uniform(3, 24)))
                continue
            if fin in self.net.sites.index:
                typ = self.net.sites.at[fin, "type_site"]
                evt = {"ENTREE": "ENTREE_PLATEFORME", "TRI": "TRI", "HUB": "TRI",
                       "AGENCE": "ARRIVEE_AGENCE"}[typ]
                scans.append((evt, fin, t, None, et.transporteur))
                if typ == "ENTREE":
                    t += pd.Timedelta(hours=float(rng.uniform(4, 30)))   # douane
                elif typ == "AGENCE" and i == len(c.etapes) - 2:
                    lendemain = (t + pd.Timedelta(hours=6)).normalize() + pd.Timedelta(
                        hours=float(rng.uniform(6.5, 8.5)))
                    t = max(lendemain, t + pd.Timedelta(minutes=30))
                    scans.append(("DEPART_TOURNEE", fin, t, None, c.etapes[i + 1].transporteur))
                else:
                    t += pd.Timedelta(hours=float(rng.uniform(1, 8 if c.service != "express" else 3)))
            else:
                t += pd.Timedelta(hours=float(rng.uniform(0.3, 5)))      # position dans la tournée
                evt = "LIVRE_RELAIS" if c.livraison == "point_relais" else "LIVRE"
                site = c.etapes[i - 1].vers if i else fin
                scans.append((evt, site, t, c.destination, et.transporteur))
        c.scans = scans

    def colis(self, n: int) -> list[Colis]:
        rng = self.rng
        noms = list(C.CLIENTS)
        parts = np.array([C.CLIENTS[k][0] for k in noms])
        clients = rng.choice(noms, size=n, p=parts / parts.sum())
        dates = _date_commande(rng, n)
        tous = []
        for i in range(n):
            client = clients[i]
            _, typ, (mu, sigma) = C.CLIENTS[client]
            orig, perimetre = self.origine(client, typ)
            if perimetre == "international":
                service = "express" if rng.random() < 0.12 else "international"
            elif typ == "C2C":
                service = _tirer(rng, {"standard": 0.55, "ecologique": 0.3, "express": 0.15})
            else:
                service = _tirer(rng, {"standard": 0.58, "express": 0.27, "ecologique": 0.15})
            livraison = "point_relais" if rng.random() < (0.8 if client == "VINTED" else 0.28) else "domicile"
            poids = float(np.clip(rng.lognormal(mu, sigma), 0.05, 60 if client == "LEROY MERLIN" else 30))
            densite = rng.uniform(80, 350)                         # kg/m3
            vol = poids / densite
            ratio = rng.dirichlet([3, 2, 1.5])
            cote = (vol * 1e6) ** (1 / 3)
            dims = tuple(sorted((round(float(cote * (r * 3) ** 0.5), 1) for r in ratio), reverse=True))
            dest = self.net.ville_aleatoire()
            if orig.get("ville") == dest["ville"] and orig.get("code") is None:
                dest = self.net.ville_aleatoire()
            c = Colis(tracking=f"FC{rng.integers(10**9, 10**10)}", client=client, service=service,
                      livraison=livraison, poids_kg=round(poids, 3), dims_cm=dims, cree_le=dates[i],
                      origine=orig, destination=dest)
            self.acheminer(c, perimetre)
            self.horodater(c)
            tous.append(c)
        return tous


# ---------------------------------------------------------------------------
# Écriture des sources dégradées
# ---------------------------------------------------------------------------
ALIAS_SITES = {  # codes de l'ancien WMS encore utilisés par certains scanners
    "TRI-IDF": "GON01", "TRI-NAT": "ORL-HUB", "TRI-LYS": "LYS02", "TRI-MRS": "MRS01",
    "TRI-BOD": "BDX01", "TRI-LIL": "LIL-TRI", "ENT-CDG": "CDG-FRET", "ENT-LEH": "LEH-PORT",
}
VARIANTES_CLIENT = {
    "AMAZON": ["AMAZON EU SARL", "Amazon", "amazon.fr", "AMAZON FRANCE LOGISTIQUE"],
    "VINTED": ["VINTED UAB", "Vinted", "vinted"],
    "CDISCOUNT": ["CDISCOUNT SA", "Cdiscount", "C-DISCOUNT"],
    "SHEIN": ["SHEIN DISTRIBUTION", "Shein", "SHEIN DIST. CORP"],
    "ZALANDO": ["ZALANDO SE", "Zalando"],
    "DECATHLON": ["DECATHLON FRANCE", "Decathlon"],
    "BACK MARKET": ["BACK MARKET", "BackMarket", "Back Market SAS"],
    "LEROY MERLIN": ["LEROY MERLIN FRANCE", "Leroy-Merlin"],
}
CODES_CLIENT = {k: f"{100100 + i * 7}" for i, k in enumerate(C.CLIENTS)}
VSART = {"standard": ["01", "STD", "Standard"], "express": ["02", "EXP", "Express 24h"],
         "ecologique": ["03", "ECO", "Écologique"], "international": ["04", "INT", "International"]}
PAYS_VARIANTES = {"FR": ["FR", "France", "FRA", "fr"], "CN": ["CN", "Chine", "CHN"], "HK": ["HK", "Hong Kong"],
                  "TR": ["TR", "Turquie", "TUR"], "MA": ["MA", "Maroc", "MAR"], "US": ["US", "USA", "Etats-Unis"],
                  "CA": ["CA", "Canada"], "KR": ["KR", "Corée du Sud", "KOR"], "ES": ["ES", "Espagne", "ESP"],
                  "IT": ["IT", "Italie"], "DE": ["DE", "Allemagne", "DEU"], "PL": ["PL", "Pologne"],
                  "BE": ["BE", "Belgique"], "NL": ["NL", "Pays-Bas"]}
CATEGORIES = ["Mode", "High-tech", "Maison", "Sport", "Livres", "Jouets", "Beauté", "Bricolage"]


def _sans_accents(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def _variante_ville(rng, ville: str) -> str:
    u = rng.random()
    if u < 0.55:
        return ville
    if u < 0.75:
        return ville.upper()
    if u < 0.85:
        return _sans_accents(ville).upper()
    if u < 0.93:
        return ville.replace("Saint-", "St-").replace("Sainte-", "Ste-")
    return ville.lower().replace("-", " ")


def ecrire_sap(rng, colis: list[Colis], defauts: list) -> pd.DataFrame:
    lignes = []
    for c in colis:
        o, d = c.origine, c.destination
        unite = "KG"
        poids = c.poids_kg
        u = rng.random()
        if u < 0.08:
            unite, poids = "G", round(poids * 1000)
        elif u < 0.10:
            poids = round(poids * 1000)
            defauts.append((c.tracking, "sap", "poids_en_grammes_unite_kg"))
        elif u < 0.125:
            poids = None
            defauts.append((c.tracking, "sap", "poids_manquant"))
        elif u < 0.127:
            poids = float(rng.choice([0, -1, -poids]))
            defauts.append((c.tracking, "sap", "poids_negatif_ou_nul"))
        dims, meins = list(c.dims_cm), "CM"
        v = rng.random()
        if v < 0.10:
            dims, meins = [round(x * 10) for x in dims], "MM"
        elif v < 0.22:
            dims, meins = [None, None, None], None
            defauts.append((c.tracking, "sap", "dimensions_manquantes"))
        d_fmt = rng.random()
        if d_fmt < 0.85:
            erdat = c.cree_le.strftime("%Y%m%d")
        elif d_fmt < 0.95:
            erdat = c.cree_le.strftime("%d.%m.%Y")
        else:
            erdat = c.cree_le.strftime("%Y-%m-%d")
        montant = round(float(rng.lognormal(3.3, 0.8)), 2)
        devise = "EUR"
        if o["pays"] in {"CN", "HK"} and rng.random() < 0.3:
            devise, montant = "CNY", round(montant * 7.8, 2)
        elif o["pays"] in {"US", "CA"}:
            devise, montant = "USD", round(montant * 1.08, 2)
        lignes.append({
            "VBELN": f"{rng.integers(10**7, 10**8)}",
            "TRACKING": c.tracking,
            "KUNNR": CODES_CLIENT[c.client],
            "NAME1": rng.choice(VARIANTES_CLIENT[c.client]),
            "MATKL": rng.choice(CATEGORIES),
            "BRGEW": None if poids is None else str(poids).replace(".", ","),
            "GEWEI": unite if rng.random() > 0.03 else "",
            "LAENG": dims[0], "BREIT": dims[1], "HOEHE": dims[2], "MEINS": meins,
            "VSART": rng.choice(VSART[c.service]),
            "LIVR": "PR" if c.livraison == "point_relais" else "DOM",
            "LAND1_ORIG": rng.choice(PAYS_VARIANTES[o["pays"]]),
            "ORT01_ORIG": _variante_ville(rng, o["ville"]),
            "WERKS": o["code"] if o.get("code") else "",
            "LAND1_DEST": rng.choice(PAYS_VARIANTES["FR"]),
            "ORT01_DEST": _variante_ville(rng, d["ville"]),
            "REGIO_DEST": d["departement"] if rng.random() > 0.04 else "",
            "ERDAT": erdat,
            "ERZET": c.cree_le.strftime("%H%M%S"),
            "NETWR": str(montant).replace(".", ","),
            "WAERK": devise,
            "ZLSCH": rng.choice(["CB", "PAYPAL", "VIR", "CB", "CB", "KLARNA"]),
        })
    sap = pd.DataFrame(lignes)
    # doublons : réexportations du même colis (identiques ou au format de date différent)
    idx = rng.choice(len(sap), size=int(0.012 * len(sap)), replace=False)
    dup = sap.iloc[idx].copy()
    idx2 = rng.choice(len(sap), size=int(0.005 * len(sap)), replace=False)
    dup2 = sap.iloc[idx2].copy()
    dup2["ERDAT"] = [c.cree_le.strftime("%d.%m.%Y") for c in (colis[i] for i in idx2)]
    for t in pd.concat([dup, dup2]).TRACKING:
        defauts.append((t, "sap", "ligne_en_double"))
    sap = pd.concat([sap, dup, dup2]).sample(frac=1, random_state=int(rng.integers(1e6))).reset_index(drop=True)
    return sap


def _format_tracking(rng, t: str, defauts: list) -> str:
    u = rng.random()
    if u < 0.03:
        defauts.append((t, "scan", "tracking_sans_prefixe"))
        return t[2:]
    if u < 0.06:
        return t.lower()
    if u < 0.08:
        return f"{t[:2]} {t[2:6]} {t[6:9]} {t[9:]}"
    return t


def ecrire_flashages(rng, colis: list[Colis], sim: Simulateur, defauts: list) -> list[dict]:
    """Événements de flashage, au format de deux générations de scanners."""
    sites = sim.net.sites
    v1 = set(rng.choice(sites.index, size=int(0.35 * len(sites)), replace=False))   # vieux firmware
    fin_extraction = pd.Timestamp(C.PERIODE_FIN) + pd.Timedelta(days=1)
    evenements = []
    for c in colis:
        scans = list(c.scans)
        intermediaires = [i for i, s in enumerate(scans) if s[0] in ("TRI", "ARRIVEE_AGENCE",
                                                                     "ENTREE_PLATEFORME", "HUB_PARTENAIRE")]
        # scans manquants : flashage oublié, scanner hors réseau, partenaire sans EDI
        retirer = set(i for i in intermediaires if scans[i][0] == "HUB_PARTENAIRE" and rng.random() < 0.6)
        if intermediaires and rng.random() < 0.18:
            k = min(len(intermediaires), int(rng.integers(1, 3)))
            retirer |= set(rng.choice(intermediaires, size=k, replace=False).tolist())
        if scans and scans[0][0] in ("PRISE_EN_CHARGE", "DEPOT_RELAIS") and rng.random() < 0.04:
            retirer.add(0)
        if rng.random() < 0.01:
            retirer.add(len(scans) - 1)                      # colis perdu ou scan de livraison absent
            defauts.append((c.tracking, "scan", "livraison_non_flashee"))
        for i in sorted(retirer):
            defauts.append((c.tracking, "scan", f"scan_manquant:{scans[i][0]}"))
        for i, (evt, site, t, point, transp) in enumerate(scans):
            if i in retirer or t > fin_extraction:
                continue
            if transp is not None:
                manque = 0.25 if not sim.interne[transp] else 0.08
                if rng.random() < manque:
                    defauts.append((c.tracking, "scan", "transporteur_absent"))
                    transp = None
                elif rng.random() < 0.03:
                    transp = transp[:4]
                    defauts.append((c.tracking, "scan", "transporteur_tronque"))
            if point is None and site in sites.index:
                lat, lon = sites.at[site, "lat"], sites.at[site, "lon"]
            elif point is None and site.startswith(("PART-", "PORT-")):
                a = sim.net.aeroports.loc[site.split("-")[1]]
                lat, lon = a.lat, a.lon
            else:
                lat, lon = point["lat"], point["lon"]
            g = rng.random()
            if g < 0.30:
                lat = lon = None
            elif g < 0.32:
                lat, lon = lon, lat
                defauts.append((c.tracking, "scan", "gps_inverse"))
            elif g < 0.33:
                lat = lon = 0.0
                defauts.append((c.tracking, "scan", "gps_zero"))
            code = site
            s = rng.random()
            if site in ALIAS_SITES and s < 0.25:
                code = ALIAS_SITES[site]
            elif s < 0.30:
                code = site.lower()
            elif s < 0.33:
                code = f" {site} "
            ts = t
            if site.startswith(("PART-", "PORT-")):
                tz = sim.net.aeroports.loc[site.split("-")[1]].tz
                tz = tz if isinstance(tz, str) else FUSEAUX_SECOURS[site.split("-")[1]]
            else:
                tz = PARIS
            if rng.random() < 0.004:
                ts = t - pd.Timedelta(days=1)
                defauts.append((c.tracking, "scan", "horloge_decalee"))
            ev = {"tracking": _format_tracking(rng, c.tracking, defauts), "evt": evt, "site": code,
                  "t": ts, "tz": tz, "lat": lat, "lon": lon, "transporteur": transp,
                  "firmware": "v1" if site in v1 else "v2", "sans_fuseau": rng.random() < 0.05}
            evenements.append(ev)
            if rng.random() < 0.03:
                double = dict(ev, t=ts + pd.Timedelta(seconds=int(rng.integers(1, 90))))
                evenements.append(double)
                defauts.append((c.tracking, "scan", "scan_en_double"))
    # scans orphelins : colis d'un autre système, étiquettes réimprimées
    for _ in range(300):
        ev = dict(evenements[int(rng.integers(len(evenements)))])
        ev["tracking"] = f"FC{rng.integers(10**9, 10**10)}"
        evenements.append(ev)
        defauts.append((ev["tracking"], "scan", "scan_orphelin"))
    return evenements


def _serialiser(ev: dict) -> dict:
    """Format JSON propre à chaque génération de scanner."""
    # l'horloge de la simulation est l'heure de Paris ; chaque scanner affiche l'heure locale de son site
    t = ev["t"].tz_localize(PARIS, ambiguous=True, nonexistent="shift_forward").tz_convert(ev["tz"])
    if ev["firmware"] == "v1":
        d = {"trk": ev["tracking"], "evt": ev["evt"][:3] + "_" + ev["evt"][-3:], "site": ev["site"],
             "ts": int(t.tz_convert("UTC").timestamp() * 1000)}
        if ev["lat"] is not None:
            d["gps"] = f"{ev['lat']:.5f},{ev['lon']:.5f}"
        if ev["transporteur"]:
            d["carrier"] = ev["transporteur"]
        return d
    horodatage = t.isoformat(timespec="seconds")
    if ev.get("sans_fuseau"):
        horodatage = t.strftime("%Y-%m-%dT%H:%M:%S")          # heure locale sans décalage UTC
    d = {"tracking_id": ev["tracking"], "event_type": ev["evt"], "site_code": ev["site"],
         "timestamp": horodatage,
         "geo": {"lat": ev["lat"], "lon": ev["lon"]} if ev["lat"] is not None else None,
         "carrier_id": ev["transporteur"]}
    return d


def ecrire_transporteurs(rng, tr: pd.DataFrame, defauts: list) -> None:
    def energie(code):
        for k, v in ENERGIE.items():
            if k in code:
                return v
        return "Kérosène" if code.startswith("AIR") else ("Fioul lourd" if code.startswith("MER") else "Gazole")

    internes, st = [], []
    for r in tr.itertuples():
        libelle = rng.choice(LIBELLES_VEHICULE[r.vehicule_vrai])
        en = energie(r.vehicule_vrai)
        if r.interne:
            internes.append({"Code flotte": r.transporteur_id, "Type de véhicule": libelle,
                             "Énergie": en if rng.random() > 0.1 else "",
                             "Mise en service": int(rng.integers(2016, 2026))})
        else:
            if rng.random() < 0.12:
                libelle = ""
                defauts.append((r.transporteur_id, "transporteurs", "categorie_vehicule_absente"))
            mode = {"ROUTE": "Route", "VUL": "Route", "VELO": "Vélo", "FER": "Ferroviaire",
                    "AIR": "Aérien", "MER": "Maritime"}[r.vehicule_vrai.split("_")[0]]
            st.append({"ID transporteur": r.transporteur_id.lower() if rng.random() < 0.1 else r.transporteur_id,
                       "Raison sociale": r.raison_sociale, "Mode": mode, "Catégorie": libelle,
                       "Carburant": en if rng.random() > 0.2 else None,
                       "Fin de contrat": pd.Timestamp("2026-01-01") + pd.Timedelta(days=int(rng.integers(0, 900)))})
    st_df = pd.DataFrame(st)
    st_df = pd.concat([st_df, st_df.sample(3, random_state=1)])     # doublons dans l'annuaire
    with pd.ExcelWriter(C.SOURCES / "transporteurs.xlsx") as w:
        pd.DataFrame(internes).to_excel(w, sheet_name="Flotte interne", index=False)
        st_df.to_excel(w, sheet_name="Sous-traitants", index=False)


def ecrire_sites(rng, sim: Simulateur, defauts: list) -> None:
    s = sim.net.sites.reset_index()
    out = s[["site_code", "libelle", "type_site", "ville", "pays", "lat", "lon"]].copy()
    sans_gps = rng.choice(out.index, size=14, replace=False)
    out.loc[sans_gps, ["lat", "lon"]] = None
    for code in out.loc[sans_gps, "site_code"]:
        defauts.append((code, "sites", "coordonnees_manquantes"))
    out["lat"] = out.lat.map(lambda x: None if pd.isna(x) else f"{x:.6f}".replace(".", ","))
    out["lon"] = out.lon.map(lambda x: None if pd.isna(x) else f"{x:.6f}".replace(".", ","))
    out.to_csv(C.SOURCES / "sites_reseau.csv", sep=";", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"ancien_code": v, "site_code": k} for k, v in ALIAS_SITES.items()]).to_csv(
        C.SOURCES / "sites_alias_wms.csv", index=False)


def generer(n: int = C.NB_COLIS, seed: int = C.SEED) -> None:
    sim = Simulateur(seed)
    rng = sim.rng
    colis = sim.colis(n)
    defauts: list = []
    C.SOURCES.mkdir(parents=True, exist_ok=True)
    VERITE.mkdir(parents=True, exist_ok=True)

    # 1. SAP : export CSV Windows-1252, séparateur ';', virgule décimale
    ecrire_sap(rng, colis, defauts).to_csv(C.SOURCES / "sap_export_colis.csv", sep=";", index=False,
                                          encoding="cp1252", errors="replace")
    # 2. Flashages : un fichier JSON Lines par mois
    evts = ecrire_flashages(rng, colis, sim, defauts)
    par_mois: dict = {}
    for ev in evts:
        par_mois.setdefault(ev["t"].strftime("%Y-%m"), []).append(_serialiser(ev))
    dossier = C.SOURCES / "flashages"
    dossier.mkdir(exist_ok=True)
    for mois, lignes in par_mois.items():
        with open(dossier / f"flashages_{mois}.jsonl", "w", encoding="utf-8") as f:
            for l in lignes:
                f.write(json.dumps(l, ensure_ascii=False) + "\n")
    # 3. Transporteurs (Excel, deux onglets aux colonnes différentes) et 4. sites
    ecrire_transporteurs(rng, sim.transporteurs, defauts)
    ecrire_sites(rng, sim, defauts)

    # Vérité terrain, réservée à l'évaluation
    facteurs = R.table_facteurs().set_index("code_vehicule").kgco2e_tkm
    etapes, verite = [], []
    for c in colis:
        total = 0.0
        for k, e in enumerate(c.etapes):
            em = c.poids_kg / 1000 * e.distance_km * facteurs[e.vehicule]
            total += em
            etapes.append({"tracking": c.tracking, "rang": k, "de": e.de, "vers": e.vers, "mode": e.mode,
                           "vehicule": e.vehicule, "transporteur_id": e.transporteur,
                           "distance_km": e.distance_km, "emission_kg": em})
        verite.append({"tracking": c.tracking, "client": c.client, "service": c.service,
                       "livraison": c.livraison, "poids_kg": c.poids_kg,
                       "pays_origine": c.origine["pays"], "ville_origine": c.origine["ville"],
                       "ville_destination": c.destination["ville"],
                       "lat_dest": c.destination["lat"], "lon_dest": c.destination["lon"],
                       "distance_totale_km": sum(e.distance_km for e in c.etapes),
                       "nb_etapes": len(c.etapes), "emission_kg": total})
    pd.DataFrame(verite).to_parquet(VERITE / "colis.parquet", index=False)
    pd.DataFrame(etapes).to_parquet(VERITE / "etapes.parquet", index=False)
    sim.transporteurs.to_parquet(VERITE / "transporteurs.parquet", index=False)
    pd.DataFrame(defauts, columns=["cle", "source", "defaut"]).to_parquet(VERITE / "defauts_injectes.parquet",
                                                                           index=False)
