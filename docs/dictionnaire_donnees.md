# Dictionnaire de données

## Table `data/curated/colis_co2` (une ligne par colis)

Disponible en Parquet (types conservés) et en CSV (`;`, virgule décimale, UTF-8 avec BOM pour Excel).

### Colonnes demandées dans le cahier des charges

| Colonne | Type | Description | Source / calcul |
|---|---|---|---|
| `tracking_id` | texte | identifiant unique du colis, `FC` + 10 chiffres | SAP `TRACKING`, normalisé |
| `date_first_scan` | date-heure (Paris) | premier flashage du colis | flashages |
| `date_last_scan` | date-heure (Paris) | dernier flashage (livraison si `statut = livre`) | flashages |
| `pays_origine` | texte | code ISO 3166 alpha-2 | SAP `LAND1_ORIG`, normalisé |
| `pays_destination` | texte | code ISO 3166 alpha-2 | SAP `LAND1_DEST`, normalisé |
| `poids_kg` | réel | poids brut | SAP `BRGEW` et `GEWEI`, corrigé ou imputé |
| `volume_m3` | réel | longueur × largeur × hauteur | SAP `LAENG`, `BREIT`, `HOEHE`, `MEINS` |
| `nb_plateformes` | entier | entrées, plateformes de tri et agences traversées | trajet reconstitué |
| `distance_estimee_km` | réel | distance parcourue, somme des étapes | OSRM, orthodromie, searoute |
| `mode_transport` | texte | mode principal en distance : Camion, Camionnette, Avion, Bateau, Train, Vélo | véhicules des étapes |
| `facteur_emission_moyen_g_tkm` | réel | émission ÷ tonnes.km du colis | calcul dérivé |
| `emission_estimee_g` | réel | émission reconstituée étape par étape (g CO₂e) | poids × distance × facteur |
| `emission_ml_g` | réel | émission prédite à partir de la seule commande | `RegresseurEmission` |

### Contexte et traçabilité

| Colonne | Description |
|---|---|
| `client`, `categorie` | compte client canonique, catégorie de produit |
| `service` | standard, express, ecologique, international |
| `livraison` | domicile ou point_relais |
| `date_commande` | date et heure de la commande (SAP `ERDAT` + `ERZET`) |
| `statut` | `livre` ou `en_transit_ou_non_flashe` |
| `delai_livraison_h` | heures entre la commande et la livraison |
| `ville_origine`, `departement_origine`, `ville_destination`, `departement_destination` | lieux géocodés (nom officiel GeoNames) |
| `lat_orig`, `lon_orig`, `lat_dest`, `lon_dest` | coordonnées utilisées pour les calculs |
| `source_geo_origine`, `source_geo_destination` | `site_expedition`, `gps_point_relais`, `gps_livraison` ou `centre_ville` |
| `distance_directe_km` | vol d'oiseau origine-destination |
| `nb_etapes`, `tonne_km` | nombre d'étapes et somme des tonnes.km |
| `emission_ml_bas_g`, `emission_ml_haut_g` | intervalle de prédiction à 80 % (conformalisé) |
| `ecart_ml_pct` | écart relatif entre reconstitution et modèle |
| `a_verifier` | reconstitution hors de [bas ÷ 2 ; haut × 2] : à revoir |
| `methode_emission` | `trajet observé` ou `trajet reconstitué` |
| `taux_observation` | part des étapes dont les deux extrémités sont scannées et le véhicule connu |
| `nb_etapes_inferees` | étapes dont une extrémité a été déduite de la topologie |
| `nb_vehicules_predits` | étapes dont le véhicule vient du modèle |
| `vehicule_dernier_km`, `emission_dernier_km_g` | véhicule et émission de la livraison finale |
| `emission_avion_g`, `emission_bateau_g`, `emission_camion_g`, `emission_camionnette_g`, `emission_train_g`, `emission_velo_g` | décomposition de l'émission par mode |
| `poids_impute` | poids absent dans SAP, estimé |
| `poids_corrige` | poids saisi en grammes et corrigé |
| `poids_volumetrique_kg` | volume × 250 kg/m³, pour repérer les colis encombrants |
| `chronologie_suspecte` | au moins un scan à l'heure incohérente |

## Table `data/curated/etapes_co2` (une ligne par étape de transport)

| Colonne | Description |
|---|---|
| `tracking_id`, `rang` | colis et position de l'étape dans le trajet |
| `de`, `vers` | code de site (`TRI-IDF`, `AG-69`, `ENT-CDG`, `WH-AMA1`, `PART-PVG`...) ou `ORIGINE` / `DESTINATION` |
| `type_etape` | ENLEVEMENT, COLLECTE, PRE_ACHEMINEMENT, INTERNATIONAL(_AIR, _MER), POST_ENTREE, CAPILLAIRE_ORIGINE, LIGNE, CAPILLAIRE, DERNIER_KM |
| `de_infere`, `vers_infere` | extrémité déduite (passage non flashé) |
| `transporteur_id` | transporteur scanné à l'arrivée de l'étape |
| `vehicule` | code du véhicule (`ROUTE_ART_40T_DIESEL`, `VUL_ELEC`, `AIR_CARGO_5000P`...) |
| `source_vehicule` | `transporteur`, `regle_metier` ou `modele_ml` |
| `confiance_vehicule` | probabilité de la classe prédite (étapes prédites) |
| `mode_transport` | mode lisible |
| `distance_vol_oiseau_km`, `distance_km`, `methode_distance` | distances et méthode retenue |
| `duree_h` | temps entre les deux scans quand ils existent |
| `poids_kg`, `tonne_km` | poids du colis et tonnes.km de l'étape |
| `facteur_kgco2e_tkm`, `base_carbone_id` | facteur appliqué (moyenne pondérée si prédit) et identifiant ADEME |
| `emission_g` | émission de l'étape |

## Référentiel des facteurs

`co2.referentiels.table_facteurs()` : `code_vehicule`, `mode`, `libelle`, `kgco2e_tkm`, `unite_source`, `base_carbone_id`, `statut_source` (« Valide générique » ou « Dérivé »), `origine`.

## Sources brutes

| Fichier | Colonnes principales |
|---|---|
| `sap_export_colis.csv` | `VBELN` commande, `TRACKING`, `KUNNR` code client, `NAME1` libellé, `MATKL` catégorie, `BRGEW` poids, `GEWEI` unité, `LAENG`/`BREIT`/`HOEHE` + `MEINS`, `VSART` service, `LIVR`, `LAND1_ORIG`, `ORT01_ORIG`, `WERKS` site d'expédition, `LAND1_DEST`, `ORT01_DEST`, `REGIO_DEST`, `ERDAT`, `ERZET`, `NETWR`, `WAERK`, `ZLSCH` |
| `flashages/*.jsonl` v1 | `trk`, `evt` (code court), `site`, `ts` (epoch ms), `gps` (« lat,lon »), `carrier` |
| `flashages/*.jsonl` v2 | `tracking_id`, `event_type`, `site_code`, `timestamp` (ISO 8601), `geo` {lat, lon}, `carrier_id` |
| `transporteurs.xlsx` | onglet « Flotte interne » : code flotte, type de véhicule, énergie ; onglet « Sous-traitants » : ID, raison sociale, mode, catégorie, carburant, fin de contrat |
| `sites_reseau.csv`, `sites_alias_wms.csv` | code, libellé, type, ville, pays, coordonnées ; correspondance des anciens codes |
