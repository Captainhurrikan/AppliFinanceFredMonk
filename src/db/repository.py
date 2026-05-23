"""Accès aux données SQLite (SQL brut, sans ORM).

Mono-utilisateur / mono-machine : on ouvre une connexion par opération via un
context manager. Toutes les fonctions de lecture renvoient des DataFrames pandas
pour s'intégrer directement aux pages Streamlit et aux modules analytics.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from typing import Any, Iterator

import pandas as pd

from src import config

OPERATION_TYPES = ("BUY", "SELL", "DIV", "FEE", "DEPOSIT", "WITHDRAW")


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Connexion SQLite avec clés étrangères activées et Row factory."""
    config.ensure_data_dir()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Crée le schéma s'il n'existe pas (idempotent)."""
    config.ensure_data_dir()
    schema_sql = config.SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(schema_sql)


def _read_sql(query: str, params: tuple | dict = ()) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


# --- Référentiel des titres (securities) -----------------------------------

def upsert_security(
    ticker: str,
    libelle: str,
    secteur: str | None = None,
    pays: str | None = None,
    devise: str = "EUR",
    type_actif: str = "ACTION",
    cap_boursiere: float | None = None,
    notes: str | None = None,
) -> None:
    """Insère ou met à jour un titre (référentiel). Permet d'ajouter facilement
    un nouveau ticker depuis l'UI."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO securities
                (ticker, libelle, secteur, pays, devise, type_actif, cap_boursiere, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                libelle=excluded.libelle,
                secteur=COALESCE(excluded.secteur, securities.secteur),
                pays=COALESCE(excluded.pays, securities.pays),
                devise=excluded.devise,
                type_actif=excluded.type_actif,
                cap_boursiere=COALESCE(excluded.cap_boursiere, securities.cap_boursiere),
                notes=COALESCE(excluded.notes, securities.notes)
            """,
            (ticker, libelle, secteur, pays, devise, type_actif, cap_boursiere, notes),
        )


def get_securities(actifs_only: bool = False) -> pd.DataFrame:
    query = "SELECT * FROM securities"
    if actifs_only:
        query += " WHERE actif = 1"
    query += " ORDER BY libelle"
    return _read_sql(query)


def get_security(ticker: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM securities WHERE ticker = ?", (ticker,)).fetchone()
    return dict(row) if row else None


def set_security_active(ticker: str, actif: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE securities SET actif = ? WHERE ticker = ?", (int(actif), ticker))


# --- Opérations (source unique de vérité) ----------------------------------

def add_operation(
    op_date: str | date,
    type_: str,
    ticker: str | None = None,
    quantite: float = 0.0,
    prix_unitaire: float = 0.0,
    montant_brut: float = 0.0,
    frais: float = 0.0,
    devise: str = "EUR",
    notes: str | None = None,
) -> int:
    if type_ not in OPERATION_TYPES:
        raise ValueError(f"Type d'opération invalide : {type_!r}")
    op_date = str(op_date)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO operations
                (date, ticker, type, quantite, prix_unitaire, montant_brut, frais, devise, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (op_date, ticker, type_, quantite, prix_unitaire, montant_brut, frais, devise, notes),
        )
        return int(cur.lastrowid)


def update_operation(op_id: int, **fields: Any) -> None:
    if not fields:
        return
    allowed = {"date", "ticker", "type", "quantite", "prix_unitaire",
               "montant_brut", "frais", "devise", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE operations SET {set_clause} WHERE id = ?",
            (*updates.values(), op_id),
        )


def delete_operation(op_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM operations WHERE id = ?", (op_id,))


def get_operations(
    ticker: str | None = None,
    type_: str | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
) -> pd.DataFrame:
    clauses: list[str] = []
    params: list[Any] = []
    if ticker:
        clauses.append("ticker = ?")
        params.append(ticker)
    if type_:
        clauses.append("type = ?")
        params.append(type_)
    if date_min:
        clauses.append("date >= ?")
        params.append(date_min)
    if date_max:
        clauses.append("date <= ?")
        params.append(date_max)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    query = f"SELECT * FROM operations{where} ORDER BY date, id"
    df = _read_sql(query, tuple(params))
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def bulk_insert_operations(df: pd.DataFrame) -> int:
    """Import CSV : insère un lot d'opérations. Colonnes attendues = colonnes
    de la table operations (hors id). Renvoie le nombre de lignes insérées."""
    cols = ["date", "ticker", "type", "quantite", "prix_unitaire",
            "montant_brut", "frais", "devise", "notes"]
    rows = []
    for _, r in df.iterrows():
        if r["type"] not in OPERATION_TYPES:
            raise ValueError(f"Type invalide dans l'import : {r['type']!r}")
        rows.append(tuple(r.get(c) if c in r and pd.notna(r.get(c)) else
                          (0 if c in ("quantite", "prix_unitaire", "montant_brut", "frais")
                           else ("EUR" if c == "devise" else None))
                          for c in cols))
    with get_connection() as conn:
        conn.executemany(
            f"INSERT INTO operations ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
            rows,
        )
    return len(rows)


# --- Watchlist -------------------------------------------------------------

def upsert_watchlist(
    ticker: str,
    prix_cible_achat: float | None = None,
    prix_cible_vente: float | None = None,
    these_invest: str | None = None,
    tags: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO watchlist (ticker, prix_cible_achat, prix_cible_vente, these_invest, tags)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                prix_cible_achat=excluded.prix_cible_achat,
                prix_cible_vente=excluded.prix_cible_vente,
                these_invest=excluded.these_invest,
                tags=excluded.tags
            """,
            (ticker, prix_cible_achat, prix_cible_vente, these_invest, tags),
        )


