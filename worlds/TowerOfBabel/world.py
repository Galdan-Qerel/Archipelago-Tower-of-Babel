from collections.abc import Mapping
import sys
from typing import Any

# Imports of base Archipelago modules must be absolute.
from Options import OptionError
from worlds.AutoWorld import WebWorld, World

# Imports of your world's files must be relative.
from . import items, locations, options as babel_options, regions, rules
from .Game import game_name


class TowerOfBabelWebWorld(WebWorld):
    option_groups = babel_options.option_groups


class TowerOfBabelWorld(World):
    game = game_name

    web = TowerOfBabelWebWorld()
    options_dataclass = babel_options.TowerOfBabelOptions
    options: babel_options.TowerOfBabelOptions
    location_name_to_id = locations.LOCATION_NAME_TO_ID
    item_name_to_id = items.ITEM_NAME_TO_ID
    item_name_groups = items.item_name_groups
    location_name_groups = locations.location_name_groups
    origin_region_name = "Overworld"

    @classmethod
    def register_dynamic_player_cards(cls, player_list: list[str]) -> None:
        if not player_list:
            return
        items.register_player_card_items(player_list)
        locations.register_player_card_locations(player_list)

        cls.item_name_to_id = dict(items.ITEM_NAME_TO_ID)
        cls.item_id_to_name = {code: name for name, code in cls.item_name_to_id.items()}
        cls.item_names = frozenset(cls.item_name_to_id)
        cls.item_name_groups = {
            group_name: frozenset(group_set)
            for group_name, group_set in items.item_name_groups.items()
        }
        cls.item_name_groups["Everything"] = cls.item_names
        cls.all_item_and_group_names = frozenset(cls.item_names | set(cls.item_name_groups))

        cls.location_name_to_id = dict(locations.LOCATION_NAME_TO_ID)
        cls.location_id_to_name = {code: name for name, code in cls.location_name_to_id.items()}
        cls.location_names = frozenset(cls.location_name_to_id)
        cls.location_name_groups = {
            group_name: frozenset(group_set)
            for group_name, group_set in locations.location_name_groups.items()
        }
        cls.location_name_groups["Everywhere"] = cls.location_names

        worlds_mod = sys.modules.get("worlds")
        if worlds_mod is not None and hasattr(worlds_mod, "network_data_package"):
            games_pkg = worlds_mod.network_data_package.get("games")
            if isinstance(games_pkg, dict) and cls.game in games_pkg:
                games_pkg[cls.game] = cls.get_data_package_data()

    @classmethod
    def register_dynamic_milestone_locations(
        cls,
        clues_in_pool: int,
        interval: int,
        cache_size: int,
    ) -> None:
        if interval <= 0 or cache_size <= 0 or clues_in_pool <= 0:
            return
        locations.register_milestone_locations(clues_in_pool, interval, cache_size)

        cls.location_name_to_id = dict(locations.LOCATION_NAME_TO_ID)
        cls.location_id_to_name = {code: name for name, code in cls.location_name_to_id.items()}
        cls.location_names = frozenset(cls.location_name_to_id)
        cls.location_name_groups = {
            group_name: frozenset(group_set)
            for group_name, group_set in locations.location_name_groups.items()
        }
        cls.location_name_groups["Everywhere"] = cls.location_names

        worlds_mod = sys.modules.get("worlds")
        if worlds_mod is not None and hasattr(worlds_mod, "network_data_package"):
            games_pkg = worlds_mod.network_data_package.get("games")
            if isinstance(games_pkg, dict) and cls.game in games_pkg:
                games_pkg[cls.game] = cls.get_data_package_data()

    def get_card_players(self) -> list[str]:
        cleaned: list[str] = []
        for entry in self.options.player_list.value:
            name = str(entry).strip()
            if name and name not in cleaned:
                cleaned.append(name)
        return cleaned

    def generate_early(self) -> None:
        if (
            not self.options.include_letters
            and not self.options.include_numbers
            and not self.options.include_symbols
            and self.options.goal == babel_options.Goal.option_full_language_unlock
        ):
            raise OptionError(
                f"Tower of Babel ({self.player_name}): At least one character pool "
                "(Include Letters, Include Numbers, or Include Symbols) must be enabled "
                "when Goal is 'Full Language Unlock'."
            )

        if self.options.clues_to_goal.value > self.options.clues_in_pool.value:
            self.options.clues_to_goal.value = self.options.clues_in_pool.value

        if self.options.goal == babel_options.Goal.option_mysteries_of_the_cosmos:
            self.register_dynamic_milestone_locations(
                int(self.options.clues_in_pool.value),
                int(self.options.milestone_interval.value),
                int(self.options.milestone_cache_size.value),
            )

        card_players = self.get_card_players()
        if card_players:
            self.register_dynamic_player_cards(card_players)

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
        card_players = self.get_card_players()
        card_item_map = {
            f"{p} {t}": self.item_name_to_id[f"{p} {t}"]
            for p in card_players
            for t in ("Draw", "Discard")
            if f"{p} {t}" in self.item_name_to_id
        }
        num_draws = int(self.options.num_draws.value)
        num_discards = int(self.options.num_discards.value)
        card_loc_map: dict[str, int] = {}
        for p in card_players:
            for i in range(1, num_draws + 1):
                loc_name = f"{p} Draw {i}"
                if loc_name in self.location_name_to_id:
                    card_loc_map[loc_name] = self.location_name_to_id[loc_name]
            for i in range(1, num_discards + 1):
                loc_name = f"{p} Discard {i}"
                if loc_name in self.location_name_to_id:
                    card_loc_map[loc_name] = self.location_name_to_id[loc_name]

        clues_in_pool = int(self.options.clues_in_pool.value)
        milestone_interval = int(self.options.milestone_interval.value)
        milestone_cache_size = int(self.options.milestone_cache_size.value)
        milestone_loc_map: dict[str, int] = {}
        if (
            self.options.goal == babel_options.Goal.option_mysteries_of_the_cosmos
            and milestone_interval > 0
            and milestone_cache_size > 0
        ):
            for clue_count in range(milestone_interval, clues_in_pool + 1, milestone_interval):
                for cache_idx in range(1, milestone_cache_size + 1):
                    loc_name = f"Cosmic Milestone ({clue_count} Clues) - Cache {cache_idx}"
                    if loc_name in self.location_name_to_id:
                        milestone_loc_map[loc_name] = self.location_name_to_id[loc_name]

        return {
            "goal": int(self.options.goal.value),
            "include_letters": bool(self.options.include_letters.value),
            "include_numbers": bool(self.options.include_numbers.value),
            "include_symbols": bool(self.options.include_symbols.value),
            "clues_in_pool": clues_in_pool,
            "clues_to_goal": int(self.options.clues_to_goal.value),
            "milestone_interval": milestone_interval,
            "milestone_cache_size": milestone_cache_size,
            "milestone_location_name_to_id": milestone_loc_map,
            "player_list": card_players,
            "starting_hand": int(self.options.starting_hand.value),
            "num_discards": num_discards,
            "num_draws": num_draws,
            "card_item_name_to_id": card_item_map,
            "card_location_name_to_id": card_loc_map,
            # Upcoming features:
            # "hint_cost_reduction": bool(self.options.hint_cost_reduction.value),
            # "hint_cost_reduction_amount": int(self.options.hint_cost_reduction_amount.value),
        }
