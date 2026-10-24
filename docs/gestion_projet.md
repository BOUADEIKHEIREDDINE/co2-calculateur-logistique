# Gestion de projet

Le projet suit la démarche Scrum présentée en cours, avec un tableau Kanban pour le suivi quotidien.

## 1. Analyse du besoin

**Contexte.** FastColis livre des colis en France pour des clients grands comptes. Ces clients doivent publier l'empreinte carbone de leurs livraisons et demandent à FastColis un chiffre par colis ou par commande.

**Objectifs métier.**

* **Comparabilité** : une seule méthode (EN 16258, facteurs ADEME) pour tous les clients, tous les services, toutes les origines.
* **Qualité** : un chiffre juste à quelques pourcents, dont chaque gramme se rattache à une étape, un véhicule et une source.
* **Rapidité d'analyse** : le pipeline complet tourne en moins de deux minutes ; un client obtient son bilan sans intervention de l'équipe data.
* **Anticipation** : estimer un envoi avant qu'il parte, pour orienter le choix du service.

**Contraintes.**

* Sources hétérogènes : export SAP aux noms de colonnes techniques, logs de scanners en deux formats, annuaire Excel des transporteurs.
* Chaîne partiellement observée : scans oubliés, partenaires étrangers sans échange de données, transporteurs non renseignés, colis encore en transit.
* Absence de référentiel : ni table de distances, ni facteurs d'émission, ni description du réseau.
* Données internes indisponibles pour le projet : elles sont simulées, ce que le cours autorise.

## 2. Vision produit

> Donner à chaque client de FastColis l'empreinte carbone de chacun de ses colis, expliquée étape par étape, et les moyens de la réduire.

| Objectif produit | Résultat attendu |
|---|---|
| 1. Un dataset unifié et propre | table Curated, une ligne par colis, colonnes du cahier des charges |
| 2. Une émission fiable même sans données complètes | reconstitution des trajets et modèles d'apprentissage |
| 3. Une restitution utilisable par un non-spécialiste | interface, bilans Excel, présentation |

## 3. Équipe et rôles

| Membre | Rôle Scrum | Responsabilité principale |
|---|---|---|
| Kheireddine BOUADI | Product Owner | vision, priorisation du backlog, architecture du pipeline |
| Maël RAZAFIMBELO | Scrum Master | animation des rituels, règles de validation et rapport qualité |
| Mohamed BEN AMOR | Data Engineer | ingestion, nettoyage, référentiels externes |
| Ael Boece NGODA LONTSI | Data Scientist | modèles d'apprentissage, évaluation |
| Abdallah BENSMAIL | Data Analyst | interface client, visualisations, présentation |

Parties prenantes : direction RSE de FastColis, responsables RSE des clients grands comptes, équipe SI (exploitation des scanners et de SAP).

## 4. Product backlog

