from collections.abc import Mapping
from typing import Any

# Imports of base Archipelago modules must be absolute.
from worlds.AutoWorld import World

# Imports of your world's files must be relative.
from . import items, locations, regions, rules#, web_world
#from . import options as apquest_options
from .Game import game_name

class TowerOfBabelWorld(World):
    game = game_name

    #web = web_world.APQuestWebWorld()
    #options_dataclass = apquest_options.APQuestOptions
    #options: apquest_options.APQuestOptions    
    location_name_to_id = locations.LOCATION_NAME_TO_ID
    item_name_to_id = items.ITEM_NAME_TO_ID
    item_name_groups = items.item_name_groups
    location_name_groups = locations.location_name_groups
    origin_region_name = "Overworld"

    def create_regions(self) -> None:
        regions.create_and_connect_regions(self)
        locations.create_all_locations(self)

    def set_rules(self) -> None:
        rules.set_all_rules(self)

    def create_items(self) -> None:
        items.create_all_items(self)
    def create_item(self, name: str) -> items.TowerOfBabelItem:
        return items.create_item_with_correct_classification(self, name)
    def get_filler_item_name(self) -> str:
        return items.get_random_filler_item_name(self)
    def fill_slot_data(self) -> Mapping[str, Any]:
        return {}