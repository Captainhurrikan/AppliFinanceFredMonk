"""Signaux d'aide à la décision : techniques (explicites, jamais en boîte noire)
et fondamentaux, plus alertes de prise de bénéfices / stop-loss et watchlist.

L'outil AIDE à décider — il ne génère aucune recommandation automatique
d'achat/vente.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import DEFAULT_PROFIT_TAKE, DEFAULT_STOP_LOSS


# --- Indicateurs techniques (transparents) ---------------------------------

def rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """RSI de Wilder sur `period` jours (lissage exponentiel des gains/pertes)."""
    delta = prices.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.fillna(100.0)


def moving_averages(prices: pd.Series, windows: tuple[int, ...] = (50, 200)) -> pd.DataFrame:
    """Moyennes mobiles simples pour les fenêtres demandées."""
    return pd.DataFrame({f"MM{w}": prices.rolling(w).mean() for w in windows})


def golden_death_cross(prices: pd.Series, short: int = 50, long: int = 200) -> str | None:
    """Détecte un croisement MM court / MM long sur la dernière séance.

    Renvoie 'golden' (MM50 passe au-dessus MM200), 'death' (inverse) ou None.
    """
    if len(prices) < long + 1:
        return None
    ma_s = prices.rolling(short).mean()
    ma_l = prices.rolling(long).mean()
    diff = ma_s - ma_l
    if diff.iloc[-2] <= 0 < diff.iloc[-1]:
        return "golden"
    if diff.iloc[-2] >= 0 > diff.iloc[-1]:
        return "death"
    return None


def distance_to_52w_high(prices: pd.Series) -> float | None:
    """Distance (fraction négative) entre le cours actuel et le plus haut 52 sem."""
    window = prices.tail(252)
    if window.empty:
        return None
    high = window.max()
    if high == 0:
        return None
    return float(prices.iloc[-1] / high - 1.0)


def technical_snapshot(prices: pd.Series) -> dict:
    """Synthèse technique d'un titre (RSI, MM, croisement, distance 52 sem)."""
    if prices is None or prices.empty:
        return {}
    prices = prices.dropna()
    ma = moving_averages(prices)
    last = prices.iloc[-1]
    rsi_series = rsi(prices)
    return {
        "cours": float(last),
        "rsi14": float(rsi_series.iloc[-1]) if not rsi_series.empty else None,
        "mm50": float(ma["MM50"].iloc[-1]) if not ma["MM50"].isna().all() else None,
        "mm200": float(ma["MM200"].iloc[-1]) if not ma["MM200"].isna().all() else None,
        "croisement": golden_death_cross(prices),
        "dist_52w_high": distance_to_52w_high(prices),
    }


# --- Alertes prise de bénéfices / stop-loss --------------------------------

def position_alerts(
    positions: pd.DataFrame,
    profit_take: float = DEFAULT_PROFIT_TAKE,
    stop_loss: float = DEFAULT_STOP_LOSS,
    custom: dict[str, dict] | None = None,
) -> list[dict]:
    """Alertes par ligne basées sur la +/-value latente vs PRU.

    `custom` : seuils par ticker, ex {'AIR.PA': {'profit_take': 0.4}}.
    Renvoie une liste de dicts {ticker, type, perf, seuil, message}.
    """
    custom = custom or {}
    alerts: list[dict] = []
    if positions.empty or "perf_latente" not in positions.columns:
        return alerts
    for _, r in positions.iterrows():
        ticker = r["ticker"]
        perf = r["perf_latente"]
        if perf is None or pd.isna(perf):
            continue
        pt = custom.get(ticker, {}).get("profit_take", profit_take)
        sl = custom.get(ticker, {}).get("stop_loss", stop_loss)
        if perf >= pt:
            alerts.append({"ticker": ticker, "type": "PROFIT_TAKE", "perf": perf,
                           "seuil": pt,
                           "message": f"{ticker} : +{perf:.1%} (≥ {pt:.0%}) — envisager une prise de bénéfices"})
        elif perf <= sl:
            alerts.append({"ticker": ticker, "type": "STOP_LOSS", "perf": perf,
                           "seuil": sl,
                           "message": f"{ticker} : {perf:.1%} (≤ {sl:.0%}) — stop-loss mental atteint"})
    return alerts


def watchlist_alerts(watchlist: pd.DataFrame, current_prices: dict[str, float]) -> list[dict]:
    """Alerte quand le cours atteint un prix cible d'achat/vente de la watchlist."""
    alerts: list[dict] = []
    if watchlist.empty:
        return alerts
    for _, r in watchlist.iterrows():
        ticker = r["ticker"]
        cours = current_prices.get(ticker)
        if cours is None:
            continue
        cible_achat = r.get("prix_cible_achat")
        cible_vente = r.get("prix_cible_vente")
        if cible_achat and pd.notna(cible_achat) and cours <= cible_achat:
            alerts.append({"ticker": ticker, "type": "CIBLE_ACHAT", "cours": cours,
                           "cible": cible_achat,
                           "message": f"{ticker} : {cours:.2f} ≤ cible d'achat {cible_achat:.2f}"})
        if cible_vente and pd.notna(cible_vente) and cours >= cible_vente:
            alerts.append({"ticker": ticker, "type": "CIBLE_VENTE", "cours": cours,
                           "cible": cible_vente,
                           "message": f"{ticker} : {cours:.2f} ≥ cible de vente {cible_vente:.2f}"})
    return alerts


