import plotly.graph_objects as go
import streamlit as st

from commun import (graphique, pct, COULEURS_MODE, COULEURS_SERVICE, ENCRE_2, calculateur, masse, nombre, pipeline_pret,
                    style)
from co2 import config as C
from co2 import referentiels as R

st.title("Calculer l'empreinte d'un envoi")
st.caption("Pour un colis à venir : le trajet est celui que suivrait le colis dans notre réseau, "
           "avec la flotte réellement utilisée cette année sur chaque étape.")

if not pipeline_pret():
    st.stop()
calc = calculateur()


@st.cache_data
def villes_fr() -> list[str]:
    v = R.villes_france().sort_values("population", ascending=False)
    return v.drop_duplicates("name").name.tolist()


ETRANGER = {**{v: p for v, (p, _) in C.ORIGINES_INTERNATIONALES.items()},
            **{v: p for v, (p, _) in C.ORIGINES_EUROPE.items()}}
NOMS_ETRANGER = {"New York City": "New York", "Warsaw": "Varsovie", "Brussels": "Bruxelles", "Milan": "Milan",
                 "Seoul": "Séoul", "Barcelona": "Barcelone"}
ENTREPOTS = {f"{client.title()} : {ville}": f"WH-{client[:3]}{i}" for client, villes in C.ENTREPOTS.items()
             for i, ville in enumerate(villes, 1)}

type_depart = st.radio("Le colis part", ["d'une ville en France", "d'un entrepôt", "de l'étranger"],
                       horizontal=True)
with st.form("envoi"):
    c1, c2 = st.columns(2)
    ville_fr = entrepot = etranger = None
    with c1:
        st.markdown("**Départ**")
        if type_depart == "d'une ville en France":
            ville_fr = st.selectbox("Ville de départ", villes_fr(), index=villes_fr().index("Lyon"))
        elif type_depart == "d'un entrepôt":
            entrepot = st.selectbox("Entrepôt", list(ENTREPOTS))
        else:
            etranger = st.selectbox("Ville de départ", list(ETRANGER),
                                    format_func=lambda v: f"{NOMS_ETRANGER.get(v, v)} ({ETRANGER[v]})")
    with c2:
        st.markdown("**Arrivée**")
        arrivee = st.selectbox("Ville de destination", villes_fr(), index=villes_fr().index("Rennes"))
        poids = st.number_input("Poids du colis (kg)", min_value=0.05, max_value=70.0, value=1.0, step=0.1)
        service = st.radio("Service", ["standard", "express", "ecologique"], horizontal=True,
                           format_func=lambda s: {"standard": "Standard", "express": "Express 24 h",
                                                  "ecologique": "Écologique"}[s])
        livraison = st.radio("Livraison", ["domicile", "point_relais"], horizontal=True,
                             format_func=lambda s: "À domicile" if s == "domicile" else "En point relais")
    ok = st.form_submit_button("Calculer", type="primary", use_container_width=True)

if ok:
    st.session_state["calcule"] = True
