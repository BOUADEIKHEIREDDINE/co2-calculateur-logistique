"""Construit et exécute le notebook de présentation du pipeline (python notebooks/construire_notebook.py)."""
from pathlib import Path

import nbformat as nbf
from nbconvert import HTMLExporter
from nbconvert.preprocessors import ExecutePreprocessor

ICI = Path(__file__).resolve().parent
nb = nbf.v4.new_notebook()
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

nb.cells = [
    md("""# Calculateur CO₂ logistique : le pipeline de data wrangling pas à pas

Projet FastColis. Objectif : construire un **dataset unifié et propre** donnant l'émission de CO₂ de chaque
colis, à partir de sources hétérogènes et incomplètes, puis l'exposer à nos clients grands comptes.

Ce notebook ne contient pas la logique : il appelle les modules du paquet `co2` dans l'ordre des étapes
du cours (découverte, ingestion, structuration et nettoyage, enrichissement, mapping et feature
engineering, validation, publication) et montre ce que chacune produit. Pour tout relancer d'un bloc :
`python run_pipeline.py`."""),
    code("""import sys, json
from pathlib import Path
RACINE = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(RACINE))
import pandas as pd
from IPython.display import Image, Markdown, display
pd.set_option("display.max_columns", 30, "display.width", 200)
from co2 import config as C, ingestion, decouverte, nettoyage, referentiels as R"""),

    md("""## 0. Les sources

| Source | Format | Contenu | Nature |
|---|---|---|---|
| Export SAP | CSV Windows-1252, `;`, virgule décimale | commandes, clients, poids, dimensions, service | fictive |
| Flashages | 12 fichiers JSON Lines, deux firmwares | scans des colis : site, heure, GPS, transporteur | fictive |
| Annuaire transporteurs | Excel, 2 onglets aux colonnes différentes | flotte interne et sous-traitants | fictive |
| Référentiel des sites | CSV | plateformes, agences, entrepôts | fictive (villes réelles) |
| Base Carbone ADEME | CSV latin-1, 18 616 lignes | facteurs d'émission officiels | **réelle** |
| GeoNames cities5000 | TSV | villes, coordonnées, population, fuseau | **réelle** |
| OpenFlights | CSV | aéroports (codes IATA, coordonnées) | **réelle** |
| OSRM (OpenStreetMap) | API | distances routières réelles entre sites | **réelle** |
| searoute | bibliothèque | distances maritimes réelles | **réelle** |

Les sources internes sont simulées (le cours l'autorise) avec les défauts que l'on rencontre en vrai.
Comme on connaît leur vérité terrain, on peut **mesurer** la qualité du pipeline, ce qui serait impossible
sur de vraies données."""),

    md("## 1. Découverte\n\nPremier réflexe : réduire chaque valeur à sa forme (chiffre → 9, lettre → A) pour "
       "voir les formats concurrents sans écrire de règle."),
    code("""raw = ingestion.ingerer()
for nom, df in raw.items():
    print(f"{nom:32s} {len(df):>8,} lignes  {df.shape[1]:>3} colonnes".replace(",", " "))"""),
    code("""for c in decouverte.constats(raw):
    print("•", c)"""),
    code("""decouverte.profiler(raw["sap"]).head(14)"""),
    code("""raw["flashages"].groupby("firmware").head(2)"""),

    md("## 2. Ingestion\n\nChaque lecteur garde tout en texte et ajoute la traçabilité (`_fichier`, `_ligne`). "
       "Les deux formats de scanners sont ramenés à un même schéma brut. Les tables sont figées en Parquet "
       "dans `data/raw`."),
    code("""raw["sap"][["TRACKING", "NAME1", "BRGEW", "GEWEI", "VSART", "LAND1_ORIG", "ERDAT", "_fichier", "_ligne"]].sample(6, random_state=1)"""),

    md("## 3. Structuration et nettoyage\n\nRenommage des colonnes SAP en noms métier, conversion des unités, "
       "dates, codes, doublons. Chaque règle est inscrite au journal."),
    code("""rc = nettoyage.nettoyer(raw)
rc["journal_nettoyage"]"""),
    code("""rc["colis"].head()"""),
    code("""rc["transporteurs"][["transporteur_id", "libelle_vehicule", "energie", "code_vehicule"]].sample(8, random_state=3)"""),

    md("## 4. Enrichissement\n\nFacteurs ADEME extraits par identifiant (jamais recopiés à la main), géocodage, "
       "topologie du réseau apprise depuis les scans, reconstitution des trajets, distances par mode."),
    code("""R.table_facteurs()[["code_vehicule", "libelle", "kgco2e_tkm", "base_carbone_id", "statut_source"]]"""),
    code("""etapes = pd.read_parquet(C.ENRICHED / "etapes.parquet")
exemple = etapes.tracking_id.iloc[0]
etapes[etapes.tracking_id == exemple][["rang", "de", "vers", "type_etape", "vers_infere", "distance_vol_oiseau_km", "distance_km", "methode_distance"]]"""),
    code("""etapes.methode_distance.value_counts()"""),

    md("## 5. Mapping, feature engineering et apprentissage\n\nChaque étape reçoit un véhicule : celui du "
       "transporteur quand il est connu, sinon une prédiction. Trois modèles sont comparés à une règle simple :"),
    code("""resume = json.loads((C.REPORTS / "resume_pipeline.json").read_text())
pd.DataFrame(resume["metriques_modeles"]).T"""),
    code("""cur = pd.read_parquet(C.CURATED / "colis_co2.parquet")
cur[["tracking_id", "date_first_scan", "date_last_scan", "pays_origine", "pays_destination", "poids_kg", "volume_m3",
     "nb_plateformes", "distance_estimee_km", "mode_transport", "facteur_emission_moyen_g_tkm",
     "emission_estimee_g", "emission_ml_g", "taux_observation"]].head(8)"""),

    md("## 6. Validation\n\nRègles de cohérence (bornes, sommes, inégalité triangulaire, vitesses) puis évaluation "
       "contre la vérité terrain."),
    code("""pd.read_csv(C.REPORTS / "06_regles_validation.csv")"""),
    code("""ev = resume["evaluation"]
pd.DataFrame({k: ev[k] for k in ("emission_reconstituee", "emission_ml", "distance")}).T"""),
    code("""display(Image(C.FIGURES / "05_estime_vs_reel.png", width=480))
display(Image(C.FIGURES / "04_erreur_par_observation.png", width=700))"""),
    code("""pd.DataFrame(ev["defauts"])"""),

    md("## 7. Analyse et publication\n\nLa table Curated est publiée en Parquet et en CSV, avec un bilan Excel "
       "par client et l'interface Streamlit (`python run_app.py`)."),
    code("""for f in ["01_colis_vs_emissions_avion", "06_g_par_kg", "02_distribution_par_service", "03_colis_par_mois"]:
    display(Image(C.FIGURES / f"{f}.png", width=700))"""),
    code("""bilan = cur.groupby("client").agg(colis=("tracking_id", "size"),
                                  t_co2e=("emission_estimee_g", lambda s: round(s.sum() / 1e6, 2)),
                                  g_par_colis=("emission_estimee_g", lambda s: round(s.mean())),
                                  part_avion=("emission_avion_g", lambda s: round(s.sum() / cur.loc[s.index, "emission_estimee_g"].sum(), 3)))
bilan.sort_values("t_co2e", ascending=False)"""),
    md("""## Conclusions

* L'avion concentre l'essentiel des émissions alors qu'il ne concerne qu'une minorité de colis : c'est le
  premier sujet à traiter avec les clients qui importent d'Asie.
* Sur le territoire, l'option écologique (train, véhicules électriques, vélos cargo) divise l'émission par
  kilo par près de deux ; l'express n'émet pas plus que le standard.
* Le trajet reconstitué à partir des scans est précis à quelques pourcents, même quand la moitié du trajet
  n'est pas observée : la topologie du réseau, apprise dans les données, comble les trous.
* Le modèle qui n'utilise que la commande (avant expédition) se trompe de 15 à 18 % en médiane : il sert
  d'estimation a priori et de garde-fou pour repérer les reconstitutions douteuses."""),
]

nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
ExecutePreprocessor(timeout=900, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(ICI)}})
nbf.write(nb, ICI / "co2_pipeline.ipynb")
html, _ = HTMLExporter(template_name="lab").from_notebook_node(nb)
(ICI / "co2_pipeline.html").write_text(html, encoding="utf-8")
print("notebook écrit et exécuté")
