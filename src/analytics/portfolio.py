"""Dérivation du portefeuille depuis la table `operations`.

Les positions ne sont JAMAIS saisies : elles sont reconstruites ici à partir
des opérations (source unique de vérité).

PRU : méthode du Coût Moyen Pondéré (CMP), frais d'achat inclus.
Plus-value réalisée : calculée à la vente par rapport au PRU du moment.
(FIFO non utilisé — cf. CLAUDE.md.)
"""

from __future__ import annotations

import pandas as pd

# Signe de l'impact cash de chaque type d'opération.
# montant_brut et frais sont exprimés en EUR.


def cash_impact(row: pd.Series) -> float:
    """Impact net sur le cash disponible d'une opération (en EUR)."""
    t = row["type"]
    brut = float(row.get("montant_brut") or 0.0)
    frais = float(row.get("frais") or 0.0)
    qte = float(row.get("quantite") or 0.0)
    pu = float(row.get("prix_unitaire") or 0.0)
    if t == "BUY":
        montant = brut if brut else qte * pu
        return -(montant + frais)
    if t == "SELL":
        montant = brut if brut else qte * pu
        return montant - frais
    if t == "DIV":
        return brut - frais
    if t == "FEE":
        return -(brut + frais)
    if t == "DEPOSIT":
        return brut
    if t == "WITHDRAW":
        return -brut
    return 0.0


def cash_balance(operations: pd.DataFrame) -> float:
    """Cash disponible = somme des impacts cash de toutes les opérations."""
    if operations.empty:
        return 0.0
    return float(operations.apply(cash_impact, axis=1).sum())


def _buy_amount(row: pd.Series) -> float:
    brut = float(row.get("montant_brut") or 0.0)
    qte = float(row.get("quantite") or 0.0)
    pu = float(row.get("prix_unitaire") or 0.0)
    return brut if brut else qte * pu


def build_positions(operations: pd.DataFrame) -> pd.DataFrame:
    """Reconstruit les positions courantes par ticker (PRU CMP).

    Colonnes renvoyées : ticker, quantite, pru, cout_total, pv_realisee,
    dividendes, frais_titre. Ne contient que les tickers à quantité > 0.
    """
    cols = ["ticker", "quantite", "pru", "cout_total", "pv_realisee",
            "dividendes", "frais_titre"]
    if operations.empty:
        return pd.DataFrame(columns=cols)

    ops = operations.copy()
    ops = ops[ops["ticker"].notna()]
    ops = ops.sort_values(["ticker", "date", "id"])

    rows: list[dict] = []
    for ticker, grp in ops.groupby("ticker"):
        qte = 0.0
        cout_total = 0.0  # coût total des titres détenus (PRU * qte)
        pv_realisee = 0.0
        dividendes = 0.0
        frais_titre = 0.0
        for _, r in grp.iterrows():
            t = r["type"]
            frais = float(r.get("frais") or 0.0)
            if t == "BUY":
                montant = _buy_amount(r)
                cout_total += montant + frais  # frais d'achat inclus dans le PRU
                qte += float(r.get("quantite") or 0.0)
                frais_titre += frais
            elif t == "SELL":
                q_vendue = float(r.get("quantite") or 0.0)
                pru = cout_total / qte if qte > 0 else 0.0
                montant = _buy_amount(r)  # qte*pu ou montant_brut
                prix_vente_net = (montant - frais)
                pv_realisee += prix_vente_net - pru * q_vendue
                cout_total -= pru * q_vendue
                qte -= q_vendue
                frais_titre += frais
                if qte < 1e-9:  # ligne soldée
                    qte = 0.0
                    cout_total = 0.0
            elif t == "DIV":
                dividendes += float(r.get("montant_brut") or 0.0) - frais
            elif t == "FEE":
                frais_titre += float(r.get("montant_brut") or 0.0) + frais

        pru = cout_total / qte if qte > 0 else 0.0
        rows.append({
            "ticker": ticker,
            "quantite": qte,
            "pru": pru,
            "cout_total": cout_total,
            "pv_realisee": pv_realisee,
            "dividendes": dividendes,
            "frais_titre": frais_titre,
        })

    df = pd.DataFrame(rows, columns=cols)
    return df[df["quantite"] > 1e-9].reset_index(drop=True)


