from __future__ import annotations

import json
import pkgutil
from typing import TYPE_CHECKING, Any
from BaseClasses import Location
from .Game import game_name

if TYPE_CHECKING:
    from .world import TowerOfBabelWorld

# We use a slightly higher BASE_ID for locations to prevent overlap with your Item IDs
LOCATION_BASE_ID = 7481000
CARD_LOCATION_BASE_ID = 7482000
MILESTONE_LOCATION_BASE_ID = 7490000
MAX_CLUES_IN_POOL = 200
MAX_CARDS_IN_POOL = 100
MAX_MILESTONE_CACHE_SIZE = 50

# Dynamically load the locations.json file from the apworld package
try:
    raw_data = pkgutil.get_data(__name__, "data/locations.json")
    if raw_data is None:
        raise FileNotFoundError("locations.json could not be found in the package namespace.")

    # Since the JSON is now a direct array, we remove the ["data"] key extraction
    location_data: list[dict[str, Any]] = json.loads(raw_data.decode("utf-8"))
except Exception as e:
    raise FileNotFoundError(f"Could not load locations.json. Ensure it is in the correct directory. Error: {e}")

# Append dynamic Clue of the Cosmos locations (1..MAX_CLUES_IN_POOL) so their IDs are registered globally
for i in range(1, MAX_CLUES_IN_POOL + 1):
    loc_name = f"Collect {i} Clues of the Cosmos"
    if not any(loc["name"] == loc_name for loc in location_data):
        location_data.append({
            "name": loc_name,
            "category": ["Clues"],
            "clue_index": i,
            "requires": f"|Clue of the Cosmos:{i}|",
        })

# Dynamically build LOCATION_NAME_TO_ID by iterating over the location_data list
LOCATION_NAME_TO_ID = {
    loc["name"]: LOCATION_BASE_ID + index
    for index, loc in enumerate(location_data, start=1)
}

location_name_groups = {
    "All": set(LOCATION_NAME_TO_ID.keys()),
    "Letters": {loc["name"] for loc in location_data if "Letters" in loc.get("category", [])},
    "Numbers": {loc["name"] for loc in location_data if "Numbers" in loc.get("category", [])},
    "Symbols": {loc["name"] for loc in location_data if "Symbols" in loc.get("category", [])},
    "Clues": {loc["name"] for loc in location_data if "Clues" in loc.get("category", [])},
    "Milestones": set(),
    "Draws": set(),
    "Discards": set(),
}


def register_milestone_locations(
    clues_in_pool: int = MAX_CLUES_IN_POOL,
    interval: int = 10,
    cache_size: int = 2,
    custom_mapping: dict[str, int] | None = None,
) -> dict[str, int]:
    """Dynamically registers 'Cosmic Milestone (<M> Clues) - Cache 1..Y' locations and returns Name -> ID."""
    registered: dict[str, int] = {}
    if interval <= 0 or cache_size <= 0 or clues_in_pool <= 0:
        return registered

    for clue_count in range(interval, clues_in_pool + 1, interval):
        for cache_idx in range(1, cache_size + 1):
            loc_name = f"Cosmic Milestone ({clue_count} Clues) - Cache {cache_idx}"
            if not any(loc["name"] == loc_name for loc in location_data):
                location_data.append({
                    "name": loc_name,
                    "category": ["Milestones"],
                    "milestone_clues": clue_count,
                    "cache_index": cache_idx,
                    "requires": f"|Clue of the Cosmos:{clue_count}|",
                })

            if custom_mapping and loc_name in custom_mapping:
                LOCATION_NAME_TO_ID[loc_name] = int(custom_mapping[loc_name])
            elif loc_name not in LOCATION_NAME_TO_ID:
                LOCATION_NAME_TO_ID[loc_name] = (
                    MILESTONE_LOCATION_BASE_ID
                    + (clue_count - 1) * MAX_MILESTONE_CACHE_SIZE
                    + cache_idx
                )

            location_name_groups["All"].add(loc_name)
            location_name_groups["Milestones"].add(loc_name)
            registered[loc_name] = LOCATION_NAME_TO_ID[loc_name]
    return registered


