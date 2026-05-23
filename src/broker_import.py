"""Import des exports broker (Caisse d'Épargne / Banque Populaire).

Deux fichiers CSV (séparateur ';', encodage cp1252, en-têtes/pieds de page) :
- carnet d'ordres -> opérations (achats/ventes EXÉCUTÉS uniquement)
- portefeuille    -> référentiel des titres + snapshot de réconciliation + cash

Stratégie retenue (cf. échanges) : remplacement complet à chaque import et
positions **dérivées strictement des ordres exécutés**. Le fichier portefeuille
sert de référence de réconciliation (affichée) et de source du cash (liquidités).
"""

from __future__ import annotations

import csv
import io
import unicodedata
from datetime import datetime

import pandas as pd

from src.db import repository
from src.market.isin_map import ISIN_TO_TICKER, ticker_for_isin


# --- Helpers de parsing ----------------------------------------------------

def _decode(content: bytes) -> list[str]:
    """Décode en cp1252 (exports Windows) et renvoie les lignes."""
    text = content.decode("cp1252", errors="replace")
    return text.splitlines()


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower().strip()


def _to_float_fr(value: str) -> float | None:
    """Convertit un nombre au format français ('2 000', '181,78', '+ 75,51')."""
    if value is None:
        return None
    s = value.replace("\xa0", " ").replace("+", "").strip()
    s = s.replace(" ", "").replace(",", ".")
    if not s or s in ("-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_date_fr(value: str) -> str | None:
    """'22/05/26' -> '2026-05-22' (ISO)."""
    value = (value or "").strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _find_header(lines: list[str], must_contain: str) -> int:
    """Index de la ligne d'en-tête (qui contient `must_contain`, sans accents)."""
    needle = _strip_accents(must_contain)
    for i, line in enumerate(lines):
        if needle in _strip_accents(line):
            return i
    return -1


def _clean_libelle(libelle: str) -> str:
    return libelle.replace("Titres en portefeuille", "").strip()


# --- Parsing du carnet d'ordres -------------------------------------------

def parse_orders(content: bytes) -> pd.DataFrame:
    """Renvoie un DataFrame des ordres EXÉCUTÉS : date, isin, libelle, sens
    (BUY/SELL), quantite, prix."""
    lines = _decode(content)
    h = _find_header(lines, "Date de statut")
    if h < 0:
        return pd.DataFrame(columns=["date", "isin", "libelle", "sens", "quantite", "prix"])

    reader = csv.reader(io.StringIO("\n".join(lines[h + 1:])), delimiter=";")
    rows: list[dict] = []
    for parts in reader:
        if len(parts) < 13:
            continue
        statut = _strip_accents(parts[11])
        if not statut.startswith("execut"):  # garde uniquement "Exécuté"
            continue
        sens_raw = _strip_accents(parts[4])
        sens = "BUY" if sens_raw.startswith("achat") else ("SELL" if sens_raw.startswith("vente") else None)
        if sens is None:
            continue
        qte = _to_float_fr(parts[6])
        prix = _to_float_fr(parts[9])
        date = _to_date_fr(parts[12]) or _to_date_fr(parts[3])
        if qte is None or prix is None or date is None:
            continue
        rows.append({
            "date": date,
            "isin": parts[1].strip(),
            "libelle": _clean_libelle(parts[0]),
            "sens": sens,
            "quantite": qte,
            "prix": prix,
        })
    return pd.DataFrame(rows)


# --- Parsing du portefeuille ----------------------------------------------

def parse_portfolio(content: bytes) -> tuple[list[dict], float | None, str | None]:
    """Renvoie (positions, cash_liquidités, date_position).

    positions = list de dicts {isin, libelle, quantite, devise, cours,
    valorisation, pru, pv_latente, pct_actif}.
    """
    lines = _decode(content)
    h = _find_header(lines, "Prix d'acquisition")
    positions: list[dict] = []
    if h >= 0:
        reader = csv.reader(io.StringIO("\n".join(lines[h + 1:])), delimiter=";")
        for parts in reader:
            if len(parts) < 9:
                continue
            isin = parts[1].strip()
            libelle = _clean_libelle(parts[0])
            if not isin or _strip_accents(libelle).startswith("total"):
                continue  # ligne TOTAL ACTIONS / pied de page
            positions.append({
                "isin": isin,
                "libelle": libelle,
                "quantite": _to_float_fr(parts[2]),
                "devise": parts[3].strip() or "EUR",
                "cours": _to_float_fr(parts[4]),
                "valorisation": _to_float_fr(parts[5]),
                "pru": _to_float_fr(parts[6]),
                "pv_latente": _to_float_fr(parts[7]),
                "pct_actif": _to_float_fr(parts[8]),
            })

    cash = None
    as_of = None
    for line in lines:
        norm = _strip_accents(line)
        if "liquidites" in norm and cash is None:
            # Format "Liquidités : 1 150,49 EUR" (séparateur ':')
            cash = _to_float_fr(line.split(":")[-1].replace("EUR", ""))
        if norm.startswith("position au"):
            # "Position au 23/05/26 à 14h30"
            for tok in line.split():
                d = _to_date_fr(tok)
                if d:
                    as_of = d
                    break
    return positions, cash, as_of


# --- Import complet --------------------------------------------------------

def import_broker_files(orders_content: bytes, portfolio_content: bytes,
                        replace: bool = True) -> dict:
    """Importe les deux fichiers. Remplacement complet par défaut.

    Renvoie un rapport : nb d'ordres exécutés, nb de positions broker, cash,
    date de position, ISIN non mappés, lignes non cotées.
    """
    repository.init_db()
    if replace:
        repository.wipe_imported_data()

    orders = parse_orders(orders_content)
    positions, cash, as_of = parse_portfolio(portfolio_content)
    as_of = as_of or datetime.today().date().isoformat()

    # Référentiel des titres : union des ISIN du portefeuille et des ordres.
    libelles: dict[str, str] = {}
    for p in positions:
        libelles[p["isin"]] = p["libelle"]
    for _, o in orders.iterrows():
        libelles.setdefault(o["isin"], o["libelle"])

    unmapped: list[str] = []
    non_cotes: list[str] = []
    isin_to_key: dict[str, str] = {}
    for isin, libelle in libelles.items():
        ticker = ticker_for_isin(isin)  # mappé, ou ISIN si inconnu
        type_actif = "ACTION"
        if isin in ISIN_TO_TICKER and ISIN_TO_TICKER[isin] is None:
            ticker = isin
            type_actif = "NON_COTE"
            non_cotes.append(isin)
        elif isin not in ISIN_TO_TICKER:
            unmapped.append(isin)
        isin_to_key[isin] = ticker
        repository.upsert_security(ticker, libelle, devise="EUR",
                                   type_actif=type_actif, isin=isin)

    # Opérations dérivées des ordres exécutés.
    for _, o in orders.iterrows():
        key = isin_to_key.get(o["isin"], o["isin"])
        montant = o["quantite"] * o["prix"]
        op_type = o["sens"]
        repository.add_operation(o["date"], op_type, ticker=key,
                                 quantite=o["quantite"], prix_unitaire=o["prix"],
                                 montant_brut=montant, frais=0.0,
                                 notes="Import carnet d'ordres")

    # Réconciliation du cash : on ajoute un DEPOSIT pour que le cash dérivé
    # corresponde aux liquidités du relevé (les apports/dividendes ne figurent
    # pas dans le carnet d'ordres).
    if cash is not None:
        ops_now = repository.get_operations()
        from src.analytics.portfolio import cash_balance
        impacts = cash_balance(ops_now)
        deposit = cash - impacts
        deposit_date = orders["date"].min() if not orders.empty else as_of
        repository.add_operation(deposit_date, "DEPOSIT", montant_brut=deposit,
                                 notes="Réconciliation cash (import broker)")

    # Snapshot de réconciliation.
    snap_rows = []
    for p in positions:
        snap_rows.append({
            "ticker": isin_to_key.get(p["isin"], p["isin"]),
            "isin": p["isin"],
            "libelle": p["libelle"],
            "quantite": p["quantite"],
            "devise": p["devise"],
            "cours": p["cours"],
            "valorisation": p["valorisation"],
            "pru": p["pru"],
            "pv_latente": p["pv_latente"],
            "pct_actif": p["pct_actif"],
        })
    repository.replace_import_snapshot(snap_rows, as_of)

    repository.set_meta("last_import", datetime.now().isoformat(timespec="seconds"))
    repository.set_meta("broker_cash", str(cash) if cash is not None else "")
    repository.set_meta("position_as_of", as_of)

    return {
        "n_orders": int(len(orders)),
        "n_positions": len(positions),
        "cash": cash,
        "as_of": as_of,
        "unmapped_isins": unmapped,
        "non_cotes": non_cotes,
    }
