# Guide d'utilisation de l'interface

Ce guide s'adresse aux clients de FastColis et à leurs équipes RSE. Aucune connaissance technique n'est nécessaire.

## Ouvrir l'outil

L'équipe FastColis lance l'outil avec `python run_app.py`, puis il s'ouvre dans un navigateur à l'adresse http://localhost:8501. Le menu à gauche donne accès aux cinq pages.

## Calculer l'empreinte d'un envoi

1. Choisissez d'où part le colis : une ville en France, un de vos entrepôts, ou une ville à l'étranger.
2. Choisissez la ville d'arrivée (vous pouvez taper les premières lettres).
3. Indiquez le poids, le service (standard, express 24 h, écologique) et le mode de livraison (domicile ou point relais).
4. Cliquez sur **Calculer**.

Vous obtenez :

* **l'empreinte du colis** en grammes ou kilos de CO₂ équivalent, avec une fourchette quand le véhicule utilisé le jour J peut varier ;
* **une équivalence** en kilomètres parcourus seul en voiture ;
* **la carte du trajet** et **le détail étape par étape**, pour voir où se concentrent les émissions ;
* **la comparaison des autres options** et l'option la plus sobre.

Exemple : un colis de 1 kg de Shenzhen à Rennes émet environ 9,8 kg de CO₂e par avion, contre 150 g par bateau.

## Consulter votre bilan

Page **Mon bilan carbone** :

1. Choisissez votre compte et la période.
2. Lisez les quatre chiffres clés : colis expédiés, émissions, moyenne par colis (comparée au réseau), part des trajets entièrement scannés.
3. Le graphique mensuel montre la saisonnalité ; la répartition par mode montre ce qui pèse.
4. Les **leviers de réduction** se règlent avec les curseurs : basculer une part des envois standard en écologique, transporter une part des colis aériens par bateau, remplacer de l'express par du standard. Le gain s'affiche aussitôt.
5. Le bouton **Bilan Excel de la période** télécharge la synthèse par service, par mois et le détail de chaque colis.

## Comprendre les chiffres

* **CO₂e (CO₂ équivalent)** : tous les gaz à effet de serre convertis en CO₂ selon leur effet sur le climat.
* **Trajet observé / reconstitué** : un trajet est observé quand chaque étape a été scannée et que le véhicule est connu. Sinon, les étapes manquantes sont déduites du fonctionnement du réseau ; l'écart avec la réalité reste de quelques pourcents.
* La page **Comment c'est calculé** détaille la méthode et les facteurs officiels de l'ADEME ; la page **Fiabilité des données** montre les contrôles appliqués.
