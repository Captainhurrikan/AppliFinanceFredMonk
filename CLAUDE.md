# CLAUDE.md — Règles projet et conventions

Document de référence pour les itérations futures (humain ou Claude). À lire
avant toute modification.

## 1. Principes directeurs

1. **L'outil aide à décider, il ne décide pas.** Aucune recommandation
   automatique d'achat/vente. Aucun signal en boîte noire : tout indicateur doit
   être explicable et reproductible.
2. **Déterminisme et transparence.** Pas d'IA générative dans les analyses. Les
   scores et signaux reposent sur des formules documentées ici.
3. **Source unique de vérité = table `operations`.** Les positions, le cash, les
   performances sont **toujours dérivés** des opérations. Ne jamais stocker une
   position « en dur ».
4. **Sources de données gratuites uniquement.** `yfinance` en primaire. Scraping
   ciblé (Yahoo HTML, Boursorama) en secours seulement, avec User-Agent réaliste
   + rate limiting (`config.SCRAPE_MIN_INTERVAL_S`) + cache agressif. Pas de FMP,
   Alpha Vantage payant, IEX, Bloomberg.
5. **Mono-utilisateur / mono-machine.** SQLite, SQL brut (`sqlite3`), pas d'ORM,
   pas d'authentification, pas de Docker (pour l'instant).
6. **Robustesse réseau.** Tout appel externe passe par `market/cache.py::safe_fetch`
   qui journalise et renvoie un `FetchResult` explicite (OK / EMPTY / ERROR).
   L'UI ne doit jamais planter parce que yfinance a échoué : elle dégrade
   (repli sur le PRU pour les cours).
7. **Cotations via `yf.download` (endpoint *chart*).** Les cours, historiques,
   FX et benchmarks passent par `yf.download(...)` (`market/prices.py::_download_close`),
   l'endpoint le plus fiable de Yahoo (approche éprouvée). On évite `Ticker.info`
   et `fast_info` pour les **prix** car l'endpoint `quoteSummary` est davantage
   bloqué (403). Les métadonnées/fondamentaux (`.info`) restent en best-effort
   via une session `curl_cffi` (impersonation Chrome, `cache.py::get_yf_session`)
   et peuvent échouer sans casser l'UI. Les titres `NON_COTE` (parts sociales)
   ne sont jamais interrogés et restent valorisés au PRU.

## 2. Architecture par couches

Implémentation et dépendances dans cet ordre (les couches basses n'importent
jamais les hautes) :

```
db (repository, schema, seed)
  └── market (prices, fundamentals, news, cache)        # st.cache_data + safe_fetch
        └── analytics (performance, portfolio, risk, signals)   # purs, sans Streamlit
              └── services.py                            # glue
                    └── pages/ + ui/components.py         # Streamlit
```

- **`analytics/` ne dépend PAS de Streamlit ni du réseau** → testable unitairement.
- **`services.py`** est le seul endroit qui combine données + cotations + calculs
  pour les pages. Les pages ne font pas d'accès DB/réseau « sauvage » : elles
  passent par `services` ou `repository`.
- Les pages sont déclarées dans `streamlit_app.py` via `st.navigation` /
  `st.Page` (Streamlit ≥ 1.36), ce qui permet de les ranger sous `src/pages/`.

## 3. Conventions de code

- Python **3.11+**, `from __future__ import annotations` en tête de module.
- Français pour les libellés UI, commentaires et docstrings métier.
- Fonctions de lecture DB → renvoient des **DataFrames pandas**.
- Cache Streamlit : `st.cache_data` pour les données (TTL), `st.cache_resource`
  pour le bootstrap. TTL définis dans `config.py` :
  - cotations intraday : 15 min (`TTL_INTRADAY`)
  - fondamentaux : 24 h (`TTL_FUNDAMENTALS`)
  - historiques longs : 7 jours (`TTL_HISTORY`)
- Pas de clés API dans le code.
- Tickers = **symboles yfinance complets** (ex : `AIR.PA`, `ASML.AS`). Un nouveau
  titre s'ajoute facilement via la page Opérations (métadonnées auto-remplies).

## 4. Modèle de données (SQLite)

Tables (cf. `src/db/schema.sql`) :

- `operations` — **source unique de vérité**. `type ∈ {BUY, SELL, DIV, FEE,
  DEPOSIT, WITHDRAW}`. `montant_brut` et `frais` en **EUR** ; `prix_unitaire`
  dans la devise du titre.
- `securities` — référentiel des titres (libellé, secteur, pays, devise…).
- `watchlist` — titres surveillés + prix cibles + thèse.
- `alertes` — alertes configurables (prise de bénéfices, stop-loss, seuils).
- `fondamentaux_cache` — cache fondamentaux (TTL applicatif 24 h, `json_raw`).
- `frais_recurrents` — droits de garde, abonnements.
- `prix_cache` — cache local de cotations (robustesse / scraping limité).

## 5. Calculs financiers — choix figés

### PRU — Coût Moyen Pondéré (CMP)
Le PRU est calculé en **CMP, frais d'achat inclus** :
`PRU = coût_total / quantité`, où `coût_total` cumule `quantité×prix + frais`
des achats. À la vente, la quantité diminue mais le PRU reste inchangé (on retire
`PRU × quantité_vendue` du coût total). **FIFO non utilisé** sauf demande
explicite ultérieure.

### Plus-value réalisée
Calculée à la vente, par rapport au PRU **au moment de la vente** :
`PV = (montant_vente − frais) − PRU × quantité_vendue`.

