from __future__ import annotations

import json
import pkgutil
from BaseClasses import Item, ItemClassification
from .Game import filler_item_name, game_name
from typing import List, Dict, Any, TYPE_CHECKING
from .locations import location_data

if TYPE_CHECKING:
    from .world import TowerOfBabelWorld

try:
    raw_data = pkgutil.get_data(__name__, "data/items.json")
    item_data: List[Dict[str, Any]] = json.loads(raw_data.decode("utf-8"))
except Exception as e:
    raise FileNotFoundError(f"Could not load items.json. Ensure it is in the correct directory. Error: {e}")

BASE_ID = 7480000
CARD_ITEM_BASE_ID = 7480100

ITEM_NAME_TO_ID = {
    item["name"]: BASE_ID + index
    for index, item in enumerate(item_data, start=1)
}

item_name_groups = {
    "All": set(ITEM_NAME_TO_ID.keys()),
    "Letters": {item["name"] for item in item_data if "Letters" in item.get("tags", [])},
    "Numbers": {item["name"] for item in item_data if "Numbers" in item.get("tags", [])},
    "Symbols": {item["name"] for item in item_data if "Symbols" in item.get("tags", [])},
    "Hint": {item["name"] for item in item_data if "Hint" in item.get("tags", [])},
    "Clues": {item["name"] for item in item_data if "Clues" in item.get("tags", [])},
    "Draws": set(),
    "Discards": set(),
}

_CLASSIFICATION_MAP = {
    "progression": ItemClassification.progression,
    "useful": ItemClassification.useful,
    "filler": ItemClassification.filler,
    "trap": ItemClassification.trap,
}

DEFAULT_ITEM_CLASSIFICATIONS = {
    item["name"]: _CLASSIFICATION_MAP.get(item.get("classification", "progression"), ItemClassification.progression)
    for item in item_data
}


def register_player_card_items(
    player_list: list[str],
    custom_mapping: dict[str, int] | None = None,
) -> dict[str, int]:
    """Dynamically registers '<Player> Draw' and '<Player> Discard' items and returns their Name -> ID mapping."""
    registered: dict[str, int] = {}
    for raw_player in player_list:
        player_name = str(raw_player).strip()
        if not player_name:
            continue
        for card_type, group_name in (("Draw", "Draws"), ("Discard", "Discards")):
            item_name = f"{player_name} {card_type}"
            if custom_mapping and item_name in custom_mapping:
                item_id = int(custom_mapping[item_name])
                ITEM_NAME_TO_ID[item_name] = item_id
            elif item_name not in ITEM_NAME_TO_ID:
                existing_card_ids = [i for i in ITEM_NAME_TO_ID.values() if i >= CARD_ITEM_BASE_ID]
                next_id = (max(existing_card_ids) + 1) if existing_card_ids else (CARD_ITEM_BASE_ID + 1)
                ITEM_NAME_TO_ID[item_name] = next_id

            DEFAULT_ITEM_CLASSIFICATIONS[item_name] = ItemClassification.progression
            item_name_groups["All"].add(item_name)
            item_name_groups[group_name].add(item_name)
            registered[item_name] = ITEM_NAME_TO_ID[item_name]
    return registered


class TowerOfBabelItem(Item):
    game = game_name


def get_random_filler_item_name(world: TowerOfBabelWorld) -> str:
    return filler_item_name


def create_item_with_correct_classification(
    world: TowerOfBabelWorld,
    name: str,
    classification: ItemClassification | None = None,
) -> TowerOfBabelItem:
    if classification is None:
        classification = DEFAULT_ITEM_CLASSIFICATIONS[name]

    return TowerOfBabelItem(name, classification, ITEM_NAME_TO_ID[name], world.player)


def create_letter_items(world: TowerOfBabelWorld) -> list[TowerOfBabelItem]:
    """Creates a list of Item objects for all items tagged with 'Letters'."""
    return [
        world.create_item(item["name"])
        for item in item_data
        if "Letters" in item.get("tags", [])
    ]


def create_number_items(world: TowerOfBabelWorld) -> list[TowerOfBabelItem]:
    """Creates a list of Item objects for all items tagged with 'Numbers'."""
    return [
        world.create_item(item["name"])
        for item in item_data
        if "Numbers" in item.get("tags", [])
    ]


def create_symbol_items(world: TowerOfBabelWorld) -> list[TowerOfBabelItem]:
    """Creates a list of Item objects for all items tagged with 'Symbols'."""
    return [
        world.create_item(item["name"])
        for item in item_data
        if "Symbols" in item.get("tags", [])
    ]


def create_clue_items(world: TowerOfBabelWorld, count: int) -> list[TowerOfBabelItem]:
    """Creates `count` 'Clue of the Cosmos' items for the itempool."""
    return [world.create_item("Clue of the Cosmos") for _ in range(count)]


def create_milestone_filler_items(world: TowerOfBabelWorld) -> list[TowerOfBabelItem]:
    """Creates Filler items matching the number of Milestone Cache locations in 'Mysteries of the Cosmos' mode."""
    clues_in_pool = int(world.options.clues_in_pool)
    interval = int(world.options.milestone_interval)
    cache_size = int(world.options.milestone_cache_size)
    if interval <= 0 or cache_size <= 0 or clues_in_pool <= 0:
        return []

    num_milestones = len(range(interval, clues_in_pool + 1, interval))
    total_filler = num_milestones * cache_size
    return [world.create_item(filler_item_name) for _ in range(total_filler)]


def create_card_items(world: TowerOfBabelWorld) -> list[TowerOfBabelItem]:
    """Creates '<Player> Draw' and '<Player> Discard' items for each player in Player List."""
    cards: list[TowerOfBabelItem] = []
    num_draws = int(world.options.num_draws)
    num_discards = int(world.options.num_discards)
    for player_name in world.get_card_players():
        for _ in range(num_draws):
            cards.append(world.create_item(f"{player_name} Draw"))
        for _ in range(num_discards):
            cards.append(world.create_item(f"{player_name} Discard"))
    return cards


def create_all_items(world: TowerOfBabelWorld) -> None:
    itempool: list[TowerOfBabelItem] = []

    # Add the enabled character sub-pools
    if world.options.include_letters:
        itempool += create_letter_items(world)
    if world.options.include_numbers:
        itempool += create_number_items(world)
    if world.options.include_symbols:
        itempool += create_symbol_items(world)

    # Add Clue of the Cosmos and Milestone Cache filler items when Goal is Mysteries of the Cosmos
    if world.options.goal == world.options.goal.option_mysteries_of_the_cosmos:
        itempool += create_clue_items(world, int(world.options.clues_in_pool))
        itempool += create_milestone_filler_items(world)

    # Add Player Draw and Discard items when Player List is populated
    if world.get_card_players():
        itempool += create_card_items(world)

    # Submit the randomized items to the multiworld pool
    world.multiworld.itempool += itempool

    # Loop through the JSON data to handle forced item placements (e.g. Victory on Full Alphabet)
    for loc in location_data:
        if "place_item" in loc:
            for item_name in loc["place_item"]:
                location_obj = world.multiworld.get_location(loc["name"], world.player)
                location_obj.place_locked_item(world.create_item(item_name))
