"""Point d'entrée Streamlit de l'application de suivi PEA.

Initialise la base au premier lancement (schéma + données de démo si vide) puis
construit la navigation multipage. Lancement : `streamlit run streamlit_app.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Garantit que la racine du dépôt est importable (`from src...`).
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db import repository  # noqa: E402
from src.db.seed import seed_demo_data  # noqa: E402

st.set_page_config(page_title="PEA — Suivi actif", page_icon="📈", layout="wide")


@st.cache_resource
def _bootstrap() -> bool:
    """Crée le schéma et insère les données de démo si la base est vide.
    Mis en cache_resource pour ne s'exécuter qu'une fois par session serveur."""
    repository.init_db()
    seed_demo_data(force=False)
    return True


_bootstrap()

PAGES_DIR = ROOT / "src" / "pages"

# NB : seules Import / Dashboard / Positions sont actives pour le moment.
# Les autres pages (Opérations, Performance, Analyse fonda, Risque,
# Opportunités) restent dans src/pages/ mais sont retirées de la navigation.
pages = [
    st.Page(str(PAGES_DIR / "0_import.py"), title="Import / Mise à jour", icon="📥", default=True),
    st.Page(str(PAGES_DIR / "1_dashboard.py"), title="Dashboard", icon="🏠"),
    st.Page(str(PAGES_DIR / "2_positions.py"), title="Positions", icon="📊"),
]

st.navigation(pages).run()