### TWR (Time-Weighted Return)
Neutralise les apports/retraits → indicateur à comparer aux benchmarks.
Implémentation : chaînage des rendements quotidiens. **Convention** : un flux
externe (dépôt/retrait) du jour *t* intervient en **début de journée**, d'où
`r_t = V_t / (V_{t-1} + F_t) − 1`, puis `TWR = ∏(1 + r_t) − 1`. Les dividendes
sont **internes** (ils alimentent le cash, font partie du portefeuille) ; seuls
DEPOSIT/WITHDRAW sont des flux externes.

### MWR (Money-Weighted Return)
Équivalent IRR sur flux datés (**XIRR**), résolu par `scipy.optimize.brentq` sur
la VAN actuarielle (convention actes/365). Point de vue investisseur : dépôts
négatifs, retraits + valeur finale positifs. Renvoie `None` si non résoluble.

### Volatilité
Écart-type des **rendements quotidiens × √252** (annualisée).

### Max drawdown
Sur l'**indice TWR rebasé** (hors apports) : `min(V_t / max_cumulé_t − 1)`.

### Beta
`cov(rendements_portefeuille, rendements_benchmark) / var(benchmark)` sur
l'intersection des dates (≈ 1 an glissant). Beta du portefeuille = somme
pondérée (par valorisation) des betas des lignes.

## 6. Score fondamental synthétique

Algo **simple et transparent** (`analytics/signals.py::fundamental_score`) :
4 piliers notés 0–100 via des **paliers explicites**, un ratio manquant contribue
de façon neutre (50), `Global` = moyenne des piliers.

- **Value** : PER, P/B, EV/EBITDA (bas = bon).
- **Quality** : ROE, ROIC, marge opérationnelle (élevés = bon).
- **Growth** : croissance CA et EPS (élevées = bon).
- **Income** : rendement du dividende (élevé = bon) + payout soutenable (< 60 %).

Ce n'est **pas** une recommandation : c'est un résumé chiffré et reproductible.

## 6 bis. Import des exports broker (`src/broker_import.py`)

Import des relevés Caisse d'Épargne / Banque Populaire (CSV `;`, **cp1252**,
nombres FR). Deux formats du fichier d'opérations, **détectés automatiquement**
(`parse_operations_file`) :

- **« Historique opérations »** (recommandé) : en-tête `Nature de l'opération`,
  **montants nets** (frais inclus → PRU exact), inclut les dividendes
  (`CREDIT COUPONS` → `DIV`, quantité ignorée car = taille de position). Les
  lignes techniques (détachement/sortie de droits à 0) sont neutralisées.
- **« Carnet d'ordres »** (ancien) : en-tête `Date de statut`, ordres `Exécuté`
  uniquement, hors dividendes.

Décisions figées avec l'utilisateur :

- **Remplacement complet** à chaque import (`repository.wipe_imported_data` :
  vide `operations`, `securities`, `import_snapshot`, caches ; conserve
  watchlist / alertes / frais récurrents).
- **Dérivation stricte** : positions/PRU dérivés **uniquement** des ordres
  **exécutés** (statut « Exécuté »). On assume que certaines lignes manquent
  (antérieures à l'historique, non cotées, ventes sans achat → quantité ≤ 0,
  filtrées par `build_positions`). `import_snapshot` conserve le relevé pour la
  **réconciliation** affichée (page Import).
- **Cash** : on insère un `DEPOSIT` de réconciliation pour que le cash dérivé
  égale les **liquidités** du relevé (les apports/dividendes n'étant pas dans le
  carnet). Le cash reste donc « dérivé des opérations ».
- **ISIN → ticker** : `src/market/isin_map.py` (pré-rempli Euronext Paris,
  None = non coté). Clé `securities.ticker` = ticker mappé, sinon l'ISIN.
  Éditable via la page Import (`repository.remap_ticker` répercute sur
  `operations` et `import_snapshot`).

La page `src/pages/0_import.py` est la page d'accueil (`default=True`).

## 7. Benchmarks

Indices Gross Return indisponibles gratuitement → **proxys ETF UCITS
capitalisants** (`config.BENCHMARKS`, modifiables). Le proxy CAC par défaut est
l'indice prix `^FCHI` (sous-estime les dividendes réinvestis) ; le remplacer par
un ETF CAC accumulant si souhaité. Les benchmarks sont rebasés sur la date de
départ du portefeuille pour une comparaison équitable.

## 8. Limites MVP / dette technique connue

- Conversion FX au **spot courant** (pas de série FX historique).
- Comparaison sectorielle = médiane **interne** des titres en cache (pas encore
  de scraping de médianes sectorielles externes).
- Stress tests = modèle **linéaire via beta** ; scénarios taux/récession à
  enrichir (corrélations conditionnelles, sensibilités sectorielles).
- Sentiment des news = **lexique de mots-clés** basique (non IA).
- `prix_cache` est en place mais le chemin principal de cotation s'appuie surtout
  sur `st.cache_data` ; brancher davantage le cache SQLite pour le hors-ligne.

## 9. Tests

- `pytest` doit rester vert avant tout commit.
- Tout nouveau calcul financier dans `analytics/` → **test unitaire avec cas
  connu** dans `tests/`.
- Toute nouvelle page → l'ajouter à `tests/test_pages_smoke.py` (exécution sans
  exception via `AppTest`, données de marché simulées).

## 10. Méthode d'itération

1. Modifier la couche concernée en respectant l'ordre des dépendances.
2. Ajouter/mettre à jour les tests.
3. `pytest` vert.
4. Commits Git granulaires, messages clairs en français.
