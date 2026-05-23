"""Composants Streamlit réutilisables (formatage, badges, formulaires)."""

from __future__ import annotations

import pandas as pd
import streamlit as st


# --- Formatage -------------------------------------------------------------

def fmt_eur(value: float | None, decimals: int = 0) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.{decimals}f} €".replace(",", " ").replace(".", ",", 1) \
        if decimals else f"{value:,.0f} €".replace(",", " ")


def fmt_pct(value: float | None, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value * 100:+.{decimals}f} %"


def fmt_num(value: float | None, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.{decimals}f}".replace(",", " ")


# --- Indicateurs / badges --------------------------------------------------

def kpi(col, label: str, value: str, delta: str | None = None,
        help_text: str | None = None) -> None:
    col.metric(label, value, delta=delta, help=help_text)


def fetch_status_badge(status_ok: bool, label: str = "") -> None:
    """Affiche un badge d'état de récupération de données."""
    if status_ok:
        st.caption(f"🟢 Données à jour {label}")
    else:
        st.caption(f"🟠 Données partielles ou indisponibles {label}")


def signal_chip(favorable: bool | None, message: str) -> None:
    if favorable is True:
        st.success(message, icon="✅")
    elif favorable is False:
        st.warning(message, icon="⚠️")
    else:
        st.info(message)


def section_title(title: str, subtitle: str | None = None) -> None:
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)


# --- Formulaire d'opération ------------------------------------------------

OPERATION_LABELS = {
    "Achat": "BUY",
    "Vente": "SELL",
    "Dividende": "DIV",
    "Frais": "FEE",
    "Dépôt": "DEPOSIT",
    "Retrait": "WITHDRAW",
}


def operation_form(securities: pd.DataFrame, default_ticker: str | None = None,
                   default_type: str = "Achat", key: str = "op_form") -> dict | None:
    """Formulaire de saisie d'une opération. Renvoie un dict prêt pour
    repository.add_operation, ou None si non soumis."""
    import datetime as _dt

    tickers = securities["ticker"].tolist() if not securities.empty else []
    with st.form(key=key, clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        op_date = c1.date_input("Date", value=_dt.date.today())
        type_label = c2.selectbox("Type", list(OPERATION_LABELS.keys()),
                                  index=list(OPERATION_LABELS.keys()).index(default_type))
        type_ = OPERATION_LABELS[type_label]

        needs_ticker = type_ in ("BUY", "SELL", "DIV")
        ticker = None
        if needs_ticker and tickers:
            idx = tickers.index(default_ticker) if default_ticker in tickers else 0
            ticker = c3.selectbox("Titre", tickers, index=idx)
        elif needs_ticker:
            ticker = c3.text_input("Ticker (yfinance, ex: AIR.PA)")

        q1, q2, q3 = st.columns(3)
        quantite = prix = montant = frais = 0.0
        if type_ in ("BUY", "SELL"):
            quantite = q1.number_input("Quantité", min_value=0.0, step=1.0)
            prix = q2.number_input("Prix unitaire", min_value=0.0, step=0.01)
            frais = q3.number_input("Frais (€)", min_value=0.0, step=0.01)
        else:
            montant = q1.number_input("Montant (€)", min_value=0.0, step=0.01)
            if type_ in ("DIV", "FEE"):
                frais = q2.number_input("Frais (€)", min_value=0.0, step=0.01)

        notes = st.text_input("Notes", value="")
        submitted = st.form_submit_button("Enregistrer l'opération")

    if not submitted:
        return None
    if needs_ticker and not ticker:
        st.error("Sélectionne ou saisis un ticker.")
        return None

    return {
        "op_date": op_date.isoformat(),
        "type_": type_,
        "ticker": ticker,
        "quantite": quantite,
        "prix_unitaire": prix,
        "montant_brut": montant,
        "frais": frais,
        "notes": notes or None,
    }


def perf_color(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "gray"
    return "green" if value >= 0 else "red"
