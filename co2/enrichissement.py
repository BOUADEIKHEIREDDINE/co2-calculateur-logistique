"""Étape 4 : enrichissement.

* géocodage des origines et destinations (GeoNames, GPS des scans de livraison) ;
* topologie du réseau apprise à partir des flashages ;
* reconstitution du trajet de chaque colis, étape par étape, y compris les
  passages non flashés, que l'on déduit de la topologie ;
* distance de chaque étape selon son mode (OSRM, orthodromie + 95 km pour
  l'aérien, route maritime pour le fret conteneur) ;
* imputation du poids manquant.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter

import numpy as np
import pandas as pd

from . import config as C
from . import referentiels as R
from .geo import distance_mer_km, haversine_km
from .nettoyage import Journal, fr, sans_accents

EUROPE = {"ES", "IT", "DE", "PL", "BE", "NL"}
ENTREE_DE_PAYS_EUROPE = {"ES": "ENT-PPG", "IT": "ENT-STR", "DE": "ENT-STR", "PL": "ENT-STR",
                         "BE": "ENT-LIL", "NL": "ENT-LIL"}


# ---------------------------------------------------------------------------
# Géocodage
# ---------------------------------------------------------------------------
def cle_ville(nom) -> str:
    if not isinstance(nom, str):
        return ""
    s = sans_accents(nom).upper().strip()
    s = re.sub(r"\bSTE?[- ]", lambda m: "SAINTE-" if m.group(0).startswith("STE") else "SAINT-", s)
    return re.sub(r"[^A-Z0-9]", "", s)


class Geocodeur:
    def __init__(self):
        v = R.villes().copy()
        v["cle"] = v.name.map(cle_ville)
        self.v = v.sort_values("population", ascending=False)
        fr = R.villes_france().copy()
        fr["cle"] = fr.name.map(cle_ville)
        self.fr = fr.sort_values("population", ascending=False)
        self.index_fr = self.fr.drop_duplicates(["cle", "departement"]).set_index(["cle", "departement"])
        self.index_fr_seul = self.fr.drop_duplicates("cle").set_index("cle")
        self.cles_fr = list(self.index_fr_seul.index)

    def france(self, ville, departement=None) -> tuple:
        """(lat, lon, département, nom officiel, méthode)."""
        k = cle_ville(ville)
        if isinstance(departement, str) and (k, departement) in self.index_fr.index:
            r = self.index_fr.loc[(k, departement)]
            return r.lat, r.lon, departement, r["name"], "nom+departement"
        if k in self.index_fr_seul.index:
            r = self.index_fr_seul.loc[k]
            return r.lat, r.lon, r.departement, r["name"], "nom"
        proche = difflib.get_close_matches(k, self.cles_fr, n=1, cutoff=0.85)
        if proche:
            r = self.index_fr_seul.loc[proche[0]]
            return r.lat, r.lon, r.departement, r["name"], "approchant"
        return np.nan, np.nan, departement, None, "echec"

    def etranger(self, ville, pays) -> tuple:
        m = self.v[(self.v.pays == pays) & (self.v.cle == cle_ville(ville))]
        if m.empty:
            cand = self.v[self.v.pays == pays]
            proche = difflib.get_close_matches(cle_ville(ville), list(cand.cle), n=1, cutoff=0.8)
            if not proche:
                return np.nan, np.nan, None, "echec"
            m = cand[cand.cle == proche[0]]
        r = m.iloc[0]
        return r.lat, r.lon, r["name"], "nom"


def geocoder(colis: pd.DataFrame, sites: pd.DataFrame, scans: pd.DataFrame, j: Journal) -> pd.DataFrame:
    g = Geocodeur()
    df = colis.copy()
    s = sites.set_index("site_code")

    # Destination : ville + département, puis GPS du scan de livraison quand il existe
    cles = df[["ville_destination_brute", "departement_destination"]].drop_duplicates()
    res = {(v, d): g.france(v, d) for v, d in cles.itertuples(index=False)}
    r = [res[(v, d)] for v, d in zip(df.ville_destination_brute, df.departement_destination)]
    df["lat_dest"], df["lon_dest"] = [x[0] for x in r], [x[1] for x in r]
    dep_manquant = df.departement_destination.isna()
    df["departement_destination"] = [x[2] for x in r]
    df["ville_destination"] = [x[3] for x in r]
    methode = pd.Series([x[4] for x in r])
    j.note("colis", "département de destination absent", dep_manquant.sum(), "déduit de la ville (GeoNames)")
    j.note("colis", "villes de destination rapprochées par similarité", (methode == "approchant").sum(),
           "orthographe approchante acceptée (seuil 0,85)")
    j.note("colis", "destination non géocodée", (methode == "echec").sum(), "laissée vide")

    livr = scans[scans.evenement.isin(["LIVRE", "LIVRE_RELAIS"]) & scans.lat.notna()]
    livr = livr.drop_duplicates("tracking_id").set_index("tracking_id")
    gps = df.tracking_id.map(livr.lat).notna()
    proche = gps & (haversine_km(df.tracking_id.map(livr.lat), df.tracking_id.map(livr.lon),
                                 df.lat_dest, df.lon_dest) < 60)
    df.loc[proche, "lat_dest"] = df.loc[proche, "tracking_id"].map(livr.lat)
    df.loc[proche, "lon_dest"] = df.loc[proche, "tracking_id"].map(livr.lon)
    df["source_geo_destination"] = np.where(proche, "gps_livraison", "centre_ville")
    j.note("colis", "position de livraison GPS", proche.sum(),
           f"remplace le centre-ville ({(gps & ~proche).sum()} GPS rejetés : à plus de 60 km de la ville)")

    # Origine : site d'expédition SAP, point relais de dépôt (GPS), ou ville
    depot = scans[(scans.evenement == "DEPOT_RELAIS") & scans.lat.notna()].drop_duplicates("tracking_id")
    depot = depot.set_index("tracking_id")
    lat_o, lon_o, dep_o, src_o, ville_o = [], [], [], [], []
    cache = {}
    for t, site, pays, ville in zip(df.tracking_id, df.site_expedition, df.pays_origine, df.ville_origine_brute):
        if isinstance(site, str) and site in s.index:
            lat_o.append(s.at[site, "lat"]); lon_o.append(s.at[site, "lon"])
            dep_o.append(None); src_o.append("site_expedition"); ville_o.append(s.at[site, "ville"])
            continue
        if (ville, pays) not in cache:
            cache[(ville, pays)] = (g.france(ville) if pays == "FR" else
                                    (*g.etranger(ville, pays)[:2], None, g.etranger(ville, pays)[2], "nom"))
        la, lo, dep, nom, _ = cache[(ville, pays)]
        if t in depot.index:
            la, lo, src = depot.at[t, "lat"], depot.at[t, "lon"], "gps_point_relais"
        else:
            src = "centre_ville"
        lat_o.append(la); lon_o.append(lo); dep_o.append(dep); src_o.append(src); ville_o.append(nom)
    df["lat_orig"], df["lon_orig"], df["departement_origine"] = lat_o, lon_o, dep_o
    df["source_geo_origine"], df["ville_origine"] = src_o, ville_o
    j.note("colis", "origines géocodées", df.lat_orig.notna().sum(),
           "site d'expédition, GPS du point relais ou ville GeoNames")
    return df


# ---------------------------------------------------------------------------
# Topologie apprise à partir des scans
# ---------------------------------------------------------------------------
def apprendre_topologie(scans: pd.DataFrame, sites: pd.DataFrame) -> dict[str, str]:
    """Plateforme de tri de rattachement de chaque agence, entrepôt et porte d'entrée.

    Pour une agence : le TRI flashé juste avant son arrivée. Pour un entrepôt ou
    une entrée : le TRI flashé juste après. À défaut, le TRI le plus proche.
    """
    sc = scans[~scans.site_code.str.startswith("PR-")].sort_values(["tracking_id", "rang", "horodatage_utc"])
    prec = sc.groupby("tracking_id").site_code.shift()
    suiv = sc.groupby("tracking_id").site_code.shift(-1)
    est_tri = lambda x: x.str.startswith("TRI-") & (x != "TRI-NAT")
    votes: dict[str, Counter] = {}
    m = sc.evenement.eq("ARRIVEE_AGENCE") & est_tri(prec.fillna(""))
    for a, t in zip(sc.site_code[m], prec[m]):
        votes.setdefault(a, Counter())[t] += 1
    m = sc.site_code.str.match(r"^(WH|ENT|AG)-") & est_tri(suiv.fillna(""))
    for a, t in zip(sc.site_code[m], suiv[m]):
        votes.setdefault(a, Counter())[t] += 1
    topo = {a: c.most_common(1)[0][0] for a, c in votes.items()}
    tri = sites[sites.site_code.str.match(r"^TRI-") & (sites.site_code != "TRI-NAT")]
    for r in sites.itertuples():
        if r.site_code not in topo and re.match(r"^(WH|ENT|AG)-", r.site_code):
            d = haversine_km(r.lat, r.lon, tri.lat.values, tri.lon.values)
            topo[r.site_code] = tri.site_code.values[int(np.argmin(d))]
    return topo


# ---------------------------------------------------------------------------
# Reconstitution des trajets
# ---------------------------------------------------------------------------
def type_etape(de: str, vers: str) -> str:
    if de == "ORIGINE":
        if vers.startswith(("PART-", "PORT-")):
            return "PRE_ACHEMINEMENT"
        if vers.startswith("ENT-"):
            return "INTERNATIONAL"
        if vers.startswith("AG-"):
            return "COLLECTE"
        return "ENLEVEMENT" if vers.startswith("TRI-") else "AUTRE"
    if de.startswith("WH-"):
        return "ENLEVEMENT"
    if de.startswith("PART-"):
        return "INTERNATIONAL_AIR"
    if de.startswith("PORT-"):
        return "INTERNATIONAL_MER"
    if de.startswith("ENT-"):
        return "POST_ENTREE"
    if vers == "DESTINATION":
        return "DERNIER_KM"
    if de.startswith("TRI-") and vers.startswith("TRI-"):
        return "LIGNE"
    if de.startswith("AG-") and vers.startswith("TRI-"):
        return "CAPILLAIRE_ORIGINE"
    if de.startswith("TRI-") and vers.startswith("AG-"):
        return "CAPILLAIRE"
    return "AUTRE"


def reconstituer(colis: pd.DataFrame, scans: pd.DataFrame, sites: pd.DataFrame, topo: dict,
                 mode_international, j: Journal) -> pd.DataFrame:
    """Une ligne par étape : sites observés + sites déduits de la topologie.

    `mode_international(colis_ligne, delai_h)` renvoie « air », « mer » ou « route » quand
    la porte d'entrée d'un colis venu de l'étranger n'a pas été flashée.
    """
    sc = scans[~scans.site_code.str.startswith("PR-")].sort_values(["tracking_id", "rang", "horodatage_utc"])
    groupes = {t: g for t, g in sc.groupby("tracking_id", sort=False)}
    agences = {r.departement: r.site_code for r in sites[sites.site_code.str.startswith("AG-")].itertuples()}
    port_de_tri = {topo[e]: e for e in ("ENT-LEH", "ENT-RTM", "ENT-FOS")}
    lignes = []
    n_inferes = Counter()
    for c in colis.itertuples(index=False):
        g = groupes.get(c.tracking_id)
        chemin, transp, temps = [], {}, {}
        if g is not None:
            for evt, site, tr, h in zip(g.evenement, g.site_code, g.transporteur_id, g.horodatage_utc):
                if site.startswith("WH-"):
                    temps.setdefault(site, h)
                    continue
                if not chemin or chemin[-1] != site:
                    chemin.append(site)
                    temps[site] = h
                if isinstance(tr, str):
                    transp[(site, evt in ("DEPART_TOURNEE", "LIVRE", "LIVRE_RELAIS"))] = tr
        infere = set()
        etranger = c.pays_origine != "FR"
        # 1. Entrée en France d'un colis venu de l'étranger
        if etranger and not any(x.startswith("ENT-") for x in chemin):
            if c.pays_origine in EUROPE:
                entree = ENTREE_DE_PAYS_EUROPE[c.pays_origine]
            else:
                premier = temps.get(chemin[0]) if chemin else None
                delai = (premier.tz_convert(None) - c.date_commande).total_seconds() / 3600 if premier is not None else np.nan
                mode = mode_international(c, delai)
                if mode == "air":
                    entree = "ENT-CDG"
                elif mode == "route":
                    entree = "ENT-STR"
                else:
                    entree = port_de_tri.get(chemin[0] if chemin else "", "ENT-LEH")
            idx = 1 if chemin and chemin[0].startswith(("PART-", "PORT-")) else 0
            chemin.insert(idx, entree)
            infere.add(entree)
            n_inferes["porte d'entrée"] += 1
        # 2. Agence d'origine d'un dépôt en point relais, entrepôt d'expédition
        if not etranger and not isinstance(c.site_expedition, str):
            ag_o = agences.get(c.departement_origine)
            if ag_o and (not chemin or chemin[0] != ag_o):
                chemin.insert(0, ag_o)
                infere.add(ag_o)
                n_inferes["agence d'origine"] += 1
        if isinstance(c.site_expedition, str):
            chemin.insert(0, c.site_expedition)
        # 3. Agence de destination
        ag_d = agences.get(c.departement_destination)
        if ag_d and (not chemin or chemin[-1] != ag_d):
            chemin.append(ag_d)
            infere.add(ag_d)
            n_inferes["agence de destination"] += 1
        # 4. Plateformes de tri non flashées : on quitte un entrepôt, une entrée ou l'agence
        #    d'origine par sa plateforme de rattachement ; on n'arrive à l'agence de
        #    destination que depuis la sienne
        complet = chemin[:1]
        for i, site in enumerate(chemin[1:], 1):
            prec = complet[-1]
            if prec.startswith(("WH-", "ENT-")) or (prec.startswith("AG-") and len(complet) == 1):
                t = topo.get(prec)
                if t and site != t:
                    complet.append(t)
                    infere.add(t)
                    n_inferes["plateforme de tri"] += 1
            if i == len(chemin) - 1 and site.startswith("AG-"):
                t = topo.get(site)
                if t and complet[-1] != t:
                    complet.append(t)
                    infere.add(t)
                    n_inferes["plateforme de tri"] += 1
            complet.append(site)
        points = (["ORIGINE"] if not isinstance(c.site_expedition, str) else []) + complet + ["DESTINATION"]
        for k in range(len(points) - 1):
            de, vers = points[k], points[k + 1]
            if de == vers:
                continue
            arrivee_tr = transp.get((de, True)) if vers == "DESTINATION" else transp.get((vers, False))
            t0, t1 = temps.get(de), temps.get(vers)
            duree = (t1 - t0).total_seconds() / 3600 if t0 is not None and t1 is not None else np.nan
            lignes.append((c.tracking_id, k, de, vers, de in infere, vers in infere, arrivee_tr, duree))
    et = pd.DataFrame(lignes, columns=["tracking_id", "rang", "de", "vers", "de_infere", "vers_infere",
                                       "transporteur_id", "duree_h"])
    et["rang"] = et.groupby("tracking_id").cumcount()
    et["type_etape"] = [type_etape(a, b) for a, b in zip(et.de, et.vers)]
    for nom, n in n_inferes.items():
        j.note("etapes", f"passage non flashé : {nom}", n, "déduit de la topologie du réseau")
    return et


# ---------------------------------------------------------------------------
# Distances
# ---------------------------------------------------------------------------
def coefficient_detour() -> float:
    """Rapport médian distance routière OSRM / distance à vol d'oiseau sur le réseau."""
    osrm = pd.read_csv(R.CACHE_OSRM)
    s = R.reseau_sites().set_index("site_code")
    h = haversine_km(s.loc[osrm.de, "lat"].values, s.loc[osrm.de, "lon"].values,
                     s.loc[osrm.vers, "lat"].values, s.loc[osrm.vers, "lon"].values)
    ok = h > 20
    return float(np.median(osrm.distance_route_km.values[ok] / h[ok]))