def register_player_card_locations(
    player_list: list[str],
    max_draws: int = MAX_CARDS_IN_POOL,
    max_discards: int = MAX_CARDS_IN_POOL,
    custom_mapping: dict[str, int] | None = None,
) -> dict[str, int]:
    """Dynamically registers '<Player> Draw 1..N' and '<Player> Discard 1..N' locations and returns Name -> ID."""
    registered: dict[str, int] = {}
    for raw_player in player_list:
        player_name = str(raw_player).strip()
        if not player_name:
            continue

        for card_type, group_name, max_count in (
            ("Draw", "Draws", max_draws),
            ("Discard", "Discards", max_discards),
        ):
            for i in range(1, max_count + 1):
                loc_name = f"{player_name} {card_type} {i}"
                if not any(loc["name"] == loc_name for loc in location_data):
                    location_data.append({
                        "name": loc_name,
                        "category": [group_name],
                        "player_card": player_name,
                        "card_type": card_type,
                        "card_index": i,
                        "requires": f"|{player_name} {card_type}:{i}|",
                    })

                if custom_mapping and loc_name in custom_mapping:
                    LOCATION_NAME_TO_ID[loc_name] = int(custom_mapping[loc_name])
                elif loc_name not in LOCATION_NAME_TO_ID:
                    existing_card_ids = [
                        idx for idx in LOCATION_NAME_TO_ID.values()
                        if CARD_LOCATION_BASE_ID <= idx < MILESTONE_LOCATION_BASE_ID
                    ]
                    next_id = (max(existing_card_ids) + 1) if existing_card_ids else (CARD_LOCATION_BASE_ID + 1)
                    LOCATION_NAME_TO_ID[loc_name] = next_id

                location_name_groups["All"].add(loc_name)
                location_name_groups[group_name].add(loc_name)
                registered[loc_name] = LOCATION_NAME_TO_ID[loc_name]
    return registered


class TowerOfBabelLocation(Location):
    game = game_name


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


def create_clue_locations(world: "TowerOfBabelWorld", overworld, count: int) -> None:
    """Adds 'Collect 1..count Clues of the Cosmos' locations to the Overworld."""
    for i in range(1, count + 1):
        loc_name = f"Collect {i} Clues of the Cosmos"
        overworld.locations.append(TowerOfBabelLocation(
            world.player,
            loc_name,
            world.location_name_to_id[loc_name],
            overworld
        ))


def create_milestone_locations(world: "TowerOfBabelWorld", overworld) -> None:
    """Adds 'Cosmic Milestone (<M> Clues) - Cache 1..Y' locations to the Overworld."""
    clues_in_pool = int(world.options.clues_in_pool)
    interval = int(world.options.milestone_interval)
    cache_size = int(world.options.milestone_cache_size)
    if interval <= 0 or cache_size <= 0 or clues_in_pool <= 0:
        return

    for clue_count in range(interval, clues_in_pool + 1, interval):
        for cache_idx in range(1, cache_size + 1):
            loc_name = f"Cosmic Milestone ({clue_count} Clues) - Cache {cache_idx}"
            overworld.locations.append(TowerOfBabelLocation(
                world.player,
                loc_name,
                world.location_name_to_id[loc_name],
                overworld
            ))


def create_card_locations(world: "TowerOfBabelWorld", overworld) -> None:
    """Adds '<Player> Draw 1..N' and '<Player> Discard 1..N' locations for each player in Player List."""
    num_draws = int(world.options.num_draws)
    num_discards = int(world.options.num_discards)
    for player_name in world.get_card_players():
        for i in range(1, num_draws + 1):
            loc_name = f"{player_name} Draw {i}"
            overworld.locations.append(TowerOfBabelLocation(
                world.player,
                loc_name,
                world.location_name_to_id[loc_name],
                overworld
            ))
        for i in range(1, num_discards + 1):
            loc_name = f"{player_name} Discard {i}"
            overworld.locations.append(TowerOfBabelLocation(
                world.player,
                loc_name,
                world.location_name_to_id[loc_name],
                overworld
            ))


def create_regular_locations(world: "TowerOfBabelWorld") -> None:
    """Master function to populate the Overworld with all active locations."""
    overworld = world.get_region("Overworld")

    # Populate the enabled character location sub-groups
    if world.options.include_letters:
        create_letter_locations(world, overworld)
    if world.options.include_numbers:
        create_number_locations(world, overworld)
    if world.options.include_symbols:
        create_symbol_locations(world, overworld)

    # Populate Clue of the Cosmos and Milestone Cache locations when Goal is Mysteries of the Cosmos
    if world.options.goal == world.options.goal.option_mysteries_of_the_cosmos:
        create_clue_locations(world, overworld, int(world.options.clues_in_pool))
        create_milestone_locations(world, overworld)

    # Populate Player Draw and Discard locations when Player List is populated
    if world.get_card_players():
        create_card_locations(world, overworld)

    # Add the Victory location manually (exempt from categories)
    for loc in location_data:
        if loc.get("victory"):
            overworld.locations.append(TowerOfBabelLocation(
                world.player,
                loc["name"],
                world.location_name_to_id[loc["name"]],
                overworld
            ))