def realized_summary(operations: pd.DataFrame) -> pd.DataFrame:
    """Bénéfices réalisés par ticker : plus-value réalisée (ventes) + dividendes.

    Contrairement à `build_positions`, inclut les lignes totalement soldées
    (déjà vendues) afin de refléter l'intégralité des bénéfices effectués.
    Colonnes : ticker, pv_realisee, dividendes, frais_titre, total_realise.
    Ne garde que les tickers ayant une plus-value réalisée ou un dividende.
    """
    cols = ["ticker", "pv_realisee", "dividendes", "frais_titre", "total_realise"]
    if operations.empty:
        return pd.DataFrame(columns=cols)

    ops = operations[operations["ticker"].notna()].sort_values(["ticker", "date", "id"])
    rows: list[dict] = []
    for ticker, grp in ops.groupby("ticker"):
        qte = 0.0
        cout_total = 0.0  # coût des titres encore détenus (PRU * qte)
        pv_realisee = 0.0
        dividendes = 0.0
        frais_titre = 0.0
        for _, r in grp.iterrows():
            t = r["type"]
            frais = float(r.get("frais") or 0.0)
            if t == "BUY":
                cout_total += _buy_amount(r) + frais
                qte += float(r.get("quantite") or 0.0)
                frais_titre += frais
            elif t == "SELL":
                q = float(r.get("quantite") or 0.0)
                pru = cout_total / qte if qte > 0 else 0.0
                pv_realisee += (_buy_amount(r) - frais) - pru * q
                cout_total -= pru * q
                qte -= q
                frais_titre += frais
                if qte < 1e-9:  # ligne soldée
                    qte = 0.0
                    cout_total = 0.0
            elif t == "DIV":
                dividendes += float(r.get("montant_brut") or 0.0) - frais
            elif t == "FEE":
                frais_titre += float(r.get("montant_brut") or 0.0) + frais
        rows.append({
            "ticker": ticker,
            "pv_realisee": pv_realisee,
            "dividendes": dividendes,
            "frais_titre": frais_titre,
            "total_realise": pv_realisee + dividendes,
        })

    df = pd.DataFrame(rows, columns=cols)
    mask = (df["pv_realisee"].abs() > 1e-9) | (df["dividendes"].abs() > 1e-9)
    return df[mask].reset_index(drop=True)


def realized_pnl(operations: pd.DataFrame) -> float:
    """Plus-value réalisée totale (toutes lignes, y compris soldées)."""
    summary = realized_summary(operations)
    return float(summary["pv_realisee"].sum()) if not summary.empty else 0.0


def total_dividends(operations: pd.DataFrame) -> float:
    if operations.empty:
        return 0.0
    div = operations[operations["type"] == "DIV"]
    return float((div["montant_brut"] - div["frais"]).sum()) if not div.empty else 0.0


def total_fees(operations: pd.DataFrame) -> float:
    if operations.empty:
        return 0.0
    fee_rows = operations[operations["type"] == "FEE"]
    fees_explicit = float((fee_rows["montant_brut"] + fee_rows["frais"]).sum()) if not fee_rows.empty else 0.0
    fees_trades = float(operations[operations["type"].isin(["BUY", "SELL"])]["frais"].sum())
    return fees_explicit + fees_trades


# --- Séries temporelles (valorisation jour à jour) -------------------------

def quantity_timeline(operations: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Matrice quantités détenues (lignes = dates du calendrier, colonnes = tickers)."""
    ops = operations[operations["ticker"].notna() &
                     operations["type"].isin(["BUY", "SELL"])].copy()
    if ops.empty:
        return pd.DataFrame(index=calendar)
    ops["signed_qte"] = ops.apply(
        lambda r: r["quantite"] if r["type"] == "BUY" else -r["quantite"], axis=1)
    daily = ops.groupby([ops["date"].dt.normalize(), "ticker"])["signed_qte"].sum().unstack(fill_value=0.0)
    daily = daily.reindex(calendar, fill_value=0.0)
    return daily.cumsum()


def cash_timeline(operations: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.Series:
    """Solde cash cumulé jour à jour."""
    if operations.empty:
        return pd.Series(0.0, index=calendar)
    ops = operations.copy()
    ops["impact"] = ops.apply(cash_impact, axis=1)
    daily = ops.groupby(ops["date"].dt.normalize())["impact"].sum()
    daily = daily.reindex(calendar, fill_value=0.0)
    return daily.cumsum()


def external_flows_timeline(operations: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.Series:
    """Flux externes (dépôts +, retraits -) par jour — pour le calcul du TWR."""
    if operations.empty:
        return pd.Series(0.0, index=calendar)
    ext = operations[operations["type"].isin(["DEPOSIT", "WITHDRAW"])].copy()
    if ext.empty:
        return pd.Series(0.0, index=calendar)
    ext["flow"] = ext.apply(
        lambda r: r["montant_brut"] if r["type"] == "DEPOSIT" else -r["montant_brut"], axis=1)
    daily = ext.groupby(ext["date"].dt.normalize())["flow"].sum()
    return daily.reindex(calendar, fill_value=0.0)


def build_value_series(
    operations: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """Construit la valorisation quotidienne du portefeuille.

    `prices` : DataFrame de cours (index = dates, colonnes = tickers, en EUR),
    déjà converti et forward-fillé par la couche market.
    Renvoie un DataFrame indexé par date avec : positions_value, cash,
    total_value, external_flow.
    """
    if operations.empty:
        return pd.DataFrame(columns=["positions_value", "cash", "total_value", "external_flow"])

    start = operations["date"].min().normalize()
    end = pd.Timestamp.today().normalize()
    calendar = pd.bdate_range(start=start, end=end)
    if calendar.empty:
        calendar = pd.DatetimeIndex([start])

    qty = quantity_timeline(operations, calendar)
    cash = cash_timeline(operations, calendar)
    flows = external_flows_timeline(operations, calendar)

    if qty.empty or prices.empty:
        positions_value = pd.Series(0.0, index=calendar)
    else:
        px = prices.reindex(calendar).ffill().bfill()
        common = [t for t in qty.columns if t in px.columns]
        if common:
            positions_value = (qty[common] * px[common]).sum(axis=1)
        else:
            positions_value = pd.Series(0.0, index=calendar)

    total = positions_value + cash
    return pd.DataFrame({
        "positions_value": positions_value,
        "cash": cash,
        "total_value": total,
        "external_flow": flows,
    })