if st.session_state.get("calcule"):
    try:
        dest = calc.localiser(arrivee)
        code_entrepot = None
        if type_depart == "d'une ville en France":
            orig = calc.localiser(ville_fr)
        elif type_depart == "d'un entrepôt":
            code_entrepot = ENTREPOTS[entrepot]
            orig = calc.localiser(entrepot.split(" : ")[1])
        else:
            orig = calc.localiser(etranger, ETRANGER[etranger])
        serv = service if orig["pays"] == "FR" or service == "express" else "international"
        r = calc.estimer(orig, dest, poids, serv, livraison, entrepot=code_entrepot)
        options = calc.comparer(orig, dest, poids, entrepot=code_entrepot)
    except (ValueError, KeyError) as e:
        st.error(f"Calcul impossible : {e}")
        st.stop()

    st.divider()
    a, b = st.columns([1, 1.3])
    with a:
        st.markdown(f"<div style='color:{ENCRE_2}'>Empreinte estimée de ce colis</div>"
                    f"<div style='font-size:3rem;font-weight:700;line-height:1.1'>{masse(r['total_g'])} "
                    f"<span style='font-size:1.3rem;font-weight:500'>CO₂e</span></div>"
                    + (f"<div style='color:{ENCRE_2}'>entre {masse(r['bas_g'])} et {masse(r['haut_g'])} selon "
                       f"les véhicules affectés le jour J</div>" if r["haut_g"] > 1.03 * r["bas_g"] else ""),
                    unsafe_allow_html=True)
        st.write("")
        km = r["km_voiture"]
        st.markdown(f"C'est l'équivalent de **{nombre(km, 1 if km < 10 else 0)} km** parcourus seul dans une "
                    f"voiture moyenne, pour un trajet de **{nombre(r['distance_km'])} km** à travers notre réseau.")
        if orig["pays"] != "FR" and serv != "express":
            st.caption("Hors Europe, ce calcul suppose un transport aérien. Comparez avec le bateau ci-dessous.")
    with b:
        e = r["etapes"]
        fig = go.Figure()
        for _, l in e.iterrows():
            mode = l["mode"].split(" /")[0]
            fig.add_trace(go.Scattergeo(lat=[l.lat_de, l.lat_vers], lon=[l.lon_de, l.lon_vers], mode="lines+markers",
                                        line=dict(width=2.5, color=COULEURS_MODE.get(mode, "#2a78d6")),
                                        marker=dict(size=8, color="white", line=dict(width=2, color=ENCRE_2)),
                                        name=l.etape, hovertemplate=f"{l.etape}<br>{l.de} → {l.vers}<br>"
                                        f"{nombre(l.distance_km)} km : {masse(l.emission_g)}<extra></extra>",
                                        showlegend=False))
        lointain = orig["pays"] not in ("FR", "ES", "IT", "DE", "BE", "NL", "PL")
        fond = dict(showcountries=True, countrycolor="#d8d7d2", showland=True, landcolor="#f1f3ef",
                    showocean=True, oceancolor="#eef4f8", showframe=False, coastlinecolor="#c9c8c2")
        if lointain:
            fig.update_geos(projection_type="natural earth", fitbounds="locations", **fond)
        else:
            lats = list(e.lat_de) + list(e.lat_vers)
            lons = list(e.lon_de) + list(e.lon_vers)
            fig.update_geos(projection_type="mercator", resolution=50,
                            lataxis_range=[min(min(lats) - 1.5, 41.5), max(max(lats) + 1.5, 51.3)],
                            lonaxis_range=[min(min(lons) - 2, -5), max(max(lons) + 2, 9.8)], **fond)
        fig.update_layout(title="Le trajet du colis")
        graphique(fig, 330)

    st.subheader("Étape par étape")
    e = r["etapes"].copy()
    e["part"] = e.emission_g / e.emission_g.sum()
    fig = go.Figure(go.Bar(
        y=e.etape[::-1], x=e.emission_g[::-1], orientation="h",
        marker=dict(color=[COULEURS_MODE.get(m.split(" /")[0], "#2a78d6") for m in e["mode"][::-1]],
                    line=dict(color="#fcfcfb", width=2)),
        text=[f"{masse(g)} ({pct(p)})" for g, p in zip(e.emission_g[::-1], e.part[::-1])], textposition="outside",
        customdata=list(zip(e.de[::-1], e.vers[::-1], e.distance_km[::-1], e["mode"][::-1])),
        hovertemplate="%{customdata[0]} → %{customdata[1]}<br>%{customdata[2]:.0f} km en %{customdata[3]}"
                      "<extra></extra>"))
    fig.update_xaxes(title="g CO₂e", range=[0, e.emission_g.max() * 1.35], tickformat=",d")
    graphique(fig, 60 + 46 * len(e))
    with st.expander("Voir le détail chiffré"):
        t = e[["etape", "de", "vers", "mode", "distance_km", "facteur_kgco2e_tkm", "emission_g"]].rename(columns={
            "etape": "Étape", "de": "De", "vers": "Vers", "mode": "Mode", "distance_km": "Distance (km)",
            "facteur_kgco2e_tkm": "Facteur (kg CO₂e par t.km)", "emission_g": "Émission (g CO₂e)"})
        st.dataframe(t.round(4), hide_index=True, use_container_width=True)
        st.caption(f"Contrôle par apprentissage automatique sur l'historique : {masse(r['modele_g'])}. "
                   "Émission = poids (t) × distance (km) × facteur (kg CO₂e par t.km).")

    st.subheader("Et avec une autre option ?")
    options["libelle"] = options.service + ", " + options.livraison.str.lower()
    o = options.iloc[::-1]
    base = options.emission_g.max()
    fig = go.Figure(go.Bar(
        y=o.libelle, x=o.emission_g, orientation="h",
        marker=dict(color=[COULEURS_SERVICE.get(s.split(" (")[0], "#2a78d6") for s in o.service],
                    line=dict(color="#fcfcfb", width=2)),
        error_x=dict(type="data", symmetric=False, array=o.haut_g - o.emission_g,
                     arrayminus=o.emission_g - o.bas_g, color="#8a8984", thickness=1.2, width=4),
        text=[masse(g) for g in o.emission_g], textposition="outside",
        hovertemplate="%{y} : %{x:.0f} g CO₂e<extra></extra>"))
    fig.update_xaxes(title="g CO₂e (trait fin : fourchette)", range=[0, options.haut_g.max() * 1.15], tickformat=",d")
    graphique(fig, 70 + 40 * len(o))
    meilleure = options.iloc[0]
    if meilleure.emission_g < r["total_g"] * 0.97:
        gain = 1 - meilleure.emission_g / r["total_g"]
        st.success(f"Option la plus sobre : **{meilleure.service.lower()}, {meilleure.livraison.lower()}**, "
                   f"soit {pct(gain)} de CO₂ en moins que votre choix actuel.", icon=":material/eco:")
    else:
        st.success("Votre choix est déjà le plus sobre parmi les options proposées.", icon=":material/eco:")