def distances(et: pd.DataFrame, colis: pd.DataFrame, sites: pd.DataFrame, j: Journal) -> pd.DataFrame:
    s = sites.set_index("site_code")
    c = colis.set_index("tracking_id")
    osrm = pd.read_csv(R.CACHE_OSRM)
    route = dict(zip(zip(osrm.de, osrm.vers), osrm.distance_route_km))
    detour = coefficient_detour()
    j.note("etapes", "coefficient de détour routier", 0,
           f"{detour:.3f} (médiane OSRM / vol d'oiseau sur {fr(len(osrm))} paires du réseau)")

    def coords(code, tracking, cote):
        if code == "ORIGINE":
            return c.at[tracking, "lat_orig"], c.at[tracking, "lon_orig"]
        if code == "DESTINATION":
            return c.at[tracking, "lat_dest"], c.at[tracking, "lon_dest"]
        return s.at[code, "lat"], s.at[code, "lon"]

    la0, lo0, la1, lo1 = [], [], [], []
    for t, de, vers in zip(et.tracking_id, et.de, et.vers):
        a, b = coords(de, t, 0), coords(vers, t, 1)
        la0.append(a[0]); lo0.append(a[1]); la1.append(b[0]); lo1.append(b[1])
    et["lat_de"], et["lon_de"], et["lat_vers"], et["lon_vers"] = la0, lo0, la1, lo1
    et["distance_vol_oiseau_km"] = haversine_km(et.lat_de, et.lon_de, et.lat_vers, et.lon_vers)

    pr = et.tracking_id.map(c.livraison).eq("point_relais")
    d = et.distance_vol_oiseau_km * detour
    methode = pd.Series("vol_oiseau_x_detour", index=et.index)
    cle = list(zip(et.de, et.vers))
    reseau = pd.Series([route.get(k) for k in cle], index=et.index)
    d = d.where(reseau.isna(), reseau)
    methode[reseau.notna()] = "osrm"
    air = et.type_etape.eq("INTERNATIONAL_AIR") | (et.type_etape.eq("INTERNATIONAL") & et.vers.eq("ENT-CDG"))
    d[air] = et.distance_vol_oiseau_km[air] + C.AIR_KM_SUPPLEMENTAIRES
    methode[air] = "orthodromie_plus_95km"
    mer = et.type_etape.eq("INTERNATIONAL_MER") | (et.type_etape.eq("INTERNATIONAL")
                                                     & et.vers.isin(["ENT-LEH", "ENT-RTM", "ENT-FOS"]))
    d[mer] = [distance_mer_km(round(a, 2), round(b, 2), round(x, 2), round(y, 2))
              for a, b, x, y in zip(et.lat_de[mer], et.lon_de[mer], et.lat_vers[mer], et.lon_vers[mer])]
    methode[mer] = "route_maritime"
    tournee = et.type_etape.isin(["DERNIER_KM", "COLLECTE"])
    d[tournee] = d[tournee] * C.TOURNEE_FACTEUR * np.where(pr[tournee] & et.type_etape[tournee].eq("DERNIER_KM"),
                                                           0.6, 1.0)
    methode[tournee] = methode[tournee] + "_tournee"
    et["distance_km"] = d.round(2)
    et["methode_distance"] = methode
    for m, n in methode.value_counts().items():
        j.note("etapes", f"distance : {m}", n, "méthode de calcul de la distance")
    return et


