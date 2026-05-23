# PEA — Suivi actif

Application **Streamlit** de suivi et d'aide à la décision pour un PEA géré
activement (stock picking, gestion du risque, prises de bénéfices). Conçue pour
un investisseur confirmé, en local d'abord, déploiement Streamlit Cloud possible.

> L'outil **aide à décider, il ne décide pas** : aucune recommandation
> automatique d'achat/vente, aucun signal en boîte noire. Tous les calculs sont
> transparents et déterministes.

## Philosophie

- **Sources 100 % gratuites** : `yfinance` en primaire ; scraping ciblé en
  secours uniquement, avec cache agressif.
- **Source unique de vérité** : toutes les opérations (achats, ventes,
  dividendes, frais, dépôts, retraits) sont saisies dans une seule table
  `operations`. Les positions courantes sont **dérivées**, jamais saisies.
- **Mono-utilisateur, mono-machine** : SQLite, pas d'ORM, pas d'authentification.
- **Multi-horizons** : court (1m, 3m), moyen (6m, 1a), long (3a, 5a, depuis
  création).

## Installation

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements.txt
```

## Lancement

```bash
streamlit run streamlit_app.py
```

Au **premier lancement**, la base SQLite (`data/portfolio.db`) est créée
automatiquement et peuplée de **données de démo** pour explorer l'UI
immédiatement.

Pour réinitialiser / repeupler la base de démo :

```bash
python scripts/seed_demo.py            # seed seulement si la base est vide
python scripts/seed_demo.py --force    # vide puis re-seed
```

## Pages

| Page | Contenu |
|------|---------|
| 🏠 Dashboard | Valorisation, perf TWR vs benchmarks, KPIs risque, top/flop, cash, alertes du jour |
| 📊 Positions | Détail ligne par ligne (PRU, +/-value, poids, dividendes) + actions rapides |
| ✍️ Opérations | CRUD, ajout facile de titres, import CSV, historique filtrable |
| 📈 Performance | Courbe vs benchmarks, TWR vs MWR, décomposition, attribution, drawdown, heatmap mensuelle |
| 🔎 Analyse fonda | Ratios valo/qualité/croissance/solvabilité, score transparent, dividendes 10 ans |
| ⚖️ Risque | Diversification, concentration (HHI), corrélations, beta, stress tests |
| 🎯 Opportunités | Watchlist + cibles, signaux techniques/fondamentaux, alertes, news RSS |

## Benchmarks

Les indices « Gross Return » n'étant pas disponibles gratuitement, on utilise
des **proxys ETF UCITS capitalisants** (configurables dans `src/config.py`) :
MSCI World (`CW8.PA`), STOXX Europe 600 (`MEUD.PA`), CAC 40 (`^FCHI` par défaut,
remplaçable par un ETF GR). Voir `CLAUDE.md` pour les limites de ce choix.

## Tests

```bash
pytest
```

- `tests/test_performance.py` : TWR, MWR/XIRR, volatilité, drawdown, beta (cas connus).
- `tests/test_pages_smoke.py` : exécution de chaque page Streamlit sans exception
  (données de marché simulées, via `AppTest`).

## Structure

```
streamlit_app.py        # entrypoint + navigation
src/
  config.py             # paramètres (chemins, benchmarks, TTL, seuils)
  services.py           # glue données <-> cotations <-> calculs
  db/                   # schema.sql, repository.py, seed.py
  market/               # prices.py, fundamentals.py, news.py, cache.py
  analytics/            # performance.py, portfolio.py, risk.py, signals.py
  pages/                # 1_dashboard ... 7_opportunites
  ui/components.py      # composants Streamlit réutilisables
tests/                  # tests unitaires + smoke
scripts/seed_demo.py    # (re)peuplement des données de démo
```

## Limites connues (v1 / MVP)

- Conversion FX au **spot courant** (pas de série historique) — sans impact pour
  un PEA majoritairement EUR.
- Comparaison sectorielle = médiane **interne** des titres suivis (scraping
  sectoriel externe à venir).
- Stress tests = modèle **linéaire via beta** (scénarios taux/récession à enrichir).
- Le proxy CAC par défaut est un indice prix (sous-estime les dividendes réinvestis).
