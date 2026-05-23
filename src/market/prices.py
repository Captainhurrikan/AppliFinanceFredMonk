"""Cotations via yfinance, avec cache Streamlit (TTL) et conversion FX en EUR.

Tous les appels passent par le wrapper `safe_fetch` (cf. cache.py) : en cas
d'échec, on renvoie des structures vides plutôt que de planter l'UI.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
import yfinance as yf

from src.config import BASE_CURRENCY, TTL_HISTORY, TTL_INTRADAY
from src.market.cache import FetchStatus, get_yf_session, safe_fetch


def _ticker(symbol: str):
    """yf.Ticker avec session curl_cffi (utilisé pour les métadonnées .info)."""
    return yf.Ticker(symbol, session=get_yf_session())


def _download_close(symbol: str, period: str = "5d", start=None) -> pd.Series:
    """Série de clôtures via `yf.download` (endpoint *chart*, le plus fiable —
    même approche que l'app DCA de référence). Index tz-naïf, vide si rien.

    `yf.download` renvoie parfois des colonnes MultiIndex ('Close', <ticker>) :
    on extrait la colonne Close de façon robuste.
    """
    kwargs = {"progress": False, "auto_adjust": True}
    if start is not None:
        data = yf.download(symbol, start=start, **kwargs)
    else:
        data = yf.download(symbol, period=period, **kwargs)
    if data is None or len(data) == 0:
        return pd.Series(dtype=float)

    cols = data.columns
    if isinstance(cols, pd.MultiIndex):
        if "Close" not in cols.get_level_values(0):
            return pd.Series(dtype=float)
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
    else:
        if "Close" not in cols:
            return pd.Series(dtype=float)
        close = data["Close"]

    close = pd.to_numeric(close, errors="coerce").dropna()
    idx = pd.to_datetime(close.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    close.index = idx
    return close


# --- Métadonnées d'un titre (pour alimenter le référentiel facilement) -----

@st.cache_data(ttl=TTL_HISTORY, show_spinner=False)
def fetch_security_info(ticker: str) -> dict:
    """Récupère libellé, secteur, pays, devise via yfinance pour pré-remplir
    l'ajout d'un nouveau titre. Renvoie {} si indisponible."""
    def _call():
        info = _ticker(ticker).info
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
    """Historique de clôtures ajustées d'un ticker (via yf.download). Index =
    dates, colonne 'close'. DataFrame vide si indisponible."""
    res = safe_fetch(f"history:{ticker}", _download_close, ticker, period)
    if res.status != FetchStatus.OK:
        return pd.DataFrame(columns=["close"])
    return res.data.to_frame("close")


@st.cache_data(ttl=TTL_INTRADAY, show_spinner=False)
def fetch_last_price(ticker: str) -> float | None:
    """Dernier cours connu (devise du titre) via yf.download. None si indispo."""
    res = safe_fetch(f"last:{ticker}", _download_close, ticker, "5d")
    s = res.unwrap()
    if s is None or len(s) == 0:
        return None
    return float(s.iloc[-1])


# --- Conversion de change --------------------------------------------------

@st.cache_data(ttl=TTL_INTRADAY, show_spinner=False)
def fetch_fx_rate(devise: str, base: str = BASE_CURRENCY) -> float:
    """Taux pour convertir `devise` -> `base` (EUR). 1.0 si même devise."""
    if not devise or devise.upper() == base.upper():
        return 1.0
    pair = f"{devise.upper()}{base.upper()}=X"  # ex: USDEUR=X -> EUR par USD

    res = safe_fetch(f"fx:{pair}", _download_close, pair, "5d")
    s = res.unwrap()
    if s is None or len(s) == 0:
        return 1.0
    return float(s.iloc[-1])


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
