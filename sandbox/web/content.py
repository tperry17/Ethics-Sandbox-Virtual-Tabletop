"""Shared editorial content for the public site and tabletop."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Principle:
    """One norm of engagement shown to participants and facilitators."""

    title: str
    copy: str


# These norms are intentionally data, not template copy: the tabletop can
# import the same list when its session chrome is implemented.
PRINCIPLES: tuple[Principle, ...] = (
    Principle(
        title="Steelman before you object",
        copy=(
            "State the strongest version of a position before explaining "
            "where you differ."
        ),
    ),
    Principle(
        title="Disagree with the position, not the person",
        copy=(
            "Question claims, reasons, and consequences without assigning "
            "motives or character."
        ),
    ),
    Principle(
        title="Make room, then take room",
        copy=(
            "Notice how much you have spoken; invite others in and "
            "contribute when your view is missing."
        ),
    ),
    Principle(
        title="Ask before you assume",
        copy=(
            "When a claim surprises you, seek the experience or reasoning behind it."
        ),
    ),
    Principle(
        title="Name uncertainty",
        copy=(
            "Say what you know, what you infer, and what would change your confidence."
        ),
    ),
    Principle(
        title="Change your mind out loud",
        copy="Treat revision as part of serious inquiry, and say what moved you.",
    ),
)
