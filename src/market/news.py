"""Flux RSS d'actualités par ticker via Google News (feedparser).

Sentiment basique par mots-clés (transparent, non IA) : positif / négatif /
neutre selon un lexique simple.
"""

from __future__ import annotations

import urllib.parse

import streamlit as st

try:
    import feedparser
except ImportError:  # dégradation propre si feedparser indisponible
    feedparser = None

from src.config import TTL_INTRADAY
from src.market.cache import safe_fetch

_POSITIFS = {"hausse", "record", "bénéfice", "croissance", "surperforme",
             "relève", "dividende", "rachat", "contrat", "succès", "beats",
             "upgrade", "profit", "gains", "soars", "jumps"}
_NEGATIFS = {"baisse", "chute", "perte", "alerte", "avertissement", "recul",
             "enquête", "amende", "licenciement", "downgrade", "miss", "plunges",
             "falls", "warning", "lawsuit", "cuts"}


def _sentiment(titre: str) -> str:
    mots = set(titre.lower().replace(",", " ").replace(".", " ").split())
    pos = len(mots & _POSITIFS)
    neg = len(mots & _NEGATIFS)
    if pos > neg:
        return "positif"
    if neg > pos:
        return "négatif"
    return "neutre"


@st.cache_data(ttl=TTL_INTRADAY, show_spinner=False)
def fetch_news(query: str, limit: int = 8) -> list[dict]:
    """Renvoie les dernières actualités Google News pour une requête (ex: nom
    de société ou ticker). Liste de dicts {titre, lien, date, sentiment}."""
    if feedparser is None:
        return []
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=fr&gl=FR&ceid=FR:fr"

    res = safe_fetch(f"news:{query}", feedparser.parse, url)
    feed = res.unwrap()
    if not feed or not getattr(feed, "entries", None):
        return []
    items = []
    for entry in feed.entries[:limit]:
        titre = entry.get("title", "")
        items.append({
            "titre": titre,
            "lien": entry.get("link", ""),
            "date": entry.get("published", ""),
            "sentiment": _sentiment(titre),
        })
    return items
