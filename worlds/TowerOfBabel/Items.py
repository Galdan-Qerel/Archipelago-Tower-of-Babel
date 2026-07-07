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
}

DEFAULT_ITEM_CLASSIFICATIONS = {
    item["name"]: ItemClassification.progression 
    for item in item_data
}

class TowerOfBabelItem(Item):
    game = game_name

def get_random_filler_item_name(world: TowerOfBabelWorld) -> str:
    return filler_item_name


def create_item_with_correct_classification(world: TowerOfBabelWorld, name: str) -> TowerOfBabelItem:
    classification = DEFAULT_ITEM_CLASSIFICATIONS[name]

    return TowerOfBabelItem(name, classification, ITEM_NAME_TO_ID[name], world.player)

def create_letter_items(world) -> list:
    """Creates a list of Item objects for all items tagged with 'Letters'."""
    return [
        world.create_item(item["name"]) 
        for item in item_data 
        if "Letters" in item.get("tags", [])
    ]

def create_number_items(world) -> list:
    """Creates a list of Item objects for all items tagged with 'Numbers'."""
    return [
        world.create_item(item["name"]) 
        for item in item_data 
        if "Numbers" in item.get("tags", [])
    ]

def create_symbol_items(world) -> list:
    """Creates a list of Item objects for all items tagged with 'Symbols'."""
    return [
        world.create_item(item["name"]) 
        for item in item_data 
        if "Symbols" in item.get("tags", [])
    ]

def create_all_items(world):
    itempool = []
    
    # Add the distinct sub-pools
    itempool += create_letter_items(world)
    itempool += create_number_items(world)
    itempool += create_symbol_items(world)
    
    # Submit the randomized items to the multiworld pool
    world.multiworld.itempool += itempool
    
    # Loop through the JSON data to handle forced item placements
    for loc in location_data:
        if "place_item" in loc:
            for item_name in loc["place_item"]:
                # Fetch the actual location object we created earlier in Regions.py
                location_obj = world.multiworld.get_location(loc["name"], world.player)
                
                # Lock the item directly to the location so it never randomizes
                location_obj.place_locked_item(world.create_item(item_name))