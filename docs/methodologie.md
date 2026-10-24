# Méthodologie

Ce document explique comment le pipeline passe de fichiers bruts à une émission par colis, quelles hypothèses il pose et comment sa qualité est mesurée. Les chiffres cités sont ceux de la dernière exécution (`reports/resume_pipeline.json`).

## 1. Principe du calcul

Pour chaque étape *e* du trajet d'un colis :

```
émission(e) [g CO₂e] = poids [t] × distance(e) [km] × facteur(véhicule de e) [kg CO₂e / t.km] × 1 000
```

L'émission du colis est la somme de ses étapes. C'est l'approche de la norme EN 16258 et du dispositif réglementaire français d'information CO₂ des prestations de transport, avec les facteurs de la Base Carbone de l'ADEME. Le périmètre est celui du transport (du réservoir à la roue et en amont, tel que fourni par la Base Carbone) ; les bâtiments et la fabrication des véhicules sont exclus.

## 2. Découverte (`co2/decouverte.py`)

Le profilage réduit chaque valeur à sa forme : chaque chiffre devient `9`, chaque lettre `A`, et les répétitions sont compactées (`9{8}`). Une colonne qui présente plusieurs formes contient des formats concurrents. Les constats générés automatiquement (`reports/01_decouverte.md`) ont guidé toutes les règles de nettoyage :

* trois formats de date dans `ERDAT` (`9{8}`, `99.99.9{4}`, `9{4}-99-99`) ;
* trois unités de poids (KG, G, vide) et 1 158 poids supérieurs à 70 « kg » ;
* 22 libellés de clients pour 8 codes clients, 37 écritures de pays, 12 codes de service ;
* deux formats de scanners (v1 : epoch en millisecondes et codes courts ; v2 : ISO 8601) ;
* des codes de site absents du référentiel (anciens codes WMS, partenaires étrangers) ;
* 30 % de scans sans GPS, 28 % sans transporteur, des horodatages sans fuseau horaire.

## 3. Ingestion (`co2/ingestion.py`)

Chaque lecteur conserve les valeurs en texte et ajoute deux colonnes de traçabilité, `_fichier` et `_ligne`. Les deux schémas de scanners sont ramenés à un schéma brut commun. Les tables sont figées en Parquet dans `data/raw` pour que les étapes suivantes ne relisent jamais les sources.

## 4. Structuration et nettoyage (`co2/nettoyage.py`)

Toutes les règles écrivent dans un journal (table, règle, lignes concernées, action), publié dans `reports/journal_traitements.csv` et dans l'interface.

| Domaine | Règle |
|---|---|
| Colonnes SAP | renommage des noms techniques (`BRGEW`, `VSART`, `ERDAT`...) en noms métier |
| Clients | le code `KUNNR` fait foi ; le libellé canonique est le plus fréquent une fois normalisé (sans suffixe juridique ni domaine) |
| Poids | virgule décimale ; unité G divisée par 1 000 ; une valeur > 70 avec unité KG ou vide, plausible une fois divisée par 1 000, est traitée comme des grammes ; poids nul ou négatif mis à vide |
| Dimensions | MM convertis en cm ; volume en m³ ; dimension > 2 m rejetée |
| Codes | services, livraison, pays (ISO 3166 alpha-2) |
| Dates | trois formats explicites, jamais d'inférence automatique |
| Doublons SAP | un seul enregistrement par numéro de suivi |
| Numéros de suivi | majuscules, espaces retirés, préfixe `FC` ajouté aux numéros à 10 chiffres |
| Sites | casse, espaces, table des anciens codes WMS ; sites partenaires (`PART-SZX`...) ajoutés depuis OpenFlights |
| Horodatages | epoch ms en UTC ; ISO avec décalage ; ISO sans fuseau interprété à l'heure locale du site |
| GPS | (0, 0) mis à vide ; latitude et longitude permutées quand la position inversée est bien plus proche du site |
| Transporteurs | identifiants normalisés, doublons de casse supprimés ; catégorie de véhicule classée par expressions régulières sur le libellé et l'énergie (attention : « gazole » contient « gaz ») |
| Doubles flashages | même colis, même événement, même site à moins de 5 minutes |
| Orphelins | scans d'un numéro absent de SAP mis en quarantaine (`data/raw_clean/rejets.parquet`) |
| Chronologie | dans l'ordre logique des événements, l'heure ne doit pas reculer de plus de 5 minutes (le firmware v2 tronque les millisecondes et certains sites sont accolés) |

