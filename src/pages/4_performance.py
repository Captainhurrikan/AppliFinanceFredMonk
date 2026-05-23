"""Performance — courbes, TWR vs MWR, décomposition, attribution, drawdown."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import services
from src.analytics import performance, portfolio
from src.db import repository
from src.ui import components as ui

st.title("📈 Performance")

twr_idx = services.get_twr_index()
history = services.get_portfolio_history()
ops = repository.get_operations()

if twr_idx.empty or history.empty:
    st.info("Cotations indisponibles : impossible de tracer les courbes pour l'instant. "
            "Les calculs s'afficheront dès la récupération des cours.")
    st.stop()

# --- Courbe portefeuille (TWR rebasé 100) vs benchmarks --------------------
ui.section_title("Évolution (base 100)", "Portefeuille en TWR vs proxys ETF")
fig = go.Figure()
fig.add_trace(go.Scatter(x=twr_idx.index, y=twr_idx * 100, name="Portefeuille (TWR)",
                         line=dict(width=3)))
for nom, serie in services.get_benchmark_indices(twr_idx).items():
    fig.add_trace(go.Scatter(x=serie.index, y=serie * 100, name=nom,
                             line=dict(width=1.5, dash="dot")))
fig.update_layout(height=420, hovermode="x unified", yaxis_title="Base 100",
                  legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

# --- TWR vs MWR ------------------------------------------------------------
ui.section_title("TWR vs MWR")
twr_total = performance.twr(history["total_value"], history["external_flow"])
mwr = performance.mwr(services.get_mwr_cashflows())
c1, c2 = st.columns(2)
c1.metric("TWR (Time-Weighted Return)", ui.fmt_pct(twr_total))
c1.caption("Neutralise les apports/retraits → mesure la **qualité de gestion**. "
           "C'est l'indicateur à comparer aux benchmarks.")
c2.metric("MWR (Money-Weighted Return, annualisé)",
          ui.fmt_pct(mwr) if mwr is not None else "—")
c2.caption("Équivalent TRI : pondère par les montants et le **timing des flux** → "
           "mesure le rendement réellement perçu par l'investisseur.")

# --- Décomposition de la performance --------------------------------------
ui.section_title("Décomposition de la performance")
snapshot = services.get_portfolio_snapshot()
pv_latente = float(snapshot["pv_latente"].sum()) if not snapshot.empty else 0.0
pv_realisee = portfolio.realized_pnl(ops)
dividendes = portfolio.total_dividends(ops)
frais = portfolio.total_fees(ops)
decomp = pd.DataFrame({
    "Composante": ["+/- value réalisée", "+/- value latente", "Dividendes", "Frais"],
    "Montant (€)": [pv_realisee, pv_latente, dividendes, -frais],
})
fig2 = go.Figure(go.Bar(
    x=decomp["Composante"], y=decomp["Montant (€)"],
    marker_color=["#2E86C1", "#28B463", "#F1C40F", "#E74C3C"]))
fig2.update_layout(height=320, yaxis_title="€")
st.plotly_chart(fig2, use_container_width=True)
st.metric("Résultat net total (hors apports)",
          ui.fmt_eur(pv_realisee + pv_latente + dividendes - frais))

# --- Attribution par position ---------------------------------------------
ui.section_title("Attribution", "Contribution de chaque position au résultat latent")
if not snapshot.empty:
    attrib = snapshot[["libelle", "pv_latente", "dividendes"]].copy()
    attrib["Contribution (€)"] = attrib["pv_latente"] + attrib["dividendes"]
    attrib = attrib.sort_values("Contribution (€)", ascending=False)
    st.dataframe(
        attrib.rename(columns={"libelle": "Titre", "pv_latente": "+/- value latente",
                               "dividendes": "Dividendes"})
        .style.format({"+/- value latente": lambda v: ui.fmt_eur(v),
                       "Dividendes": lambda v: ui.fmt_eur(v),
                       "Contribution (€)": lambda v: ui.fmt_eur(v)}),
        hide_index=True, use_container_width=True)

# --- Drawdown --------------------------------------------------------------
ui.section_title("Drawdown")
dd = performance.drawdown_series(twr_idx)
mdd = performance.max_drawdown(twr_idx)
fig3 = go.Figure(go.Scatter(x=dd.index, y=dd * 100, fill="tozeroy",
                            line=dict(color="#E74C3C")))
fig3.update_layout(height=300, yaxis_title="Drawdown (%)")
st.plotly_chart(fig3, use_container_width=True)
st.metric("Max drawdown sur la période", ui.fmt_pct(mdd))

# --- Rendements mensuels (heatmap) -----------------------------------------
ui.section_title("Rendements mensuels")
monthly = performance.monthly_returns_table(twr_idx)
if not monthly.empty:
    month_cols = [c for c in monthly.columns if c != "Année"]
    fig4 = go.Figure(go.Heatmap(
        z=monthly[month_cols].values * 100,
        x=month_cols, y=monthly.index.astype(str),
        colorscale="RdYlGn", zmid=0,
        text=(monthly[month_cols].values * 100).round(1),
        texttemplate="%{text}", colorbar=dict(title="%")))
    fig4.update_layout(height=80 + 40 * len(monthly))
    st.plotly_chart(fig4, use_container_width=True)
    st.dataframe(
        monthly.style.format(lambda v: ui.fmt_pct(v)),
        use_container_width=True)
else:
    st.caption("Pas assez d'historique pour le tableau mensuel.")
