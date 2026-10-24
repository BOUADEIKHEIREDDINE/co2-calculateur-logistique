import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from commun import (graphique, pct, COULEURS_MODE, COULEURS_SERVICE, SERVICES, colis, masse, nombre, pipeline_pret, style,
                    tuile)

st.title("Mon bilan carbone")
if not pipeline_pret():
    st.stop()

tout = colis()
clients = sorted(tout.client.unique())
c1, c2 = st.columns([1, 2])
with c1:
    client = st.selectbox("Compte client", clients, index=clients.index("AMAZON"),
                          format_func=lambda c: c.title())
with c2:
    mois = sorted(tout.date_commande.dt.to_period("M").unique())
    debut, fin = st.select_slider("Période", options=mois, value=(mois[0], mois[-1]),
                                  format_func=lambda p: p.strftime("%m/%Y"))
df = tout[(tout.client == client) & tout.date_commande.dt.to_period("M").between(debut, fin)]
if df.empty:
    st.warning("Aucun colis sur cette période.")
    st.stop()
reseau = tout[tout.date_commande.dt.to_period("M").between(debut, fin)]

k1, k2, k3, k4 = st.columns(4)
with k1:
    tuile("Colis expédiés", nombre(len(df)))
with k2:
    tuile("Émissions", masse(df.emission_estimee_g.sum()) + " CO₂e")
with k3:
    moy, moy_r = df.emission_estimee_g.mean(), reseau.emission_estimee_g.mean()
    tuile("Par colis, en moyenne", masse(moy),
          f"{'au-dessus' if moy > moy_r else 'en dessous'} de la moyenne du réseau ({masse(moy_r)})")
with k4:
    tuile("Trajets entièrement scannés", pct((df.taux_observation == 1).mean()),
          "le reste est complété par déduction")

st.write("")
g, d = st.columns([1.4, 1])
with g:
    m = df.groupby(df.date_commande.dt.to_period("M").dt.to_timestamp()).agg(
        colis=("tracking_id", "size"), kg=("emission_estimee_g", lambda s: s.sum() / 1000))
    fig = go.Figure(go.Bar(x=m.index, y=m.kg, marker=dict(color="#2a78d6", line=dict(color="#fcfcfb", width=2)),
                           customdata=m.colis, hovertemplate="%{x|%B %Y}<br>%{y:.1f} kg CO₂e<br>"
                                                             "%{customdata} colis<extra></extra>"))
    fig.update_layout(title="Émissions par mois (kg CO₂e)")
    fig.update_xaxes(dtick="M1", tickformat="%m/%y")
    graphique(fig, 320)
with d:
    cols = {"Avion": "emission_avion_g", "Camion": "emission_camion_g", "Camionnette": "emission_camionnette_g",
            "Bateau": "emission_bateau_g", "Train": "emission_train_g", "Vélo": "emission_velo_g"}
    parts = {k: df[v].sum() for k, v in cols.items() if v in df and df[v].sum() > 0}
    tot = sum(parts.values())
    ordre = sorted(parts, key=parts.get)
    fig = go.Figure(go.Bar(y=ordre, x=[100 * parts[k] / tot for k in ordre], orientation="h",
                           marker=dict(color=[COULEURS_MODE[k] for k in ordre], line=dict(color="#fcfcfb", width=2)),
                           text=[pct(parts[k] / tot, 1) for k in ordre], textposition="outside",
                           hovertemplate="%{y} : %{x:.1f} %<extra></extra>"))
    fig.update_layout(title="D'où viennent vos émissions")
    fig.update_xaxes(ticksuffix=" %", range=[0, 112])
    graphique(fig, 320)

s = df.groupby("service").agg(colis=("tracking_id", "size"), total=("emission_estimee_g", "sum"),
                              moyenne=("emission_estimee_g", "mean"), poids=("poids_kg", "mean"))
s.index = s.index.map(SERVICES)
st.subheader("Par service")
t = pd.DataFrame({"Service": s.index, "Colis": [nombre(x) for x in s.colis], "Émissions": [masse(x) for x in s.total],
                  "Par colis": [masse(x) for x in s.moyenne], "Poids moyen": [f"{nombre(x, 2)} kg" for x in s.poids],
                  "Part des émissions": [pct(x / s.total.sum()) for x in s.total]})
