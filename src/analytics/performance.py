"""Calculs de performance et de risque temporels (purs, sans dépendance UI).

Indicateurs : TWR, MWR (XIRR), volatilité annualisée, max drawdown, beta,
rendements mensuels. Module conçu pour être testable unitairement (cf.
tests/test_performance.py).

Conventions documentées (voir aussi CLAUDE.md) :
- TWR : on chaîne les rendements quotidiens en neutralisant les flux externes
  (dépôts/retraits). Hypothèse : un flux externe du jour t intervient en début
  de journée, donc r_t = V_t / (V_{t-1} + F_t) - 1.
- MWR : équivalent IRR sur flux datés (XIRR), résolu par scipy.optimize.brentq.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR


# --- Rendements ------------------------------------------------------------

def daily_returns(values: pd.Series) -> pd.Series:
    """Rendements simples jour à jour d'une série de valeurs."""
    return values.pct_change().dropna()


def twr_index(values: pd.Series, external_flows: pd.Series | None = None) -> pd.Series:
    """Indice de croissance TWR rebasé à 1.0.

    `values` : valeur totale du portefeuille (titres + cash) en fin de journée.
    `external_flows` : flux externes nets (dépôt > 0, retrait < 0), alignés sur
    l'index de `values`. Un flux du jour t est supposé intervenir en début de
    journée (avant variation de marché).
    """
    values = values.dropna()
    if values.empty:
        return pd.Series(dtype=float)
    if external_flows is None:
        external_flows = pd.Series(0.0, index=values.index)
    flows = external_flows.reindex(values.index).fillna(0.0)

    prev = values.shift(1)
    # Rendement quotidien neutralisant le flux entrant du jour.
    denom = prev + flows
    daily = values / denom - 1.0
    daily.iloc[0] = 0.0  # première observation = base
    daily = daily.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return (1.0 + daily).cumprod()


def twr(values: pd.Series, external_flows: pd.Series | None = None) -> float:
    """Time-Weighted Return total sur toute la période (en fraction)."""
    idx = twr_index(values, external_flows)
    if idx.empty:
        return 0.0
    return float(idx.iloc[-1] - 1.0)


def _year_fraction(d0: date, d1: date) -> float:
    return (d1 - d0).days / 365.0


def xnpv(rate: float, cashflows: list[tuple[date, float]]) -> float:
    """Valeur actuelle nette de flux datés (convention actes/365)."""
    if rate <= -1.0:
        return float("inf")
    t0 = cashflows[0][0]
    return sum(cf / (1.0 + rate) ** _year_fraction(t0, t) for t, cf in cashflows)


def xirr(cashflows: list[tuple[date, float]],
         low: float = -0.9999, high: float = 10.0) -> float | None:
    """Taux de rendement interne sur flux datés (MWR), via brentq.

    `cashflows` : liste (date, montant) du point de vue de l'investisseur :
    dépôt = négatif (sortie de poche), retrait/valeur finale = positif.
    Renvoie None si non résoluble (pas de changement de signe, etc.).
    """
    from scipy.optimize import brentq

    flows = sorted(((_to_date(d), float(v)) for d, v in cashflows), key=lambda x: x[0])
    amounts = [v for _, v in flows]
    if not amounts or min(amounts) >= 0 or max(amounts) <= 0:
        return None  # XIRR exige au moins un flux négatif et un positif

    f = lambda r: xnpv(r, flows)
    try:
        f_low, f_high = f(low), f(high)
        if np.isnan(f_low) or np.isnan(f_high) or f_low * f_high > 0:
            return None
        return float(brentq(f, low, high, maxiter=1000))
    except (ValueError, RuntimeError):
        return None


def mwr(cashflows: list[tuple[date, float]]) -> float | None:
    """Alias explicite : Money-Weighted Return = XIRR des flux."""
    return xirr(cashflows)


# --- Risque temporel -------------------------------------------------------

def annualized_volatility(returns: pd.Series,
                          periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Volatilité annualisée = écart-type des rendements quotidiens × √périodes."""
    returns = returns.dropna()
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))


def drawdown_series(value_index: pd.Series) -> pd.Series:
    """Série du drawdown courant (fraction négative) d'un indice de valeur."""
    value_index = value_index.dropna()
    if value_index.empty:
        return pd.Series(dtype=float)
    running_max = value_index.cummax()
    return value_index / running_max - 1.0


def max_drawdown(value_index: pd.Series) -> float:
    """Drawdown maximal (valeur négative, ex : -0.32 = -32 %)."""
    dd = drawdown_series(value_index)
    if dd.empty:
        return 0.0
    return float(dd.min())


def beta(portfolio_returns: pd.Series, benchmark_returns: pd.Series) -> float | None:
    """Beta = cov(port, bench) / var(bench), sur l'intersection des dates."""
    df = pd.concat([portfolio_returns, benchmark_returns], axis=1, join="inner").dropna()
    if len(df) < 2:
        return None
    p, b = df.iloc[:, 0], df.iloc[:, 1]
    var_b = b.var(ddof=1)
    if var_b == 0:
        return None
    return float(p.cov(b) / var_b)


def cumulative_return(value_index: pd.Series) -> float:
    vi = value_index.dropna()
    if len(vi) < 2 or vi.iloc[0] == 0:
        return 0.0
    return float(vi.iloc[-1] / vi.iloc[0] - 1.0)


def period_return(value_index: pd.Series, days: int) -> float | None:
    """Rendement sur les `days` derniers jours calendaires de l'indice."""
    vi = value_index.dropna()
    if vi.empty:
        return None
    end = vi.index[-1]
    start_target = end - pd.Timedelta(days=days)
    window = vi[vi.index <= start_target]
    # Si la fenêtre demandée précède le début de l'historique, on rebase sur
    # la première valeur disponible (rendement depuis l'origine).
    start_val = window.iloc[-1] if not window.empty else vi.iloc[0]
    if start_val == 0:
        return None
    return float(vi.iloc[-1] / start_val - 1.0)


def monthly_returns_table(value_index: pd.Series) -> pd.DataFrame:
    """Tableau année × mois des rendements mensuels (à partir d'un indice TWR)."""
    vi = value_index.dropna()
    if vi.empty:
        return pd.DataFrame()
    monthly = (1.0 + daily_returns(vi)).resample("ME").prod() - 1.0
    if monthly.empty:
        return pd.DataFrame()
    table = monthly.to_frame("ret")
    table["year"] = table.index.year
    table["month"] = table.index.month
    pivot = table.pivot_table(index="year", columns="month", values="ret")
    pivot = pivot.reindex(columns=range(1, 13))
    mois = ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun",
            "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"]
    pivot.columns = mois
    pivot["Année"] = (1.0 + monthly).groupby(monthly.index.year).prod() - 1.0
    return pivot


# --- Utilitaires -----------------------------------------------------------

def _to_date(d: date | datetime | str | pd.Timestamp) -> date:
    if isinstance(d, str):
        return datetime.strptime(d[:10], "%Y-%m-%d").date()
    if isinstance(d, pd.Timestamp):
        return d.date()
    if isinstance(d, datetime):
        return d.date()
    return d
