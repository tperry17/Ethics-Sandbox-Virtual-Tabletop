"""Assembling an ``Exercise`` from its content CSVs.

Every exercise's catalog and detail-page copy lives under
``content/site/exercise*.csv`` (see ``content/README.md``), keyed by slug.
This is the one place that reads those files; each exercise module (e.g.
``sandbox.games.value_cards``) just names its slug.
"""

from __future__ import annotations

from sandbox.content_loading import read_rows, rows_for_slug
from sandbox.games.models import Exercise, LearningOutcome, PreviewCard

EXERCISES_CSV = "site/exercises.csv"
SESSION_SHAPE_CSV = "site/exercise_session_shape.csv"
TENSIONS_CSV = "site/exercise_tensions.csv"
LEARNING_OUTCOMES_CSV = "site/exercise_learning_outcomes.csv"
FACILITATOR_NOTES_CSV = "site/exercise_facilitator_notes.csv"
PREVIEW_ZONES_CSV = "site/exercise_preview_zones.csv"
PREVIEW_CARDS_CSV = "site/exercise_preview_cards.csv"


def load_exercise(slug: str) -> Exercise:
    """The ``Exercise`` named ``slug``, built from its content CSV rows."""
    matches = [row for row in read_rows(EXERCISES_CSV) if row["slug"] == slug]
    if not matches:
        raise KeyError(f"No row for slug {slug!r} in content/{EXERCISES_CSV}.")
    fields = matches[0]

    preview_cards = tuple(
        PreviewCard(title=row["title"], copy=row["copy"], folio=row["folio"])
        for row in rows_for_slug(PREVIEW_CARDS_CSV, slug)
    )

    return Exercise(
        slug=fields["slug"],
        title=fields["title"],
        short_description=fields["short_description"],
        premise=fields["premise"],
        group_size=fields["group_size"],
        running_time=fields["running_time"],
        facilitator=fields["facilitator"],
        alongside=fields["alongside"],
        session_shape=tuple(
            row["text"] for row in rows_for_slug(SESSION_SHAPE_CSV, slug)
        ),
        tensions=tuple(row["text"] for row in rows_for_slug(TENSIONS_CSV, slug)),
        facilitator_notes=tuple(
            row["text"] for row in rows_for_slug(FACILITATOR_NOTES_CSV, slug)
        ),
        preview_label=fields["preview_label"],
        preview_zones=tuple(
            row["label"] for row in rows_for_slug(PREVIEW_ZONES_CSV, slug)
        ),
        preview_cards=preview_cards,
        learning_outcomes=tuple(
            LearningOutcome(title=row["title"], text=row["text"])
            for row in rows_for_slug(LEARNING_OUTCOMES_CSV, slug)
        ),
    )


__all__ = ["load_exercise"]
