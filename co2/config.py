"""Paramètres partagés par tout le pipeline : chemins, réseau logistique, hypothèses.

Toutes les hypothèses chiffrées du projet sont regroupées ici pour être relues
et modifiées à un seul endroit.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EXTERNAL = DATA / "external"        # sources publiques téléchargées (ADEME, GeoNames, OpenFlights)
SOURCES = DATA / "sources"          # extractions internes FastColis (fictives, avec leurs défauts)
RAW_CLEAN = DATA / "raw_clean"      # étape 3 : données structurées et nettoyées
ENRICHED = DATA / "enriched"        # étape 4 : distances, modes, facteurs
CURATED = DATA / "curated"          # étape 5 : table prête pour le ML et les clients
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
MODELS = DATA / "models"

SEED = 42
PERIODE_DEBUT = "2025-10-01"
PERIODE_FIN = "2026-09-30"
NB_COLIS = 60_000

# ---------------------------------------------------------------------------
# Réseau FastColis : plateformes d'entrée, de tri, hubs étrangers
# Les coordonnées ne sont pas saisies à la main : elles viennent de GeoNames
# (villes) ou d'OpenFlights (aéroports), via co2.referentiels.
# ---------------------------------------------------------------------------
PLATEFORMES_ENTREE = {
    # code: (nom, ville GeoNames, pays, porte d'entrée)
    "ENT-CDG": ("Roissy CDG fret", "CDG", "FR", "air"),
    "ENT-LEH": ("Port du Havre", "Le Havre", "FR", "mer"),
    "ENT-FOS": ("Port de Marseille-Fos", "Fos-sur-Mer", "FR", "mer"),
    "ENT-RTM": ("Port de Rotterdam", "Rotterdam", "NL", "mer"),
    "ENT-LIL": ("Lille Lesquin international", "Lesquin", "FR", "route"),
    "ENT-STR": ("Strasbourg international", "Strasbourg", "FR", "route"),
    "ENT-PPG": ("Perpignan Saint-Charles", "Perpignan", "FR", "route"),
}

PLATEFORMES_TRI = {
    "TRI-IDF": ("Tri Île-de-France", "Gonesse"),
    "TRI-NAT": ("Hub national Orléans", "Saran"),
    "TRI-LYS": ("Tri Lyon", "Corbas"),
    "TRI-MRS": ("Tri Marseille", "Vitrolles"),
    "TRI-BOD": ("Tri Bordeaux", "Cestas"),
    "TRI-TLS": ("Tri Toulouse", "Toulouse"),
    "TRI-LIL": ("Tri Lille", "Lesquin"),
    "TRI-NTE": ("Tri Nantes", "Carquefou"),
    "TRI-REN": ("Tri Rennes", "Rennes"),
    "TRI-STR": ("Tri Strasbourg", "Strasbourg"),
    "TRI-MPL": ("Tri Montpellier", "Montpellier"),
    "TRI-DIJ": ("Tri Dijon", "Dijon"),
}

# Origines hors Europe : ville GeoNames -> (pays, aéroport de départ OpenFlights)
ORIGINES_INTERNATIONALES = {
    "Shenzhen": ("CN", "SZX"),
    "Shanghai": ("CN", "PVG"),
    "Hong Kong": ("HK", "HKG"),
    "Istanbul": ("TR", "IST"),
    "Casablanca": ("MA", "CMN"),
    "New York City": ("US", "JFK"),
    "Montréal": ("CA", "YUL"),
    "Seoul": ("KR", "ICN"),
}
ORIGINES_EUROPE = {
    # ville: (pays, plateforme d'entrée routière)
    "Madrid": ("ES", "ENT-PPG"),
    "Barcelona": ("ES", "ENT-PPG"),
    "Milan": ("IT", "ENT-STR"),
    "Leipzig": ("DE", "ENT-STR"),
    "Mönchengladbach": ("DE", "ENT-LIL"),
    "Warsaw": ("PL", "ENT-STR"),
    "Brussels": ("BE", "ENT-LIL"),
    "Amsterdam": ("NL", "ENT-LIL"),
}

# Entrepôts des clients B2C en France (villes réelles, sites fictifs)
ENTREPOTS = {
    "AMAZON": ["Saran", "Brétigny-sur-Orge", "Montélimar", "Douai", "Amiens"],
    "CDISCOUNT": ["Cestas", "Saint-Priest"],
    "ZALANDO": ["Moissy-Cramayel"],
    "DECATHLON": ["Lille", "Torcy", "Rognac"],
    "BACK MARKET": ["Rungis"],
    "LEROY MERLIN": ["Valence", "Rambouillet"],
}

CLIENTS = {
    # nom: (part du volume, type, (mu, sigma) du log-poids en kg)
    "AMAZON": (0.33, "B2C", (0.0, 0.85)),
    "VINTED": (0.22, "C2C", (-0.35, 0.6)),
    "CDISCOUNT": (0.11, "B2C", (0.4, 0.9)),
    "SHEIN": (0.10, "INTL", (-0.9, 0.5)),
    "ZALANDO": (0.08, "B2C", (-0.2, 0.5)),
    "DECATHLON": (0.08, "B2C", (0.5, 0.9)),
    "BACK MARKET": (0.05, "B2C", (-0.3, 0.4)),
    "LEROY MERLIN": (0.03, "B2C", (1.8, 0.8)),
}

SERVICES = ["standard", "express", "ecologique", "international"]

# ---------------------------------------------------------------------------
# Hypothèses de calcul (documentées dans docs/methodologie.md)
# ---------------------------------------------------------------------------
DETOUR_ROUTE_DEFAUT = 1.25      # remplacé par la valeur calibrée sur OSRM si disponible
DETOUR_FER = 1.30
AIR_KM_SUPPLEMENTAIRES = 95     # forfait de la norme EN 16258 / GLEC pour les trajets aériens
TOURNEE_FACTEUR = 1.6           # un colis du dernier km fait partie d'une tournée : détour moyen
POIDS_VOLUMETRIQUE_KG_M3 = 250  # pour signaler les colis légers mais encombrants
MAX_POIDS_KG = 70               # au-delà : messagerie palettes, hors périmètre colis
VITESSES_KMH = {"air": 550, "mer": 30, "fer": 45, "route_longue": 65, "route_courte": 40,
                "vul": 25, "velo": 12}

# Équivalence grand public : voiture particulière, motorisation moyenne 2023
# Base Carbone ADEME, identifiant 43791 : 0,256 kgCO2e/km
VOITURE_KG_PAR_KM = 0.256
BASE_CARBONE_VOITURE_ID = 43791
