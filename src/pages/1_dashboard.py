"""Dashboard — vue « PEA Synthèse » : tableau détaillé des positions + totaux.

Reproduit la mise en forme de l'onglet « PEA Synthèse » de l'utilisateur :
Numéraire (cash), tableau ligne par ligne (Date, Mouvement, Type, Entreprise,
Quantité, PRU, Capital Investi, % Actifs, Cours Actuel,
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
ui.refresh_prices_button(key="refresh_dashboard")

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
    "Date": "", "Mouvement": "", "Type": "", "Entreprise": "TOTAL",
    "Quantité": float("nan"), "PRU": float("nan"),
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

# --- Bénéfices réalisés (opérations passées) -------------------------------
st.divider()
st.subheader("💰 Bénéfices réalisés")
st.caption("Plus-values effectives (lignes vendues, en tout ou partie) et "
           "dividendes perçus depuis l'origine. Complémentaire des plus-values "
           "latentes ci-dessus, qui ne portent que sur les titres encore détenus.")

realized = services.get_realized_summary()
if realized.empty:
    st.info("Aucune vente ni dividende enregistré pour l'instant.")
else:
    total_pv_real = float(realized["pv_realisee"].sum())
    total_div_real = float(realized["dividendes"].sum())
    total_benef = total_pv_real + total_div_real

    kr = st.columns(3)
    kr[0].metric("Plus-value réalisée", ui.fmt_eur(total_pv_real),
                 help="Gains/pertes effectifs sur les titres vendus (frais inclus)")
    kr[1].metric("Dividendes perçus", ui.fmt_eur(total_div_real),
                 help="Total des coupons encaissés depuis l'origine (frais déduits)")
    kr[2].metric("Total bénéfices réalisés", ui.fmt_eur(total_benef),
                 help="Plus-value réalisée + dividendes perçus")

    rrows = []
    for _, r in realized.iterrows():
        t = r["ticker"]
        rrows.append({
            "Type": _type_label(t),
            "Entreprise": r.get("libelle") or t,
            "Plus-value réalisée (€)": r["pv_realisee"],
            "Dividendes perçus (€)": r["dividendes"],
            "Total réalisé (€)": r["total_realise"],
        })
    rrows.append({
        "Type": "", "Entreprise": "TOTAL",
        "Plus-value réalisée (€)": total_pv_real,
        "Dividendes perçus (€)": total_div_real,
        "Total réalisé (€)": total_benef,
    })
    rdf = pd.DataFrame(rrows)

    rfmt = {
        "Plus-value réalisée (€)": lambda v: ui.fmt_eur(v, 2),
        "Dividendes perçus (€)": lambda v: ui.fmt_eur(v, 2),
        "Total réalisé (€)": lambda v: ui.fmt_eur(v, 2),
    }
    rstyler = (rdf.style.format(rfmt)
               .apply(_highlight_total, axis=1)
               .map(_color_pv, subset=["Plus-value réalisée (€)", "Total réalisé (€)"]))
    st.dataframe(rstyler, hide_index=True, use_container_width=True)
