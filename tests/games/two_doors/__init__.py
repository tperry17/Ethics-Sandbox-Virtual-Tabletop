"""Two Doors: the reference game for the game-definition format.

Two seats, a small deck, a private hand each, and a public pair of doors.
Each person is dealt one card - a reason for choosing a door - and argues
for it; Reveal lays both cards face up side by side. It is kept in the repo
with the tests as the worked example of ``game.yaml`` and of the Python
escape hatch; it is not an exercise, and the app does not load it unless
``SANDBOX_EXTRA_GAMES`` names ``tests/games``.
"""
