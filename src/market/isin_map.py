"""Correspondance ISIN -> ticker yfinance (Euronext Paris principalement).

Les exports broker fournissent des codes ISIN ; yfinance a besoin de symboles
(ex: AI.PA). Cette table est pré-remplie pour les valeurs connues et reste
éditable depuis la page Import. Une entrée à None signifie "non coté"
(ex: parts sociales) : aucune donnée de marché ne sera récupérée.
"""

from __future__ import annotations

# ISIN -> symbole yfinance (None = non coté / pas de cotation yfinance).
ISIN_TO_TICKER: dict[str, str | None] = {
    "FR0000120073": "AI.PA",      # AIR LIQUIDE
    "FR0000131906": "RNO.PA",     # RENAULT
    "FR0010220475": "ALO.PA",     # ALSTOM
    "FR0012333284": "ABVX.PA",    # ABIVAX
    "FR0000053225": "MMT.PA",     # METROPOLE TELEVISION (M6)
    "FR001400OLP5": "ALBPS.PA",   # BIOPHYTIS
    "FR0000054900": "TFI.PA",     # TF1
    "FR0010331421": "IPH.PA",     # INNATE PHARMA
    "FR0010282822": "VU.PA",      # VUSION (ex SES-imagotag)
    "FR0000038242": "LBIRD.PA",   # LUMIBIRD
    "FR001400SVN0": "ALDRV.PA",   # DRONE VOLT
    "FR0013451044": "ALHGR.PA",   # HOFFMANN GREEN CEMENT
    "FR0000120172": "CA.PA",      # CARREFOUR
    "FR0013506730": "VK.PA",      # VALLOUREC
    "FR0000074072": "BIG.PA",     # BIGBEN INTERACTIVE
    "QS0007946807": None,         # CEIDF parts sociales (non coté)
}


def ticker_for_isin(isin: str, fallback_to_isin: bool = True) -> str | None:
    """Renvoie le ticker yfinance pour un ISIN.

    Si l'ISIN est connu et coté -> le ticker. Si connu mais non coté -> None.
    Si inconnu -> l'ISIN lui-même (pour servir de clé), ou None selon le flag.
    """
    if isin in ISIN_TO_TICKER:
        return ISIN_TO_TICKER[isin]
    return isin if fallback_to_isin else None
