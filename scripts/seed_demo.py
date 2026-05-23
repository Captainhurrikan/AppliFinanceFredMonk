#!/usr/bin/env python3
"""Repeuple la base de démonstration.

Usage :
    python scripts/seed_demo.py            # seed seulement si base vide
    python scripts/seed_demo.py --force    # réinitialise et re-seed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permet d'exécuter le script directement (ajoute la racine au PYTHONPATH).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.db import repository  # noqa: E402
from src.db.seed import seed_demo_data  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed des données de démo PEA")
    parser.add_argument("--force", action="store_true",
                        help="Vide les opérations existantes avant de re-seeder")
    args = parser.parse_args()

    repository.init_db()
    if args.force:
        with repository.get_connection() as conn:
            for table in ("operations", "watchlist", "alertes", "frais_recurrents",
                          "fondamentaux_cache", "prix_cache", "securities"):
                conn.execute(f"DELETE FROM {table}")
        print("Tables vidées.")

    applied = seed_demo_data(force=args.force)
    if applied:
        print(f"Données de démo insérées dans {config.DB_PATH}")
    else:
        print("Base non vide : seed ignoré (utiliser --force pour réinitialiser).")


if __name__ == "__main__":
    main()
