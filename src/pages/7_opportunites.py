"""Opportunités & signaux — watchlist, signaux techniques/fondamentaux, news."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src import config, services
from src.analytics import signals
from src.db import repository
from src.market import fundamentals as fonda
from src.market import news as news_mod
from src.market import prices as market_prices
from src.ui import components as ui

st.title("🎯 Opportunités & signaux")
st.caption("Signaux explicites, jamais en boîte noire. L'outil aide à décider, "
           "il ne génère aucune recommandation automatique.")

snapshot = services.get_portfolio_snapshot()
wl = repository.get_watchlist()

# --- Alertes prise de bénéfices / stop-loss -------------------------------
ui.section_title("Alertes prise de bénéfices / stop-loss")
pos_alerts = signals.position_alerts(
    snapshot,
    profit_take=config.DEFAULT_PROFIT_TAKE,
    stop_loss=config.DEFAULT_STOP_LOSS,
)
if pos_alerts:
    for a in pos_alerts:
        icon = "🟢" if a["type"] == "PROFIT_TAKE" else "🔴"
        st.warning(f"{icon} {a['message']}")
else:
    st.success(f"Aucune ligne au-delà de +{config.DEFAULT_PROFIT_TAKE:.0%} ni en "
               f"deçà de {config.DEFAULT_STOP_LOSS:.0%}.", icon="✅")

# --- Watchlist + cibles ----------------------------------------------------
ui.section_title("Watchlist")
with st.expander("➕ Ajouter / modifier une ligne de watchlist"):
    cc = st.columns(3)
    wt = cc[0].text_input("Ticker").strip().upper()
    ca = cc[1].number_input("Prix cible d'achat", min_value=0.0, step=0.01)
    cv = cc[2].number_input("Prix cible de vente", min_value=0.0, step=0.01)
    these = st.text_area("Thèse d'investissement", height=80)
    tags = st.text_input("Tags (séparés par ;)")
    if st.button("Enregistrer dans la watchlist") and wt:
        repository.upsert_security(wt, wt)
        repository.upsert_watchlist(wt, ca or None, cv or None, these or None, tags or None)
        st.success(f"{wt} ajouté à la watchlist.")
        st.rerun()

if not wl.empty:
    wl_prices = services.get_current_prices(wl["ticker"].tolist())
    view = wl.copy()
    view["cours"] = view["ticker"].map(wl_prices)

    def _statut(r):
        cours = r["cours"]
        if cours is None:
            return "—"
        if r["prix_cible_achat"] and cours <= r["prix_cible_achat"]:
            return "🟢 Cible d'achat atteinte"
        if r["prix_cible_vente"] and cours >= r["prix_cible_vente"]:
            return "🔴 Cible de vente atteinte"
        return "⏳ En attente"

    view["statut"] = view.apply(_statut, axis=1)
    st.dataframe(
        view[["ticker", "cours", "prix_cible_achat", "prix_cible_vente", "statut", "these_invest", "tags"]]
        .rename(columns={"ticker": "Ticker", "cours": "Cours",
                         "prix_cible_achat": "Cible achat", "prix_cible_vente": "Cible vente",
                         "statut": "Statut", "these_invest": "Thèse", "tags": "Tags"}),
        hide_index=True, use_container_width=True)

    for a in signals.watchlist_alerts(wl, wl_prices):
        st.warning(a["message"], icon="🔔")

    rm = st.columns([2, 1])
    to_del = rm[0].selectbox("Retirer de la watchlist", ["(aucun)"] + wl["ticker"].tolist())
    if rm[1].button("🗑️ Retirer") and to_del != "(aucun)":
        repository.delete_watchlist(to_del)
        st.rerun()
else:
    st.caption("Watchlist vide.")

# --- Signaux techniques + fondamentaux par titre --------------------------
ui.section_title("Signaux par titre")
tickers = sorted(set(
    (snapshot["ticker"].tolist() if not snapshot.empty else []) +
    (wl["ticker"].tolist() if not wl.empty else [])
))
if tickers:
    ticker = st.selectbox("Titre", tickers, key="signal_ticker")
    hist = market_prices.fetch_history(ticker, period="2y")
    if not hist.empty:
        tech = signals.technical_snapshot(hist["close"])
        m = st.columns(4)
        m[0].metric("RSI 14j", ui.fmt_num(tech.get("rsi14"), 0),
                    help="< 30 survendu, > 70 suracheté")
        cross = {"golden": "🟢 Golden cross", "death": "🔴 Death cross",
                 None: "—"}.get(tech.get("croisement"), "—")
        m[1].metric("Croisement MM50/MM200", cross)
        m[2].metric("Distance plus-haut 52s",
                    ui.fmt_pct(tech.get("dist_52w_high")) if tech.get("dist_52w_high") is not None else "—")
        m[3].metric("Cours", ui.fmt_num(tech.get("cours"), 2))

        # Graphique cours + MM50 + MM200
        ma = signals.moving_averages(hist["close"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=hist["close"], name="Cours"))
        fig.add_trace(go.Scatter(x=ma.index, y=ma["MM50"], name="MM50",
                                 line=dict(dash="dot")))
        fig.add_trace(go.Scatter(x=ma.index, y=ma["MM200"], name="MM200",
                                 line=dict(dash="dash")))
        fig.update_layout(height=360, hovermode="x unified",
                          legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Cotations indisponibles pour le graphique technique.")

    # Signaux fondamentaux
    f = fonda.get_fundamentals(ticker)
    fsigs = signals.fundamental_signals(f)
    if fsigs:
        st.markdown("**Signaux fondamentaux**")
        for s in fsigs:
            ui.signal_chip(s["favorable"], s["message"])

    # --- News RSS ----------------------------------------------------------
    ui.section_title("Actualités", "Google News — sentiment par mots-clés (basique)")
    sec = repository.get_security(ticker)
    query = sec["libelle"] if sec and sec.get("libelle") else ticker
    items = news_mod.fetch_news(query)
    if items:
        for it in items:
            emoji = {"positif": "🟢", "négatif": "🔴", "neutre": "⚪"}[it["sentiment"]]
            st.markdown(f"{emoji} [{it['titre']}]({it['lien']})  \n"
                        f"<span style='color:gray;font-size:0.8em'>{it['date']}</span>",
                        unsafe_allow_html=True)
    else:
        st.caption("Aucune actualité récupérée (flux indisponible ou feedparser absent).")
else:
    st.caption("Ajoute des positions ou des titres en watchlist pour voir les signaux.")
