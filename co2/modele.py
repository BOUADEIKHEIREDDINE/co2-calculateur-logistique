"""Apprentissage supervisé là où les données manquent.

Trois modèles, chacun comparé à une règle simple sur un jeu de test :

1. ModeInternational : air, mer ou route pour un colis venu de l'étranger dont la
   porte d'entrée n'a pas été flashée (le délai entre commande et premier scan
   en France trahit le mode) ;
2. ClassifieurVehicule : véhicule d'une étape dont le transporteur est inconnu
   (distance, durée, vitesse, type d'étape, service...) ;
3. RegresseurEmission : émission d'un colis à partir des seules informations de
   commande, avec un intervalle à 80 %. C'est le moteur du calculateur client,
   utilisable avant même l'expédition.
"""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from . import config as C
from .geo import haversine_km

PORTES = {"ENT-CDG": "air", "ENT-LEH": "mer", "ENT-RTM": "mer", "ENT-FOS": "mer", "ENT-STR": "route",
          "ENT-LIL": "route", "ENT-PPG": "route"}


def _categories(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        out[c] = out[c].astype("category")
    return out


class ModeInternational:
    CAT = ["pays_origine", "service", "client"]
    NUM = ["poids_kg", "delai_h"]

    def __init__(self):
        self.modele = HistGradientBoostingClassifier(max_iter=200, categorical_features="from_dtype",
                                                     random_state=C.SEED)
        self.metriques: dict = {}

    @staticmethod
    def delais(colis: pd.DataFrame, scans: pd.DataFrame) -> pd.Series:
        fr = scans[scans.rang >= 2].sort_values("horodatage_utc").drop_duplicates("tracking_id")
        premier = colis.tracking_id.map(fr.set_index("tracking_id").horodatage_utc).dt.tz_convert(None)
        return (premier - colis.date_commande).dt.total_seconds() / 3600

    def ajuster(self, colis: pd.DataFrame, scans: pd.DataFrame) -> "ModeInternational":
        ent = scans[scans.evenement == "ENTREE_PLATEFORME"].drop_duplicates("tracking_id")
        df = colis[~colis.pays_origine.isin(["FR", "ES", "IT", "DE", "PL", "BE", "NL"])].copy()
        df["delai_h"] = self.delais(df, scans)
        df["y"] = df.tracking_id.map(ent.set_index("tracking_id").site_code).map(PORTES)
        df = df[df.y.notna()]
        X = _categories(df[self.CAT + self.NUM], self.CAT)
        Xa, Xt, ya, yt = train_test_split(X, df.y, test_size=0.25, random_state=C.SEED, stratify=df.y)
        self.modele.fit(Xa, ya)
        regle = Xt.pays_origine.astype(str).map(df.groupby("pays_origine").y.agg(lambda s: s.mode()[0]))
        self.metriques = {"n_apprentissage": len(Xa), "n_test": len(Xt),
                          "precision_modele": accuracy_score(yt, self.modele.predict(Xt)),
                          "precision_regle_pays": accuracy_score(yt, regle)}
        self.modele.fit(X, df.y)
        self._cats = {c: X[c].cat.categories for c in self.CAT}
        return self

    def __call__(self, c, delai_h: float) -> str:
        ligne = pd.DataFrame([{**{k: getattr(c, k) for k in self.CAT + ["poids_kg"]}, "delai_h": delai_h}])
        for k in self.CAT:
            ligne[k] = pd.Categorical(ligne[k], categories=self._cats[k])
        return str(self.modele.predict(ligne[self.CAT + self.NUM])[0])


class ClassifieurVehicule:
    CAT = ["type_etape", "service", "livraison", "client", "zone_origine"]
    NUM = ["distance_km", "duree_h", "vitesse_kmh", "poids_kg", "population_dest", "mois"]
    TYPES = ["COLLECTE", "ENLEVEMENT", "POST_ENTREE", "LIGNE", "CAPILLAIRE", "CAPILLAIRE_ORIGINE",
             "DERNIER_KM", "INTERNATIONAL"]

    def __init__(self):
        self.modele = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08,
                                                     categorical_features="from_dtype", random_state=C.SEED)
        self.metriques: dict = {}

    @classmethod
    def preparer(cls, et: pd.DataFrame) -> pd.DataFrame:
        X = et[[c for c in cls.CAT + cls.NUM if c in et]].copy()
        return _categories(X, cls.CAT)

    def ajuster(self, et: pd.DataFrame) -> "ClassifieurVehicule":
        connu = et[et.type_etape.isin(self.TYPES) & et.vehicule_observe.notna()
                   & ~et.vehicule_observe.isin(["AIR", "MER"])]
        X, y = self.preparer(connu), connu.vehicule_observe
        Xa, Xt, ya, yt = train_test_split(X, y, test_size=0.2, random_state=C.SEED)
        self.modele.fit(Xa, ya)
        freq = connu.loc[Xa.index].groupby(["type_etape", "service"]).vehicule_observe.agg(lambda s: s.mode()[0])
        regle = [freq.get((a, b)) for a, b in zip(connu.loc[Xt.index, "type_etape"], connu.loc[Xt.index, "service"])]
        self.metriques = {"n_apprentissage": len(Xa), "n_test": len(Xt),
                          "precision_modele": accuracy_score(yt, self.modele.predict(Xt)),
                          "precision_regle_frequence": accuracy_score(yt, pd.Series(regle).fillna("?"))}
        self.modele.fit(X, y)
        self.regle = connu.groupby(["type_etape", "service"]).vehicule_observe.agg(lambda s: s.mode()[0])
        return self

    def predire(self, et: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """Classe la plus probable, sa probabilité, et toutes les probabilités (une colonne par véhicule)."""
        X = self.preparer(et)
        proba = self.modele.predict_proba(X)
        return (self.modele.classes_[proba.argmax(1)], proba.max(1),
                pd.DataFrame(proba, columns=self.modele.classes_, index=et.index))


class RegresseurEmission:
    """Émission d'un colis (g CO2e) à partir de la commande seule."""
    CAT = ["client", "categorie", "service", "livraison", "pays_origine"]
    NUM = ["poids_kg", "volume_m3", "lat_orig", "lon_orig", "lat_dest", "lon_dest", "distance_directe_km",
           "depuis_entrepot", "mois"]

    def __init__(self):
        kw = dict(max_iter=500, learning_rate=0.06, max_leaf_nodes=48, categorical_features="from_dtype",
                  random_state=C.SEED)
        self.median = HistGradientBoostingRegressor(loss="absolute_error", **kw)
        self.bas = HistGradientBoostingRegressor(loss="quantile", quantile=0.1, **kw)
        self.haut = HistGradientBoostingRegressor(loss="quantile", quantile=0.9, **kw)
        self.metriques: dict = {}

    @classmethod
    def preparer(cls, colis: pd.DataFrame) -> pd.DataFrame:
        X = colis.copy()
        X["distance_directe_km"] = haversine_km(X.lat_orig, X.lon_orig, X.lat_dest, X.lon_dest)
        X["depuis_entrepot"] = X.site_expedition.notna().astype(int) if "site_expedition" in X else 0
        X["mois"] = pd.to_datetime(X.date_commande).dt.month if "date_commande" in X else 6
        X = X[cls.CAT + cls.NUM]
        return _categories(X, cls.CAT)

    def ajuster(self, colis: pd.DataFrame, cible: str = "emission_estimee_g") -> "RegresseurEmission":
        """Apprentissage (60 %), calibration conformale de l'intervalle (20 %), test (20 %)."""
        X, y = self.preparer(colis), np.log1p(colis[cible])
        Xa, Xr, ya, yr = train_test_split(X, y, test_size=0.4, random_state=C.SEED)
        Xc, Xt, yc, yt = train_test_split(Xr, yr, test_size=0.5, random_state=C.SEED)
        for m in (self.median, self.bas, self.haut):
            m.fit(Xa, ya)
        # régression quantile conformalisée : on élargit l'intervalle de la marge qui garantit
        # 80 % de couverture sur le jeu de calibration
        score = np.maximum(self.bas.predict(Xc) - yc, yc - self.haut.predict(Xc))
        self.marge = float(np.quantile(score, 0.8 * (1 + 1 / len(yc))))
        p = np.expm1(self.median.predict(Xt))
        lo = np.expm1(self.bas.predict(Xt) - self.marge)
        hi = np.expm1(self.haut.predict(Xt) + self.marge)
        vrai = np.expm1(yt)
        # référence naïve : facteur moyen observé x poids x distance directe
        fac = (colis.loc[Xa.index, cible] / (Xa.poids_kg * Xa.distance_directe_km.clip(lower=5))).median()
        naif = fac * Xt.poids_kg * Xt.distance_directe_km.clip(lower=5)
        self.metriques = {
            "n_apprentissage": len(Xa), "n_test": len(Xt),
            "r2_log": r2_score(yt, np.log1p(p)),
            "erreur_absolue_mediane_pct": float(np.median(np.abs(p - vrai) / vrai) * 100),
            "erreur_absolue_mediane_pct_naif": float(np.median(np.abs(naif - vrai) / vrai) * 100),
            "mae_g": mean_absolute_error(vrai, p),
            "couverture_intervalle_80": float(((vrai >= lo) & (vrai <= hi)).mean()),
            "marge_conformale_log": self.marge,
        }
        self.test_index = Xt.index
        self._cats = {c: X[c].cat.categories for c in self.CAT}
        return self

    def predire(self, colis: pd.DataFrame) -> pd.DataFrame:
        X = self.preparer(colis)
        for c in self.CAT:
            X[c] = pd.Categorical(X[c].astype(str), categories=self._cats[c])
        out = pd.DataFrame({"median": np.expm1(self.median.predict(X)),
                            "bas": np.expm1(self.bas.predict(X) - self.marge),
                            "haut": np.expm1(self.haut.predict(X) + self.marge)}, index=colis.index)
        out["bas"] = np.minimum(out.bas, out["median"])
        out["haut"] = np.maximum(out.haut, out["median"])
        return out

    def sauver(self) -> None:
        C.MODELS.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, C.MODELS / "regresseur_emission.joblib")
        (C.MODELS / "regresseur_emission_metriques.json").write_text(json.dumps(self.metriques, indent=2))

    @staticmethod
    def charger() -> "RegresseurEmission":
        return joblib.load(C.MODELS / "regresseur_emission.joblib")
