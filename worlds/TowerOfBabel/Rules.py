from __future__ import annotations
import re
from typing import TYPE_CHECKING
from worlds.generic.Rules import set_rule

from .locations import location_data

if TYPE_CHECKING:
    from . import TowerOfBabelWorld


def set_all_rules(world: "TowerOfBabelWorld") -> None:
    # We can still safely set the completion condition at the multiworld root
    world.multiworld.completion_condition[world.player] = lambda state: state.has("Victory", world.player)

    # ==========================================
    # PARSE JSON LOCATION LOGIC
    # ==========================================
    for loc_data in location_data:
        loc_name = loc_data["name"]
        requires_str = loc_data.get("requires", "")
        
        if not requires_str:
            continue
            
        try:
            # MODERN SYNTAX: Let the World wrapper handle the multiworld and player ID for us!
            location = world.get_location(loc_name)
        except KeyError:
            continue
        
        # 1. Parse Standard Item Requirements (e.g., "|Letter A|")
        if requires_str.startswith("|") and not requires_str.startswith("|@"):
            item_name = requires_str.strip("|")
            set_rule(location, lambda state, item=item_name: state.has(item, world.player))
            
        # 2. Parse Group Requirements (e.g., "|@Letters:26|")
        elif requires_str.startswith("|@"):
            match = re.match(r"\|@(.+):(\d+)\|", requires_str)
            if match:
                group_name = match.group(1)
                count = int(match.group(2))
                
                set_rule(location, lambda state, g=group_name, c=count: state.has_group(g, world.player, c))