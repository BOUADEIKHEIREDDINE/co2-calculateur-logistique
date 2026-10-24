# Rapport qualité et validation

Généré par `co2.validation` (étape 6). Statut : OK (aucune anomalie), ALERTE (moins de 1 %), ECHEC (1 % ou plus).

## Règles de cohérence

| regle                  | description                                                       |   anomalies |   controles | statut   |
|:-----------------------|:------------------------------------------------------------------|------------:|------------:|:---------|
| unicite_tracking       | un numéro de suivi par colis                                      |           0 |       60000 | OK       |
| poids_borne            | poids dans ]0 ; 70] kg                                            |           0 |       60000 | OK       |
| volume_borne           | volume < 0,5 m3 quand il est connu                                |           1 |       52767 | ALERTE   |
| inegalite_triangulaire | distance parcourue >= distance à vol d'oiseau origine-destination |           0 |       60000 | OK       |
| distance_positive      | aucune étape de distance négative ou > 25 000 km                  |           0 |      263000 | OK       |
| total_egal_sous_totaux | émission du colis = somme des émissions de ses étapes             |           0 |       60000 | OK       |
| facteur_reference      | chaque étape a un facteur du référentiel                          |           0 |      263000 | OK       |
| facteurs_plausibles    | facteurs ADEME dans les bornes attendues par mode                 |           0 |          22 | OK       |
| vitesse_plausible      | vitesse moyenne entre deux scans compatible avec le mode          |          64 |      151346 | ALERTE   |
| date_dans_periode      | commande dans la période étudiée                                  |           0 |       60000 | OK       |
| delai_plausible        | délai de livraison entre 0 et 60 jours                            |           0 |       58998 | OK       |
| emission_positive      | émission strictement positive                                     |           0 |       60000 | OK       |
| geocodage_complet      | origine et destination géolocalisées                              |           0 |       60000 | OK       |

## Statistiques descriptives (table Curated)

|                     |   count |    mean |     std |   min |    10% |    50% |     90% |       max |
|:--------------------|--------:|--------:|--------:|------:|-------:|-------:|--------:|----------:|
| poids_kg            |   60000 |    1.51 |    2.41 |  0.05 |   0.33 |   0.86 |    3.09 |     70    |
| volume_m3           |   52767 |    0.01 |    0.01 |  0    |   0    |   0    |    0.01 |      0.54 |
| distance_estimee_km |   60000 | 1966.28 | 3502.63 |  7.5  | 191    | 766.8  | 9725.6  |  21780.5  |
| nb_plateformes      |   60000 |    3.32 |    0.73 |  1    |   2    |   3    |    4    |      6    |
| emission_estimee_g  |   60000 |  828.28 | 3090.71 |  0.31 |  18.74 |  88.76 | 2384.32 | 137402    |
| emission_ml_g       |   60000 |  864.26 | 2736.2  |  2.12 |  21.29 |  87.01 | 2834.29 |  48123.9  |
| delai_livraison_h   |   58998 |   58.5  |   94.2  |  6.83 |  23.43 |  44.43 |   92.81 |   1108.64 |
| taux_observation    |   60000 |    0.72 |    0.25 |  0    |   0.33 |   0.75 |    1    |      1    |

## Journal des traitements

