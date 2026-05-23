"""Fondamentaux via yfinance (source primaire), persistés dans la table
`fondamentaux_cache` avec TTL applicatif de 24 h.

Scraping de secours (Yahoo HTML) prévu mais activé uniquement si yfinance ne
couvre pas — avec User-Agent réaliste et rate limiting (cf. config).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import yfinance as yf

from src.config import TTL_FUNDAMENTALS
from src.db import repository
from src.market.cache import get_yf_session, safe_fetch


def _ticker(symbol: str):
    return yf.Ticker(symbol, session=get_yf_session())


def _safe_div(a, b):
    try:
        if a is None or b in (None, 0):
            return None
        return a / b
    except (TypeError, ZeroDivisionError):
        return None


def _extract_from_info(info: dict) -> dict:
    """Mappe le dict yfinance `info` vers nos champs normalisés."""
    if not info:
        return {}
    return {
        "per": info.get("trailingPE"),
        "per_forward": info.get("forwardPE"),
        "peg": info.get("pegRatio") or info.get("trailingPegRatio"),
        "price_to_book": info.get("priceToBook"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "dividende_yield": info.get("dividendYield"),
        "payout_ratio": info.get("payoutRatio"),
        "ratio_dette_eq": _safe_div(info.get("debtToEquity"), 100.0)
                          if info.get("debtToEquity") else None,
        "current_ratio": info.get("currentRatio"),
        "roe": info.get("returnOnEquity"),
        "roic": None,  # non fourni par yfinance.info ; laissé à l'enrichissement
        "marge_op": info.get("operatingMargins"),
        "marge_nette": info.get("profitMargins"),
        "ca_growth": info.get("revenueGrowth"),
        "eps_growth": info.get("earningsGrowth"),
        "div_growth_5a": info.get("fiveYearAvgDividendYield"),
        "secteur": info.get("sector"),
    }


def _fetch_yfinance(ticker: str) -> dict:
    def _call():
        return _ticker(ticker).info

    res = safe_fetch(f"fundamentals:{ticker}", _call)
    if not res.ok or not res.data:
        return {}
    return _extract_from_info(res.data)


def get_fundamentals(ticker: str, force_refresh: bool = False) -> dict:
    """Renvoie les fondamentaux d'un ticker. Sert le cache SQLite si frais
    (< 24 h), sinon rafraîchit via yfinance et persiste."""
    cached = repository.get_fundamentals_cache(ticker)
    if cached and not force_refresh:
        try:
            age = datetime.now() - datetime.fromisoformat(cached["date_maj"])
            if age < timedelta(seconds=TTL_FUNDAMENTALS):
                return cached
        except (ValueError, TypeError):
            pass

    data = _fetch_yfinance(ticker)
    if data:
        repository.upsert_fundamentals(ticker, data, source="yfinance")
        return repository.get_fundamentals_cache(ticker) or data
    return cached or {}


@st.cache_data(ttl=TTL_FUNDAMENTALS, show_spinner=False)
def get_dividend_history(ticker: str) -> pd.Series:
    """Historique des dividendes (par date de détachement)."""
    def _call():
        return _ticker(ticker).dividends

    res = safe_fetch(f"dividends:{ticker}", _call)
    div = res.unwrap()
    if div is None or len(div) == 0:
        return pd.Series(dtype=float)
    div.index = pd.to_datetime(div.index).tz_localize(None)
    return div


def sector_medians(tickers: list[str]) -> pd.DataFrame:
    """Médianes par secteur des ratios des titres fournis (comparaison interne).

    MVP : utilise les fondamentaux déjà en cache plutôt qu'un scraping sectoriel
    externe. À raffiner (scraping de médianes sectorielles) dans une itération
    ultérieure.
    """
    rows = []
    for t in tickers:
        f = repository.get_fundamentals_cache(t)
        if f and f.get("secteur"):
            rows.append(f)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    metrics = ["per", "price_to_book", "ev_ebitda", "dividende_yield", "roe", "marge_op"]
    metrics = [m for m in metrics if m in df.columns]
    return df.groupby("secteur")[metrics].median(numeric_only=True)
