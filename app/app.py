"""Interface client du calculateur CO2 FastColis : streamlit run app/app.py"""
import streamlit as st

st.set_page_config(page_title="Calculateur CO2 FastColis", page_icon="🌿", layout="wide")

st.markdown("""<style>
.block-container {padding-top: 2rem; max-width: 1200px}
h1, h2, h3 {letter-spacing: -0.01em}
div[data-testid="stMetricValue"] {font-size: 1.6rem}
</style>""", unsafe_allow_html=True)

pages = [
    st.Page("vues/accueil.py", title="Accueil", icon=":material/home:", default=True),
    st.Page("vues/calcul.py", url_path="calcul", title="Calculer un envoi", icon=":material/calculate:"),
    st.Page("vues/bilan.py", url_path="bilan", title="Mon bilan carbone", icon=":material/insights:"),
    st.Page("vues/methode.py", url_path="methode", title="Comment c'est calculé", icon=":material/menu_book:"),
    st.Page("vues/qualite.py", url_path="qualite", title="Fiabilité des données", icon=":material/verified:"),
]
st.navigation(pages).run()
