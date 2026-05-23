"""Risque — diversification, concentration, corrélations, beta, stress tests."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import config, services
from src.analytics import risk
from src.market import prices as market_prices
from src.ui import components as ui

st.title("⚖️ Risque")

snapshot = services.get_portfolio_snapshot()
if snapshot.empty:
    st.info("Aucune position : analyse de risque indisponible.")
    st.stop()

# --- Alertes de concentration ---------------------------------------------
alerts = risk.concentration_alerts(snapshot)
if alerts:
    for a in alerts:
        st.warning(a, icon="⚠️")
else:
    st.success("Aucune alerte de concentration (ligne ≤ 15 %, secteur ≤ 30 %).", icon="✅")

# --- Indices de concentration ---------------------------------------------
ui.section_title("Concentration")
valos = snapshot.set_index("ticker")["valorisation"]
c = st.columns(2)
c[0].metric("Indice Herfindahl (HHI)", ui.fmt_num(risk.herfindahl(valos), 3),
            help="0 = parfaitement diversifié, 1 = mono-position")
c[1].metric("Nombre effectif de positions", ui.fmt_num(risk.effective_positions(valos), 1),
            help="1 / HHI")

# --- Diversification (camemberts) -----------------------------------------
ui.section_title("Diversification")
dims = [("secteur", "Secteur"), ("pays", "Pays"), ("devise", "Devise")]
cols = st.columns(len(dims))
for col, (dim, label) in zip(cols, dims):
    if dim not in snapshot.columns:
        continue
    alloc = risk.allocation_by(snapshot, dim)
    if alloc.empty:
        continue
    fig = px.pie(alloc, names=dim, values="valorisation", title=label, hole=0.4)
    fig.update_layout(height=300, showlegend=False, margin=dict(t=40, b=0))
    fig.update_traces(textinfo="label+percent")
    col.plotly_chart(fig, use_container_width=True)

# --- Matrice de corrélation -----------------------------------------------
ui.section_title("Matrice de corrélation", "Rendements quotidiens (1 an)")
price_matrix = services.get_price_matrix(period="1y")
corr = risk.correlation_matrix(price_matrix)
if not corr.empty:
    fig = go.Figure(go.Heatmap(z=corr.values, x=corr.columns, y=corr.index,
                               colorscale="RdBu", zmid=0, zmin=-1, zmax=1,
                               text=corr.round(2).values, texttemplate="%{text}"))
    fig.update_layout(height=120 + 50 * len(corr))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Pas assez de cotations pour calculer les corrélations.")

# --- Beta par ligne et global ---------------------------------------------
ui.section_title("Beta", f"vs {config.DEFAULT_BENCHMARK}")
bench_serie = market_prices.fetch_benchmark(config.BENCHMARKS[config.DEFAULT_BENCHMARK],
                                            period="1y")
betas = risk.position_betas(price_matrix, bench_serie) if not price_matrix.empty else None
beta_pf = None
if betas is not None and not betas.empty:
    beta_pf = risk.portfolio_beta(price_matrix, valos, bench_serie)
    beta_df = betas.rename("Beta").to_frame()
    beta_df.index.name = "Ticker"
    st.dataframe(beta_df.style.format({"Beta": lambda v: ui.fmt_num(v, 2)}),
                 use_container_width=True)
st.metric("Beta portefeuille", ui.fmt_num(beta_pf, 2) if beta_pf is not None else "—")

# --- Stress tests ----------------------------------------------------------
ui.section_title("Stress tests", "Modèle MVP : impact linéaire via les betas")
if betas is not None and not betas.empty:
    stress = risk.stress_test(snapshot, betas, config.STRESS_SCENARIOS)
    if not stress.empty:
        st.dataframe(
            stress.style.format({
                "Choc marché": ui.fmt_pct,
                "Impact (€)": lambda v: ui.fmt_eur(v),
                "Impact (%)": ui.fmt_pct,
                "Valo après choc (€)": lambda v: ui.fmt_eur(v),
            }),
            hide_index=True, use_container_width=True)
    st.caption("Hypothèses : chaque ligne réagit selon son beta historique vs "
               "benchmark. Scénarios taux/récession à enrichir dans une itération "
               "ultérieure (corrélations conditionnelles).")
else:
    st.caption("Betas indisponibles : stress tests non calculables pour l'instant.")
