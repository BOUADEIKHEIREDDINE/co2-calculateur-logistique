import pandas as pd
import streamlit as st

from commun import nombre, pipeline_pret, resume
from co2 import config as C
from co2 import referentiels as R

st.title("Comment c'est calculé")

st.markdown("""
### Le principe

Pour chaque étape du trajet d'un colis, on multiplie trois nombres :

> **poids du colis** (en tonnes) × **distance parcourue** (en km) × **facteur d'émission du véhicule**
> (en kg de CO₂e par tonne transportée sur un kilomètre)

puis on additionne les étapes. C'est la méthode de la norme européenne EN 16258 et de la réglementation
française sur l'information CO₂ des prestations de transport, avec les facteurs officiels de l'ADEME.

### D'où viennent les informations

* **Le trajet** : chaque passage du colis dans une plateforme est scanné (« flashé »). Ces scans
  donnent l'ordre des étapes. Quand un scan manque, l'étape est déduite du fonctionnement du réseau
  (chaque agence est desservie par une plateforme de tri précise).
* **Les distances** : sur la route, la distance réelle par le réseau routier (OpenStreetMap, service OSRM) ;
  en avion, la distance à vol d'oiseau plus 95 km (approches et attentes, selon la norme) ; en bateau, la
  route maritime réelle (canal de Suez compris).
* **Le véhicule** : il est connu quand le transporteur est renseigné. Sinon, un modèle d'apprentissage
  automatique l'estime à partir de la vitesse, de la distance et du type d'étape, et le calcul utilise la
  moyenne des facteurs possibles pondérée par leur probabilité.
* **Le poids** : celui déclaré à la commande, corrigé quand il a été saisi en grammes. S'il manque, il est
  estimé à partir du volume et de la densité habituelle de la catégorie de produit.
""")

r = resume()
ev = r.get("evaluation") or {}
if ev:
    e = ev["emission_reconstituee"]
    st.markdown(f"""
### Quelle précision ?

Le calcul a été testé sur l'ensemble des {nombre(r['colis'])} colis de l'année, pour lesquels la valeur
exacte est connue (données d'entraînement simulées). L'écart médian est de **{nombre(e['erreur_mediane_pct'], 1)} %**
et l'écart sur le total de l'année de **{nombre(e['biais_total_pct'], 2)} %** :
{nombre(e['part_a_moins_de_20pct'], 0)} % des colis sont estimés à moins de 20 % près.
""")

st.markdown("### Les facteurs d'émission utilisés")
f = R.table_facteurs()
f["Facteur (g CO₂e par t.km)"] = (f.kgco2e_tkm * 1000).round(1)
st.dataframe(f[["libelle", "Facteur (g CO₂e par t.km)", "base_carbone_id", "origine"]].rename(columns={
    "libelle": "Véhicule", "base_carbone_id": "Identifiant Base Carbone", "origine": "Source"}),
    hide_index=True, use_container_width=True)
st.caption("Source : Base Carbone de l'ADEME (licence ouverte), téléchargée depuis data.ademe.fr. "
           "Les facteurs aériens incluent l'effet des traînées de condensation, comme le recommande l'ADEME. "
           "Deux facteurs absents de la base (utilitaire électrique, vélo cargo) sont dérivés de valeurs qui y figurent.")

st.markdown(f"""
### Les limites, honnêtement

* Les émissions des bâtiments (plateformes, agences) et la fabrication des véhicules ne sont pas comptées :
  seul le transport l'est, comme dans l'information CO₂ réglementaire.
* Le dernier kilomètre est calculé comme une part de tournée : distance de l'agence au client multipliée par
  {nombre(C.TOURNEE_FACTEUR, 1)} pour tenir compte des détours, réduite de 40 % en point relais (tournées groupées).
* Le trajet du client vers le point relais n'est pas inclus.
* Les données internes de ce prototype (commandes, scans, transporteurs) sont simulées ; les référentiels
  (facteurs ADEME, villes, aéroports, distances routières et maritimes) sont réels.
""")
