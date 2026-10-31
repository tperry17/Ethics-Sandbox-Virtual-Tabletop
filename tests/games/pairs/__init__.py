"""Pairs: the reference game for the game-definition format.

Two seats, a small deck, a private hand each, and a public middle. Each
person is dealt three cards; whoever holds two of a rank has "caught a
pair", and Catch pairs lays every pair face up in the middle. It is kept in
the repo with the tests as the worked example of ``game.yaml`` and of the
Python escape hatch; it is not an exercise, and the app does not load it
unless ``SANDBOX_EXTRA_GAMES`` names ``tests/games``.
"""
