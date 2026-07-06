from __future__ import annotations

import json
import pkgutil
from typing import TYPE_CHECKING, Any
from BaseClasses import ItemClassification, Location
from . import items

if TYPE_CHECKING:
    from .world import TowerOfBabelWorld
from .Game import game_name
from typing import Any

if TYPE_CHECKING:
    from .world import TowerOfBabelWorld

# We use a slightly higher BASE_ID for locations to prevent overlap with your Item IDs
LOCATION_BASE_ID = 7481000

# Dynamically load the locations.json file from the apworld package
try:
    raw_data = pkgutil.get_data(__name__, "data/locations.json")
    if raw_data is None:
        raise FileNotFoundError("locations.json could not be found in the package namespace.")
        
    # Since the JSON is now a direct array, we remove the ["data"] key extraction
    location_data: list[dict[str, Any]] = json.loads(raw_data.decode("utf-8"))
except Exception as e:
    raise FileNotFoundError(f"Could not load locations.json. Ensure it is in the correct directory. Error: {e}")

# Dynamically build LOCATION_NAME_TO_ID by iterating over the JSON array
LOCATION_NAME_TO_ID = {
    loc["name"]: LOCATION_BASE_ID + index 
    for index, loc in enumerate(location_data, start=1)
}

location_name_groups = {
    "All": set(LOCATION_NAME_TO_ID.keys()),
    "Letters": {loc["name"] for loc in location_data if "Letters" in loc.get("category", [])},
    "Numbers": {loc["name"] for loc in location_data if "Numbers" in loc.get("category", [])},
    "Symbols": {loc["name"] for loc in location_data if "Symbols" in loc.get("category", [])},
}

class TowerOfBabelLocation(Location):
    game = "TowerOfBabel"
    
def get_location_names_with_ids(location_names: list[str]) -> dict[str, int | None]:
    return {location_name: LOCATION_NAME_TO_ID[location_name] for location_name in location_names}


def create_all_locations(world: TowerOfBabelWorld) -> None:
    create_regular_locations(world)

def create_letter_locations(world: "TowerOfBabelWorld", overworld) -> None:
    """Adds all locations categorized as 'Letters' to the Overworld."""
    for loc in location_data:
        if "Letters" in loc.get("category", []):
            overworld.locations.append(TowerOfBabelLocation(
                world.player, 
                loc["name"], 
                world.location_name_to_id[loc["name"]], 
                overworld
            ))

def create_number_locations(world: "TowerOfBabelWorld", overworld) -> None:
    """Adds all locations categorized as 'Numbers' to the Overworld."""
    for loc in location_data:
        if "Numbers" in loc.get("category", []):
            overworld.locations.append(TowerOfBabelLocation(
                world.player, 
                loc["name"], 
                world.location_name_to_id[loc["name"]], 
                overworld
            ))

def create_symbol_locations(world: "TowerOfBabelWorld", overworld) -> None:
    """Adds all locations categorized as 'Symbols' to the Overworld."""
    for loc in location_data:
        if "Symbols" in loc.get("category", []):
            overworld.locations.append(TowerOfBabelLocation(
                world.player, 
                loc["name"], 
                world.location_name_to_id[loc["name"]], 
                overworld
            ))

def create_regular_locations(world: "TowerOfBabelWorld") -> None:
    """Master function to populate the Overworld with all JSON locations."""
    overworld = world.get_region("Overworld")
    
    # Populate the standard location sub-groups
    create_letter_locations(world, overworld)
    create_number_locations(world, overworld)
    create_symbol_locations(world, overworld)
    
    # Add the Victory location manually (exempt from categories)
    for loc in location_data:
        if loc.get("victory"):
            overworld.locations.append(TowerOfBabelLocation(
                world.player, 
                loc["name"], 
                world.location_name_to_id[loc["name"]], 
                overworld
            ))