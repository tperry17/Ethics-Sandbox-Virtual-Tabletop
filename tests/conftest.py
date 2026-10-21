"""Load the fixture games in ``tests/games`` alongside the real ones.

Set before any test imports ``sandbox.games``, whose registry reads it once
on import. The browser tests set the same variable for their server in
``playwright.config.ts``.
"""

import os
from pathlib import Path

os.environ["SANDBOX_EXTRA_GAMES"] = str(Path(__file__).resolve().parent / "games")
