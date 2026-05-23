"""Import / Mise à jour — point d'entrée : charger les deux exports broker.

Stratégie : remplacement complet, positions dérivées strictement des ordres
exécutés, mapping ISIN -> ticker éditable, rapport de réconciliation vs relevé.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src import broker_import, services
from src.db import repository
from src.ui import components as ui

st.title("📥 Import / Mise à jour des données")
st.caption("Charge tes deux exports broker pour mettre à jour l'ensemble de "
           "l'application. Remplacement complet : les données précédentes sont "
           "écrasées à chaque import.")

last_import = repository.get_meta("last_import")
if last_import:
    as_of = repository.get_meta("position_as_of", "—")
    cash = repository.get_meta("broker_cash", "")
    st.info(f"Dernier import : **{last_import}** · position au **{as_of}** · "
            f"liquidités relevé : **{cash} €**")

# --- Téléversement ---------------------------------------------------------
c1, c2 = st.columns(2)
orders_file = c1.file_uploader(
    "Historique des opérations (CSV)", type=["csv"], key="orders",
    help="Export « Historique opérations » (recommandé, montants nets + "
         "dividendes) ou ancien « Carnet d'ordres » — format détecté "
         "automatiquement.")
portfolio_file = c2.file_uploader("Portefeuille (CSV)", type=["csv"], key="portfolio")

if st.button("🔄 Importer et mettre à jour", type="primary",
             disabled=not (orders_file and portfolio_file)):
    report = broker_import.import_broker_files(
        orders_file.getvalue(), portfolio_file.getvalue(), replace=True)
    st.cache_data.clear()  # invalide les caches de cotations/fondamentaux
    st.success(
        f"Import réussi : {report['n_orders']} opérations, "
        f"{report['n_positions']} lignes au relevé, "
        f"cash {report['cash']} € (position au {report['as_of']}).")
    if report["unmapped_isins"]:
        st.warning("ISIN sans ticker yfinance connu (à compléter ci-dessous) : "
                   + ", ".join(report["unmapped_isins"]))
    if report["non_cotes"]:
        st.caption("Lignes non cotées (pas de cours yfinance, ex. parts "
                   "sociales) : " + ", ".join(report["non_cotes"]))
    st.rerun()

st.divider()

# --- Rien d'importé encore -------------------------------------------------
if not last_import and repository.get_import_snapshot().empty:
    st.info("Aucun import pour l'instant. Charge les deux fichiers ci-dessus. "
            "(En attendant, l'application affiche des données de démonstration.)")
    st.stop()

# --- Réconciliation dérivé vs relevé broker -------------------------------
ui.section_title("Réconciliation", "Positions dérivées des ordres vs relevé broker")
st.caption("Tu as choisi la dérivation stricte : les positions proviennent "
           "uniquement des ordres exécutés. Ce tableau met en évidence les "
           "écarts avec ton relevé (lignes antérieures à l'historique d'ordres, "
           "non cotées, ou ventes sans achat dans la période).")

derived = services.get_portfolio_snapshot()
broker = repository.get_import_snapshot()

if broker.empty:
    st.caption("Pas de relevé importé.")
else:
    d = (derived[["ticker", "quantite", "valorisation"]]
         .rename(columns={"quantite": "qte_derivee", "valorisation": "valo_live"})
         if not derived.empty else
         pd.DataFrame(columns=["ticker", "qte_derivee", "valo_live"]))
    b = broker[["ticker", "libelle", "quantite", "pru", "valorisation"]].rename(
        columns={"quantite": "qte_broker", "pru": "pru_broker",
                 "valorisation": "valo_broker"})
    recon = b.merge(d, on="ticker", how="outer")
    recon["libelle"] = recon["libelle"].fillna(recon["ticker"])
    recon["qte_derivee"] = recon["qte_derivee"].fillna(0.0)
    recon["qte_broker"] = recon["qte_broker"].fillna(0.0)
    recon["ecart_qte"] = recon["qte_derivee"] - recon["qte_broker"]

    def _flag(r):
        if r["qte_broker"] > 0 and r["qte_derivee"] == 0:
            return "⚠️ Absente du dérivé"
        if abs(r["ecart_qte"]) > 1e-6:
            return "⚠️ Écart de quantité"
        return "✅ OK"

    recon["statut"] = recon.apply(_flag, axis=1)
    st.dataframe(
        recon[["libelle", "ticker", "qte_broker", "qte_derivee", "ecart_qte",
               "pru_broker", "valo_broker", "statut"]]
        .rename(columns={"libelle": "Titre", "ticker": "Ticker",
                         "qte_broker": "Qté relevé", "qte_derivee": "Qté dérivée",
                         "ecart_qte": "Écart", "pru_broker": "PRU relevé",
                         "valo_broker": "Valo relevé"})
        .style.format({"PRU relevé": lambda v: ui.fmt_num(v, 2),
                       "Valo relevé": lambda v: ui.fmt_eur(v)}),
        hide_index=True, use_container_width=True)

    n_ko = int((recon["statut"] != "✅ OK").sum())
    if n_ko:
        st.caption(f"{n_ko} ligne(s) en écart — attendu en dérivation stricte. "
                   "Pour les réconcilier, ajoute les ordres manquants (page "
                   "Opérations) ou complète le mapping ci-dessous.")

# --- Mapping ISIN -> ticker (éditable) ------------------------------------
st.divider()
ui.section_title("Correspondance ISIN → ticker", "Corrige un ticker mal mappé "
                 "puis enregistre (les cours/fondamentaux se brancheront)")
secs = repository.get_securities()
if not secs.empty:
    editable = secs[["isin", "libelle", "ticker", "type_actif"]].copy()
    edited = st.data_editor(
        editable, hide_index=True, use_container_width=True,
        disabled=["isin", "libelle", "type_actif"], key="map_editor")
    if st.button("💾 Enregistrer les tickers"):
        changed = 0
        for (_, old), (_, new) in zip(editable.iterrows(), edited.iterrows()):
            if old["ticker"] != new["ticker"] and new["ticker"]:
                repository.remap_ticker(old["ticker"], new["ticker"].strip())
                changed += 1
        st.cache_data.clear()
        st.success(f"{changed} ticker(s) mis à jour.")
        st.rerun()