| table         | regle                                                              |   lignes | action                                                                   |
|:--------------|:-------------------------------------------------------------------|---------:|:-------------------------------------------------------------------------|
| sap           | libellés clients                                                   |       22 | 22 libellés ramenés à 8 clients via le code KUNNR                        |
| sap           | poids en grammes (unité G)                                         |     4734 | divisé par 1 000                                                         |
| sap           | poids > 70 kg avec unité KG ou vide                                |     1334 | valeur en grammes : divisée par 1 000                                    |
| sap           | poids nul ou négatif                                               |      132 | mis à vide puis imputé                                                   |
| sap           | dimensions en mm                                                   |     6220 | converties en cm                                                         |
| sap           | dimension > 2 m                                                    |        0 | volume mis à vide                                                        |
| sap           | codes de service                                                   |       12 | 12 écritures ramenées à 4 services                                       |
| sap           | codes pays                                                         |       37 | 37 écritures ramenées à 14 codes ISO 3166                                |
| sap           | formats de date                                                    |     9424 | trois formats convertis en datetime                                      |
| sap           | doublons de numéro de suivi                                        |     1020 | supprimés (755 copies exactes, 265 réexportations au format différent)   |
| sites         | coordonnées manquantes                                             |       14 | géocodées via GeoNames (ville, pays)                                     |
| sites         | sites partenaires inconnus du référentiel                          |       15 | ajoutés depuis OpenFlights (code IATA)                                   |
| transporteurs | identifiants en double (casse)                                     |        3 | dédoublonnés                                                             |
| transporteurs | catégorie de véhicule absente                                      |        7 | 1 déduites du mode, 6 laissées inconnues (imputées par étape)            |
| flashages     | numéros de suivi mal formés                                        |    28970 | majuscules, espaces retirés, préfixe FC ajouté                           |
| flashages     | codes d'événement du firmware v1                                   |   159599 | traduits dans la nomenclature v2                                         |
| flashages     | codes de site (espaces, casse, anciens codes WMS)                  |   119705 | normalisés ; 23746 anciens codes traduits                                |
| flashages     | horodatages sans fuseau horaire                                    |     9940 | interprétés à l'heure locale du site                                     |
| flashages     | GPS à (0, 0)                                                       |     3634 | mis à vide                                                               |
| flashages     | latitude et longitude inversées                                    |     7048 | permutées                                                                |
| flashages     | identifiant transporteur tronqué ou inconnu                        |     7838 | mis à vide                                                               |
| flashages     | double flashage (< 5 min)                                          |    10539 | supprimés                                                                |
| flashages     | scans orphelins                                                    |      300 | mis en quarantaine (data/raw_clean/rejets)                               |
| flashages     | horodatage incohérent (avant la commande ou ordre logique inversé) |     1464 | signalés ; l'ordre logique prime pour reconstituer le trajet             |
| colis         | poids manquant imputé par le volume                                |     1476 | volume x densité médiane de la catégorie                                 |
| colis         | poids manquant imputé par la médiane                               |      195 | médiane du couple client x catégorie                                     |
| colis         | département de destination absent                                  |     2378 | déduit de la ville (GeoNames)                                            |
| colis         | villes de destination rapprochées par similarité                   |        0 | orthographe approchante acceptée (seuil 0,85)                            |
| colis         | destination non géocodée                                           |        0 | laissée vide                                                             |
| colis         | position de livraison GPS                                          |    40801 | remplace le centre-ville (0 GPS rejetés : à plus de 60 km de la ville)   |
| colis         | origines géocodées                                                 |    60000 | site d'expédition, GPS du point relais ou ville GeoNames                 |
| etapes        | passage non flashé : plateforme de tri                             |     9802 | déduit de la topologie du réseau                                         |
| etapes        | passage non flashé : agence d'origine                              |     1127 | déduit de la topologie du réseau                                         |
| etapes        | passage non flashé : porte d'entrée                                |      846 | déduit de la topologie du réseau                                         |
| etapes        | passage non flashé : agence de destination                         |      373 | déduit de la topologie du réseau                                         |
| etapes        | coefficient de détour routier                                      |        0 | 1.269 (médiane OSRM / vol d'oiseau sur 16 512 paires du réseau)          |
| etapes        | distance : osrm                                                    |   176568 | méthode de calcul de la distance                                         |
| etapes        | distance : vol_oiseau_x_detour_tournee                             |    72114 | méthode de calcul de la distance                                         |
| etapes        | distance : orthodromie_plus_95km                                   |     6915 | méthode de calcul de la distance                                         |
| etapes        | distance : vol_oiseau_x_detour                                     |     6507 | méthode de calcul de la distance                                         |
| etapes        | distance : route_maritime                                          |      896 | méthode de calcul de la distance                                         |
| etapes        | véhicule connu par le transporteur                                 |   192828 | facteur direct                                                           |
| etapes        | véhicule fixé par règle métier (international)                     |     3420 | aérien selon distance, maritime selon la ligne, pré-acheminement routier |
| etapes        | véhicule prédit par le modèle                                      |    66752 | transporteur inconnu ; confiance médiane 76%                             |
| colis         | écart fort entre reconstitution et modèle                          |      391 | signalés pour revue (hors de [bas/2 ; haut x 2])                         |

## Modèles d'apprentissage

**Mode des colis internationaux (porte d'entrée non flashée)** : n_apprentissage = 5 505, n_test = 1 836, precision_modele = 0.985, precision_regle_pays = 0.874

**Véhicule d'une étape sans transporteur** : n_apprentissage = 148 412, n_test = 37 104, precision_modele = 0.707, precision_regle_frequence = 0.697

**Émission d'un colis à partir de la commande** : n_apprentissage = 21 445, n_test = 7 149, r2_log = 0.87, erreur_absolue_mediane_pct = 16.827, erreur_absolue_mediane_pct_naif = 55.729, mae_g = 199.197, couverture_intervalle_80 = 0.794, marge_conformale_log = 0.043


## Évaluation contre la vérité terrain

Les données internes étant simulées, on connaît l'émission exacte de chaque colis. Le pipeline ne lit jamais cette vérité ; elle sert uniquement ici.

|                       |   erreur_mediane_pct |   erreur_p90_pct |   biais_total_pct |   part_a_moins_de_20pct |
|:----------------------|---------------------:|-----------------:|------------------:|------------------------:|
| emission_reconstituee |                  2.2 |             15.9 |              0.5  |                    92.2 |
| emission_ml           |                 15.9 |             64.4 |              4.86 |                    56.6 |
| distance              |                  0.4 |              3.1 |             -0.36 |                    99   |

### Erreur selon la part du trajet observée

| part_observee   |   colis |   erreur_reconstituee_pct |   erreur_ml_pct |
|:----------------|--------:|--------------------------:|----------------:|
| < 50 %          |   15302 |                       4.3 |            18.3 |
| 50-75 %         |   18187 |                       2.6 |            16.7 |
| 75-99 %         |    8811 |                       1.6 |            11.9 |
| 100 %           |   17700 |                       1.1 |            14.9 |

### Erreur par service (émission reconstituée)

| service       |   erreur_mediane_pct |   erreur_p90_pct |   biais_total_pct |   part_a_moins_de_20pct |
|:--------------|---------------------:|-----------------:|------------------:|------------------------:|
| ecologique    |                  4.6 |             44   |             -0.84 |                    79.5 |
| express       |                  1.8 |             12.1 |              0.27 |                    95   |
| international |                  0.3 |              8.6 |              0.74 |                    95.2 |
| standard      |                  2.7 |             13.8 |             -0.97 |                    93.9 |

### Véhicules prédits

Sur 55 567 étapes comparables, le véhicule prédit est le bon dans 76.0 % des cas.


### Défauts injectés et traités

| defaut                                                       |   injectes |   traites |
|:-------------------------------------------------------------|-----------:|----------:|
| SAP : doublons supprimés                                     |       1020 |      1020 |
| SAP : grammes saisis en kg (inclut les grammes à unité vide) |       1166 |      1334 |
| SAP : poids manquants (+ imputés par médiane)                |       1542 |      1539 |
| SAP : poids nuls ou négatifs                                 |        129 |       132 |
| Scans : doubles flashages                                    |      10611 |     10539 |
| Scans : GPS inversés                                         |       6871 |      7048 |
| Scans : GPS à zéro                                           |       3531 |      3634 |
| Scans : orphelins                                            |        300 |       300 |
| Scans : transporteur tronqué                                 |       7607 |      7838 |
| Scans : horloge décalée                                      |       1402 |      1464 |
| Sites : coordonnées manquantes                               |         14 |        14 |
