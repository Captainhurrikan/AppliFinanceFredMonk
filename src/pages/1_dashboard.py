"""Dashboard — vue « PEA Synthèse » : tableau détaillé des positions + totaux.

Reproduit la mise en forme de l'onglet « PEA Synthèse » de l'utilisateur :
Numéraire (cash), tableau ligne par ligne (Date, Mouvement, Type, Entreprise,
Code, Secteur, Quantité, PRU, Capital Investi, % Actifs, Cours Actuel,
Plus-Value € et %, Valorisation, Dividende de l'année) et ligne de totaux
(incluant le cash, comme dans le fichier source).

Positions dérivées strictement des opérations (cf. CLAUDE.md). Les blocs
performance/risque/benchmarks restent sur les pages dédiées.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src import services
from src.db import repository
from src.ui import components as ui

st.title("🏠 Dashboard — PEA Synthèse")
st.caption("Synthèse du portefeuille (positions dérivées des opérations). "
           "L'outil aide à décider, il ne décide pas.")

snapshot = services.get_portfolio_snapshot()
cash = services.get_cash()
annee = date.today().year

if snapshot.empty:
    st.info("Aucune position. Importe tes fichiers dans la page « Import / "
            "Mise à jour » ou saisis des opérations.")
    st.stop()

# --- Données complémentaires (date d'entrée, type, dividendes de l'année) ---
ops = repository.get_operations()
secs = repository.get_securities().set_index("ticker")

# Date d'entrée = 1er achat de la ligne ; dividendes = coupons de l'année.
first_buy: dict[str, pd.Timestamp] = {}
buys = ops[(ops["type"] == "BUY") & ops["ticker"].notna()]
if not buys.empty:
    first_buy = buys.groupby("ticker")["date"].min().to_dict()

div_annee: dict[str, float] = {}
divs = ops[(ops["type"] == "DIV") & ops["ticker"].notna()].copy()
if not divs.empty:
    divs = divs[divs["date"].dt.year == annee]
    if not divs.empty:
        s = (divs["montant_brut"] - divs["frais"]).groupby(divs["ticker"]).sum()
        div_annee = s.to_dict()

TYPE_LABELS = {"NON_COTE": "Part Sociale", "ETF": "ETF", "OBLIGATION": "Obligation"}


def _type_label(ticker: str) -> str:
    ta = secs.loc[ticker, "type_actif"] if ticker in secs.index else "ACTION"
    return TYPE_LABELS.get(ta, "Action")


# --- Totaux (le total inclut le numéraire, comme le fichier source) --------
total_titres = float(snapshot["valorisation"].sum())
total_cout = float(snapshot["cout_total"].sum())
total_pv = float(snapshot["pv_latente"].sum())
total_pv_pct = total_pv / total_cout if total_cout else None
total_div = float(sum(div_annee.values()))
total_assets = total_titres + cash
capital_assets = total_cout + cash

# --- KPIs d'en-tête --------------------------------------------------------
k = st.columns(5)
k[0].metric("Numéraire", ui.fmt_eur(cash), help="Liquidités disponibles")
k[1].metric("Capital investi", ui.fmt_eur(capital_assets),
            help="Coût des positions (PRU × qté, frais inclus) + numéraire")
k[2].metric("Valorisation totale", ui.fmt_eur(total_assets),
            help="Valorisation des titres + numéraire")
k[3].metric("Plus-value latente", ui.fmt_eur(total_pv),
            delta=ui.fmt_pct(total_pv_pct) if total_pv_pct is not None else None)
k[4].metric(f"Dividendes {annee}", ui.fmt_eur(total_div))

# --- Tableau de synthèse ---------------------------------------------------
rows = []
for _, r in snapshot.iterrows():
    t = r["ticker"]
    fb = first_buy.get(t)
    pct_actifs = (r["valorisation"] / total_assets) if total_assets else None
    rows.append({
        "Date": fb.strftime("%d/%m/%Y") if pd.notna(fb) else "",
        "Mouvement": "Achat",
        "Type": _type_label(t),
        "Entreprise": r.get("libelle") or t,
        "Code": t.split(".")[0],
        "Secteur": r.get("secteur") or "—",
        "Quantité": r["quantite"],
        "PRU": r["pru"],
        "Capital Investi": r["cout_total"],
        "% Actifs": pct_actifs,
        "Cours Actuel": r["cours"],
        "+/- Value (€)": r["pv_latente"],
        "+/- Value (%)": r["perf_latente"],
        "Valorisation": r["valorisation"],
        f"Dividende {annee}": div_annee.get(t, 0.0),
    })

# Ligne de totaux (NaN pour les colonnes non agrégées -> affichées « — »).
rows.append({
    "Date": "", "Mouvement": "", "Type": "", "Entreprise": "TOTAL", "Code": "",
    "Secteur": "", "Quantité": float("nan"), "PRU": float("nan"),
    "Capital Investi": capital_assets, "% Actifs": float("nan"),
    "Cours Actuel": float("nan"), "+/- Value (€)": total_pv,
    "+/- Value (%)": total_pv_pct, "Valorisation": total_assets,
    f"Dividende {annee}": total_div,
})

df = pd.DataFrame(rows)


def _fr(v, dec: int) -> str:
    """Nombre au format français (séparateur milliers espace, décimale virgule)."""
    if v is None or pd.isna(v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")


fmt = {
    "Quantité": lambda v: _fr(v, 0),
    "PRU": lambda v: _fr(v, 3),
    "Capital Investi": lambda v: ui.fmt_eur(v, 2),
    "% Actifs": ui.fmt_pct,
    "Cours Actuel": lambda v: _fr(v, 4),
    "+/- Value (€)": lambda v: ui.fmt_eur(v, 2),
    "+/- Value (%)": ui.fmt_pct,
    "Valorisation": lambda v: ui.fmt_eur(v, 2),
    f"Dividende {annee}": lambda v: ui.fmt_eur(v, 2),
}


def _highlight_total(row):
    return ["font-weight: bold" if row["Entreprise"] == "TOTAL" else "" for _ in row]


def _color_pv(v):
    if v is None or pd.isna(v):
        return ""
    return "color: #1e8e3e" if v >= 0 else "color: #d93025"


styler = (df.style.format(fmt)
          .apply(_highlight_total, axis=1)
          .map(_color_pv, subset=["+/- Value (€)", "+/- Value (%)"]))

st.dataframe(styler, hide_index=True, use_container_width=True)
st.caption(f"Numéraire : {ui.fmt_eur(cash, 2)} · le total inclut le numéraire. "
           "Cours et valorisation au prix yfinance du jour (repli sur le PRU si "
           "indisponible, ex. titres non cotés).")
