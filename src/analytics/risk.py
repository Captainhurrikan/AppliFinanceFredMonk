"""Analyse du risque : diversification, concentration, corrélations, beta,
stress tests simples. Calculs transparents et déterministes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.analytics.performance import beta, daily_returns
from src.config import MAX_POSITION_WEIGHT, MAX_SECTOR_WEIGHT


def weights(valorisations: pd.Series) -> pd.Series:
    """Poids de chaque position (somme = 1)."""
    total = valorisations.sum()
    if total <= 0:
        return valorisations * 0.0
    return valorisations / total


def herfindahl(valorisations: pd.Series) -> float:
    """Indice de Herfindahl-Hirschman (HHI) sur les poids : 0 (diversifié) à 1
    (mono-position). Égal à 1/N pour N positions équipondérées."""
    w = weights(valorisations)
    return float((w ** 2).sum())


def effective_positions(valorisations: pd.Series) -> float:
    """Nombre effectif de positions = 1 / HHI."""
    hhi = herfindahl(valorisations)
    return float(1.0 / hhi) if hhi > 0 else 0.0


def allocation_by(positions: pd.DataFrame, dimension: str,
                  value_col: str = "valorisation") -> pd.DataFrame:
    """Répartition de la valorisation par dimension (secteur, pays, devise...)."""
    if positions.empty or dimension not in positions.columns:
        return pd.DataFrame(columns=[dimension, value_col, "poids"])
    grp = positions.groupby(positions[dimension].fillna("Inconnu"))[value_col].sum()
    total = grp.sum()
    out = grp.reset_index()
    out["poids"] = out[value_col] / total if total > 0 else 0.0
    return out.sort_values(value_col, ascending=False).reset_index(drop=True)


def concentration_alerts(positions: pd.DataFrame) -> list[str]:
    """Alertes de concentration : ligne > 15 %, secteur > 30 %."""
    alerts: list[str] = []
    if positions.empty or "valorisation" not in positions.columns:
        return alerts
    w = weights(positions.set_index("ticker")["valorisation"])
    for ticker, poids in w.items():
        if poids > MAX_POSITION_WEIGHT:
            alerts.append(f"Ligne {ticker} = {poids:.1%} (> {MAX_POSITION_WEIGHT:.0%})")
    if "secteur" in positions.columns:
        sect = allocation_by(positions, "secteur")
        for _, r in sect.iterrows():
            if r["poids"] > MAX_SECTOR_WEIGHT:
                alerts.append(f"Secteur {r['secteur']} = {r['poids']:.1%} "
                              f"(> {MAX_SECTOR_WEIGHT:.0%})")
    return alerts


def correlation_matrix(price_history: pd.DataFrame) -> pd.DataFrame:
    """Matrice de corrélation des rendements quotidiens entre positions."""
    if price_history.empty or price_history.shape[1] < 2:
        return pd.DataFrame()
    rets = price_history.pct_change().dropna(how="all")
    return rets.corr()


def position_betas(price_history: pd.DataFrame, benchmark: pd.Series) -> pd.Series:
    """Beta de chaque ligne vs benchmark (rendements quotidiens)."""
    if price_history.empty or benchmark is None or benchmark.empty:
        return pd.Series(dtype=float)
    bench_ret = daily_returns(benchmark)
    out = {}
    for col in price_history.columns:
        b = beta(daily_returns(price_history[col]), bench_ret)
        if b is not None:
            out[col] = b
    return pd.Series(out)


def portfolio_beta(price_history: pd.DataFrame, valorisations: pd.Series,
                   benchmark: pd.Series) -> float | None:
    """Beta du portefeuille = somme pondérée des betas des lignes."""
    betas = position_betas(price_history, benchmark)
    if betas.empty:
        return None
    w = weights(valorisations)
    common = [t for t in betas.index if t in w.index]
    if not common:
        return None
    return float(sum(betas[t] * w[t] for t in common))


def stress_test(positions: pd.DataFrame, betas: pd.Series,
                scenarios: dict[str, float]) -> pd.DataFrame:
    """Impact estimé de chocs de marché via les betas.

    Pour chaque scénario (choc marché en %), impact ligne = valo × beta × choc.
    MVP : modèle linéaire simple basé sur le beta (pas de saut de corrélation).
    """
    if positions.empty:
        return pd.DataFrame()
    pos = positions.set_index("ticker")
    rows = []
    for nom, choc in scenarios.items():
        impact_total = 0.0
        for ticker, r in pos.iterrows():
            b = betas.get(ticker, 1.0)
            impact_total += r["valorisation"] * b * choc
        val_totale = pos["valorisation"].sum()
        rows.append({
            "Scénario": nom,
            "Choc marché": choc,
            "Impact (€)": impact_total,
            "Impact (%)": impact_total / val_totale if val_totale else 0.0,
            "Valo après choc (€)": val_totale + impact_total,
        })
    return pd.DataFrame(rows)
