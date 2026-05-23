"""Configuration centrale de l'application PEA.

Tous les paramètres ajustables (chemins, benchmarks, TTL de cache, seuils de
risque et d'alerte) sont regroupés ici pour rester transparents et faciles à
modifier. Aucune clé API : toutes les sources sont gratuites.
"""

from __future__ import annotations

from pathlib import Path

# --- Chemins ---------------------------------------------------------------
# config.py vit dans src/, donc parents[1] == racine du dépôt.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
DATA_DIR: Path = PROJECT_ROOT / "data"
DB_PATH: Path = DATA_DIR / "portfolio.db"
SCHEMA_PATH: Path = PROJECT_ROOT / "src" / "db" / "schema.sql"

# --- Devise de référence ---------------------------------------------------
# Le PEA est libellé en euros : toutes les valorisations sont ramenées en EUR.
BASE_CURRENCY: str = "EUR"

# --- Benchmarks (proxys ETF UCITS capitalisants) ---------------------------
# Les indices "Gross Return" ne sont pas disponibles gratuitement sur yfinance.
# On utilise donc des ETF capitalisants (dividendes réinvestis) comme proxys.
# Modifiable librement : le 1er élément est le benchmark de référence.
# NB : vérifier/ajuster les tickers selon disponibilité yfinance. Le proxy CAC
# par défaut est l'indice prix ^FCHI (à remplacer par un ETF GR si souhaité).
BENCHMARKS: dict[str, str] = {
    "MSCI World (CW8)": "CW8.PA",       # Amundi MSCI World UCITS ETF EUR Acc
    "STOXX Europe 600 (MEUD)": "MEUD.PA",  # Amundi STOXX Europe 600 Acc
    "CAC 40 (^FCHI)": "^FCHI",          # indice prix — proxy GR à substituer si besoin
}
DEFAULT_BENCHMARK: str = "MSCI World (CW8)"

# --- TTL de cache (en secondes) --------------------------------------------
TTL_INTRADAY: int = 15 * 60          # cotations intraday : 15 min
TTL_FUNDAMENTALS: int = 24 * 60 * 60  # fondamentaux : 24 h
TTL_HISTORY: int = 7 * 24 * 60 * 60   # historiques longs : 7 jours

# --- Constantes financières ------------------------------------------------
TRADING_DAYS_PER_YEAR: int = 252

# --- Seuils de risque ------------------------------------------------------
MAX_POSITION_WEIGHT: float = 0.15   # alerte si une ligne dépasse 15 %
MAX_SECTOR_WEIGHT: float = 0.30     # alerte si un secteur dépasse 30 %

# --- Seuils d'alerte par défaut (configurables par ligne ensuite) ----------
DEFAULT_PROFIT_TAKE: float = 0.30   # +30 % depuis achat -> alerte prise de bénéfices
DEFAULT_STOP_LOSS: float = -0.15    # -15 % depuis achat -> alerte stop-loss mental

# --- Scénarios de stress test (chocs de marché appliqués via beta) ---------
STRESS_SCENARIOS: dict[str, float] = {
    "Marché -10 %": -0.10,
    "Marché -20 %": -0.20,
    "Marché -30 %": -0.30,
}

# --- Réseau (scraping de secours uniquement) -------------------------------
HTTP_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
SCRAPE_MIN_INTERVAL_S: float = 1.5  # rate limiting minimal entre requêtes


def ensure_data_dir() -> None:
    """Crée le dossier data/ s'il n'existe pas encore."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