def get_watchlist() -> pd.DataFrame:
    return _read_sql("SELECT * FROM watchlist ORDER BY ticker")


def delete_watchlist(ticker: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))


# --- Alertes ---------------------------------------------------------------

def add_alerte(ticker: str | None, type_alerte: str, seuil: float | None,
               notes: str | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO alertes (ticker, type_alerte, seuil, notes) VALUES (?, ?, ?, ?)",
            (ticker, type_alerte, seuil, notes),
        )
        return int(cur.lastrowid)


def get_alertes(actifs_only: bool = False) -> pd.DataFrame:
    query = "SELECT * FROM alertes"
    if actifs_only:
        query += " WHERE actif = 1"
    query += " ORDER BY ticker, type_alerte"
    return _read_sql(query)


def set_alerte_active(alerte_id: int, actif: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE alertes SET actif = ? WHERE id = ?", (int(actif), alerte_id))


def delete_alerte(alerte_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM alertes WHERE id = ?", (alerte_id,))


# --- Frais récurrents ------------------------------------------------------

def add_frais_recurrent(libelle: str, montant: float, frequence: str,
                        date_debut: str | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO frais_recurrents (libelle, montant, frequence, date_debut) "
            "VALUES (?, ?, ?, COALESCE(?, date('now')))",
            (libelle, montant, frequence, date_debut),
        )
        return int(cur.lastrowid)


def get_frais_recurrents(actifs_only: bool = True) -> pd.DataFrame:
    query = "SELECT * FROM frais_recurrents"
    if actifs_only:
        query += " WHERE actif = 1"
    return _read_sql(query)


def delete_frais_recurrent(frais_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM frais_recurrents WHERE id = ?", (frais_id,))


# --- Cache fondamentaux ----------------------------------------------------

def upsert_fundamentals(ticker: str, data: dict[str, Any], source: str = "yfinance") -> None:
    """Persiste les fondamentaux d'un ticker. `data` contient les ratios connus ;
    le brut complet est stocké dans json_raw."""
    fields = ["per", "per_forward", "peg", "price_to_book", "ev_ebitda",
              "dividende_yield", "payout_ratio", "ratio_dette_eq", "current_ratio",
              "roe", "roic", "marge_op", "marge_nette", "ca_growth", "eps_growth",
              "div_growth_5a", "secteur"]
    values = [data.get(f) for f in fields]
    with get_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO fondamentaux_cache
                (ticker, date_maj, {', '.join(fields)}, source, json_raw)
            VALUES (?, datetime('now'), {', '.join(['?'] * len(fields))}, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                date_maj=datetime('now'),
                {', '.join(f"{f}=excluded.{f}" for f in fields)},
                source=excluded.source,
                json_raw=excluded.json_raw
            """,
            (ticker, *values, source, json.dumps(data, default=str)),
        )


def get_fundamentals_cache(ticker: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM fondamentaux_cache WHERE ticker = ?", (ticker,)
        ).fetchone()
    return dict(row) if row else None


def get_all_fundamentals() -> pd.DataFrame:
    return _read_sql("SELECT * FROM fondamentaux_cache")


# --- Cache des cotations ---------------------------------------------------

def store_prices(ticker: str, prices: pd.DataFrame, devise: str = "EUR",
                 source: str = "yfinance") -> None:
    """Stocke un historique de cotations. `prices` indexé par date, colonnes
    'close' et optionnellement 'adj_close'."""
    if prices.empty:
        return
    rows = []
    for idx, r in prices.iterrows():
        d = pd.Timestamp(idx).strftime("%Y-%m-%d")
        close = float(r["close"]) if "close" in r and pd.notna(r["close"]) else None
        adj = float(r["adj_close"]) if "adj_close" in r and pd.notna(r.get("adj_close")) else close
        rows.append((ticker, d, close, adj, devise, source))
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO prix_cache (ticker, date, close, adj_close, devise, source)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, date) DO UPDATE SET
                close=excluded.close, adj_close=excluded.adj_close,
                devise=excluded.devise, source=excluded.source,
                fetched_at=datetime('now')
            """,
            rows,
        )


def get_cached_prices(ticker: str) -> pd.DataFrame:
    df = _read_sql(
        "SELECT date, close, adj_close, devise FROM prix_cache "
        "WHERE ticker = ? ORDER BY date",
        (ticker,),
    )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    return df


# --- Initialisation / état -------------------------------------------------

def is_empty() -> bool:
    """True si aucune opération n'est enregistrée (base vierge)."""
    with get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
    return n == 0
