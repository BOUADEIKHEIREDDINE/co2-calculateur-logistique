"""Figures d'analyse (notebook, rapport, présentation), même palette que l'interface."""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import config as C  # noqa: E402

BLEU, ORANGE, AQUA, JAUNE, MAGENTA, VERT = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"
ENCRE, ENCRE_2, ENCRE_3, GRILLE, FOND = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb"
MODES = {"Avion": ORANGE, "Camion": BLEU, "Camionnette": AQUA, "Bateau": JAUNE, "Train": MAGENTA, "Vélo": VERT}
SERVICES = {"standard": ("Standard", BLEU), "express": ("Express", ORANGE), "ecologique": ("Écologique", AQUA),
            "international": ("International", JAUNE)}

plt.rcParams.update({
    "figure.facecolor": FOND, "axes.facecolor": FOND, "savefig.facecolor": FOND, "font.size": 11,
    "axes.edgecolor": GRILLE, "axes.labelcolor": ENCRE_2, "xtick.color": ENCRE_3, "ytick.color": ENCRE_3,
    "axes.titlecolor": ENCRE, "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRILLE,
    "grid.linewidth": 0.8, "axes.axisbelow": True, "legend.frameon": False, "font.family": "DejaVu Sans",
    "axes.formatter.use_locale": False,
})


def _fr(x, dec=0):
    return f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")


def _sauver(fig, nom):
    C.FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(C.FIGURES / f"{nom}.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def colis_vs_emissions(colis: pd.DataFrame):
    avion = colis.emission_avion_g > 0
    lignes = {"Colis": [avion.mean(), 1 - avion.mean()],
              "Émissions": [colis.emission_avion_g.sum() / colis.emission_estimee_g.sum(),
                            1 - colis.emission_avion_g.sum() / colis.emission_estimee_g.sum()]}
    fig, ax = plt.subplots(figsize=(8, 2.6))
    for i, (nom, (a, b)) in enumerate(lignes.items()):
        ax.barh(i, a, color=ORANGE, height=0.55, edgecolor=FOND, linewidth=2)
        ax.barh(i, b, left=a, color=BLEU, height=0.55, edgecolor=FOND, linewidth=2)
        ax.text(a / 2, i, f"{_fr(100 * a)} %", ha="center", va="center", color="white", fontweight="bold")
        ax.text(a + b / 2, i, f"{_fr(100 * b)} %", ha="center", va="center", color="white", fontweight="bold")
    ax.set_yticks([0, 1], list(lignes))
    ax.set_xlim(0, 1)
    ax.xaxis.set_visible(False)
    ax.grid(False)
    ax.invert_yaxis()
    ax.set_title("Colis passés par l'avion (orange) et tous les autres (bleu)")
    _sauver(fig, "01_colis_vs_emissions_avion")


def distribution_par_service(colis: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 4))
    bins = np.logspace(0, 5, 70)
    for s, (lib, coul) in SERVICES.items():
        v = colis.loc[colis.service == s, "emission_estimee_g"]
        ax.hist(v, bins=bins, histtype="step", linewidth=2, color=coul, label=f"{lib} (médiane {_fr(v.median())} g)")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fr(x)))
    ax.set_xlabel("g CO₂e par colis (échelle logarithmique)")
    ax.set_ylabel("Nombre de colis")
    ax.set_title("Émission par colis selon le service")
    ax.legend(loc="upper right")
    _sauver(fig, "02_distribution_par_service")


def mensuel(colis: pd.DataFrame):
    m = colis.groupby(colis.date_commande.dt.to_period("M")).agg(n=("tracking_id", "size"),
                                                                    t=("emission_estimee_g", "sum"))
    fig, ax = plt.subplots(figsize=(8, 3.6))
    x = np.arange(len(m))
    ax.bar(x, m.n, color=BLEU, width=0.8, edgecolor=FOND, linewidth=2)
    ax.set_xticks(x, [p.strftime("%m/%y") for p in m.index])
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: _fr(v)))
    pic = int(m.n.values.argmax())
    ax.text(pic + 0.55, m.n.iloc[pic] * 0.93, "Black Friday\net Noël", color=ENCRE_2, va="top")
    ax.set_ylim(0, m.n.max() * 1.08)
    ax.set_title("Colis expédiés par mois")
    _sauver(fig, "03_colis_par_mois")


