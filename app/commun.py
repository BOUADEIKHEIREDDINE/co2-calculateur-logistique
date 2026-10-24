"""Données, couleurs et petits composants partagés par les pages de l'interface."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from co2 import config as C  # noqa: E402

# Une couleur fixe par entité (palette validée, ordre des emplacements respecté)
COULEURS_MODE = {"Camion": "#2a78d6", "Avion": "#eb6834", "Camionnette": "#1baf7a", "Bateau": "#eda100",
                 "Train": "#e87ba4", "Vélo": "#008300"}
COULEURS_SERVICE = {"Standard": "#2a78d6", "Express 24 h": "#eb6834", "Écologique": "#1baf7a",
                    "International": "#eda100"}
ENCRE, ENCRE_2, ENCRE_3, GRILLE, FOND = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb"
SERVICES = {"standard": "Standard", "express": "Express 24 h", "ecologique": "Écologique",
            "international": "International"}


def nombre(x: float, decimales: int = 0) -> str:
    s = f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")
    return s


def pct(x: float, decimales: int = 0) -> str:
    """Part (0-1) au format français : 12 %, 84,3 %."""
    return f"{nombre(100 * x, decimales)}\u202f%"


def masse(g: float) -> str:
    """Affiche une masse de CO2e dans l'unité la plus lisible."""
    if g >= 1e6:
        return f"{nombre(g / 1e6, 1)} t"
    if g >= 1000:
        return f"{nombre(g / 1000, 2 if g < 10_000 else 1)} kg"
    return f"{nombre(g, 0 if g >= 10 else 1)} g"


CONFIG = {"displayModeBar": False, "locale": "fr"}


def graphique(fig: go.Figure, hauteur: int = 360) -> None:
    st.plotly_chart(style(fig, hauteur), use_container_width=True, config=CONFIG)


def style(fig: go.Figure, hauteur: int = 360) -> go.Figure:
    fig.update_layout(height=hauteur, margin=dict(l=8, r=8, t=36, b=8), paper_bgcolor=FOND, plot_bgcolor=FOND,
                      font=dict(family="sans-serif", size=13, color=ENCRE_2), title_font=dict(color=ENCRE, size=15),
                      hoverlabel=dict(bgcolor="white", font_color=ENCRE, bordercolor=GRILLE),
                      legend=dict(orientation="h", y=-0.15, x=0, font=dict(color=ENCRE_2)),
                      separators=", ")
    fig.update_xaxes(gridcolor=GRILLE, zeroline=False, linecolor=GRILLE, tickfont=dict(color=ENCRE_3))
    fig.update_yaxes(gridcolor=GRILLE, zeroline=False, linecolor=GRILLE, tickfont=dict(color=ENCRE_3))
    return fig


def tuile(titre: str, valeur: str, aide: str = "") -> None:
    st.markdown(
        f"""<div style="border:1px solid {GRILLE};border-radius:10px;padding:14px 16px;background:white;height:100%">
        <div style="color:{ENCRE_2};font-size:0.85rem">{titre}</div>
        <div style="color:{ENCRE};font-size:1.7rem;font-weight:650;line-height:1.3">{valeur}</div>
        <div style="color:{ENCRE_3};font-size:0.8rem">{aide}</div></div>""", unsafe_allow_html=True)


@st.cache_data(show_spinner="Chargement des données...")
def colis() -> pd.DataFrame:
    return pd.read_parquet(C.CURATED / "colis_co2.parquet")


@st.cache_data
def etapes() -> pd.DataFrame:
    return pd.read_parquet(C.CURATED / "etapes_co2.parquet")


@st.cache_data
def resume() -> dict:
    return json.loads((C.REPORTS / "resume_pipeline.json").read_text(encoding="utf-8"))


@st.cache_data
def regles() -> pd.DataFrame:
    return pd.read_csv(C.REPORTS / "06_regles_validation.csv")


@st.cache_data
def journal() -> pd.DataFrame:
    return pd.read_csv(C.REPORTS / "journal_traitements.csv")


@st.cache_resource(show_spinner="Préparation du calculateur...")
def calculateur():
    from co2.calculateur import Calculateur
    return Calculateur()


def pipeline_pret() -> bool:
    if not (C.CURATED / "colis_co2.parquet").exists():
        st.error("Les données ne sont pas encore calculées. Lancez d'abord `python run_pipeline.py`.")
        return False
    return True
