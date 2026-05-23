-- Schéma SQLite de l'application PEA.
-- Source unique de vérité = table `operations`. Les positions courantes sont
-- TOUJOURS dérivées (jamais saisies directement).

PRAGMA foreign_keys = ON;

-- Référentiel des titres : permet d'ajouter facilement un nouveau ticker
-- (libellé, secteur, pays, devise) depuis l'application.
CREATE TABLE IF NOT EXISTS securities (
    ticker      TEXT PRIMARY KEY,           -- symbole yfinance complet (ex: AIR.PA)
    libelle     TEXT NOT NULL,
    secteur     TEXT,
    pays        TEXT,
    devise      TEXT NOT NULL DEFAULT 'EUR',
    type_actif  TEXT DEFAULT 'ACTION',       -- ACTION / ETF / OBLIGATION ...
    cap_boursiere REAL,                       -- capitalisation (devise du titre)
    date_ajout  TEXT NOT NULL DEFAULT (date('now')),
    actif       INTEGER NOT NULL DEFAULT 1,   -- 1 = suivi, 0 = archivé
    notes       TEXT
);

-- Source unique de vérité : toutes les opérations du compte.
CREATE TABLE IF NOT EXISTS operations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,             -- ISO 'YYYY-MM-DD'
    ticker        TEXT,                       -- NULL pour DEPOSIT/WITHDRAW/FEE génériques
    type          TEXT NOT NULL CHECK (type IN
                    ('BUY','SELL','DIV','FEE','DEPOSIT','WITHDRAW')),
    quantite      REAL NOT NULL DEFAULT 0,
    prix_unitaire REAL NOT NULL DEFAULT 0,    -- dans la devise du titre
    montant_brut  REAL NOT NULL DEFAULT 0,    -- montant brut de l'opération (EUR)
    frais         REAL NOT NULL DEFAULT 0,    -- frais associés (EUR)
    devise        TEXT NOT NULL DEFAULT 'EUR',
    notes         TEXT,
    FOREIGN KEY (ticker) REFERENCES securities(ticker) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_operations_ticker ON operations(ticker);
CREATE INDEX IF NOT EXISTS idx_operations_date ON operations(date);
CREATE INDEX IF NOT EXISTS idx_operations_type ON operations(type);

-- Watchlist : titres surveillés avec prix cibles et thèse d'investissement.
CREATE TABLE IF NOT EXISTS watchlist (
    ticker            TEXT PRIMARY KEY,
    date_ajout        TEXT NOT NULL DEFAULT (date('now')),
    prix_cible_achat  REAL,
    prix_cible_vente  REAL,
    these_invest      TEXT,
    tags              TEXT
);

-- Alertes configurables (prise de bénéfices, stop-loss, seuils techniques).
CREATE TABLE IF NOT EXISTS alertes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT,
    type_alerte   TEXT NOT NULL,             -- PROFIT_TAKE / STOP_LOSS / PRICE_ABOVE / PRICE_BELOW / RSI ...
    seuil         REAL,
    actif         INTEGER NOT NULL DEFAULT 1,
    date_creation TEXT NOT NULL DEFAULT (date('now')),
    notes         TEXT
);

CREATE INDEX IF NOT EXISTS idx_alertes_ticker ON alertes(ticker);

-- Cache des fondamentaux (TTL applicatif de 24 h ; json_raw conserve le brut).
CREATE TABLE IF NOT EXISTS fondamentaux_cache (
    ticker          TEXT PRIMARY KEY,
    date_maj        TEXT NOT NULL,
    per             REAL,
    per_forward     REAL,
    peg             REAL,
    price_to_book   REAL,
    ev_ebitda       REAL,
    dividende_yield REAL,
    payout_ratio    REAL,
    ratio_dette_eq  REAL,
    current_ratio   REAL,
    roe             REAL,
    roic            REAL,
    marge_op        REAL,
    marge_nette     REAL,
    ca_growth       REAL,
    eps_growth      REAL,
    div_growth_5a   REAL,
    secteur         TEXT,
    source          TEXT,                      -- yfinance / scrape:<site>
    json_raw        TEXT
);

-- Frais récurrents (droits de garde, abonnements...).
CREATE TABLE IF NOT EXISTS frais_recurrents (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    libelle    TEXT NOT NULL,
    montant    REAL NOT NULL,
    frequence  TEXT NOT NULL CHECK (frequence IN ('mensuelle','annuelle')),
    date_debut TEXT NOT NULL DEFAULT (date('now')),
    actif      INTEGER NOT NULL DEFAULT 1
);

-- Cache local des cotations historiques (robustesse hors-ligne + scraping limité).
CREATE TABLE IF NOT EXISTS prix_cache (
    ticker     TEXT NOT NULL,
    date       TEXT NOT NULL,
    close      REAL,
    adj_close  REAL,
    devise     TEXT,
    source     TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_prix_cache_ticker ON prix_cache(ticker);
