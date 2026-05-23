"""Données de démonstration pour tester l'UI immédiatement.

Quelques titres et opérations fictives mais cohérentes (PEA en EUR). Appelé
automatiquement au premier lancement si la base est vide, et rejouable via
scripts/seed_demo.py.
"""

from __future__ import annotations

from src.db import repository

# Référentiel des titres de démo (tickers yfinance réels, place de Paris).
DEMO_SECURITIES = [
    ("AIR.PA", "Airbus SE", "Industrials", "France", "EUR", "ACTION"),
    ("MC.PA", "LVMH", "Consumer Cyclical", "France", "EUR", "ACTION"),
    ("TTE.PA", "TotalEnergies", "Energy", "France", "EUR", "ACTION"),
    ("SAN.PA", "Sanofi", "Healthcare", "France", "EUR", "ACTION"),
    ("CW8.PA", "Amundi MSCI World UCITS ETF", "Diversifié", "Monde", "EUR", "ETF"),
]

# Opérations de démo (date, type, ticker, qte, prix, montant_brut, frais, notes).
DEMO_OPERATIONS = [
    ("2024-01-15", "DEPOSIT", None, 0, 0, 30000, 0, "Apport initial"),
    ("2024-01-16", "BUY", "AIR.PA", 50, 140.0, 0, 5, "Ouverture ligne Airbus"),
    ("2024-01-16", "BUY", "MC.PA", 10, 750.0, 0, 8, "Ouverture ligne LVMH"),
    ("2024-02-01", "BUY", "TTE.PA", 100, 62.0, 0, 6, "Ouverture ligne TotalEnergies"),
    ("2024-03-20", "DIV", "TTE.PA", 0, 0, 74.0, 0, "Acompte dividende"),
    ("2024-05-10", "DEPOSIT", None, 0, 0, 10000, 0, "Renforcement de compte"),
    ("2024-05-12", "BUY", "SAN.PA", 60, 90.0, 0, 5, "Ouverture ligne Sanofi"),
    ("2024-06-15", "DIV", "AIR.PA", 0, 0, 90.0, 0, "Dividende Airbus"),
    ("2024-09-02", "SELL", "MC.PA", 5, 680.0, 0, 6, "Allègement partiel LVMH"),
    ("2024-12-31", "FEE", None, 0, 0, 30.0, 0, "Droits de garde annuels"),
    ("2025-02-03", "BUY", "CW8.PA", 20, 480.0, 0, 4, "Diversification ETF World"),
    ("2025-03-17", "DIV", "TTE.PA", 0, 0, 78.0, 0, "Acompte dividende"),
    ("2025-06-16", "DIV", "AIR.PA", 0, 0, 95.0, 0, "Dividende Airbus"),
]

DEMO_WATCHLIST = [
    ("ASML.AS", 580.0, 950.0, "Leader mondial litho EUV, moat technologique fort", "tech;qualité"),
    ("OR.PA", 320.0, 480.0, "L'Oréal — croissance régulière, pricing power", "conso;qualité"),
]

DEMO_FRAIS = [
    ("Droits de garde", 30.0, "annuelle"),
]


def seed_demo_data(force: bool = False) -> bool:
    """Peuple la base avec les données de démo.

    Si `force` est False, ne fait rien si des opérations existent déjà.
    Renvoie True si le seed a effectivement été appliqué.
    """
    repository.init_db()
    if not force and not repository.is_empty():
        return False

    for ticker, lib, sect, pays, dev, typ in DEMO_SECURITIES:
        repository.upsert_security(ticker, lib, sect, pays, dev, typ)

    for d, t, tk, q, pu, mb, fr, note in DEMO_OPERATIONS:
        repository.add_operation(d, t, ticker=tk, quantite=q, prix_unitaire=pu,
                                 montant_brut=mb, frais=fr, notes=note)

    for tk, ca, cv, these, tags in DEMO_WATCHLIST:
        repository.upsert_security(tk, tk)  # référentiel minimal
        repository.upsert_watchlist(tk, prix_cible_achat=ca, prix_cible_vente=cv,
                                    these_invest=these, tags=tags)

    for lib, montant, freq in DEMO_FRAIS:
        repository.add_frais_recurrent(lib, montant, freq)

    # Alertes de démo
    repository.add_alerte("AIR.PA", "PROFIT_TAKE", 0.30, "Prise de bénéfices +30 %")
    repository.add_alerte("SAN.PA", "STOP_LOSS", -0.15, "Stop-loss mental -15 %")
    return True