# ---------------------------------------------------------------------------
# Poids manquants
# ---------------------------------------------------------------------------
def imputer_poids(colis: pd.DataFrame, j: Journal) -> pd.DataFrame:
    df = colis.copy()
    densite = (df.poids_kg / df.volume_m3).replace([np.inf, -np.inf], np.nan)
    med_densite = densite.groupby(df.categorie).median()
    med_poids = df.groupby(["client", "categorie"]).poids_kg.median()
    manque = df.poids_kg.isna()
    par_volume = manque & df.volume_m3.notna()
    df.loc[par_volume, "poids_kg"] = df.volume_m3[par_volume] * df.categorie[par_volume].map(med_densite)
    reste = df.poids_kg.isna()
    df.loc[reste, "poids_kg"] = [med_poids.get((a, b)) for a, b in zip(df.client[reste], df.categorie[reste])]
    df["poids_kg"] = df.poids_kg.clip(upper=C.MAX_POIDS_KG)
    df["poids_impute"] = manque
    j.note("colis", "poids manquant imputé par le volume", par_volume.sum(),
           "volume x densité médiane de la catégorie")
    j.note("colis", "poids manquant imputé par la médiane", reste.sum(), "médiane du couple client x catégorie")
    df["poids_volumetrique_kg"] = df.volume_m3 * C.POIDS_VOLUMETRIQUE_KG_M3
    return df