st.dataframe(t, hide_index=True, use_container_width=True)

# --- leviers -------------------------------------------------------------------------------------
st.subheader("Leviers de réduction")
st.caption("Simulation sur vos envois de la période : chaque levier applique l'émission moyenne par kilo "
           "observée sur le réseau pour l'option de remplacement.")
par_kg = reseau.groupby("service").apply(lambda x: x.emission_estimee_g.sum() / x.poids_kg.sum(),
                                         include_groups=False)
intl = reseau[reseau.pays_origine.isin(["CN", "HK", "KR", "US", "CA", "MA", "TR"])]
air_kg = intl[intl.emission_avion_g > 0]
mer_kg = intl[intl.emission_bateau_g > 0]
f_air = air_kg.emission_estimee_g.sum() / air_kg.poids_kg.sum() if len(air_kg) else 0
f_mer = mer_kg.emission_estimee_g.sum() / mer_kg.poids_kg.sum() if len(mer_kg) else 0

l1, l2, l3 = st.columns(3)
with l1:
    x1 = st.slider("Envois standard basculés en écologique", 0, 100, 30, 5, format="%d %%")
with l2:
    x2 = st.slider("Colis aériens transportés par bateau", 0, 100, 20, 5, format="%d %%",
                   disabled=df.emission_avion_g.sum() == 0)
with l3:
    x3 = st.slider("Express remplacés par standard", 0, 100, 30, 5, format="%d %%")
std = df[(df.service == "standard") & (df.pays_origine == "FR")]
gain1 = x1 / 100 * (std.emission_estimee_g.sum() - std.poids_kg.sum() * par_kg.get("ecologique", 0))
av = df[df.emission_avion_g > 0]
gain2 = x2 / 100 * (av.emission_estimee_g.sum() - av.poids_kg.sum() * f_mer) if len(av) else 0
exp = df[(df.service == "express") & (df.pays_origine == "FR")]
gain3 = x3 / 100 * (exp.emission_estimee_g.sum() - exp.poids_kg.sum() * par_kg.get("standard", 0))
gains = {"Écologique": max(gain1, 0), "Bateau": max(gain2, 0), "Standard": gain3}
total = df.emission_estimee_g.sum()
g1, g2, g3, g4 = st.columns(4)
with g1:
    tuile("Gain : écologique", masse(gains["Écologique"]), f"{pct(gains['Écologique'] / total, 1)} du total")
with g2:
    tuile("Gain : bateau", masse(gains["Bateau"]), f"{pct(gains['Bateau'] / total, 1)} du total")
with g3:
    tuile("Gain : express vers standard", masse(gains["Standard"]) if gains["Standard"] >= 0
          else "−" + masse(-gains["Standard"]), f"{pct(gains['Standard'] / total, 1)} du total")
with g4:
    somme = sum(gains.values())
    tuile("Total des leviers", masse(somme), f"{pct(somme / total, 1)} de vos émissions")
if gain3 <= 0 < x3:
    st.caption("Sur le territoire, l'express n'émet pas plus que le standard : ses camions roulent en ligne "
               "directe, sans détour par le hub national. Le vrai levier est l'écologique (train, véhicules "
               "électriques, vélos cargo).")
if len(av):
    st.caption(f"Un kilo venu d'Asie par avion émet en moyenne {masse(f_air)} CO₂e, contre {masse(f_mer)} "
               "par bateau : c'est de loin le levier le plus puissant, au prix d'un délai de plusieurs semaines.")

# --- export --------------------------------------------------------------------------------------
st.subheader("Télécharger")
tampon = io.BytesIO()
with pd.ExcelWriter(tampon) as w:
    t.to_excel(w, sheet_name="Par service", index=False)
    m.rename(columns={"colis": "Colis", "kg": "kg CO2e"}).to_excel(w, sheet_name="Par mois")
    df[["tracking_id", "date_commande", "service", "livraison", "pays_origine", "ville_origine",
        "ville_destination", "poids_kg", "distance_estimee_km", "mode_transport", "emission_estimee_g",
        "methode_emission"]].to_excel(w, sheet_name="Détail des colis", index=False)
st.download_button("Bilan Excel de la période", tampon.getvalue(),
                   file_name=f"bilan_co2_{client.lower().replace(' ', '_')}_{debut}_{fin}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