## 5. Enrichissement (`co2/enrichissement.py`)

**Géocodage.** Les villes sont rapprochées de GeoNames par une clé normalisée (sans accents, `St-` développé en `Saint-`, ponctuation retirée), avec le département quand il existe, puis par similarité de chaîne (seuil 0,85). La position GPS du scan de livraison remplace le centre-ville quand elle est à moins de 60 km de celui-ci ; le GPS du point relais de dépôt fait de même pour l'origine des colis entre particuliers.

**Topologie apprise.** Pour chaque agence, la plateforme de tri flashée juste avant son arrivée ; pour chaque entrepôt ou porte d'entrée, celle flashée juste après. Le vote majoritaire donne 117 rattachements. Aucune carte du réseau n'est fournie au pipeline.

**Reconstitution des trajets.** Les scans d'un colis sont ordonnés par rang logique puis par heure. On insère ensuite les passages non flashés :

* la porte d'entrée d'un colis étranger (route pour l'Europe ; sinon prédite par le modèle `ModeInternational`) ;
* l'agence d'origine d'un dépôt en point relais ;
* l'agence de destination ;
* la plateforme de rattachement à la sortie d'un entrepôt, d'une entrée ou de l'agence d'origine, et à l'arrivée sur l'agence de destination.

Chaque étape porte un indicateur `de_infere` / `vers_infere`.

**Distances.**

| Cas | Méthode |
|---|---|
| Deux sites du réseau | distance routière OSRM réelle (16 512 paires en cache) |
| Autre trajet routier | vol d'oiseau × 1,27, médiane du rapport OSRM / vol d'oiseau sur le réseau |
| Train | vol d'oiseau × 1,30 |
| Avion | orthodromie + 95 km (forfait EN 16258 pour les approches et attentes) |
| Bateau | route maritime réelle (searoute), canal de Suez compris |
| Dernier kilomètre et collecte | distance de tournée : × 1,6 ; − 40 % en point relais (tournées groupées) |

**Poids manquants.** Volume × densité médiane de la catégorie ; à défaut, médiane du couple client × catégorie. Le poids volumétrique (250 kg/m³) est calculé pour information.

## 6. Mapping, feature engineering et modèles (`co2/features.py`, `co2/modele.py`)

**Facteurs.** 20 facteurs proviennent directement de la Base Carbone (identifiants dans `co2/referentiels.py`) ; deux sont dérivés de valeurs qui y figurent :

* utilitaire électrique = utilitaire gazole × (porteur 3,5-7,5 t électrique / porteur 3,5-7,5 t gazole) ;
* vélo cargo = mix électrique France 2024 × 0,015 kWh/km ÷ 0,08 t de charge moyenne.

Les facteurs aériens incluent l'effet des traînées, comme le recommande l'ADEME ; le facteur dépend de la distance du vol. Le facteur maritime dépend de la ligne (Asie-Europe du Nord, Asie-Méditerranée, Europe-Afrique, transatlantique).

**Véhicule de chaque étape.** Dans l'ordre : le transporteur scanné à l'arrivée de l'étape (annuaire nettoyé) ; une règle métier pour l'international ; sinon le modèle `ClassifieurVehicule`. Pour une étape prédite, le facteur retenu est la moyenne des facteurs pondérée par les probabilités du modèle : prendre la seule classe la plus probable ferait disparaître les véhicules rares et biaiserait le total (− 6 % sur l'option écologique, ramené à − 0,8 %).

**Les trois modèles** (gradient boosting `HistGradientBoosting` de scikit-learn, chacun comparé à une règle simple sur un jeu de test) :

| Modèle | Variables | Règle de référence | Règle | Modèle |
|---|---|---|---|---|
| `ModeInternational` | pays, service, client, poids, délai commande → premier scan en France | mode le plus fréquent du pays | 87,4 % | 98,5 % |
| `ClassifieurVehicule` | type d'étape, distance, durée, vitesse, service, client, population de la ville... | véhicule le plus fréquent par type d'étape et service | 69,7 % | 70,7 % |
| `RegresseurEmission` | informations de commande seulement | facteur moyen × poids × distance directe | 55,7 % d'erreur médiane | 16,8 % |

Le régresseur est entraîné sur les colis livrés dont au moins 75 % du trajet est observé (60 % apprentissage, 20 % calibration, 20 % test). Ses quantiles 10 % et 90 % sont élargis par régression quantile conformalisée : l'intervalle à 80 % couvre 79,4 % des colis de test. Il sert à trois choses : `emission_ml_g` dans la table finale, le signalement des reconstitutions douteuses (`a_verifier`, 0,7 % des colis) et le contrôle affiché par le calculateur.

## 7. Validation (`co2/validation.py`)

**Règles de cohérence** (`reports/06_regles_validation.csv`) : unicité, bornes de poids et de volume, inégalité triangulaire (le trajet est au moins aussi long que le vol d'oiseau), distances positives, total du colis égal à la somme de ses étapes, facteur présent et plausible, vitesse entre deux scans compatible avec le mode, dates dans la période, délais plausibles, géocodage complet. Résultat : 11 règles OK, 2 alertes sous 1 % (un volume de 0,54 m³, 64 vitesses improbables liées à des horloges décalées).

**Évaluation contre la vérité terrain.**

| Mesure | Reconstitution | Modèle commande seule |
|---|---|---|
| Erreur médiane par colis | 2,2 % | 15,9 % |
| Erreur au 90e centile | 15,9 % | 64,4 % |
| Biais sur le total | + 0,5 % | + 4,9 % |
| Colis à moins de 20 % | 92,2 % | 56,6 % |

L'erreur de la reconstitution passe de 1,1 % pour les trajets entièrement observés à 4,3 % quand moins de la moitié du trajet l'est. La distance totale est juste à 0,4 % près en médiane. Les défauts injectés sont tous retrouvés (doublons SAP 1 020 sur 1 020, orphelins 300 sur 300, horloges décalées 1 464 signalées pour 1 402 injectées...).

## 8. Calculateur d'envoi (`co2/calculateur.py`)

Pour un envoi qui n'existe pas encore, le trajet type suit la topologie apprise. Chaque étape reçoit le facteur effectivement observé sur l'année pour ce type d'étape et ce service (rapport des émissions aux tonnes.km, mix de flotte compris), et les lignes entre plateformes sont allongées du détour moyen observé par service (+ 12,7 % en standard, à cause du hub national). La fourchette va du 10e au 90e centile des facteurs des véhicules réellement affectés à chaque étape.

## 9. Hypothèses et limites

* Données internes simulées : la précision mesurée vaut pour ce réseau simulé ; sur de vraies données, il faudrait une campagne de contrôle (par exemple des tournées équipées de GPS).
* Le coefficient de tournée (1,6) et la réduction en point relais (− 40 %) sont des hypothèses métier à calibrer sur les tournées réelles.
* Le pré-acheminement à l'étranger (de la ville au port ou à l'aéroport) est compté quand le partenaire le scanne, sinon ignoré (moins de 1 % de l'émission d'un colis aérien).
* Le trajet du client vers le point relais n'est pas inclus.
* Les montants en devises étrangères sont conservés tels quels : ils ne servent pas au calcul.
