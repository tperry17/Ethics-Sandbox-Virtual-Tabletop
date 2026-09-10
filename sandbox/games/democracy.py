"""Definition for the Democracy Simulation exercise."""

from sandbox.games.models import Exercise, PreviewCard

# TODO(content): Confirm the timing, mechanics, prompts, and facilitator guidance
# below with the exercise author; CLAUDE.md supplies only the exercise title.
DEMOCRACY_SIMULATION = Exercise(
    slug="democracy-simulation",
    title="Democracy Simulation",
    short_description=(
        "Make a collective decision while information, authority, and the "
        "costs of delay are unevenly distributed."
    ),
    premise=(
        "A group must act on a shared problem, but no participant begins "
        "with the whole picture. The table makes competing proposals and "
        "unequal knowledge visible, then asks the group to examine how it "
        "reached a decision."
    ),
    group_size="6–30 people",
    running_time="60–90 minutes",
    facilitator="Required",
    alongside="A video or phone call for the full 60–90 minutes",
    session_shape=(
        "Take a role and inspect the information and responsibilities "
        "available to you.",
        "Share evidence, form proposals, and decide how the group will "
        "make a binding choice.",
        "Reconstruct the decision together: whose knowledge travelled, "
        "whose did not, and why.",
    ),
    tensions=(
        "The trade-off between broad participation and acting in time.",
        "Who is trusted when knowledge is incomplete or unevenly distributed.",
        "Whether a procedurally fair decision can still produce an unjust result.",
    ),
    facilitator_notes=(
        "Do not resolve uncertainty for the group; ask participants what "
        "would justify acting despite it.",
        "Track who speaks, whose evidence enters proposals, and where "
        "informal authority emerges.",
        "In the debrief, separate criticism of the outcome from criticism "
        "of the process that produced it.",
    ),
    preview_label=(
        "A shared decision table with evidence, proposals, and a decision area"
    ),
    preview_zones=("Evidence", "Proposals", "Decision"),
    preview_cards=(
        PreviewCard(
            "Partial report",
            "Evidence from one part of the community.",
            "EVIDENCE 03",
        ),
        PreviewCard(
            "Act now", "Choose a response before conditions worsen.", "PROPOSAL A"
        ),
        PreviewCard(
            "Consult first", "Seek wider testimony before deciding.", "PROPOSAL B"
        ),
    ),
)
