"""Public metadata shared by exercise definitions and the website."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PreviewCard:
    """One card shown in a table preview."""

    title: str
    copy: str
    folio: str


@dataclass(frozen=True)
class Exercise:
    """Everything the public site needs to describe an exercise."""

    slug: str
    title: str
    short_description: str
    premise: str
    group_size: str
    running_time: str
    facilitator: str
    alongside: str
    session_shape: tuple[str, ...]
    tensions: tuple[str, ...]
    facilitator_notes: tuple[str, ...]
    preview_label: str
    preview_zones: tuple[str, ...]
    preview_cards: tuple[PreviewCard, ...]
