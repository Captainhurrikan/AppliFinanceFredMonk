"""Positions — détail ligne par ligne du portefeuille."""

from __future__ import annotations

import streamlit as st

from src import services
from src.ui import components as ui

st.title("📊 Positions")
ui.refresh_prices_button(key="refresh_positions")

snapshot = services.get_portfolio_snapshot()

if snapshot.empty:
    st.info("Aucune position ouverte. Ajoute des opérations dans la page Opérations.")
    st.stop()

display = snapshot.copy()
display = display[[
    "ticker", "libelle", "quantite", "pru", "cours",
    "valorisation", "pv_latente", "perf_latente", "poids", "dividendes",
]].rename(columns={
    "ticker": "Ticker", "libelle": "Libellé",
    "quantite": "Qté", "pru": "PRU", "cours": "Cours", "valorisation": "Valo",
    "pv_latente": "+/- value (€)", "perf_latente": "+/- value (%)",
    "poids": "Poids", "dividendes": "Div. perçus",
})

st.dataframe(
    display.style.format({
        "Qté": lambda v: ui.fmt_num(v, 0),
        "PRU": lambda v: ui.fmt_num(v, 2),
        "Cours": lambda v: ui.fmt_num(v, 2),
        "Valo": lambda v: ui.fmt_eur(v),
        "+/- value (€)": lambda v: ui.fmt_eur(v),
        "+/- value (%)": ui.fmt_pct,
        "Poids": ui.fmt_pct,
        "Div. perçus": lambda v: ui.fmt_eur(v),
    }),
    hide_index=True, use_container_width=True,
)

c1, c2, c3 = st.columns(3)
c1.metric("Valorisation titres", ui.fmt_eur(snapshot["valorisation"].sum()))
c2.metric("+/- value latente totale", ui.fmt_eur(snapshot["pv_latente"].sum()))
c3.metric("Dividendes perçus cumulés", ui.fmt_eur(snapshot["dividendes"].sum()))

st.divider()
ui.section_title("Action rapide", "Pré-remplit une opération pour la ligne choisie")
acc = st.columns([2, 1, 1])
ticker = acc[0].selectbox("Titre", snapshot["ticker"].tolist())
if acc[1].button("➕ Renforcer", use_container_width=True):
    st.session_state["prefill_op"] = {"ticker": ticker, "type": "Achat"}
    st.switch_page("src/pages/3_operations.py")
if acc[2].button("➖ Vendre", use_container_width=True):
    st.session_state["prefill_op"] = {"ticker": ticker, "type": "Vente"}
    st.switch_page("src/pages/3_operations.py")
