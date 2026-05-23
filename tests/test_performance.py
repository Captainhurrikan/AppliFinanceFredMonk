"""Tests unitaires des calculs financiers (cas connus).

Couvre TWR, MWR/XIRR, volatilité, max drawdown et beta.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from src.analytics import performance as perf


def _series(values, start="2024-01-01"):
    idx = pd.bdate_range(start=start, periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


# --- TWR -------------------------------------------------------------------

def test_twr_simple_growth_no_flows():
    # 100 -> 110 -> 121 : +10 % puis +10 % => +21 %
    values = _series([100, 110, 121])
    assert perf.twr(values) == pytest.approx(0.21, abs=1e-9)


def test_twr_neutralise_les_apports():
    # Apport le jour 0 (100), +10 %, puis apport de 500 sans variation de marché.
    values = _series([100, 110, 610])
    flows = _series([100, 0, 500])
    # Le TWR ne doit refléter que la performance de marché (+10 %).
    assert perf.twr(values, flows) == pytest.approx(0.10, abs=1e-9)


def test_twr_index_rebase_a_un():
    values = _series([100, 110, 121])
    idx = perf.twr_index(values)
    assert idx.iloc[0] == pytest.approx(1.0)
    assert idx.iloc[-1] == pytest.approx(1.21, abs=1e-9)


def test_twr_apport_jour_initial():
    # Premier jour = dépôt qui finance l'achat : rendement initial = 0.
    values = _series([1000, 1100])
    flows = _series([1000, 0])
    assert perf.twr(values, flows) == pytest.approx(0.10, abs=1e-9)


# --- MWR / XIRR ------------------------------------------------------------

def test_xirr_un_an_dix_pourcent():
    flows = [(dt.date(2024, 1, 1), -1000.0), (dt.date(2025, 1, 1), 1100.0)]
    rate = perf.xirr(flows)
    assert rate == pytest.approx(0.10, abs=1e-3)


def test_xirr_avec_apport_intermediaire():
    # Investit 1000, ajoute 1000 à 6 mois, vaut 2200 à 1 an.
    flows = [
        (dt.date(2024, 1, 1), -1000.0),
        (dt.date(2024, 7, 1), -1000.0),
        (dt.date(2025, 1, 1), 2200.0),
    ]
    rate = perf.xirr(flows)
    assert rate is not None and rate > 0


def test_xirr_sans_changement_de_signe_renvoie_none():
    flows = [(dt.date(2024, 1, 1), -1000.0), (dt.date(2025, 1, 1), -500.0)]
    assert perf.xirr(flows) is None


def test_xnpv_zero_au_taux_solution():
    flows = [(dt.date(2024, 1, 1), -1000.0), (dt.date(2025, 1, 1), 1100.0)]
    rate = perf.xirr(flows)
    assert perf.xnpv(rate, flows) == pytest.approx(0.0, abs=1e-4)


# --- Volatilité ------------------------------------------------------------

def test_volatilite_annualisee():
    rets = pd.Series([0.01, -0.01, 0.02, -0.02, 0.015])
    expected = rets.std(ddof=1) * np.sqrt(252)
    assert perf.annualized_volatility(rets) == pytest.approx(expected)


def test_volatilite_serie_constante_est_nulle():
    rets = pd.Series([0.0, 0.0, 0.0])
    assert perf.annualized_volatility(rets) == 0.0


# --- Max drawdown ----------------------------------------------------------

def test_max_drawdown_cas_connu():
    # 100 -> 120 -> 90 -> 110 : pire chute depuis le pic 120 vers 90 = -25 %.
    values = _series([100, 120, 90, 110])
    assert perf.max_drawdown(values) == pytest.approx(-0.25, abs=1e-9)


def test_drawdown_nul_si_monotone_croissant():
    values = _series([100, 110, 120, 130])
    assert perf.max_drawdown(values) == pytest.approx(0.0)


def test_drawdown_series_longueur():
    values = _series([100, 120, 90, 110])
    dd = perf.drawdown_series(values)
    assert len(dd) == 4
    assert dd.iloc[2] == pytest.approx(-0.25, abs=1e-9)


# --- Beta ------------------------------------------------------------------

def test_beta_egal_un_si_identique():
    bench = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
    assert perf.beta(bench, bench) == pytest.approx(1.0, abs=1e-9)


def test_beta_double_amplitude():
    bench = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
    port = bench * 2.0
    assert perf.beta(port, bench) == pytest.approx(2.0, abs=1e-9)


def test_beta_donnees_insuffisantes():
    assert perf.beta(pd.Series([0.01]), pd.Series([0.01])) is None


# --- Rendements mensuels ---------------------------------------------------

def test_monthly_returns_table_structure():
    values = _series(list(range(100, 200)), start="2024-01-01")
    table = perf.monthly_returns_table(values)
    assert not table.empty
    assert "Année" in table.columns


def test_period_return():
    values = _series([100, 105, 110, 120], start="2024-01-01")
    # période couvrant tout l'historique
    assert perf.period_return(values, days=3650) == pytest.approx(0.20, abs=1e-9)
