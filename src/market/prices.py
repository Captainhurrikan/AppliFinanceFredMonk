"""Cotations via yfinance, avec cache Streamlit (TTL) et conversion FX en EUR.

Tous les appels passent par le wrapper `safe_fetch` (cf. cache.py) : en cas
d'échec, on renvoie des structures vides plutôt que de planter l'UI.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
import yfinance as yf

from src.config import BASE_CURRENCY, TTL_HISTORY, TTL_INTRADAY
from src.market.cache import FetchStatus, safe_fetch


# --- Métadonnées d'un titre (pour alimenter le référentiel facilement) -----

@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_security_info(ticker: str) -> dict:
    """Récupère libellé, secteur, pays, devise via yfinance pour pré-remplir
    l'ajout d'un nouveau titre. Renvoie {} si indisponible."""
    def _call():
        info = yf.Ticker(ticker).info
        if not info or info.get("regularMarketPrice") is None and not info.get("shortName"):
            return {}
        return info

    res = safe_fetch(f"info:{ticker}", _call)
    if not res.ok or not res.data:
        return {}
    info = res.data
    return {
        "ticker": ticker,
        "libelle": info.get("shortName") or info.get("longName") or ticker,
        "secteur": info.get("sector"),
        "pays": info.get("country"),
        "devise": info.get("currency", BASE_CURRENCY),
        "cap_boursiere": info.get("marketCap"),
        "type_actif": "ETF" if info.get("quoteType") == "ETF" else "ACTION",
    }


# --- Historique de cotations -----------------------------------------------

@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_history(ticker: str, period: str = "5y") -> pd.DataFrame:
    """Historique de clôtures ajustées d'un ticker. Index = dates, colonne
    'close'. DataFrame vide si indisponible."""
    def _call():
        df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        return df

    res = safe_fetch(f"history:{ticker}", _call)
    if res.status != FetchStatus.OK:
        return pd.DataFrame(columns=["close"])
    df = res.data
    if "Close" not in df.columns:
        return pd.DataFrame(columns=["close"])
    out = df[["Close"]].rename(columns={"Close": "close"})
    out.index = pd.to_datetime(out.index).tz_localize(None)
    return out


@st.cache_data(ttl=TTL_INTRADAY, show_spinner=False)
def fetch_last_price(ticker: str) -> float | None:
    """Dernier cours connu (devise du titre). None si indisponible."""
    def _call():
        t = yf.Ticker(ticker)
        fast = getattr(t, "fast_info", None)
        if fast and fast.get("last_price"):
            return float(fast["last_price"])
        hist = t.history(period="5d", auto_adjust=True)
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return None

    res = safe_fetch(f"last:{ticker}", _call)
    return res.unwrap()


# --- Conversion de change --------------------------------------------------

@st.cache_data(ttl=TTL_INTRADAY, show_spinner=False)
def fetch_fx_rate(devise: str, base: str = BASE_CURRENCY) -> float:
    """Taux pour convertir `devise` -> `base` (EUR). 1.0 si même devise."""
    if not devise or devise.upper() == base.upper():
        return 1.0
    pair = f"{devise.upper()}{base.upper()}=X"  # ex: USDEUR=X -> EUR par USD

    def _call():
        hist = yf.Ticker(pair).history(period="5d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])

    res = safe_fetch(f"fx:{pair}", _call)
    rate = res.unwrap()
    return rate if rate else 1.0


def to_eur(amount: float, devise: str) -> float:
    """Convertit un montant de `devise` vers EUR."""
    return amount * fetch_fx_rate(devise)


# --- Construction de la matrice de prix EUR pour un portefeuille -----------

@st.cache_data(ttl=TTL_HISTORY, show_spinner="Chargement des cotations…")
def fetch_price_matrix(tickers: tuple[str, ...], devises: tuple[str, ...],
                       period: str = "5y") -> pd.DataFrame:
    """Matrice de clôtures EUR (index = dates, colonnes = tickers).

    Chaque colonne est convertie en EUR via le taux de change spot courant
    (approximation MVP : pas de série FX historique).
    """
    series = {}
    for ticker, devise in zip(tickers, devises):
        hist = fetch_history(ticker, period=period)
        if hist.empty:
            continue
        close = hist["close"]
        if devise and devise.upper() != BASE_CURRENCY:
            close = close * fetch_fx_rate(devise)
        series[ticker] = close
    if not series:
        return pd.DataFrame()
    return pd.DataFrame(series).sort_index()


@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_benchmark(ticker: str, period: str = "5y") -> pd.Series:
    """Série de clôtures d'un benchmark (déjà en EUR pour les ETF .PA)."""
    hist = fetch_history(ticker, period=period)
    if hist.empty:
        return pd.Series(dtype=float)
    return hist["close"]