| Epic | Feature | User story | Priorité |
|---|---|---|---|
| **E1 Ingestion des sources** | F1.1 Découverte | US 1.1.1 En tant que data engineer, je veux un profil automatique de chaque source pour repérer les formats concurrents. | haute |
| | F1.2 Lecture multi-format | US 1.2.1 En tant que data engineer, je veux charger SAP, scans et transporteurs dans une couche brute unique et traçable. | haute |
| | F1.3 Référentiels externes | US 1.3.1 En tant que data engineer, je veux télécharger les facteurs ADEME, les villes et les aéroports, et mettre en cache les distances routières. | haute |
| **E2 Qualité et nettoyage** | F2.1 Normalisation | US 2.1.1 En tant que data wrangler, je veux harmoniser unités, dates, codes pays et clients. | haute |
| | F2.2 Doublons et rejets | US 2.2.1 En tant que data wrangler, je veux supprimer les doublons et isoler les scans orphelins. | haute |
| | F2.3 Journal | US 2.3.1 En tant que data steward, je veux un journal de chaque correction appliquée. | moyenne |
| **E3 Calcul et modèles** | F3.1 Trajets | US 3.1.1 En tant que data engineer, je veux reconstituer le trajet de chaque colis, y compris les passages non flashés. | haute |
| | F3.2 Distances et facteurs | US 3.2.1 En tant que responsable RSE, je veux des distances réelles par mode et des facteurs officiels identifiés. | haute |
| | F3.3 Apprentissage | US 3.3.1 En tant que data scientist, je veux estimer le véhicule quand le transporteur manque. US 3.3.2 Je veux prédire l'émission d'un envoi à partir de la commande. | moyenne |
| | F3.4 Validation | US 3.4.1 En tant que responsable data, je veux un rapport de validation automatique et une mesure de la précision. | haute |
| **E4 Restitution client** | F4.1 Calculateur | US 4.1.1 En tant que client, je veux connaître l'empreinte d'un envoi et la comparer aux autres options. | haute |
| | F4.2 Bilan | US 4.2.1 En tant que responsable RSE d'un client, je veux mon bilan mensuel, ses causes et un export Excel. | haute |
| | F4.3 Transparence | US 4.3.1 En tant que client, je veux comprendre la méthode et voir les contrôles appliqués. | moyenne |

## 5. Sprints

| Sprint | Objectif | User stories |
|---|---|---|
| 1 | Des données propres et traçables | US 1.1.1, 1.2.1, 1.3.1, 2.1.1, 2.2.1, 2.3.1 |
| 2 | Une émission fiable par colis | US 3.1.1, 3.2.1, 3.3.1, 3.3.2, 3.4.1 |
| 3 | Le client a son outil | US 4.1.1, 4.2.1, 4.3.1, présentation |

### Sprint 1 backlog

| User story | Tâche technique | Responsable |
|---|---|---|
| US 1.1.1 | Profilage par formes et constats automatiques (`decouverte.py`) | Mohamed BEN AMOR |
| US 1.2.1 | Lecteurs SAP (cp1252), JSON Lines v1 et v2, Excel deux onglets (`ingestion.py`) | Mohamed BEN AMOR |
| US 1.3.1 | Téléchargement Base Carbone, GeoNames, OpenFlights ; cache OSRM (`referentiels.py`) | Kheireddine BOUADI |
| US 2.1.1 | Règles de poids, dimensions, dates, codes, clients (`nettoyage.py`) | Mohamed BEN AMOR |
| US 2.1.1 | Classement des véhicules par expressions régulières | Ael Boece NGODA LONTSI |
| US 2.2.1 | Doublons SAP, doubles flashages, quarantaine des orphelins | Maël RAZAFIMBELO |
| US 2.3.1 | Journal des traitements et tests unitaires | Maël RAZAFIMBELO |
| US 1.2.1 | Génération des sources simulées et de la vérité terrain (`simulation.py`) | Kheireddine BOUADI |
| tous | Revue de sprint : présentation du rapport de découverte | Abdallah BENSMAIL |

## 6. Tableau Kanban

| File d'attente | En analyse | Prêt pour le dév | En dév | En recette | Terminé |
|---|---|---|---|---|---|
| API du calculateur | Émissions des plateformes | | | | US 1.1.1 à 4.3.1 |
| Tournées GPS réelles | | | | | |

Limites de travail en cours : 3 cartes en développement, 2 en recette (« cesser de commencer, commencer par terminer »).

## 7. Definition of Done

Une user story est terminée quand :

* le code est dans le paquet `co2` ou `app`, lisible et commenté là où c'est utile ;
* chaque transformation de données écrit une ligne dans le journal ;
* les tests passent (`python -m pytest tests`) et les règles de validation restent au vert ou en alerte justifiée ;
* le pipeline complet s'exécute sans erreur (`python run_pipeline.py`) ;
* la documentation (README, méthodologie, dictionnaire) est à jour.
