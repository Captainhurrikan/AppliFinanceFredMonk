"""Analyse fondamentale — ratios, score transparent, historique dividendes."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import services
from src.analytics import signals
from src.db import repository
from src.market import fundamentals as fonda
from src.ui import components as ui

st.title("🔎 Analyse fondamentale")
st.caption("Ratios issus de yfinance (mis en cache 24 h). Score 100 % déterministe "
           "et documenté — aucune IA générative.")

snapshot = services.get_portfolio_snapshot()
wl = repository.get_watchlist()
tickers = sorted(set(
    (snapshot["ticker"].tolist() if not snapshot.empty else []) +
    (wl["ticker"].tolist() if not wl.empty else [])
))

if not tickers:
    st.info("Aucun titre en portefeuille ni en watchlist.")
    st.stop()

c = st.columns([3, 1])
ticker = c[0].selectbox("Titre", tickers)
refresh = c[1].button("🔄 Rafraîchir")

f = fonda.get_fundamentals(ticker, force_refresh=refresh)
if not f:
    st.warning("Fondamentaux indisponibles pour ce titre (yfinance n'a rien renvoyé).")
    st.stop()

# --- Score synthétique -----------------------------------------------------
score = signals.fundamental_score(f)
ui.section_title(f"Score synthétique — {ticker}", "Global = moyenne des 4 piliers")
scols = st.columns(5)
for col, pilier in zip(scols, ["Value", "Quality", "Growth", "Income", "Global"]):
    col.metric(pilier, ui.fmt_num(score.get(pilier), 0))

# --- Blocs de ratios -------------------------------------------------------
def _block(title, items):
    ui.section_title(title)
    cc = st.columns(len(items))
    for col, (label, key, kind) in zip(cc, items):
        val = f.get(key)
        if kind == "pct":
            col.metric(label, ui.fmt_pct(val) if val is not None else "—")
        else:
            col.metric(label, ui.fmt_num(val) if val is not None else "—")

_block("Valorisation", [
    ("PER", "per", "num"), ("PER fwd", "per_forward", "num"), ("PEG", "peg", "num"),
    ("P/B", "price_to_book", "num"), ("EV/EBITDA", "ev_ebitda", "num"),
    ("Div. yield", "dividende_yield", "pct"), ("Payout", "payout_ratio", "pct"),
])
_block("Qualité", [
    ("ROE", "roe", "pct"), ("ROIC", "roic", "pct"),
    ("Marge op.", "marge_op", "pct"), ("Marge nette", "marge_nette", "pct"),
])
_block("Croissance", [
    ("CA growth", "ca_growth", "pct"), ("EPS growth", "eps_growth", "pct"),
])
_block("Solvabilité", [
    ("Dette/Equity", "ratio_dette_eq", "num"), ("Current ratio", "current_ratio", "num"),
])

# --- Signaux fondamentaux --------------------------------------------------
ui.section_title("Signaux fondamentaux")
sigs = signals.fundamental_signals(f)
if sigs:
    for s in sigs:
        ui.signal_chip(s["favorable"], s["message"])
else:
    st.caption("Aucun signal fondamental marquant.")

# --- Comparaison sectorielle (interne, MVP) --------------------------------
ui.section_title("Comparaison sectorielle", "Médiane des titres suivis du même secteur")
medians = fonda.sector_medians(tickers)
secteur = f.get("secteur")
if not medians.empty and secteur in medians.index:
    st.dataframe(medians.loc[[secteur]].style.format(lambda v: ui.fmt_num(v, 2)),
                 use_container_width=True)
else:
    st.caption("Pas assez de titres du même secteur en cache pour comparer "
               "(comparaison sectorielle externe prévue dans une itération ultérieure).")

# --- Historique des dividendes (10 ans) ------------------------------------
ui.section_title("Historique des dividendes (10 ans)")
div = fonda.get_dividend_history(ticker)
if not div.empty:
    div_10y = div[div.index >= div.index.max() - pd.DateOffset(years=10)]
    fig = go.Figure(go.Bar(x=div_10y.index, y=div_10y.values, marker_color="#2E86C1"))
    fig.update_layout(height=300, yaxis_title="Dividende / action")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Aucun historique de dividendes disponible.")
