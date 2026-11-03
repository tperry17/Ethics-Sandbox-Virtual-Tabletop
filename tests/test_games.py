from sandbox.games import EXERCISES, EXERCISES_BY_SLUG


def test_exercises_are_registered_by_unique_slug() -> None:
    slugs = [exercise.slug for exercise in EXERCISES]

    assert len(slugs) == len(set(slugs))
    assert EXERCISES_BY_SLUG.keys() == set(slugs)
    for slug, exercise in EXERCISES_BY_SLUG.items():
        assert exercise.slug == slug


def test_each_exercise_has_at_least_one_of_every_preview_field() -> None:
    for exercise in EXERCISES:
        assert exercise.preview_zones
        assert exercise.preview_cards
