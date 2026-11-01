"""AA contrast for every text-on-surface pair in tokens.css, in both themes.

Also: seat tints must stay distinguishable under the two common red-green
colour-vision deficiencies. Tints never carry meaning alone (a name or a
shape always goes with them), so this is a second line of defence.
"""

import re
from pathlib import Path

import pytest

TOKENS = Path(__file__).resolve().parents[1] / "static" / "css" / "tokens.css"

# (foreground, background, minimum ratio). 4.5 for text, 3.0 for large text
# and for non-text marks such as outlines.
PAIRS: list[tuple[str, str, float]] = [
    *[
        (text, surface, 4.5)
        for text in ("--text-primary", "--text-secondary", "--text-muted")
        for surface in ("--surface-page", "--surface-raised", "--surface-sunken")
    ],
    ("--text-inverse", "--text-primary", 4.5),
    ("--text-on-felt", "--table-felt", 4.5),
    ("--text-on-felt", "--table-felt-edge", 4.5),
    ("--text-on-felt", "--table-zone-private", 4.5),
    ("--accent-rubric", "--surface-page", 4.5),
    ("--accent-rubric", "--surface-raised", 4.5),
    ("--accent-rubric", "--surface-sunken", 4.5),
    ("--semantic-assent", "--surface-page", 4.5),
    ("--semantic-assent", "--surface-raised", 4.5),
    ("--semantic-tension", "--surface-page", 4.5),
    ("--semantic-tension", "--surface-raised", 4.5),
    ("--semantic-caution", "--surface-page", 4.5),
    ("--semantic-caution", "--surface-raised", 4.5),
    ("--card-back-ink", "--card-back", 4.5),
    ("--card-back-ink", "--card-frame-deck", 4.5),
    ("--card-back-ink", "--card-frame-sidebar", 4.5),
    ("--table-zone-outline", "--table-felt", 3.0),
    ("--surface-border-strong", "--surface-page", 3.0),
    *[("--seat-ink", f"--seat-{n}", 4.5) for n in range(1, 7)],
]


def _blocks() -> dict[str, dict[str, str]]:
    css = TOKENS.read_text()
    light = re.search(r":root \{(.*?)\n\}", css, re.S)
    dark = re.search(r':root\[data-theme="dark"\] \{(.*?)\n\}', css, re.S)
    assert light and dark

    def read(body: str) -> dict[str, str]:
        return dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9a-fA-F]{6,8});", body))

    base = read(light.group(1))
    return {"light": base, "dark": {**base, **read(dark.group(1))}}


def _rgb(value: str) -> tuple[float, float, float]:
    return tuple(int(value[i : i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def _luminance(value: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(("fg", "bg", "minimum"), PAIRS)
def test_every_text_pair_meets_aa(theme: str, fg: str, bg: str, minimum: float) -> None:
    tokens = _blocks()[theme]
    ratio = contrast(tokens[fg], tokens[bg])
    assert ratio >= minimum, f"{theme}: {fg} on {bg} is {ratio:.2f}, needs {minimum}"


# -- colour vision ---------------------------------------------------------------------

# Machado et al. (2009), severity 1.0, applied in linear RGB.
PROTANOPIA = (
    (0.152286, 1.052583, -0.204868),
    (0.114503, 0.786281, 0.099216),
    (-0.003882, -0.048116, 1.051998),
)
DEUTERANOPIA = (
    (0.367322, 0.860646, -0.227968),
    (0.280085, 0.672501, 0.047413),
    (-0.011820, 0.042940, 0.968881),
)


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _simulate(
    value: str, matrix: tuple[tuple[float, ...], ...]
) -> tuple[float, float, float]:
    linear = [_linear(c) for c in _rgb(value)]
    out = [
        max(0.0, min(1.0, sum(m * c for m, c in zip(row, linear)))) for row in matrix
    ]
    encoded = [
        12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in out
    ]
    return encoded[0], encoded[1], encoded[2]


IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(
    "matrix",
    [IDENTITY, PROTANOPIA, DEUTERANOPIA],
    ids=["typical", "protanopia", "deuteranopia"],
)
def test_seat_tints_stay_distinguishable(
    theme: str, matrix: tuple[tuple[float, ...], ...]
) -> None:
    tokens = _blocks()[theme]
    labs = [_lab(_simulate(tokens[f"--seat-{n}"], matrix)) for n in range(1, 7)]
    for i in range(6):
        for j in range(i + 1, 6):
            delta = sum((a - b) ** 2 for a, b in zip(labs[i], labs[j])) ** 0.5
            assert delta >= 12, (
                f"{theme}: seats {i + 1} and {j + 1} are only {delta:.1f} apart"
            )
