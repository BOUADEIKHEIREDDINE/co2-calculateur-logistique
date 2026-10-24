import plotly.graph_objects as go
import streamlit as st

from commun import COULEURS_MODE, colis, graphique, pct, masse, nombre, pipeline_pret, resume, style, tuile

st.title("Le CO₂ de vos colis, colis par colis")
st.markdown(
    "Chaque colis confié à FastColis passe par plusieurs camions, plateformes et parfois un avion ou un bateau. "
    "Cet outil calcule l'empreinte carbone de ce trajet, étape par étape, à partir de nos scans et des "
    "facteurs d'émission officiels de l'ADEME. Il vous permet de **mesurer** vos envois passés et "
    "d'**estimer** ceux à venir.")

if pipeline_pret():
    df, r = colis(), resume()
    erreur = (r.get("evaluation") or {}).get("emission_reconstituee", {}).get("erreur_mediane_pct")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        tuile("Colis analysés", nombre(len(df)), "octobre 2025 à septembre 2026")
    with c2:
        tuile("Émissions totales", masse(df.emission_estimee_g.sum()), "CO₂ équivalent, tous clients")
    with c3:
        tuile("Colis médian", masse(df.emission_estimee_g.median()), "la moitié des colis émet moins")
    with c4:
        tuile("Précision du calcul", f"± {nombre(erreur, 1)} %" if erreur else "n.d.",
              "écart médian avec la valeur réelle")

    st.write("")
    gauche, droite = st.columns([1.1, 1])
    with gauche:
        st.subheader("Ce qui pèse vraiment")
        parts = {m: df[c].sum() for m, c in [("Avion", "emission_avion_g"), ("Camion", "emission_camion_g"),
                                             ("Camionnette", "emission_camionnette_g"),
                                             ("Bateau", "emission_bateau_g"), ("Train", "emission_train_g"),
                                             ("Vélo", "emission_velo_g")] if c in df}
        total = sum(parts.values())
        ordre = sorted(parts, key=parts.get)
        fig = go.Figure(go.Bar(
            y=ordre, x=[100 * parts[m] / total for m in ordre], orientation="h",
            marker=dict(color=[COULEURS_MODE[m] for m in ordre], line=dict(color="#fcfcfb", width=2)),
            text=[pct(parts[m] / total, 1) for m in ordre], textposition="outside",
            hovertemplate="%{y} : %{x:.1f} % des émissions<extra></extra>"))
        fig.update_layout(title="Part de chaque mode de transport dans les émissions", xaxis_title=None)
        fig.update_xaxes(ticksuffix=" %", range=[0, 105])
        graphique(fig, 300)
        avion = df.emission_avion_g.gt(0).mean()
        st.caption(f"Les colis qui prennent l'avion ne représentent que {pct(avion)} des envois, "
                   f"mais {pct(parts['Avion'] / total)} des émissions.")
    with droite:
        st.subheader("Par où commencer")
        st.markdown(
            "1. **Calculer un envoi** : saisissez un départ, une arrivée et un poids. Vous obtenez "
            "l'empreinte, le détail du trajet et la comparaison des options de livraison.\n"
            "2. **Mon bilan carbone** : choisissez votre compte pour voir vos émissions mois par mois, "
            "ce qui les explique, et l'effet de quelques leviers simples. Le bilan se télécharge en Excel.\n"
            "3. **Comment c'est calculé** : la méthode, en clair, et les sources officielles.\n"
            "4. **Fiabilité des données** : les contrôles appliqués et ce qu'ils ont corrigé.")
        st.info("Les chiffres sont exprimés en CO₂ équivalent (CO₂e) : ils incluent les autres gaz à effet "
                "de serre, convertis en CO₂ selon leur pouvoir de réchauffement.", icon=":material/info:")
