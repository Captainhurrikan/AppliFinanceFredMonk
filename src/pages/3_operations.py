"""Opérations — CRUD sur la table operations (source unique de vérité)."""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from src.db import repository
from src.market import prices as market_prices
from src.ui import components as ui

st.title("✍️ Opérations")

securities = repository.get_securities()

# --- Ajout facile d'un nouveau titre au référentiel -----------------------
with st.expander("➕ Ajouter un nouveau titre au référentiel"):
    st.caption("Saisis un ticker yfinance (ex: AIR.PA, ASML.AS). On pré-remplit "
               "les métadonnées automatiquement.")
    new_ticker = st.text_input("Ticker yfinance", key="new_sec_ticker").strip().upper()
    if st.button("Rechercher les métadonnées") and new_ticker:
        info = market_prices.fetch_security_info(new_ticker)
        if info:
            st.session_state["sec_info"] = info
        else:
            st.session_state["sec_info"] = {"ticker": new_ticker, "libelle": new_ticker,
                                            "devise": "EUR", "type_actif": "ACTION"}
            st.warning("Métadonnées indisponibles — saisie manuelle possible ci-dessous.")
    info = st.session_state.get("sec_info")
    if info and info.get("ticker") == new_ticker:
        c = st.columns(3)
        lib = c[0].text_input("Libellé", value=info.get("libelle") or new_ticker)
        sect = c[1].text_input("Secteur", value=info.get("secteur") or "")
        pays = c[2].text_input("Pays", value=info.get("pays") or "")
        c2 = st.columns(2)
        dev = c2[0].text_input("Devise", value=info.get("devise") or "EUR")
        typ = c2[1].selectbox("Type", ["ACTION", "ETF", "OBLIGATION"],
                              index=["ACTION", "ETF", "OBLIGATION"].index(
                                  info.get("type_actif", "ACTION")
                                  if info.get("type_actif") in ("ACTION", "ETF", "OBLIGATION")
                                  else "ACTION"))
        if st.button("Enregistrer le titre"):
            repository.upsert_security(new_ticker, lib, sect or None, pays or None,
                                       dev or "EUR", typ, info.get("cap_boursiere"))
            st.success(f"Titre {new_ticker} ajouté.")
            st.session_state.pop("sec_info", None)
            st.rerun()

# --- Formulaire de saisie d'opération -------------------------------------
ui.section_title("Nouvelle opération")
prefill = st.session_state.pop("prefill_op", {})
result = ui.operation_form(
    securities,
    default_ticker=prefill.get("ticker"),
    default_type=prefill.get("type", "Achat"),
)
if result:
    repository.add_operation(**result)
    st.success("Opération enregistrée.")
    st.rerun()

# --- Import CSV ------------------------------------------------------------
with st.expander("📥 Import CSV"):
    template = pd.DataFrame([
        {"date": "2024-01-16", "ticker": "AIR.PA", "type": "BUY", "quantite": 10,
         "prix_unitaire": 140.0, "montant_brut": 0, "frais": 5, "devise": "EUR",
         "notes": "exemple"},
        {"date": "2024-03-20", "ticker": "AIR.PA", "type": "DIV", "quantite": 0,
         "prix_unitaire": 0, "montant_brut": 90.0, "frais": 0, "devise": "EUR",
         "notes": "dividende"},
    ])
    st.download_button("Télécharger le template CSV",
                       template.to_csv(index=False).encode("utf-8"),
                       file_name="template_operations.csv", mime="text/csv")
    uploaded = st.file_uploader("Fichier CSV", type=["csv"])
    if uploaded is not None:
        df_csv = pd.read_csv(io.BytesIO(uploaded.getvalue()))
        st.dataframe(df_csv, hide_index=True, use_container_width=True)
        if st.button("Importer ces opérations"):
            try:
                n = repository.bulk_insert_operations(df_csv)
                st.success(f"{n} opérations importées.")
                st.rerun()
            except Exception as exc:
                st.error(f"Import impossible : {exc}")

# --- Historique + filtres + édition ---------------------------------------
ui.section_title("Historique des opérations")
ops = repository.get_operations()
if ops.empty:
    st.info("Aucune opération enregistrée.")
    st.stop()

f = st.columns(3)
ticker_filter = f[0].selectbox("Ticker", ["(tous)"] + sorted(ops["ticker"].dropna().unique().tolist()))
type_filter = f[1].selectbox("Type", ["(tous)"] + list(repository.OPERATION_TYPES))
n_rows = f[2].number_input("Lignes affichées", min_value=10, max_value=500, value=50, step=10)

filtered = ops.copy()
if ticker_filter != "(tous)":
    filtered = filtered[filtered["ticker"] == ticker_filter]
if type_filter != "(tous)":
    filtered = filtered[filtered["type"] == type_filter]
filtered = filtered.sort_values("date", ascending=False).head(int(n_rows))

st.dataframe(
    filtered[["id", "date", "ticker", "type", "quantite", "prix_unitaire",
              "montant_brut", "frais", "notes"]],
    hide_index=True, use_container_width=True,
)

# --- Suppression d'une opération ------------------------------------------
del_cols = st.columns([1, 3])
op_id = del_cols[0].number_input("ID à supprimer", min_value=0, step=1, value=0)
if del_cols[1].button("🗑️ Supprimer l'opération") and op_id > 0:
    repository.delete_operation(int(op_id))
    st.success(f"Opération {op_id} supprimée.")
    st.rerun()
