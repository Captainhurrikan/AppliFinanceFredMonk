"""Wrapper robuste pour les appels réseau (yfinance échoue souvent en silence).

Tout appel externe passe par `safe_fetch`, qui journalise et renvoie un état
explicite : OK / EMPTY (données manquantes) / ERROR (erreur réseau ou parsing).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

logger = logging.getLogger("pea.market")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

T = TypeVar("T")


class FetchStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"      # appel réussi mais aucune donnée
    ERROR = "error"      # exception réseau / parsing


@dataclass
class FetchResult(Generic[T]):
    """Résultat explicite d'un appel externe."""
    status: FetchStatus
    data: T | None = None
    message: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == FetchStatus.OK

    def unwrap(self, default: T | None = None) -> T | None:
        return self.data if self.ok else default


_YF_SESSION: Any = None
_YF_SESSION_INIT = False


def get_yf_session():
    """Session HTTP pour yfinance avec impersonation navigateur (curl_cffi).

    Yahoo Finance bloque (HTTP 403) les requêtes sans empreinte TLS de
    navigateur. `curl_cffi` imite Chrome et contourne ce blocage. Si la
    librairie est absente, on renvoie None (yfinance utilise sa session par
    défaut, au risque d'échouer)."""
    global _YF_SESSION, _YF_SESSION_INIT
    if _YF_SESSION_INIT:
        return _YF_SESSION
    _YF_SESSION_INIT = True
    try:
        from curl_cffi import requests as creq
        _YF_SESSION = creq.Session(impersonate="chrome")
        logger.info("Session yfinance via curl_cffi (impersonate=chrome) activée")
    except Exception as exc:  # pragma: no cover - dépend de l'environnement
        logger.warning("curl_cffi indisponible (%s) : session yfinance par défaut", exc)
        _YF_SESSION = None
    return _YF_SESSION


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if hasattr(value, "empty"):  # DataFrame / Series
        return bool(value.empty)
    if isinstance(value, (list, dict, str)):
        return len(value) == 0
    return False


def safe_fetch(label: str, func: Callable[..., T], *args: Any,
               retries: int = 2, backoff: float = 1.0, **kwargs: Any) -> FetchResult[T]:
    """Exécute `func` en capturant les erreurs et en renvoyant un FetchResult.

    Réessaie `retries` fois avec backoff exponentiel en cas d'exception.
    """
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            value = func(*args, **kwargs)
            if _is_empty(value):
                logger.warning("Fetch %s : données vides", label)
                return FetchResult(FetchStatus.EMPTY,
                                   message=f"Aucune donnée pour {label}")
            return FetchResult(FetchStatus.OK, data=value)
        except Exception as exc:  # yfinance lève des erreurs variées
            last_err = exc
            # Inutile (et contre-productif) de réessayer sur un rate limit :
            # cela aggrave le 429. On abandonne immédiatement.
            msg = str(exc).lower()
            if "rate limit" in msg or "too many requests" in msg:
                logger.warning("Fetch %s : rate limit Yahoo, abandon", label)
                return FetchResult(FetchStatus.ERROR,
                                   message=f"Rate limit Yahoo pour {label}")
            logger.warning("Fetch %s : tentative %d échouée (%s)",
                           label, attempt + 1, exc)
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    logger.error("Fetch %s : échec définitif (%s)", label, last_err)
    return FetchResult(FetchStatus.ERROR,
                       message=f"Erreur réseau/données pour {label} : {last_err}")
