# Rapport de découverte des sources

Généré automatiquement par `co2.decouverte` (étape 1 du pipeline). Une *forme* remplace chaque chiffre par `9` et chaque lettre par `A` : plusieurs formes pour une même colonne signalent des formats concurrents.

## Constats principaux

* SAP : 61 020 lignes pour 60 000 numéros de suivi, soit 1 020 lignes en double.
* SAP : formats de date ERDAT rencontrés : `9{8}` (51 596), `99.99.9{4}` (6 449), `9{4}-99-99` (2 975).
* SAP : unités de poids GEWEI : KG (54 451), G (4 734), vide (1 835).
* SAP : 1 568 poids illisibles ou vides, 132 nuls ou négatifs, 1 158 poids > 70 « kg » (probablement des grammes).
* SAP : 22 libellés clients pour 8 codes clients.
* SAP : 37 écritures de pays d'origine (Allemagne, BE, Belgique, CA, CHN, CN, Canada, Chine, Corée du Sud, DE, DEU, ES...).
* SAP : codes de service VSART : 01, 02, 03, 04, ECO, EXP, Express 24h, INT, International, STD, Standard, Écologique.
* Flashages : 362 199 événements, 159 599 au format v1 (epoch en ms, codes courts) et 202 600 au format v2 (ISO 8601).
* Flashages : codes d'événements : ARRIVEE_AGENCE, ARR_NCE, DEPART_TOURNEE, DEPOT_RELAIS, DEP_NEE, ENTREE_PLATEFORME, ENT_RME, HUB_PARTENAIRE, LIVRE, LIVRE_RELAIS, LIV_AIS, LIV_VRE, PRISE_EN_CHARGE, PRI_RGE, TRI, TRI_TRI.
* Flashages : 11 958 dépôts en point relais (10 014 relais, non référencés : normal). Hors relais, 26 763 scans portent 23 codes absents du référentiel (GON01, LIL-TRI, LYS02, MRS01, ORL-HUB, CDG-FRET, PART-SZX, BDX01, PART-PVG, PART-HKG...).
* Flashages : formes des numéros de suivi : `AA9{10}` (344 112), `9{10}` (10 796), `AA 9{4} 999 999` (7 291).
* Flashages : 30% des scans sans GPS, 28% sans transporteur.
* Flashages : 9 940 horodatages v2 sans fuseau horaire.
* Transporteurs : 44 flottes internes et 66 lignes sous-traitants dont 3 doublons ; 7 sans catégorie de véhicule.
* Sites : 129 sites, 14 sans coordonnées, décimales à la virgule.

## Table `sap` (61,020 lignes, 26 colonnes)

