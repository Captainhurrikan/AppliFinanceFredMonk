"""Dashboard — vue synthétique d'ensemble (consomme tous les autres modules)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import config, services
from src.analytics import performance, risk, signals
from src.db import repository
from src.market import prices as market_prices
from src.ui import components as ui

st.title("🏠 Dashboard")
st.caption("Vue synthétique du portefeuille — l'outil aide à décider, il ne décide pas.")

snapshot = services.get_portfolio_snapshot()
cash = services.get_cash()
titres = float(snapshot["valorisation"].sum()) if not snapshot.empty else 0.0
total = titres + cash

twr_idx = services.get_twr_index()
history = services.get_portfolio_history()

HORIZONS = {"1 mois": 30, "3 mois": 91, "1 an": 365}


def _horizon_eur_pct(days: int) -> tuple[float | None, float | None]:
    pct = performance.period_return(twr_idx, days) if not twr_idx.empty else None
    if pct is None or history.empty:
        return None, pct
    end = history.index[-1]
    target = end - pd.Timedelta(days=days)
    window = history["total_value"][history.index <= target]
    start_val = window.iloc[-1] if not window.empty else history["total_value"].iloc[0]
    return pct * start_val, pct


# --- Valorisation et variations -------------------------------------------
ui.section_title("Valorisation")
cols = st.columns(4)
perf_1a = performance.period_return(twr_idx, 365) if not twr_idx.empty else None
ui.kpi(cols[0], "Valorisation totale", ui.fmt_eur(total),
       delta=ui.fmt_pct(perf_1a) + " (TWR 1a)" if perf_1a is not None else None,
       help_text="Titres + cash disponible")
for col, (label, days) in zip(cols[1:], HORIZONS.items()):
    eur, pct = _horizon_eur_pct(days)
    ui.kpi(col, f"Perf {label}",
           ui.fmt_pct(pct) if pct is not None else "—",
           delta=ui.fmt_eur(eur) if eur is not None else None,
           help_text="Performance TWR (neutralise apports/retraits)")

if twr_idx.empty:
    st.info("Cotations indisponibles (hors-ligne ?) : les performances seront calculées dès que les cours seront récupérés.")

# --- TWR vs benchmarks -----------------------------------------------------
ui.section_title("Performance vs benchmarks", "TWR du portefeuille comparé aux proxys ETF")
benchmarks = services.get_benchmark_indices(twr_idx) if not twr_idx.empty else {}
rows = []
port_row = {"": "Portefeuille (TWR)"}
for label, days in HORIZONS.items():
    port_row[label] = performance.period_return(twr_idx, days) if not twr_idx.empty else None
rows.append(port_row)
for nom, serie in benchmarks.items():
    r = {"": nom}
    for label, days in HORIZONS.items():
        r[label] = performance.period_return(serie, days)
    rows.append(r)
if len(rows) > 1:
    bench_df = pd.DataFrame(rows).set_index("")
    st.dataframe(bench_df.style.format(lambda v: ui.fmt_pct(v)), use_container_width=True)
else:
    st.caption("Benchmarks indisponibles pour le moment.")

# --- KPIs risque -----------------------------------------------------------
ui.section_title("Risque (1 an glissant)")
rcols = st.columns(3)
if not twr_idx.empty:
    last_year = twr_idx[twr_idx.index >= twr_idx.index[-1] - pd.Timedelta(days=365)]
    vol = performance.annualized_volatility(performance.daily_returns(last_year))
    mdd = performance.max_drawdown(last_year)
else:
    vol = mdd = None

beta_pf = None
try:
    px = services.get_price_matrix()
    bench_serie = market_prices.fetch_benchmark(config.BENCHMARKS[config.DEFAULT_BENCHMARK])
    if not px.empty and not bench_serie.empty and not snapshot.empty:
        valos = snapshot.set_index("ticker")["valorisation"]
        beta_pf = risk.portfolio_beta(px, valos, bench_serie)
except Exception:
    beta_pf = None

ui.kpi(rcols[0], "Volatilité annualisée", ui.fmt_pct(vol) if vol is not None else "—")
ui.kpi(rcols[1], "Max drawdown", ui.fmt_pct(mdd) if mdd is not None else "—")
ui.kpi(rcols[2], "Beta portefeuille",
       ui.fmt_num(beta_pf) if beta_pf is not None else "—",
       help_text=f"vs {config.DEFAULT_BENCHMARK}")

# --- Top / Flop ------------------------------------------------------------
if not snapshot.empty:
    ui.section_title("Top / Flop (+/-value latente)")
    tcols = st.columns(2)
    ordered = snapshot.dropna(subset=["perf_latente"]).sort_values("perf_latente", ascending=False)
    top = ordered.head(3)[["libelle", "perf_latente", "pv_latente"]]
    flop = ordered.tail(3).sort_values("perf_latente")[["libelle", "perf_latente", "pv_latente"]]
    tcols[0].markdown("**🟢 Top 3 gagnantes**")
    tcols[0].dataframe(
        top.rename(columns={"libelle": "Titre", "perf_latente": "Perf", "pv_latente": "+/- value"})
        .style.format({"Perf": ui.fmt_pct, "+/- value": lambda v: ui.fmt_eur(v)}),
        hide_index=True, use_container_width=True)
    tcols[1].markdown("**🔴 Top 3 perdantes**")
    tcols[1].dataframe(
        flop.rename(columns={"libelle": "Titre", "perf_latente": "Perf", "pv_latente": "+/- value"})
        .style.format({"Perf": ui.fmt_pct, "+/- value": lambda v: ui.fmt_eur(v)}),
        hide_index=True, use_container_width=True)

# --- Cash + À regarder aujourd'hui ----------------------------------------
bottom = st.columns([1, 2])
with bottom[0]:
    ui.section_title("Cash disponible")
    st.metric("Cash", ui.fmt_eur(cash),
              help="Dépôts − achats + ventes + dividendes − frais")

with bottom[1]:
    ui.section_title("À regarder aujourd'hui")
    items: list[str] = []
    items += [a["message"] for a in signals.position_alerts(snapshot)]
    wl = repository.get_watchlist()
    if not wl.empty:
        wl_prices = services.get_current_prices(wl["ticker"].tolist())
        items += [a["message"] for a in signals.watchlist_alerts(wl, wl_prices)]
    if items:
        for msg in items:
            st.warning(msg, icon="⚠️")
    else:
        st.success("Rien de notable : aucune alerte déclenchée.", icon="✅")