# --- Signaux fondamentaux --------------------------------------------------

def fundamental_signals(fundamentals: dict) -> list[dict]:
    """Signaux fondamentaux simples et explicites à partir des ratios connus."""
    signals: list[dict] = []
    if not fundamentals:
        return signals
    per = fundamentals.get("per")
    dy = fundamentals.get("dividende_yield")
    payout = fundamentals.get("payout_ratio")
    roe = fundamentals.get("roe")
    dette = fundamentals.get("ratio_dette_eq")

    if per is not None and per > 0 and per < 12:
        signals.append({"type": "VALUE", "favorable": True,
                        "message": f"PER faible ({per:.1f}) — valorisation attractive"})
    if dy is not None and dy > 0.04:
        signals.append({"type": "INCOME", "favorable": True,
                        "message": f"Rendement élevé ({dy:.1%})"})
    if payout is not None and 0 < payout < 0.7:
        signals.append({"type": "INCOME", "favorable": True,
                        "message": f"Payout sain ({payout:.0%}) — dividende soutenable"})
    if payout is not None and payout > 1.0:
        signals.append({"type": "INCOME", "favorable": False,
                        "message": f"Payout > 100 % ({payout:.0%}) — dividende non couvert"})
    if roe is not None and roe > 0.15:
        signals.append({"type": "QUALITY", "favorable": True,
                        "message": f"ROE élevé ({roe:.1%}) — rentabilité solide"})
    if dette is not None and dette > 2.0:
        signals.append({"type": "RISK", "favorable": False,
                        "message": f"Endettement élevé (D/E {dette:.1f})"})
    return signals


def _score_band(value, thresholds, scores) -> int:
    """Attribue un score selon des paliers (transparents). `thresholds` croissants."""
    if value is None or pd.isna(value):
        return 0
    for thr, sc in zip(thresholds, scores):
        if value <= thr:
            return sc
    return scores[-1]


def fundamental_score(fundamentals: dict) -> dict:
    """Score synthétique Value / Quality / Growth / Income sur 0-100.

    Algorithme volontairement SIMPLE et TRANSPARENT (cf. CLAUDE.md) : chaque
    pilier agrège quelques ratios via des paliers explicites. Un ratio manquant
    contribue de façon neutre. Aucune boîte noire, aucun ML.
    """
    f = fundamentals or {}

    # VALUE : PER bas, P/B bas, EV/EBITDA bas = mieux.
    per = f.get("per")
    pb = f.get("price_to_book")
    ev = f.get("ev_ebitda")
    value = np.mean([
        _score_band(per, [10, 15, 20, 30], [100, 75, 50, 25, 0]) if per and per > 0 else 50,
        _score_band(pb, [1, 2, 3, 5], [100, 75, 50, 25, 0]) if pb and pb > 0 else 50,
        _score_band(ev, [6, 10, 14, 20], [100, 75, 50, 25, 0]) if ev and ev > 0 else 50,
    ])

    # QUALITY : ROE, ROIC, marge opérationnelle élevés = mieux.
    roe = f.get("roe")
    roic = f.get("roic")
    marge = f.get("marge_op")
    quality = np.mean([
        _score_band(-roe if roe is not None else None, [-0.20, -0.15, -0.10, -0.05], [100, 75, 50, 25, 0]) if roe is not None else 50,
        _score_band(-roic if roic is not None else None, [-0.15, -0.10, -0.07, -0.04], [100, 75, 50, 25, 0]) if roic is not None else 50,
        _score_band(-marge if marge is not None else None, [-0.25, -0.15, -0.10, -0.05], [100, 75, 50, 25, 0]) if marge is not None else 50,
    ])

    # GROWTH : croissance CA et EPS élevées = mieux.
    ca_g = f.get("ca_growth")
    eps_g = f.get("eps_growth")
    growth = np.mean([
        _score_band(-ca_g if ca_g is not None else None, [-0.15, -0.10, -0.05, 0], [100, 75, 50, 25, 0]) if ca_g is not None else 50,
        _score_band(-eps_g if eps_g is not None else None, [-0.15, -0.10, -0.05, 0], [100, 75, 50, 25, 0]) if eps_g is not None else 50,
    ])

    # INCOME : rendement élevé + payout soutenable = mieux.
    dy = f.get("dividende_yield")
    payout = f.get("payout_ratio")
    dy_score = _score_band(-dy if dy is not None else None, [-0.05, -0.03, -0.02, -0.01], [100, 75, 50, 25, 0]) if dy is not None else 0
    payout_score = 100 if payout is not None and 0 < payout < 0.6 else (50 if payout is not None and payout < 0.8 else (0 if payout is not None else 50))
    income = np.mean([dy_score, payout_score])

    piliers = {
        "Value": round(float(value), 1),
        "Quality": round(float(quality), 1),
        "Growth": round(float(growth), 1),
        "Income": round(float(income), 1),
    }
    piliers["Global"] = round(float(np.mean(list(piliers.values()))), 1)
    return piliers
