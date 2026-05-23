"""Smoke tests des pages Streamlit via AppTest, avec données de marché simulées.

On remplace les appels réseau (yfinance / RSS) par des données synthétiques
déterministes pour vérifier que chaque page s'exécute sans exception, à la fois
sur le chemin "données présentes" et indirectement sur la robustesse globale.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.db.seed import seed_demo_data
from src.market import fundamentals as fonda
from src.market import news as news_mod
from src.market import prices as market_prices

PAGES = [
    "src/pages/1_dashboard.py",
    "src/pages/2_positions.py",
    "src/pages/3_operations.py",
    "src/pages/4_performance.py",
    "src/pages/5_analyse_fonda.py",
    "src/pages/6_risque.py",
    "src/pages/7_opportunites.py",
]


def _synthetic_close(start="2024-01-01", base=100.0, drift=0.0004, seed=0):
    idx = pd.bdate_range(start=start, end=pd.Timestamp.today().normalize())
    rng = np.random.default_rng(seed)
    steps = drift + rng.normal(0, 0.01, len(idx))
    close = base * np.cumprod(1 + steps)
    return pd.Series(close, index=idx, name="close")


@pytest.fixture(autouse=True)
def _stub_market(monkeypatch):
    seed_demo_data(force=True)

    def fake_history(ticker, period="5y"):
        return _synthetic_close(seed=abs(hash(ticker)) % 1000).to_frame("close")

    def fake_last_price(ticker):
        return float(_synthetic_close(seed=abs(hash(ticker)) % 1000).iloc[-1])

    def fake_fx(devise, base="EUR"):
        return 1.0

    def fake_matrix(tickers, devises, period="5y"):
        return pd.DataFrame({t: _synthetic_close(seed=abs(hash(t)) % 1000) for t in tickers})

    def fake_benchmark(ticker, period="5y"):
        return _synthetic_close(seed=abs(hash(ticker)) % 1000)

    def fake_info(ticker):
        return {"ticker": ticker, "libelle": ticker, "secteur": "Tech",
                "pays": "France", "devise": "EUR", "type_actif": "ACTION"}

    def fake_fundamentals(ticker, force_refresh=False):
        return {"per": 15.0, "per_forward": 13.0, "peg": 1.2, "price_to_book": 2.5,
                "ev_ebitda": 11.0, "dividende_yield": 0.03, "payout_ratio": 0.5,
                "ratio_dette_eq": 0.8, "current_ratio": 1.5, "roe": 0.18,
                "roic": 0.12, "marge_op": 0.2, "marge_nette": 0.15,
                "ca_growth": 0.08, "eps_growth": 0.1, "secteur": "Tech"}

    def fake_dividends(ticker):
        idx = pd.date_range("2016-01-01", periods=10, freq="YE")
        return pd.Series(np.linspace(1.0, 2.0, 10), index=idx)

    monkeypatch.setattr(market_prices, "fetch_history", fake_history)
    monkeypatch.setattr(market_prices, "fetch_last_price", fake_last_price)
    monkeypatch.setattr(market_prices, "fetch_fx_rate", fake_fx)
    monkeypatch.setattr(market_prices, "fetch_price_matrix", fake_matrix)
    monkeypatch.setattr(market_prices, "fetch_benchmark", fake_benchmark)
    monkeypatch.setattr(market_prices, "fetch_security_info", fake_info)
    monkeypatch.setattr(fonda, "get_fundamentals", fake_fundamentals)
    monkeypatch.setattr(fonda, "get_dividend_history", fake_dividends)
    monkeypatch.setattr(news_mod, "fetch_news", lambda query, limit=8: [])
    yield


@pytest.mark.parametrize("page", PAGES)
def test_page_runs_without_exception(page):
    at = AppTest.from_file(page, default_timeout=60).run()
    assert not at.exception, f"Exception sur {page} : {at.exception}"


def test_entrypoint_boots_default_page():
    at = AppTest.from_file("streamlit_app.py", default_timeout=60).run()
    assert not at.exception, f"Exception sur l'entrypoint : {at.exception}"
