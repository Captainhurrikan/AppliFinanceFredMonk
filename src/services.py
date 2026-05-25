"""Couche service : assemble repository (données), market (cotations) et
analytics (calculs) pour fournir aux pages des objets prêts à l'affichage.

C'est ici qu'on enrichit les positions dérivées avec les cours temps réel et
qu'on construit les séries de valorisation et de benchmarks.
"""

from __future__ import annotations

import pandas as pd

from src import config
from src.analytics import performance, portfolio
from src.db import repository
from src.market import prices as market_prices


def get_current_prices(tickers: list[str]) -> dict[str, float]:
    """Dernier cours connu (converti en EUR) par ticker."""
    secs = repository.get_securities().set_index("ticker")
    # On exclut les titres non cotés (parts sociales) : valorisés au PRU.
    listed = tuple(t for t in tickers
                   if not (t in secs.index and secs.loc[t, "type_actif"] == "NON_COTE"))
    # Un seul appel groupé yf.download (évite le rate limit de Yahoo).
    raw = market_prices.fetch_last_prices(listed)
    out: dict[str, float] = {}
    for t, px in raw.items():
        devise = secs.loc[t, "devise"] if t in secs.index else "EUR"
        if devise and devise != config.BASE_CURRENCY:
            px = px * market_prices.fetch_fx_rate(devise)
        out[t] = px
    return out


def get_portfolio_snapshot() -> pd.DataFrame:
    """Positions courantes enrichies des cours, valorisations et +/-values.

    Colonnes : ticker, libelle, secteur, pays, devise, quantite, pru, cours,
    valorisation, cout_total, pv_latente, perf_latente, dividendes, poids,
    pv_realisee.
    """
    ops = repository.get_operations()
    positions = portfolio.build_positions(ops)
    if positions.empty:
        return positions

    secs = repository.get_securities()
    meta_cols = ["ticker", "libelle", "secteur", "pays", "devise"]
    positions = positions.merge(secs[meta_cols], on="ticker", how="left")
    positions["libelle"] = positions["libelle"].fillna(positions["ticker"])

    cours = get_current_prices(positions["ticker"].tolist())
    positions["cours"] = positions["ticker"].map(cours)
    # Repli sur le PRU si le cours est indisponible (UI ne plante pas).
    positions["cours"] = positions["cours"].fillna(positions["pru"])

    positions["valorisation"] = positions["quantite"] * positions["cours"]
    positions["pv_latente"] = positions["valorisation"] - positions["cout_total"]
    positions["perf_latente"] = positions.apply(
        lambda r: (r["cours"] / r["pru"] - 1.0) if r["pru"] else None, axis=1)

    total_valo = positions["valorisation"].sum()
    positions["poids"] = positions["valorisation"] / total_valo if total_valo else 0.0
    return positions.sort_values("valorisation", ascending=False).reset_index(drop=True)


def get_realized_summary() -> pd.DataFrame:
    """Bénéfices réalisés par ligne : plus-value effective + dividendes perçus.

    Inclut les lignes déjà soldées (vendues). Colonnes : ticker, libelle,
    secteur, pv_realisee, dividendes, frais_titre, total_realise.
    """
    ops = repository.get_operations()
    realized = portfolio.realized_summary(ops)
    if realized.empty:
        return realized

    secs = repository.get_securities()
    meta_cols = ["ticker", "libelle", "secteur"]
    realized = realized.merge(secs[meta_cols], on="ticker", how="left")
    realized["libelle"] = realized["libelle"].fillna(realized["ticker"])
    return realized.sort_values("total_realise", ascending=False).reset_index(drop=True)


def get_cash() -> float:
    return portfolio.cash_balance(repository.get_operations())


def get_total_value() -> tuple[float, float, float]:
    """Renvoie (valeur_titres, cash, valeur_totale) en EUR."""
    snap = get_portfolio_snapshot()
    titres = float(snap["valorisation"].sum()) if not snap.empty else 0.0
    cash = get_cash()
    return titres, cash, titres + cash


def get_price_matrix(period: str = "5y") -> pd.DataFrame:
    """Matrice de cours EUR pour tous les tickers détenus (et watchlist)."""
    ops = repository.get_operations()
    positions = portfolio.build_positions(ops)
    if positions.empty:
        return pd.DataFrame()
    secs = repository.get_securities().set_index("ticker")
    # On exclut les titres non cotés (pas d'historique yfinance).
    tickers = [t for t in positions["ticker"].tolist()
               if not (t in secs.index and secs.loc[t, "type_actif"] == "NON_COTE")]
    if not tickers:
        return pd.DataFrame()
    devises = [secs.loc[t, "devise"] if t in secs.index else "EUR" for t in tickers]
    return market_prices.fetch_price_matrix(tuple(tickers), tuple(devises), period=period)


def get_portfolio_history(period: str = "5y") -> pd.DataFrame:
    """Série de valorisation quotidienne du portefeuille (titres + cash + flux)."""
    ops = repository.get_operations()
    if ops.empty:
        return pd.DataFrame()
    px = get_price_matrix(period=period)
    return portfolio.build_value_series(ops, px)


def get_twr_index(period: str = "5y") -> pd.Series:
    hist = get_portfolio_history(period=period)
    if hist.empty:
        return pd.Series(dtype=float)
    return performance.twr_index(hist["total_value"], hist["external_flow"])


def get_benchmark_indices(reference_index: pd.Series,
                          period: str = "5y") -> dict[str, pd.Series]:
    """Indices de croissance des benchmarks, rebasés sur la période de
    `reference_index` (mêmes dates de départ pour comparaison équitable)."""
    if reference_index is None or reference_index.empty:
        return {}
    start = reference_index.index[0]
    out: dict[str, pd.Series] = {}
    for nom, ticker in config.BENCHMARKS.items():
        serie = market_prices.fetch_benchmark(ticker, period=period)
        if serie.empty:
            continue
        serie = serie[serie.index >= start]
        if serie.empty or serie.iloc[0] == 0:
            continue
        out[nom] = serie / serie.iloc[0]  # rebasé à 1.0
    return out


def get_mwr_cashflows() -> list[tuple]:
    """Flux datés pour le MWR (XIRR) : dépôts négatifs, valeur finale positive."""
    ops = repository.get_operations()
    if ops.empty:
        return []
    flows: list[tuple] = []
    for _, r in ops.iterrows():
        d = r["date"].date() if hasattr(r["date"], "date") else r["date"]
        if r["type"] == "DEPOSIT":
            flows.append((d, -float(r["montant_brut"])))
        elif r["type"] == "WITHDRAW":
            flows.append((d, float(r["montant_brut"])))
    _, _, total = get_total_value()
    flows.append((pd.Timestamp.today().date(), float(total)))
    return flows