| colonne    |   manquants_pct |   distincts | formes                                                               | valeurs_frequentes                                                    |
|:-----------|----------------:|------------:|:---------------------------------------------------------------------|:----------------------------------------------------------------------|
| VBELN      |             0   |       59986 | `9{8}` 100%                                                          | 75031276 (3), 13011968 (3), 79592945 (3)                              |
| TRACKING   |             0   |       60000 | `AA9{10}` 100%                                                       | FC4755401484 (3), FC9212375976 (3), FC3859936681 (2)                  |
| KUNNR      |             0   |           8 | `9{6}` 100%                                                          | 100100 (20104), 100107 (13357), 100114 (6710)                         |
| NAME1      |             0   |          22 | `A{6}` 23% | `A{6} A{6} A{10}` 8% | `A{6} AA A{4}` 8% | `A{6}.AA` 8% | AMAZON FRANCE LOGISTIQUE (5093), Amazon (5039), AMAZON EU SARL (5013) |
| MATKL      |             0   |           8 | `A{6}` 50% | `A{4}` 13% | `A{9}` 13% | `A{5}` 13%                    | Mode (7865), Bricolage (7653), Livres (7640)                          |
| BRGEW      |             2.6 |        9008 | `9,999` 78% | `9,99` 8% | `999` 6% | `9{4}` 4%                       | 0,457 (59), 0,484 (59), 0,458 (59)                                    |
| GEWEI      |             3   |           2 | `AA` 89% | `A` 8% | `∅` 3%                                           | KG (54451), G (4734)                                                  |
| LAENG      |            12   |        1105 | `99.9` 78% | `∅` 12% | `999.9` 10% | `9.9` 0%                        | 19.3 (330), 17.9 (326), 16.9 (324)                                    |
| BREIT      |            12   |         899 | `99.9` 71% | `∅` 12% | `999.9` 9% | `9.9` 8%                         | 12.7 (423), 13.0 (410), 13.9 (410)                                    |
| HOEHE      |            12   |         722 | `99.9` 46% | `9.9` 37% | `∅` 12% | `999.9` 6%                        | 8.9 (477), 9.4 (470), 10.6 (458)                                      |
| MEINS      |            12   |           2 | `AA` 88% | `∅` 12%                                                   | CM (47463), MM (6220)                                                 |
| VSART      |             0   |          12 | `99` 33% | `AAA` 33% | `A{8}` 15% | `A{7} 99A` 7%                    | STD (9466), 01 (9425), Standard (9405)                                |
| LIVR       |             0   |           2 | `AAA` 61% | `AA` 39%                                                 | DOM (37026), PR (23994)                                               |
| LAND1_ORIG |             0   |          37 | `AA` 48% | `AAA` 25% | `A{6}` 20% | `A{5}` 3%                        | fr (12447), FR (12395), France (12345)                                |
| ORT01_ORIG |             0   |        3519 | `A{6}` 22% | `A{5}` 21% | `A{8}` 13% | `A{10}` 7%                    | Shenzhen (2746), Douai (2403), Brétigny-sur-Orge (2401)               |
| WERKS      |            39.2 |          14 | `AA-AAA9` 61% | `∅` 39%                                              | WH-AMA4 (3777), WH-AMA2 (3759), WH-AMA3 (3699)                        |
| LAND1_DEST |             0   |           4 | `AA` 50% | `AAA` 25% | `A{6}` 25%                                    | FR (15440), FRA (15256), France (15173)                               |
| ORT01_DEST |             0   |        5479 | `A{5}` 13% | `A{6}` 12% | `A{7}` 11% | `A{8}` 9%                     | Paris (2093), PARIS (1009), Marseille (838)                           |
| REGIO_DEST |             4   |          96 | `99` 96% | `∅` 4% | `9A` 0%                                          | 75 (3481), 59 (3018), 13 (2725)                                       |
| ERDAT      |             0   |        1091 | `9{8}` 85% | `99.99.9{4}` 11% | `9{4}-99-99` 5%                      | 20251120 (329), 20251127 (326), 20251121 (320)                        |
| ERZET      |             0   |       37367 | `9{6}` 100%                                                          | 235400 (855), 000000 (54), 113727 (8)                                 |
| NETWR      |             0   |       12711 | `99,99` 74% | `9,99` 9% | `99,9` 8% | `999,99` 7%                    | 13,79 (26), 16,56 (26), 10,62 (26)                                    |
| WAERK      |             0   |           3 | `AAA` 100%                                                           | EUR (58466), CNY (2161), USD (393)                                    |
| ZLSCH      |             0   |           4 | `AA` 50% | `A{6}` 33% | `AAA` 17%                                    | CB (30542), VIR (10241), PAYPAL (10122)                               |

## Table `flashages` (362,199 lignes, 10 colonnes)

| colonne      |   manquants_pct |   distincts | formes                                                                                                    | valeurs_frequentes                                                                |
|:-------------|----------------:|------------:|:----------------------------------------------------------------------------------------------------------|:----------------------------------------------------------------------------------|
| firmware     |             0   |           2 | `A9` 100%                                                                                                 | v2 (202600), v1 (159599)                                                          |
| tracking     |             0   |       86382 | `AA9{10}` 95% | `9{10}` 3% | `AA 9{4} 999 999` 2%                                                         | FC7189216817 (11), FC4237281054 (11), FC7401322701 (10)                           |
| evenement    |             0   |          16 | `AAA_AAA` 44% | `A{7}_A{6}` 11% | `A{6}_A{7}` 10% | `AAA` 9%                                              | TRI_TRI (77009), ARRIVEE_AGENCE (40905), DEPART_TOURNEE (36965)                   |
| site         |             0   |       11136 | `AA-99` 51% | `AAA-AAA` 28% | `AA-AAA9` 10% | `AAA99` 4%                                                  | TRI-IDF (23830), TRI-LIL (10834), TRI-LYS (9075)                                  |
| horodatage   |             0   |      361207 | `9{4}-99-99A99:99:99+99:99` 53% | `9{13}` 44% | `9{4}-99-99A99:99:99` 3% | `9{4}-99-99A99:99:99-99:99` 0% | 2026-03-29T03:00:00+02:00 (18), 1774746000000 (12), 2026-01-10T22:36:03+01:00 (3) |
| lat          |            30   |       48457 | `99.9{5}` 55% | `<AA>` 30% | `99.9{14}` 6% | `99.9{15}` 3%                                                | 48.98693 (23892), 50.58232 (12667), 45.66798 (8988)                               |
| lon          |            30   |       48692 | `9.9{5}` 43% | `<AA>` 30% | `-9.9{5}` 6% | `9.999` 4%                                                     | 2.44892 (23893), 3.119 (12667), 4.90198 (8988)                                    |
| transporteur |            28.3 |         109 | `AA-999` 70% | `∅` 28% | `AA-9` 2%                                                                        | FC-001 (4753), FC-002 (4678), FC-005 (4642)                                       |

## Table `transporteurs_internes` (44 lignes, 6 colonnes)

