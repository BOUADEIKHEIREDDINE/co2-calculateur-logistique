"""Étape 3 : structuration et nettoyage (couche « Raw Clean »).

Chaque règle appliquée est inscrite dans un journal (table, règle, lignes
concernées, action) publié avec les données : on peut toujours expliquer
pourquoi une valeur a changé ou pourquoi une ligne a disparu.
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

from . import config as C
from . import referentiels as R
from .geo import haversine_km

PARIS = "Europe/Paris"


class Journal:
    def __init__(self):
        self.lignes: list[dict] = []

    def note(self, table: str, regle: str, n: int, action: str) -> None:
        self.lignes.append({"table": table, "regle": regle, "lignes": int(n), "action": action})

    def table(self) -> pd.DataFrame:
        return pd.DataFrame(self.lignes)


def fr(n) -> str:
    """Nombre au format français (espace fine comme séparateur de milliers)."""
    return f"{n:,}".replace(",", "\u202f")


def sans_accents(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def nombre(s: pd.Series) -> pd.Series:
    """Texte -> nombre, que la décimale soit un point ou une virgule."""
    t = s.astype("string").str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(t, errors="coerce").astype("float64")


# ---------------------------------------------------------------------------
# SAP
# ---------------------------------------------------------------------------
COLONNES_SAP = {
    "VBELN": "commande_id", "TRACKING": "tracking_id", "KUNNR": "client_code", "NAME1": "client_libelle",
    "MATKL": "categorie", "BRGEW": "poids_brut", "GEWEI": "unite_poids", "LAENG": "longueur",
    "BREIT": "largeur", "HOEHE": "hauteur", "MEINS": "unite_dim", "VSART": "service_brut",
    "LIVR": "livraison_brut", "LAND1_ORIG": "pays_origine_brut", "ORT01_ORIG": "ville_origine_brute",
    "WERKS": "site_expedition", "LAND1_DEST": "pays_destination_brut", "ORT01_DEST": "ville_destination_brute",
    "REGIO_DEST": "departement_destination", "ERDAT": "date_brute", "ERZET": "heure_brute",
    "NETWR": "montant", "WAERK": "devise", "ZLSCH": "mode_paiement",
}
SERVICES = {"01": "standard", "STD": "standard", "STANDARD": "standard",
            "02": "express", "EXP": "express", "EXPRESS 24H": "express",
            "03": "ecologique", "ECO": "ecologique", "ECOLOGIQUE": "ecologique",
            "04": "international", "INT": "international", "INTERNATIONAL": "international"}
PAYS = {"FRANCE": "FR", "FRA": "FR", "CHINE": "CN", "CHN": "CN", "HONG KONG": "HK", "TURQUIE": "TR",
        "TUR": "TR", "MAROC": "MA", "MAR": "MA", "USA": "US", "ETATS-UNIS": "US", "CANADA": "CA",
        "COREE DU SUD": "KR", "KOR": "KR", "ESPAGNE": "ES", "ESP": "ES", "ITALIE": "IT", "ALLEMAGNE": "DE",
        "DEU": "DE", "POLOGNE": "PL", "BELGIQUE": "BE", "PAYS-BAS": "NL"}
SUFFIXES_SOCIETE = r"\b(SARL|SAS|SA|SE|UAB|EU|FRANCE|LOGISTIQUE|DISTRIBUTION|DIST|CORP)\b"


def normaliser_societe(nom: str) -> str:
    s = sans_accents(str(nom)).upper()
    s = re.sub(r"\.(FR|COM)$", "", s)
    s = re.sub(SUFFIXES_SOCIETE, " ", s.replace(".", " "))
    return re.sub(r"[^A-Z]", "", s)


def normaliser_pays(s: pd.Series) -> pd.Series:
    t = s.astype("string").str.strip().str.upper().map(lambda x: sans_accents(x) if isinstance(x, str) else x)
    return t.map(lambda x: x if isinstance(x, str) and len(x) == 2 else PAYS.get(x, pd.NA))


def nettoyer_sap(sap: pd.DataFrame, j: Journal) -> pd.DataFrame:
    df = sap.rename(columns=COLONNES_SAP).copy()

    # Clients : le code KUNNR fait foi, le libellé canonique est le plus fréquent une fois normalisé
    df["client_norm"] = df.client_libelle.map(normaliser_societe)
    canon = df.groupby("client_code").client_norm.agg(lambda s: s.value_counts().index[0])
    noms = {"BACKMARKET": "BACK MARKET", "LEROYMERLIN": "LEROY MERLIN", "CDISCOUNT": "CDISCOUNT"}
    df["client"] = df.client_code.map(canon).map(lambda x: noms.get(x, x))
    j.note("sap", "libellés clients", df.client_libelle.nunique(),
           f"{df.client_libelle.nunique()} libellés ramenés à {df.client.nunique()} clients via le code KUNNR")

    # Poids : virgule décimale, unité G/KG/vide, grammes saisis comme des kg
    p = nombre(df.poids_brut)
    unite = df.unite_poids.fillna("").str.upper()
    en_g = unite.eq("G")
    p = p.where(~en_g, p / 1000)
    j.note("sap", "poids en grammes (unité G)", en_g.sum(), "divisé par 1 000")
    suspect = ~en_g & (p > C.MAX_POIDS_KG) & (p / 1000 <= C.MAX_POIDS_KG)
    p = p.where(~suspect, p / 1000)
    j.note("sap", f"poids > {C.MAX_POIDS_KG} kg avec unité KG ou vide", suspect.sum(),
           "valeur en grammes : divisée par 1 000")
    invalide = p <= 0
    p = p.mask(invalide)
    j.note("sap", "poids nul ou négatif", invalide.sum(), "mis à vide puis imputé")
    df["poids_kg"] = p
    df["poids_corrige"] = suspect.fillna(False).astype(bool)

    # Dimensions et volume
    dims = df[["longueur", "largeur", "hauteur"]].apply(nombre)
    mm = df.unite_dim.eq("MM")
    dims = dims.div(np.where(mm, 10.0, 1.0), axis=0)
    j.note("sap", "dimensions en mm", mm.sum(), "converties en cm")
    df[["longueur_cm", "largeur_cm", "hauteur_cm"]] = dims.astype("float64").values
    df["volume_m3"] = dims.prod(axis=1, min_count=3) / 1e6
    hors = (dims > 200).any(axis=1)
    df.loc[hors, "volume_m3"] = np.nan
    j.note("sap", "dimension > 2 m", hors.sum(), "volume mis à vide")

    # Service, livraison, pays
    cle = df.service_brut.astype("string").str.upper().map(lambda x: sans_accents(x) if isinstance(x, str) else x)
    df["service"] = cle.map(SERVICES)
    j.note("sap", "codes de service", df.service_brut.nunique(),
           f"{df.service_brut.nunique()} écritures ramenées à {df.service.nunique()} services")
    df["livraison"] = df.livraison_brut.map({"DOM": "domicile", "PR": "point_relais"})
    df["pays_origine"] = normaliser_pays(df.pays_origine_brut)
    df["pays_destination"] = normaliser_pays(df.pays_destination_brut)
    j.note("sap", "codes pays", df.pays_origine_brut.nunique(),
           f"{df.pays_origine_brut.nunique()} écritures ramenées à {df.pays_origine.nunique()} codes ISO 3166")

    # Dates : AAAAMMJJ (format SAP), JJ.MM.AAAA, AAAA-MM-JJ
    d = df.date_brute.astype("string").str.strip()
    date = pd.to_datetime(d, format="%Y%m%d", errors="coerce")
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        date = date.fillna(pd.to_datetime(d, format=fmt, errors="coerce"))
    heure = pd.to_timedelta(pd.to_numeric(df.heure_brute, errors="coerce").fillna(0).astype(int)
                            .astype(str).str.zfill(6).str.replace(r"(\d\d)(\d\d)(\d\d)", r"\1:\2:\3", regex=True))
    df["date_commande"] = date + heure
    j.note("sap", "formats de date", (~d.str.fullmatch(r"\d{8}")).sum(), "trois formats convertis en datetime")
    df["montant"] = nombre(df.montant)

    # Doublons : même numéro de suivi (réexportations)
    df["tracking_id"] = df.tracking_id.str.strip().str.upper()
    avant = len(df)
    exacts = df.duplicated(subset=list(COLONNES_SAP.values())).sum()
    df = df.sort_values(["tracking_id", "date_commande"]).drop_duplicates("tracking_id", keep="first")
    j.note("sap", "doublons de numéro de suivi", avant - len(df),
           f"supprimés ({exacts} copies exactes, {avant - len(df) - exacts} réexportations au format différent)")

    garde = ["tracking_id", "commande_id", "client", "client_code", "categorie", "poids_kg", "poids_corrige",
             "longueur_cm", "largeur_cm", "hauteur_cm", "volume_m3", "service", "livraison", "pays_origine",
             "ville_origine_brute", "site_expedition", "pays_destination", "ville_destination_brute",
             "departement_destination", "date_commande", "montant", "devise", "mode_paiement"]
    return df[garde].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------
def nettoyer_sites(sites: pd.DataFrame, codes_scans: pd.Series, j: Journal) -> pd.DataFrame:
    s = sites.copy()
    s["lat"], s["lon"] = nombre(s.lat), nombre(s.lon)
    manque = s.lat.isna()
    for i in s[manque].index:
        s.loc[i, ["lat", "lon"]] = R.localiser(s.at[i, "ville"], s.at[i, "pays"])
    j.note("sites", "coordonnées manquantes", manque.sum(), "géocodées via GeoNames (ville, pays)")
    s["tz"] = PARIS
    s["departement"] = s.site_code.str.extract(r"^AG-(\w+)$")[0]

    # Sites partenaires vus dans les scans mais absents du référentiel : aéroports et ports de départ
    ap = R.aeroports()
    nouveaux = []
    for code in sorted(set(codes_scans[codes_scans.str.match(r"^(PART|PORT)-[A-Z]{3}$")])):
        a = ap.loc[code[5:]]
        nouveaux.append({"site_code": code, "type_site": "PARTENAIRE_AIR" if code.startswith("PART")
                         else "PARTENAIRE_PORT", "libelle": f"Partenaire {a.ville} ({code[5:]})",
                         "ville": a.ville, "pays": None, "lat": float(a.lat), "lon": float(a.lon),
                         "tz": a.tz if isinstance(a.tz, str) else "UTC"})
    j.note("sites", "sites partenaires inconnus du référentiel", len(nouveaux),
           "ajoutés depuis OpenFlights (code IATA)")
    return pd.concat([s, pd.DataFrame(nouveaux)], ignore_index=True)


# ---------------------------------------------------------------------------
# Transporteurs
# ---------------------------------------------------------------------------
REGLES_VEHICULE = [  # (motif sur libellé + énergie, code véhicule) : la première règle qui correspond gagne
    (r"V[EÉ]LO|TRIPORTEUR", "VELO_CARGO"),
    (r"RAIL|WAGON|FERROVIAIRE", "FER_ELEC"),
    (r"A[EÉ]RIEN", "AIR"),
    (r"CONTENEUR|MARITIME", "MER"),
    (r"(SEMI|ARTICUL|TRACTEUR).*(GNV|GAZ(?!OLE))|GNV.*(SEMI|ARTICUL)", "ROUTE_ART_40T_GNC"),
    (r"(SEMI|ARTICUL|TRACTEUR).*GNL", "ROUTE_ART_40T_GNL"),
    (r"SEMI|ARTICUL|TRACTEUR", "ROUTE_ART_40T_DIESEL"),
    (r"(PORTEUR|PL).*7[.,]5.*([EÉ]LEC)", "ROUTE_RIG_7T_ELEC"),
    (r"(PORTEUR|PL) *(19|20)", "ROUTE_RIG_20T_DIESEL"),
    (r"(PORTEUR|PL) *12", "ROUTE_RIG_12T_DIESEL"),
    (r"(VUL|FOURGON|UTILITAIRE).*([EÉ]LEC)|E-FOURGON", "VUL_ELEC"),
    (r"(VUL|FOURGON|UTILITAIRE).*(GNV|GAZ(?!OLE))", "VUL_GNC"),
    (r"VUL|FOURGON|UTILITAIRE", "VUL_DIESEL"),
]


def classer_vehicule(libelle: str | None, energie: str | None) -> str | None:
    if not libelle:
        return None
    texte = f"{libelle} {energie or ''}".upper()
    for motif, code in REGLES_VEHICULE:
        if re.search(motif, texte):
            return code
    return None


def nettoyer_transporteurs(internes: pd.DataFrame, st: pd.DataFrame, j: Journal) -> pd.DataFrame:
    a = pd.DataFrame({"transporteur_id": internes["Code flotte"], "raison_sociale": "FastColis",
                      "interne": True, "libelle_vehicule": internes["Type de véhicule"],
                      "energie": internes["Énergie"], "mode_declare": "Route"})
    b = pd.DataFrame({"transporteur_id": st["ID transporteur"], "raison_sociale": st["Raison sociale"],
                      "interne": False, "libelle_vehicule": st["Catégorie"], "energie": st["Carburant"],
                      "mode_declare": st["Mode"]})
    t = pd.concat([a, b], ignore_index=True)
    t["transporteur_id"] = t.transporteur_id.str.strip().str.upper()
    avant = len(t)
    t = t.drop_duplicates("transporteur_id")
    j.note("transporteurs", "identifiants en double (casse)", avant - len(t), "dédoublonnés")
    t["code_vehicule"] = [classer_vehicule(l, e) for l, e in zip(t.libelle_vehicule, t.energie)]
    # libellé absent : le mode déclaré suffit pour l'aérien, le maritime, le fer et le vélo
    defaut_mode = {"Aérien": "AIR", "Maritime": "MER", "Ferroviaire": "FER_ELEC", "Vélo": "VELO_CARGO"}
    sans = t.code_vehicule.isna()
    t.loc[sans, "code_vehicule"] = t.loc[sans, "mode_declare"].map(defaut_mode)
    j.note("transporteurs", "catégorie de véhicule absente", sans.sum(),
           f"{t.loc[sans, 'code_vehicule'].notna().sum()} déduites du mode, "
           f"{t.code_vehicule.isna().sum()} laissées inconnues (imputées par étape)")
    return t.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Flashages
# ---------------------------------------------------------------------------
EVENEMENTS_V1 = {"TRI_TRI": "TRI", "ARR_NCE": "ARRIVEE_AGENCE", "DEP_NEE": "DEPART_TOURNEE",
                 "DEP_AIS": "DEPOT_RELAIS", "ENT_RME": "ENTREE_PLATEFORME", "HUB_IRE": "HUB_PARTENAIRE",
                 "LIV_VRE": "LIVRE", "LIV_AIS": "LIVRE_RELAIS", "PRI_RGE": "PRISE_EN_CHARGE"}
# rang logique d'un événement dans la chaîne (TRI et agences intermédiaires partagent le rang 3)
RANG = {"DEPOT_RELAIS": 0, "PRISE_EN_CHARGE": 0, "HUB_PARTENAIRE": 1, "ENTREE_PLATEFORME": 2, "TRI": 3,
        "ARRIVEE_AGENCE": 3, "DEPART_TOURNEE": 5, "LIVRE": 6, "LIVRE_RELAIS": 6}


def normaliser_tracking(s: pd.Series) -> pd.Series:
    t = s.astype("string").str.upper().str.replace(r"\s+", "", regex=True)
    return t.where(~t.str.fullmatch(r"\d{10}"), "FC" + t)


def nettoyer_flashages(fl: pd.DataFrame, alias: pd.DataFrame, sites: pd.DataFrame,
                       transporteurs: pd.DataFrame, sap: pd.DataFrame, j: Journal
                       ) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = fl.copy()
    brut = df.tracking.copy()
    df["tracking_id"] = normaliser_tracking(df.tracking)
    j.note("flashages", "numéros de suivi mal formés", (brut != df.tracking_id).sum(),
           "majuscules, espaces retirés, préfixe FC ajouté")

    df["evenement"] = df.evenement.map(lambda e: EVENEMENTS_V1.get(e, e))
    j.note("flashages", "codes d'événement du firmware v1", (df.firmware == "v1").sum(),
           "traduits dans la nomenclature v2")

    code = df.site.str.strip().str.upper()
    table_alias = dict(zip(alias.ancien_code, alias.site_code))
    df["site_code"] = code.map(lambda c: table_alias.get(c, c))
    j.note("flashages", "codes de site (espaces, casse, anciens codes WMS)", (df.site_code != df.site).sum(),
           f"normalisés ; {code.isin(table_alias).sum()} anciens codes traduits")

    # Horodatage : epoch ms (v1), ISO avec décalage (v2), ISO sans fuseau = heure locale du site
    tz_site = dict(zip(sites.site_code, sites.tz))
    utc = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    v1 = df.firmware == "v1"
    utc[v1] = pd.to_datetime(pd.to_numeric(df.horodatage[v1]), unit="ms", utc=True)
    avec_tz = ~v1 & df.horodatage.str.contains(r"[+-]\d\d:\d\d$|Z$", regex=True)
    utc[avec_tz] = pd.to_datetime(df.horodatage[avec_tz], utc=True, format="ISO8601")
    naifs = ~v1 & ~avec_tz
    for tz, idx in df[naifs].groupby(df.site_code[naifs].map(lambda c: tz_site.get(c, PARIS))).groups.items():
        locale = pd.to_datetime(df.horodatage[idx], format="ISO8601")
        utc[idx] = locale.dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    df["horodatage_utc"] = utc
    j.note("flashages", "horodatages sans fuseau horaire", naifs.sum(), "interprétés à l'heure locale du site")

    # GPS : (0, 0) = capteur sans signal ; latitude et longitude inversées
    lat, lon = nombre(df.lat), nombre(df.lon)
    zero = (lat == 0) & (lon == 0)
    lat, lon = lat.mask(zero), lon.mask(zero)
    ref = sites.set_index("site_code")[["lat", "lon"]]
    rlat = df.site_code.map(ref.lat).fillna(46.6)            # à défaut, centre de la France
    rlon = df.site_code.map(ref.lon).fillna(2.4)
    d_ok = haversine_km(lat, lon, rlat, rlon)
    d_inv = haversine_km(lon, lat, rlat, rlon)
    inverse = (d_inv < d_ok) & (d_ok > 1000)
    lat, lon = lat.where(~inverse, lon), lon.where(~inverse, lat)
    df["lat"], df["lon"] = lat, lon
    j.note("flashages", "GPS à (0, 0)", zero.sum(), "mis à vide")
    j.note("flashages", "latitude et longitude inversées", inverse.sum(), "permutées")

    # Transporteurs : identifiants tronqués ou inconnus
    t = df.transporteur.astype("string").str.strip().str.upper()
    connus = set(transporteurs.transporteur_id)
    inconnu = t.notna() & ~t.isin(connus)
    df["transporteur_id"] = t.mask(inconnu)
    j.note("flashages", "identifiant transporteur tronqué ou inconnu", inconnu.sum(), "mis à vide")

    # Doublons : même colis, même événement, même site, à moins de 5 minutes
    df = df.sort_values(["tracking_id", "horodatage_utc"])
    meme = (df.tracking_id.eq(df.tracking_id.shift()) & df.evenement.eq(df.evenement.shift())
            & df.site_code.eq(df.site_code.shift())
            & (df.horodatage_utc - df.horodatage_utc.shift()).lt(pd.Timedelta(minutes=5)))
    df = df[~meme]
    j.note("flashages", "double flashage (< 5 min)", meme.sum(), "supprimés")

    # Orphelins : colis absents de SAP, mis en quarantaine
    orphelin = ~df.tracking_id.isin(sap.tracking_id)
    rejets = df[orphelin].assign(motif="numéro de suivi absent de SAP")
    df = df[~orphelin]
    j.note("flashages", "scans orphelins", orphelin.sum(), "mis en quarantaine (data/raw_clean/rejets)")

    # Chronologie : scan antérieur à la commande, ou rang logique qui recule dans le temps.
    # L'arrivée à l'agence qui part en tournée est l'avant-dernier maillon (rang 4).
    df["rang"] = df.evenement.map(RANG)
    tournee = df[df.evenement.isin(["DEPART_TOURNEE", "LIVRE", "LIVRE_RELAIS"])]
    agence_finale = tournee.groupby("tracking_id").site_code.first()
    finale = df.evenement.eq("ARRIVEE_AGENCE") & df.site_code.eq(df.tracking_id.map(agence_finale))
    df.loc[finale, "rang"] = 4
    commande = df.tracking_id.map(sap.set_index("tracking_id").date_commande)
    commande_utc = commande.dt.tz_localize(PARIS, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    avant_cmd = df.horodatage_utc < commande_utc - pd.Timedelta(hours=1)
    # dans l'ordre logique, l'heure ne doit pas reculer (tolérance de 5 min : le firmware v2
    # tronque les millisecondes et certains sites sont accolés, comme un entrepôt et son tri)
    df = df.sort_values(["tracking_id", "rang", "horodatage_utc"])
    plus_tard_avant = df.groupby("tracking_id").horodatage_utc.cummax().groupby(df.tracking_id).shift()
    recule = df.horodatage_utc < plus_tard_avant - pd.Timedelta(minutes=5)
    df["horodatage_suspect"] = avant_cmd | recule
    j.note("flashages", "horodatage incohérent (avant la commande ou ordre logique inversé)",
           df.horodatage_suspect.sum(), "signalés ; l'ordre logique prime pour reconstituer le trajet")

    garde = ["tracking_id", "evenement", "rang", "site_code", "horodatage_utc", "horodatage_suspect",
             "lat", "lon", "transporteur_id", "firmware", "_fichier", "_ligne"]
    return df[garde].reset_index(drop=True), rejets


def nettoyer(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    j = Journal()
    sap = nettoyer_sap(raw["sap"], j)
    codes = raw["flashages"].site.str.strip().str.upper()
    sites = nettoyer_sites(raw["sites"], codes, j)
    transp = nettoyer_transporteurs(raw["transporteurs_internes"], raw["transporteurs_sous_traitants"], j)
    scans, rejets = nettoyer_flashages(raw["flashages"], raw["sites_alias"], sites, transp, sap, j)
    out = {"colis": sap, "sites": sites, "transporteurs": transp, "flashages": scans, "rejets": rejets,
           "journal_nettoyage": j.table()}
    C.RAW_CLEAN.mkdir(parents=True, exist_ok=True)
    for nom, df in out.items():
        df.to_parquet(C.RAW_CLEAN / f"{nom}.parquet", index=False)
    return out
