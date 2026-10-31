from __future__ import annotations
import re
from typing import TYPE_CHECKING
from worlds.generic.Rules import set_rule

from .locations import location_data

if TYPE_CHECKING:
    from .world import TowerOfBabelWorld


def set_all_rules(world: "TowerOfBabelWorld") -> None:
    # Set the completion condition at the multiworld root
    world.multiworld.completion_condition[world.player] = lambda state: state.has("Victory", world.player)

    # ==========================================
    # PARSE LOCATION LOGIC
    # ==========================================
    for loc_data in location_data:
        loc_name = loc_data["name"]

        try:
            location = world.get_location(loc_name)
        except KeyError:
            # Location was not created for this player's YAML options
            continue

        # Handle Victory location rules dynamically based on Goal and enabled pools
        if loc_data.get("victory"):
            if world.options.goal == world.options.goal.option_mysteries_of_the_cosmos:
                clues_needed = min(int(world.options.clues_to_goal), int(world.options.clues_in_pool))
                set_rule(
                    location,
                    lambda state, c=clues_needed: state.has("Clue of the Cosmos", world.player, c)
                )
            else:
                # Full Language Unlock: require all enabled character groups
                required_groups: list[tuple[str, int]] = []
                if world.options.include_letters:
                    required_groups.append(("Letters", 26))
                if world.options.include_numbers:
                    required_groups.append(("Numbers", 10))
                if world.options.include_symbols:
                    required_groups.append(("Symbols", 29))

                set_rule(
                    location,
                    lambda state, reqs=required_groups: all(
                        state.has_group(group_name, world.player, count)
                        for group_name, count in reqs
                    )
                )
            continue

        requires_str = loc_data.get("requires", "")
        if not requires_str:
            continue

        # 1. Parse Group Requirements (e.g., "|@Letters:26|")
        if requires_str.startswith("|@"):
            match = re.match(r"\|@(.+):(\d+)\|", requires_str)
            if match:
                group_name = match.group(1)
                count = int(match.group(2))
                set_rule(location, lambda state, g=group_name, c=count: state.has_group(g, world.player, c))

        # 2. Parse Item Count Requirements (e.g., "|Clue of the Cosmos:5|")
        elif requires_str.startswith("|") and ":" in requires_str and not requires_str.startswith("|Symbol :|"):
            match = re.match(r"\|(.+):(\d+)\|", requires_str)
            if match:
                item_name = match.group(1)
                count = int(match.group(2))
                set_rule(location, lambda state, item=item_name, c=count: state.has(item, world.player, c))

        # 3. Parse Standard Single Item Requirements (e.g., "|Letter A|", "|Symbol :|")
        elif requires_str.startswith("|"):
            item_name = requires_str.strip("|")
            set_rule(location, lambda state, item=item_name: state.has(item, world.player))
