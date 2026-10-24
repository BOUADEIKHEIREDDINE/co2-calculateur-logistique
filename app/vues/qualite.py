import pandas as pd
import streamlit as st

from commun import journal, nombre, pipeline_pret, regles, resume

st.title("Fiabilité des données")
st.markdown("Avant tout calcul, les données passent par une série de contrôles et de corrections. "
            "Cette page les rend visibles : rien n'est modifié sans laisser de trace.")
if not pipeline_pret():
    st.stop()

r = resume()
st.subheader("Contrôles de cohérence")
reg = regles()
icone = {"OK": "✅", "ALERTE": "⚠️", "ECHEC": "❌"}
st.dataframe(pd.DataFrame({"": reg.statut.map(icone), "Contrôle": reg.description,
                           "Anomalies": reg.anomalies.map(nombre), "Sur": reg.controles.map(nombre)}),
             hide_index=True, use_container_width=True, height=36 * (len(reg) + 1) + 4)
st.caption("⚠️ : moins de 1 % de lignes concernées, signalées sans bloquer le calcul.")

ev = r.get("evaluation") or {}
if ev.get("defauts"):
    st.subheader("Erreurs de saisie repérées et corrigées")
    d = pd.DataFrame(ev["defauts"])
    st.dataframe(d.rename(columns={"defaut": "Type d'erreur", "injectes": "Présentes dans les sources",
                                   "traites": "Repérées par le pipeline"}), hide_index=True, use_container_width=True)
    st.caption("Les sources de ce prototype sont simulées : on sait donc combien d'erreurs elles contiennent, "
               "et on peut vérifier que le pipeline les retrouve.")

st.subheader("Journal complet des traitements")
j = journal()
st.dataframe(j.rename(columns={"table": "Table", "regle": "Règle", "lignes": "Lignes", "action": "Action"}),
             hide_index=True, use_container_width=True, height=420)

st.subheader("Durée du calcul")
st.dataframe(pd.DataFrame(r["etapes"], columns=["Étape", "Secondes"]), hide_index=True)
