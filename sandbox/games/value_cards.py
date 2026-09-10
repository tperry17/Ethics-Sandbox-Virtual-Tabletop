"""Definition for the Value Cards Trading exercise."""

from sandbox.games.models import Exercise, PreviewCard

# TODO(content): Confirm the timing, mechanics, prompts, and facilitator guidance
# below with the exercise author; CLAUDE.md supplies only the exercise title.
VALUE_CARDS_TRADING = Exercise(
    slug="value-cards-trading",
    title="Value Cards Trading",
    short_description=(
        "Choose, exchange, and defend the values you want a group to carry "
        "into a difficult decision."
    ),
    premise=(
        "Participants begin with different value cards, trade to assemble a "
        "hand they can stand behind, and then account for what they kept, "
        "what they let go, and which values proved difficult to compare."
    ),
    group_size="4–12 people",
    running_time="45–60 minutes",
    facilitator="Recommended",
    alongside="A video or phone call for the full 45–60 minutes",
    session_shape=(
        "Read the values in your opening hand and decide which matter most to you.",
        "Trade cards across the table, explaining what you are seeking and "
        "what you can release.",
        "Compare final hands and examine the compromises, refusals, and "
        "assumptions behind them.",
    ),
    tensions=(
        "Whether values can be ranked without flattening what they mean.",
        "The difference between a value you endorse and one you will sacrifice for.",
        "How scarcity, persuasion, and other people’s priorities reshape a choice.",
    ),
    facilitator_notes=(
        "Ask people to narrate trades, not merely complete them; the "
        "reasons are the exercise.",
        "Pause if a word is carrying different meanings for different "
        "participants and make those meanings explicit.",
        "Leave time to discuss the cards nobody sought and the values "
        "participants wished were present.",
    ),
    preview_label=(
        "A shared table with value cards arranged between private hands "
        "and a trading area"
    ),
    preview_zones=("Your hand", "Trading table", "Group reflection"),
    preview_cards=(
        PreviewCard(
            "Freedom of inquiry", "Follow evidence where it leads.", "VALUE 04"
        ),
        PreviewCard("Equal standing", "Give each voice careful attention.", "VALUE 11"),
        PreviewCard("Mutual obligation", "Ask what we owe one another.", "VALUE 19"),
    ),
)
