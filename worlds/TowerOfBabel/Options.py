from dataclasses import dataclass
from typing import TYPE_CHECKING

from Options import Choice, DefaultOnToggle, OptionGroup, OptionList, PerGameCommonOptions, Range, Toggle

if TYPE_CHECKING:
    from BaseClasses import PlandoOptions
    from worlds.AutoWorld import World


class Goal(Choice):
    """
    Determines the victory condition for Tower of Babel.
    - Full Language Unlock: Unlock all enabled character sets (Letters, Numbers, and Symbols).
    - Mysteries of the Cosmos: Collect the required number of 'Clue of the Cosmos' items.
    """

    display_name = "Goal"

    option_full_language_unlock = 0
    option_mysteries_of_the_cosmos = 1

    default = option_full_language_unlock


class IncludeLetters(DefaultOnToggle):
    """
    Include the 26 English alphabet letters (A-Z) in the item and location pools.
    """

    display_name = "Include Letters"


class IncludeNumbers(DefaultOnToggle):
    """
    Include the 10 numeric digits (0-9) in the item and location pools.
    """

    display_name = "Include Numbers"


class IncludeSymbols(DefaultOnToggle):
    """
    Include the 29 punctuation and special symbols in the item and location pools.
    """

    display_name = "Include Symbols"


class CluesInPool(Range):
    """
    Total number of 'Clue of the Cosmos' items and corresponding 'Collect X Clues of the Cosmos' locations
    added to the multiworld pool when the Goal is set to 'Mysteries of the Cosmos' (or when Clues are enabled).
    """

    display_name = "Clues in Pool"

    range_start = 1
    range_end = 200
    default = 100


class CluesToGoal(Range):
    """
    Number of 'Clue of the Cosmos' items required to achieve victory when the Goal is 'Mysteries of the Cosmos'.
    If set higher than Clues in Pool, it will be clamped to Clues in Pool.
    """

    display_name = "Clues to Goal"

    range_start = 1
    range_end = 200
    default = 100


class MilestoneInterval(Range):
    """
    In 'Mysteries of the Cosmos' mode, every X 'Clue of the Cosmos' items found (up to Clues in Pool)
    unlocks a Milestone Cache that checks additional locations. Set to 0 to disable Milestone Caches.
    """

    display_name = "Milestone Interval"

    range_start = 0
    range_end = 200
    default = 10


class MilestoneCacheSize(Range):
    """
    Number of additional locations checked (items sent) at each Milestone Interval in 'Mysteries of the Cosmos' mode.
    Set to 0 to disable Milestone Caches.
    """

    display_name = "Milestone Cache Size"

    range_start = 0
    range_end = 50
    default = 2


class PlayerList(OptionList):
    """
    List of player names in the multiworld to generate '<Player> Draw' and '<Player> Discard' items and locations for.
    Example: ["Player1", "Player2"]
    """

    display_name = "Player List"
    default = []

    def verify(self, world: type["World"], player_name: str, plando_options: "PlandoOptions") -> None:
        super().verify(world, player_name, plando_options)
        cleaned: list[str] = []
        for entry in self.value:
            name = str(entry).strip()
            if name and name not in cleaned:
                cleaned.append(name)
        self.value = cleaned
        if cleaned and hasattr(world, "register_dynamic_player_cards"):
            world.register_dynamic_player_cards(cleaned)


class StartingHand(Range):
    """
    Starting hand size for each player listed in Player List.
    Does not create items or locations; used by the client UI to calculate each player's current hand size
    (Starting Hand + Draws Found - Discards Found).
    """

    display_name = "Starting Hand"

    range_start = 0
    range_end = 100
    default = 5


class NumDiscards(Range):
    """
    Number of '<Player> Discard' items and matching '<Player> Discard 1..N' locations added to the pool
    for each player in Player List.
    """

    display_name = "Number of Discards"

    range_start = 0
    range_end = 100
    default = 5


class NumDraws(Range):
    """
    Number of '<Player> Draw' items and matching '<Player> Draw 1..N' locations added to the pool
    for each player in Player List.
    """

    display_name = "Number of Draws"

    range_start = 0
    range_end = 100
    default = 5


# ==========================================
# UPCOMING FEATURES (Hint Cost Reduction)
# ==========================================
# class HintCostReduction(Toggle):
#     """
#     When enabled, finding any of the characters in '!HINT' (Symbol !, Letter H, Letter I, Letter N, Letter T)
#     reduces the native hint cost by a flat amount per character unlocked.
#     """
#
#     display_name = "Hint Cost Reduction"
#
#
# class HintCostReductionAmount(Range):
#     """
#     Flat amount (percentage points) by which the native hint cost is reduced for each '!HINT' character unlocked
#     when Hint Cost Reduction is enabled.
#     """
#
#     display_name = "Hint Cost Reduction Amount"
#
#     range_start = 1
#     range_end = 100
#     default = 2


@dataclass
class TowerOfBabelOptions(PerGameCommonOptions):
    goal: Goal
    include_letters: IncludeLetters
    include_numbers: IncludeNumbers
    include_symbols: IncludeSymbols
    clues_in_pool: CluesInPool
    clues_to_goal: CluesToGoal
    milestone_interval: MilestoneInterval
    milestone_cache_size: MilestoneCacheSize
    player_list: PlayerList
    starting_hand: StartingHand
    num_discards: NumDiscards
    num_draws: NumDraws
    # Upcoming features:
    # hint_cost_reduction: HintCostReduction
    # hint_cost_reduction_amount: HintCostReductionAmount


option_groups = [
    OptionGroup(
        "Goal & Clues",
        [Goal, CluesInPool, CluesToGoal, MilestoneInterval, MilestoneCacheSize],
    ),
    OptionGroup(
        "Character Pools",
        [IncludeLetters, IncludeNumbers, IncludeSymbols],
    ),
    OptionGroup(
        "Deck & Hand Options",
        [PlayerList, StartingHand, NumDiscards, NumDraws],
    ),
    # Upcoming features:
    # OptionGroup(
    #     "Hint Options",
    #     [HintCostReduction, HintCostReductionAmount],
    # ),
]
