"""Tests de l'import des exports broker (parsing + import complet)."""

from __future__ import annotations

import pytest

from src import broker_import as bi
from src.analytics import portfolio
from src.db import repository

ORDERS_CSV = """Carnet d'ordres
Export du 23/05/26 à 14h30
Compte N° 17515900003480065600151 MR GIOFFRE FREDERIC
Type d'ordre : Tous les ordres

Libellé Valeur;Code Valeur;Type d'actifs;Date de saisie;Sens;Devise cours;Quantité/Montant;Type de règlement;Type d'ordre;Lim./Cours exécuté;Date de validité;Statut;Date de statut
AIR LIQUIDE;FR0000120073;ACTIONS ET OBLIGATIONS;22/05/26;Achat;EUR;20;CP;LIM;181,78;29/05/26;Exécuté;22/05/26
AIR LIQUIDE;FR0000120073;ACTIONS ET OBLIGATIONS;22/05/26;Achat;EUR;20;CP;LIM;181,30;22/05/26;Annulé;22/05/26
INNATE PHARMA;FR0010331421;ACTIONS ET OBLIGATIONS;22/05/26;Vente;EUR;2 000;CP;LIM;1,648;22/05/26;Exécuté;22/05/26
RENAULT;FR0000131906;ACTIONS ET OBLIGATIONS;22/05/26;Vente;EUR;50;CP;LIM;27,75;22/05/26;Exécuté;22/05/26
"""

PORTFOLIO_CSV = """Portefeuille comptes titres
Export du 23/05/26 à 14h30
Compte N° 17515900003480065600151 MR GIOFFRE FREDERIC
Position au 23/05/26 à 14h30

Libellé Valeur;Code Valeur;Quantité;Devise cours;Cours/VL;Valorisation EUR;Prix d'acquisition moyen EUR;+/- value latente EUR;% Actif
METROPOLE TELEVISION Titres en portefeuille;FR0000053225;400;EUR;11,50;4 600,00;12,26;-303,72;14,87 %
AIR LIQUIDE Titres en portefeuille;FR0000120073;20;EUR;180,38;3 607,60;183,42;-60,71;11,66 %
CEIDF VAL DE MARNE Titres en portefeuille;QS0007946807;513;EUR;20,00;10 260,00;;;33,17 %
TOTAL ACTIONS;;;;;30 930,10;; -402,56;100,00 %

Evaluation Titres : 30 930,10 EUR
Liquidités : 1 150,49 EUR
Total des actifs : 32 080,59 EUR
"""


def _orders_bytes():
    return ORDERS_CSV.encode("cp1252")


def _portfolio_bytes():
    return PORTFOLIO_CSV.encode("cp1252")


# --- Helpers de format -----------------------------------------------------

def test_to_float_fr_formats():
    assert bi._to_float_fr("2 000") == 2000.0
    assert bi._to_float_fr("181,78") == pytest.approx(181.78)
    assert bi._to_float_fr("0,0207") == pytest.approx(0.0207)
    assert bi._to_float_fr("+ 75,51") == pytest.approx(75.51)
    assert bi._to_float_fr("-303,72") == pytest.approx(-303.72)
    assert bi._to_float_fr("") is None


def test_to_date_fr():
    assert bi._to_date_fr("22/05/26") == "2026-05-22"
    assert bi._to_date_fr("") is None


# --- Parsing ---------------------------------------------------------------

def test_parse_orders_keeps_only_executed():
    df = bi.parse_orders(_orders_bytes())
    # 3 exécutés (le BUY annulé est exclu)
    assert len(df) == 3
    assert set(df["sens"]) == {"BUY", "SELL"}
    air = df[df["isin"] == "FR0000120073"].iloc[0]
    assert air["sens"] == "BUY"
    assert air["quantite"] == 20
    assert air["prix"] == pytest.approx(181.78)
    innate = df[df["isin"] == "FR0010331421"].iloc[0]
    assert innate["quantite"] == 2000


def test_parse_portfolio():
    positions, cash, as_of = bi.parse_portfolio(_portfolio_bytes())
    assert len(positions) == 3  # TOTAL ACTIONS exclu
    assert cash == pytest.approx(1150.49)
    assert as_of == "2026-05-23"
    ceidf = [p for p in positions if p["isin"] == "QS0007946807"][0]
    assert ceidf["quantite"] == 513
    assert ceidf["libelle"] == "CEIDF VAL DE MARNE"


# --- Import complet --------------------------------------------------------

def test_import_broker_files_end_to_end():
    report = bi.import_broker_files(_orders_bytes(), _portfolio_bytes())

    assert report["n_orders"] == 3
    assert report["n_positions"] == 3
    assert report["cash"] == pytest.approx(1150.49)
    assert "QS0007946807" in report["non_cotes"]

    # 3 opérations d'ordre + 1 dépôt de réconciliation
    ops = repository.get_operations()
    assert len(ops) == 4
    assert (ops["type"] == "DEPOSIT").sum() == 1

    # Cash dérivé == liquidités broker (grâce au dépôt de réconciliation)
    assert portfolio.cash_balance(ops) == pytest.approx(1150.49, abs=1e-6)

    # Mapping ISIN -> ticker appliqué dans le référentiel
    secs = repository.get_securities().set_index("isin")
    assert secs.loc["FR0000120073", "ticker"] == "AI.PA"
    assert secs.loc["QS0007946807", "ticker"] == "QS0007946807"  # non coté
    assert secs.loc["QS0007946807", "type_actif"] == "NON_COTE"

    # Dérivation stricte : AIR LIQUIDE (achat) présent, INNATE/RENAULT
    # (ventes sans achat antérieur) -> quantité non positive -> absents.
    pos = portfolio.build_positions(ops)
    assert "AI.PA" in pos["ticker"].values
    assert "IPH.PA" not in pos["ticker"].values

    # Snapshot de réconciliation persisté
    snap = repository.get_import_snapshot()
    assert len(snap) == 3
    assert repository.get_meta("broker_cash") == "1150.49"


def test_import_replaces_previous_data():
    bi.import_broker_files(_orders_bytes(), _portfolio_bytes())
    # Réimport : remplacement complet -> pas d'accumulation
    bi.import_broker_files(_orders_bytes(), _portfolio_bytes())
    ops = repository.get_operations()
    assert len(ops) == 4