def erreur_par_observation(evaluation: dict):
    e = pd.DataFrame(evaluation["erreur_par_observation"])
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(e))
    ax.bar(x - 0.2, e.erreur_reconstituee_pct, width=0.38, color=BLEU, label="Trajet reconstitué (règles + scans)",
           edgecolor=FOND, linewidth=2)
    ax.bar(x + 0.2, e.erreur_ml_pct, width=0.38, color=ORANGE, label="Modèle sur la commande seule",
           edgecolor=FOND, linewidth=2)
    for i, (a, b) in enumerate(zip(e.erreur_reconstituee_pct, e.erreur_ml_pct)):
        ax.text(i - 0.2, a + 0.4, f"{_fr(a, 1)} %", ha="center", color=ENCRE_2, fontsize=10)
        ax.text(i + 0.2, b + 0.4, f"{_fr(b, 1)} %", ha="center", color=ENCRE_2, fontsize=10)
    ax.set_xticks(x, [f"{p}\n({_fr(n)} colis)" for p, n in zip(e.part_observee, e.colis)])
    ax.set_xlabel("Part du trajet directement observée")
    ax.set_ylabel("Erreur médiane (%)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: _fr(v)))
    ax.set_title("Erreur face à la vérité terrain")
    ax.set_ylim(0, max(e.erreur_ml_pct.max(), e.erreur_reconstituee_pct.max()) * 1.18)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=2)
    _sauver(fig, "04_erreur_par_observation")


def estime_vs_reel(colis: pd.DataFrame):
    v = pd.read_parquet(C.SOURCES / "_verite_terrain" / "colis.parquet").set_index("tracking")
    d = colis.set_index("tracking_id").join(v.emission_kg).sample(6000, random_state=C.SEED)
    fig, ax = plt.subplots(figsize=(5.2, 5))
    ax.scatter(d.emission_kg * 1000, d.emission_estimee_g, s=8, color=BLEU, alpha=0.35, linewidths=0)
    lim = [0.5, 2e5]
    ax.plot(lim, lim, color=ENCRE_3, linewidth=1, linestyle="--")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    f = mticker.FuncFormatter(lambda x, _: _fr(x))
    ax.xaxis.set_major_formatter(f)
    ax.yaxis.set_major_formatter(f)
    ax.set_xlabel("Émission réelle (g CO₂e)")
    ax.set_ylabel("Émission estimée par le pipeline")
    ax.set_title("Estimé contre réel (6 000 colis)")
    _sauver(fig, "05_estime_vs_reel")


def g_par_kg(colis: pd.DataFrame):
    fr = colis[colis.pays_origine == "FR"]
    s = fr.groupby("service").apply(lambda d: d.emission_estimee_g.sum() / d.poids_kg.sum(), include_groups=False)
    intl = colis[colis.emission_avion_g > 0]
    mer = colis[colis.emission_bateau_g > 0]
    valeurs = {"Écologique": s["ecologique"], "Express": s["express"], "Standard": s["standard"],
               "International\npar bateau": mer.emission_estimee_g.sum() / mer.poids_kg.sum(),
               "International\npar avion": intl.emission_estimee_g.sum() / intl.poids_kg.sum()}
    couleurs = [AQUA, ORANGE, BLEU, JAUNE, JAUNE]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    y = np.arange(len(valeurs))
    ax.barh(y, list(valeurs.values()), color=couleurs, height=0.6, edgecolor=FOND, linewidth=2)
    for i, v in enumerate(valeurs.values()):
        ax.text(v * 1.08, i, f"{_fr(v)} g", va="center", color=ENCRE_2)
    ax.set_yticks(y, list(valeurs))
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fr(x)))
    ax.set_xlim(right=max(valeurs.values()) * 4)
    ax.set_xlabel("g CO₂e par kilo expédié (échelle logarithmique)")
    ax.set_title("Ce que coûte un kilo selon l'option")
    _sauver(fig, "06_g_par_kg")


def defauts(evaluation: dict):
    d = pd.DataFrame(evaluation["defauts"]).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    y = np.arange(len(d))
    ax.barh(y + 0.2, d.injectes, height=0.38, color=BLEU, label="présents dans les sources", edgecolor=FOND)
    ax.barh(y - 0.2, d.traites, height=0.38, color=AQUA, label="traités par le pipeline", edgecolor=FOND)
    ax.set_yticks(y, d.defaut.str.replace(r" \(.*\)", "", regex=True))
    ax.set_xscale("symlog", linthresh=10)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fr(x)))
    ax.set_title("Défauts injectés et défauts traités")
    ax.legend(loc="upper center", bbox_to_anchor=(0.4, -0.08), ncol=2)
    _sauver(fig, "07_defauts")


def generer(colis: pd.DataFrame | None = None) -> None:
    if colis is None:
        colis = pd.read_parquet(C.CURATED / "colis_co2.parquet")
    resume = json.loads((C.REPORTS / "resume_pipeline.json").read_text(encoding="utf-8"))
    colis_vs_emissions(colis)
    distribution_par_service(colis)
    mensuel(colis)
    g_par_kg(colis)
    if resume.get("evaluation"):
        erreur_par_observation(resume["evaluation"])
        estime_vs_reel(colis)
        defauts(resume["evaluation"])