| colonne          |   manquants_pct |   distincts | formes                                                            | valeurs_frequentes                               |
|:-----------------|----------------:|------------:|:------------------------------------------------------------------|:-------------------------------------------------|
| Code flotte      |             0   |          44 | `AA-999` 100%                                                     | FC-001 (1), FC-002 (1), FC-003 (1)               |
| Type de véhicule |             0   |          20 | `A{7} 99A9` 11% | `A{7} 99A` 9% | `A-A{7}` 9% | `A{4} 99A AAA` 7% | Fourgon 12m3 (5), e-Fourgon (4), Porteur 19T (3) |
| Énergie          |            11.4 |           3 | `A{6}` 50% | `A{10}` 30% | `∅` 11% | `AAA` 9%                     | Gazole (22), Électrique (13), GNV (4)            |
| Mise en service  |             0   |          10 | `9{4}` 100%                                                       | 2019 (7), 2024 (7), 2017 (6)                     |

## Table `transporteurs_sous_traitants` (66 lignes, 8 colonnes)

| colonne         |   manquants_pct |   distincts | formes                                                                    | valeurs_frequentes                                                        |
|:----------------|----------------:|------------:|:--------------------------------------------------------------------------|:--------------------------------------------------------------------------|
| ID transporteur |             0   |          63 | `AA-999` 100%                                                             | ST-025 (2), ST-040 (2), ST-052 (2)                                        |
| Raison sociale  |             0   |          16 | `A{4} AAA A{7}` 11% | `A{4} AAA` 9% | `A{7} A{8}` 9% | `A{5} AAA A{5}` 9% | Asia Air Freight (7), Logi Sud (6), Courses Urbaines (6)                  |
| Mode            |             0   |           5 | `A{5}` 74% | `A{6}` 9% | `A{8}` 8% | `A{4}` 5%                            | Route (49), Aérien (6), Maritime (5)                                      |
| Catégorie       |            10.6 |          24 | `A{10} 9,9 A` 14% | `∅` 11% | `A{7} 99A` 11% | `AAA 9.9A` 9%              | Utilitaire 3,5 t (9), VUL 3.5T (6), Tracteur + semi (4)                   |
| Carburant       |            19.7 |           5 | `A{6}` 52% | `∅` 20% | `A{10}` 17% | `AAA` 6%                             | Gazole (34), Électrique (11), Fioul lourd (4)                             |
| Fin de contrat  |             0   |          62 | `9{4}-99-99 99:99:99` 100%                                                | 2027-09-09 00:00:00 (2), 2027-07-21 00:00:00 (2), 2028-02-13 00:00:00 (2) |

## Table `sites` (129 lignes, 7 colonnes)

| colonne   |   manquants_pct |   distincts | formes                                                               | valeurs_frequentes                                                |
|:----------|----------------:|------------:|:---------------------------------------------------------------------|:------------------------------------------------------------------|
| site_code |             0   |         129 | `AA-99` 73% | `AAA-AAA` 15% | `AA-AAA9` 11% | `AA-9A` 2%             | ENT-CDG (1), ENT-LEH (1), ENT-FOS (1)                             |
| libelle   |             0   |         129 | `A{6} A{6}` 13% | `A{6} A{5}` 11% | `A{6} A{7}` 10% | `A{6} A{8}` 9% | Roissy CDG fret (1), Port du Havre (1), Port de Marseille-Fos (1) |
| type_site |             0   |           5 | `A{6}` 80% | `A{8}_A{6}` 11% | `AAA` 9%                              | AGENCE (96), ENTREPOT_CLIENT (14), TRI (11)                       |
| ville     |             0   |         115 | `A{6}` 19% | `A{5}` 16% | `A{7}` 13% | `A{8}` 10%                    | Strasbourg (3), Le Havre (2), Lesquin (2)                         |
| pays      |             0   |           2 | `AA` 100%                                                            | FR (128), NL (1)                                                  |
| lat       |            10.9 |         104 | `99,9{6}` 89% | `∅` 11%                                              | 48,583920 (3), 49,493460 (2), 50,582320 (2)                       |
| lon       |            10.9 |         104 | `9,9{6}` 78% | `-9,9{6}` 12% | `∅` 11%                               | 7,745530 (3), 0,107850 (2), 3,119000 (2)                          |

## Table `sites_alias` (8 lignes, 2 colonnes)

| colonne     |   manquants_pct |   distincts | formes                                       | valeurs_frequentes                    |
|:------------|----------------:|------------:|:---------------------------------------------|:--------------------------------------|
| ancien_code |               0 |           8 | `AAA99` 50% | `AAA-AAA` 25% | `AAA-A{4}` 25% | GON01 (1), ORL-HUB (1), LYS02 (1)     |
| site_code   |               0 |           8 | `AAA-AAA` 100%                               | TRI-IDF (1), TRI-NAT (1), TRI-LYS (1) |
