"""Tests unitaires de la dérivation du portefeuille (cas connus).

Couvre les positions (PRU CMP) et les bénéfices réalisés (plus-value effective
+ dividendes), y compris les lignes totalement soldées.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.analytics import portfolio


def _ops(rows: list[dict]) -> pd.DataFrame:
    """Construit une table `operations` minimale pour les tests."""
    base = {
        "id": 0, "ticker": None, "type": "BUY", "date": "2024-01-01",
        "quantite": 0.0, "prix_unitaire": 0.0, "montant_brut": 0.0, "frais": 0.0,
    }
    df = pd.DataFrame([{**base, **r} for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df


# --- Bénéfices réalisés ----------------------------------------------------

def test_realized_summary_vente_et_dividende():
    # Achat 10 @ 100 (frais 5) -> coût 1005, PRU 100,5
    # Vente 10 @ 120 (frais 5) -> net 1195 ; PV = 1195 - 1005 = 190
    # Dividende brut 50 (frais 0) -> 50
    ops = _ops([
        {"id": 1, "ticker": "AIR.PA", "type": "BUY", "date": "2024-01-02",
         "quantite": 10, "prix_unitaire": 100, "frais": 5},
        {"id": 2, "ticker": "AIR.PA", "type": "DIV", "date": "2024-03-01",
         "montant_brut": 50},
        {"id": 3, "ticker": "AIR.PA", "type": "SELL", "date": "2024-06-01",
         "quantite": 10, "prix_unitaire": 120, "frais": 5},
    ])
    summary = portfolio.realized_summary(ops)
    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["pv_realisee"] == pytest.approx(190.0)
    assert row["dividendes"] == pytest.approx(50.0)
    assert row["total_realise"] == pytest.approx(240.0)


def test_realized_summary_inclut_lignes_soldees():
    # Ligne entièrement vendue : absente de build_positions, présente ici.
    ops = _ops([
        {"id": 1, "ticker": "SOLD.PA", "type": "BUY", "date": "2024-01-02",
         "quantite": 5, "prix_unitaire": 100},
        {"id": 2, "ticker": "SOLD.PA", "type": "SELL", "date": "2024-02-02",
         "quantite": 5, "prix_unitaire": 110},
    ])
    assert portfolio.build_positions(ops).empty
    summary = portfolio.realized_summary(ops)
    assert len(summary) == 1
    assert summary.iloc[0]["pv_realisee"] == pytest.approx(50.0)


def test_realized_summary_exclut_titres_sans_realise():
    # Position simplement détenue (aucune vente, aucun dividende) -> exclue.
    ops = _ops([
        {"id": 1, "ticker": "HOLD.PA", "type": "BUY", "date": "2024-01-02",
         "quantite": 3, "prix_unitaire": 50},
    ])
    assert portfolio.realized_summary(ops).empty


def test_realized_summary_vide_si_pas_operations():
    assert portfolio.realized_summary(pd.DataFrame()).empty


def test_realized_pnl_egal_somme_pv_realisee():
    ops = _ops([
        {"id": 1, "ticker": "A.PA", "type": "BUY", "date": "2024-01-02",
         "quantite": 10, "prix_unitaire": 100},
        {"id": 2, "ticker": "A.PA", "type": "SELL", "date": "2024-06-01",
         "quantite": 10, "prix_unitaire": 120},
        {"id": 3, "ticker": "B.PA", "type": "BUY", "date": "2024-01-02",
         "quantite": 5, "prix_unitaire": 200},
        {"id": 4, "ticker": "B.PA", "type": "SELL", "date": "2024-06-01",
         "quantite": 5, "prix_unitaire": 180},
    ])
    # A : +200 ; B : -100 -> total +100
    assert portfolio.realized_pnl(ops) == pytest.approx(100.0)
