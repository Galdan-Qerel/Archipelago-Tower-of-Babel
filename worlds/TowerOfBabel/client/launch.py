import asyncio
import random
import string
import unicodedata
import logging
import websockets
import json
import uuid
import os
import ast
import difflib
import ssl  # Added SSL module to handle certificate bypassing
from typing import Any

import ModuleUpdate
ModuleUpdate.update()

import Utils
from CommonClient import CommonContext, server_loop, gui_enabled, ClientCommandProcessor, get_base_parser
from ..Game import game_name

# Import your local manual items dictionary and invert it so we can look up Names by ID
from ..items import ITEM_NAME_TO_ID, item_name_groups, register_player_card_items
babel_item_id_to_name = {v: k for k, v in ITEM_NAME_TO_ID.items()}
from ..locations import (
    LOCATION_NAME_TO_ID,
    register_milestone_locations,
    register_player_card_locations,
)
from ..options import Goal

SYMBOLS_LIST = sorted(
    item_name.split(" ", 1)[-1].strip()
    for item_name in item_name_groups.get("Symbols", set())
)
SYMBOLS_CHARS = set(SYMBOLS_LIST)


logger = logging.getLogger("Client")

# -----------------------------
# SPOILER LOG PARSER LOGIC
# -----------------------------
def load_spoiler_log(spoiler_file: str):
    locations = {}
    worlds = set()
    in_locations = False

    with open(spoiler_file, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            if line.startswith("Player ") and ":" in line:
                _, world = line.split(":", 1)
                worlds.add(world.strip())
                continue

            if line == "Locations:":
                in_locations = True
                continue

            if in_locations and line.endswith(":") and " " not in line:
                break

            if in_locations and ":" in line:
                separator_found = False
                for player in worlds:
                    player_sep = f" ({player}): "
                    if player_sep in line:
                        loc, item = line.split(player_sep, 1)
                        loc = loc + f" ({player})"
                        
                        item = item.strip()
                        if item not in locations:
                            locations[item] = []
                        locations[item].append(loc.strip())
                        
                        separator_found = True
                        break
                
                if not separator_found:
                    if ": " in line:
                        loc, item = line.rsplit(": ", 1)
                    else:
                        loc, item = line.rsplit(":", 1)
                        
                    item = item.strip()
                    if item not in locations:
                        locations[item] = []
                    locations[item].append(loc.strip())

    return locations, sorted(worlds)

# -----------------------------
# COMMAND PROCESSOR
# -----------------------------
class BabelCommandProcessor(ClientCommandProcessor):
    def _cmd_babel(self, *args: str):
        """Configure the Babel slot for unlocked data. Usage: /babel "<slot_name>" [password]"""
        if not args:
            self.output("Please provide a slot name. Usage: /babel \"<slot_name>\" [password]")
            return
            
        if not self.ctx.server_address:
            self.output("Please connect the main client first using /connect")
            return

        # Archipelago splits arguments by space unless wrapped in quotes
        if len(args) == 1:
            slot_name = args[0]
            password = ""
        elif len(args) == 2:
            slot_name = args[0]
            password = args[1]
        else:
            self.output("[Babel Error] Too many arguments. If your slot name contains spaces, you MUST wrap it in quotes! Example: /babel \"My Slot Name\" my_password")
            return

        self.ctx.babel_slot = slot_name
        self.ctx.babel_password = password
        
        if self.ctx.babel_task:
            self.ctx.babel_task.cancel()
            
        self.ctx.unlocked_chars.clear()
        self.ctx.clues_collected = 0
        self.ctx.player_draws_collected.clear()
        self.ctx.player_discards_collected.clear()
        self.ctx.babel_task = asyncio.create_task(self.ctx.connect_babel())
        self.output(f"Connecting background Babel slot to '{slot_name}'...")
        
    def _cmd_unlocked(self):
        """View the symbols, Clues of the Cosmos, and Player Hands unlocked so far. (Usage: /unlocked)"""
        if not self.ctx.babel_slot:
            self.output("Babel slot not configured. Please use '/babel \"<slot_name>\" [password]' first.")
            return
            
        if self.ctx.unlocked_chars:
            self.output(f"Unlocked symbols: {', '.join(sorted(self.ctx.unlocked_chars))}")
        else:
            self.output("No symbols unlocked yet.")

        if self.ctx.babel_slot_data.get("goal") == Goal.option_mysteries_of_the_cosmos or self.ctx.clues_collected > 0:
            clues_to_goal = self.ctx.babel_slot_data.get("clues_to_goal", 100)
            clues_in_pool = int(self.ctx.babel_slot_data.get("clues_in_pool", 100))
            self.output(f"Clues of the Cosmos collected: {self.ctx.clues_collected} / {clues_to_goal}")
            interval = int(self.ctx.babel_slot_data.get("milestone_interval", 0))
            cache_size = int(self.ctx.babel_slot_data.get("milestone_cache_size", 0))
            if interval > 0 and cache_size > 0:
                total_milestones = len(range(interval, clues_in_pool + 1, interval))
                reached_milestones = min(self.ctx.clues_collected // interval, total_milestones)
                self.output(
                    f"Cosmic Milestone Caches unlocked: {reached_milestones} / {total_milestones} "
                    f"(Every {interval} clues -> {cache_size} item(s) per cache)"
                )

        hand_stats = self.ctx.get_player_hand_stats()
        if hand_stats:
            self.output("Player Hands:")
            for stat in hand_stats:
                self.output(
                    f" - {stat['player']}: Hand = {stat['current_hand']} "
                    f"(Starting: {stat['starting_hand']}, Draws: {stat['draws']}/{stat['max_draws']}, "
                    f"Discards: {stat['discards']}/{stat['max_discards']})"
                )

    def _cmd_babelspoiler(self, spoiler_path: str = ""):
        """Set the path to the Archipelago spoiler log. Usage: /babelspoiler "<path_to_spoiler>" """
        if not spoiler_path:
            self.output("Usage: /babelspoiler \"<path_to_spoiler>\"")
            return
            
        if not os.path.exists(spoiler_path):
            self.output(f"Could not find spoiler log at: {spoiler_path}")
            return
            
        self.ctx.spoiler_log_path = spoiler_path
        self.output(f"Successfully configured spoiler log path: {spoiler_path}")

    def _cmd_babelhint(self, *item_name_parts):
        """Search the configured spoiler log for a ciphered location hint. Usage: /babelhint <item name>"""
        if not self.ctx.babel_slot:
            self.output("Babel slot not configured. Please use '/babel \"<slot_name>\" [password]' first.")
            return

        if not self.ctx.spoiler_log_path:
            self.output("Spoiler log not configured. Please set it first using '/babelspoiler \"<path_to_spoiler>\"'")
            return
            
        if not os.path.exists(self.ctx.spoiler_log_path):
            self.output(f"Configured spoiler log is missing: {self.ctx.spoiler_log_path}. Please reconfigure.")
            self.ctx.spoiler_log_path = None
            return

        if not item_name_parts:
            self.output("Usage: /babelhint <item name>")
            return
            
        if not self.ctx.username:
            self.output("You must be connected to a main slot (using /connect) to search for your items.")
            return

        item_name = " ".join(item_name_parts)
        identifier = self.ctx.username
        full_query = f"{item_name} ({identifier})"
        
        try:
            locations, valid_worlds = load_spoiler_log(self.ctx.spoiler_log_path)
        except Exception as e:
            self.output(f"Error parsing spoiler log: {e}")
            return
            
        if full_query in locations:
            all_locs = locations[full_query]
            
            unfound_locs = []
            found_locs = []
            
            # --- THE NEW FILTERING ENGINE ---
            for loc in all_locs:
                is_found = False
                location_id = None
                sender_id = None
                
                # 1. Parse "Location Name (Player Name)" safely using rsplit
                if " (" in loc and loc.endswith(")"):
                    parts = loc.rsplit(" (", 1)
                    loc_name_clean = parts[0].strip()
                    sender_name = parts[1][:-1].strip()
                    
                    # 2. Resolve the Sender's Player ID safely
                    if hasattr(self.ctx, "player_names"):
                        for p_id, p_name in self.ctx.player_names.items():
                            if p_name == sender_name:
                                sender_id = p_id
                                break
                                
                    # 3. Resolve the Location ID
                    if sender_id and hasattr(self.ctx, "slot_info") and sender_id in self.ctx.slot_info:
                        game_name = self.ctx.slot_info[sender_id].game
                        if game_name in self.ctx.location_names:
                            for l_id, l_name in self.ctx.location_names[game_name].items():
                                if str(l_name).lower() == loc_name_clean.lower():
                                    location_id = l_id
                                    break
                                    
                    # 4. Check if we have received this item from this specific location & player
                    if location_id and sender_id:
                        for net_item in self.ctx.items_received:
                            if net_item.location == location_id and net_item.player == sender_id:
                                is_found = True
                                break
                
                if is_found:
                    found_locs.append(loc)
                else:
                    # ADDED: Store the resolved IDs alongside the raw string for the scouting phase
                    unfound_locs.append((loc, location_id, sender_id))
            
            # --- OUTPUT AND UI UPDATES ---
            self.output(f"[Babel] Status for '{full_query}': {len(found_locs)} Found, {len(unfound_locs)} Remaining.")
            
            if unfound_locs:
                for loc_str, loc_id, target_slot in unfound_locs:
                    if loc_id and target_slot:
                        # Extract the owner name cleanly from the spoiler log string
                        owner_name = f"Player {target_slot}"
                        if " (" in loc_str and loc_str.endswith(")"):
                            owner_name = loc_str.rsplit(" (", 1)[1][:-1].strip()

                        # Skip all lookups! We construct the package manually using the queried item_name,
                        # and explicitly set its text color to "plum" (Progression).
                        nodes = [
                            {"text": "[Babel Scout] ", "color": "green"},
                            {"type": "text", "text": owner_name, "color": "yellow"},
                            {"text": "'s "},
                            {"type": "location_id", "location": loc_id, "text": str(loc_id)},
                            {"text": " contains "},
                            {"type": "text", "text": item_name, "color": "plum"},
                            {"text": " belonging to "},
                            {"type": "player_id", "player": self.ctx.slot, "text": str(self.ctx.slot)},
                            {"text": ".\n"}
                        ]
                        
                        package = {
                            "cmd": "PrintJSON",
                            "data": nodes,
                            "type": "BabelHint"
                        }
                        self.ctx.on_print_json(package)
                    else:
                        # Fallback: Print raw text only if the Location ID literally could not be found
                        self._output_babelhint_result(full_query, loc_str)
            else:
                self.output(f"All locations for '{item_name}' have already been found! No hints needed.")
                
            return
            
        # Closest matches logic remains unchanged
        filtered_items = [i for i in locations.keys() if i.endswith(f"({identifier})")]
        guesses = difflib.get_close_matches(full_query, filtered_items, n=5, cutoff=0.0)
        
        if guesses:
            self.output(f"No exact match for '{full_query}'. Closest matches:")
            for g in guesses:
                self.output(f" - {g}")
        else:
            self.output(f"Could not find any items for '{identifier}' matching '{item_name}'.")

    def _output_babelhint_result(self, item_name: str, raw_location: str):
        nodes = [{"text": f"BabelHint for {item_name}:\nLocation: "}]
        nodes.extend(self.ctx.scramble_text_to_nodes(raw_location))
        
        package = {
            "cmd": "PrintJSON",
            "data": nodes,
            "type": "BabelHint"
        }
        self.ctx.on_print_json(package)

    def _cmd_babelhintloc(self, *args: str):
        """
        Scout a location silently via the server.
        Usage: /babelhintloc [Location Name]
        """
        if not args:
            self.output("Usage: /babelhintloc [Location Name]")
            return

        location_name = " ".join(args).strip().lower()
        
        location_id = None
        target_slot = None
        
        # 1. Iterate through all connected slots to find the location
        # self.ctx.slot_info is a dict of slot_id: slot_data
        for slot_id, slot_data in self.ctx.slot_info.items():
            game_name = slot_data.game
            
            # Check if this game exists in the NameLookupDict
            if game_name in self.ctx.location_names:
                # Direct indexing instead of .get()
                game_locs = self.ctx.location_names[game_name]
                
                # Iterate through the ID:Name map for this game
                for l_id, l_name in game_locs.items():
                    if str(l_name).lower() == location_name:
                        location_id = l_id
                        target_slot = slot_id
                        break
            if location_id:
                break
        
        if not location_id:
            self.output(f"[Babel Error] Could not find '{location_name}' in any connected world.")
            return
            
        self.output(f"[Babel] Scouting '{location_name}' (Targeting slot {target_slot})...")
        
        # 2. Wrap the async send_msgs call in a task so it fires from the synchronous command processor
        import asyncio
        asyncio.create_task(self.ctx.scout_locations_silently([location_id], target_slot))

# -----------------------------
# CONTEXT MANAGER
# -----------------------------
class BabelContext(CommonContext):
    command_processor = BabelCommandProcessor
    game = ""  
    items_handling = 0b111 
    tags = {"AP", "TextOnly"} 

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.unlocked_chars = set()
        self.clues_collected = 0
        self.player_draws_collected: dict[str, int] = {}
        self.player_discards_collected: dict[str, int] = {}
        self.babel_slot_data = {}
        self.babel_missing_locations = set()
        
        self.babel_checked_locations = set() 
        self.babel_slot = None
        self.babel_password = ""
        self.babel_task = None
        self.babel_ws = None
        self.spoiler_log_path = None  
        self.babel_initialized = False
        self.babel_private_hints = []

        # Hook into Archipelago's native string resolution to globally scramble the GUI (including the Hint Tab!)
        if hasattr(self.item_names, 'lookup_in_game'):
            self._orig_item_get_name = self.item_names.lookup_in_game
            self.item_names.lookup_in_game = self._scrambled_item_name
            
        if hasattr(self.location_names, 'lookup_in_game'):
            self._orig_loc_get_name = self.location_names.lookup_in_game
            self.location_names.lookup_in_game = self._scrambled_loc_name

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def _output_babel_unlock(self, char_norm: str):
        nodes = [
            {"text": "[Babel] ", "color": "green"},
            {"text": "Data Translated! You can now read the character: "},
            {"text": char_norm, "color": "magenta"}
        ]
        package = {
            "cmd": "PrintJSON",
            "data": nodes,
            "type": "BabelUnlock"
        }
        self.on_print_json(package)

    def _output_babel_clue(self):
        clues_to_goal = self.babel_slot_data.get("clues_to_goal", 100)
        nodes = [
            {"text": "[Babel] ", "color": "green"},
            {"text": "Cosmic Discovery! Clue of the Cosmos found ("},
            {"text": f"{self.clues_collected}/{clues_to_goal}", "color": "magenta"},
            {"text": ")"}
        ]
        package = {
            "cmd": "PrintJSON",
            "data": nodes,
            "type": "BabelUnlock"
        }
        self.on_print_json(package)

        interval = int(self.babel_slot_data.get("milestone_interval", 0))
        cache_size = int(self.babel_slot_data.get("milestone_cache_size", 0))
        clues_in_pool = int(self.babel_slot_data.get("clues_in_pool", 100))
        if (
            interval > 0
            and cache_size > 0
            and 0 < self.clues_collected <= clues_in_pool
            and self.clues_collected % interval == 0
        ):
            milestone_nodes = [
                {"text": "[Babel] ", "color": "green"},
                {"text": f"Cosmic Milestone Reached ({self.clues_collected} Clues)! Unlocked Cache of "},
                {"text": f"{cache_size} item(s)", "color": "cyan"},
                {"text": "!"},
            ]
            self.on_print_json({
                "cmd": "PrintJSON",
                "data": milestone_nodes,
                "type": "BabelUnlock",
            })

    def _output_babel_card(self, player_name: str, card_type: str):
        starting_hand = int(self.babel_slot_data.get("starting_hand", 5))
        draws = self.player_draws_collected.get(player_name, 0)
        discards = self.player_discards_collected.get(player_name, 0)
        hand_size = starting_hand + draws - discards
        nodes = [
            {"text": "[Babel] ", "color": "green"},
            {"text": f"Deck Update! {player_name} received a "},
            {"text": card_type, "color": "magenta"},
            {"text": f" (Current Hand: {hand_size} | Draws: {draws}, Discards: {discards})"}
        ]
        package = {
            "cmd": "PrintJSON",
            "data": nodes,
            "type": "BabelUnlock"
        }
        self.on_print_json(package)

    def get_player_hand_stats(self) -> list[dict[str, Any]]:
        """Returns hand calculation stats for each player in player_list (Starting Hand + Draws - Discards)."""
        player_list = self.babel_slot_data.get("player_list", [])
        starting_hand = int(self.babel_slot_data.get("starting_hand", 5))
        max_draws = int(self.babel_slot_data.get("num_draws", 0))
        max_discards = int(self.babel_slot_data.get("num_discards", 0))
        stats: list[dict[str, Any]] = []
        for raw_player in player_list:
            player_name = str(raw_player).strip()
            if not player_name:
                continue
            draws = self.player_draws_collected.get(player_name, 0)
            discards = self.player_discards_collected.get(player_name, 0)
            stats.append({
                "player": player_name,
                "starting_hand": starting_hand,
                "draws": draws,
                "discards": discards,
                "current_hand": starting_hand + draws - discards,
                "max_draws": max_draws,
                "max_discards": max_discards,
            })
        return stats

    def _evaluate_babel_logic(self):
        new_checks = []
        valid_server_locs = self.babel_checked_locations | self.babel_missing_locations
        player_list = [str(p).strip() for p in self.babel_slot_data.get("player_list", []) if str(p).strip()]

        for loc_name, loc_id in LOCATION_NAME_TO_ID.items():
            if loc_id in self.babel_checked_locations:
                continue
            if valid_server_locs and loc_id not in valid_server_locs:
                continue

            if loc_name.startswith("Found "):
                char_req = self.normalize_char(loc_name[6:])
                if char_req in self.unlocked_chars:
                    new_checks.append(loc_id)

            elif loc_name.startswith("Collect ") and loc_name.endswith(" Clues of the Cosmos"):
                try:
                    req_clues = int(loc_name.split(" ", 2)[1])
                    if self.clues_collected >= req_clues:
                        new_checks.append(loc_id)
                except ValueError:
                    pass

            elif loc_name.startswith("Cosmic Milestone (") and " Clues) - Cache " in loc_name:
                try:
                    req_str = loc_name[len("Cosmic Milestone ("):].split(" Clues)", 1)[0]
                    req_clues = int(req_str)
                    if self.clues_collected >= req_clues:
                        new_checks.append(loc_id)
                except ValueError:
                    pass

            elif loc_name == "Full Alphabet":
                goal = self.babel_slot_data.get("goal", Goal.option_full_language_unlock)
                if goal == Goal.option_mysteries_of_the_cosmos:
                    clues_to_goal = self.babel_slot_data.get("clues_to_goal", 100)
                    clues_in_pool = self.babel_slot_data.get("clues_in_pool", 100)
                    req_clues = min(clues_to_goal, clues_in_pool)
                    if self.clues_collected >= req_clues:
                        new_checks.append(loc_id)
                else:
                    inc_letters = self.babel_slot_data.get("include_letters", True)
                    inc_numbers = self.babel_slot_data.get("include_numbers", True)
                    inc_symbols = self.babel_slot_data.get("include_symbols", True)

                    goal_met = True
                    if inc_letters and not all(c in self.unlocked_chars for c in string.ascii_uppercase):
                        goal_met = False
                    if inc_numbers and not all(c in self.unlocked_chars for c in string.digits):
                        goal_met = False
                    if inc_symbols and not all(self.normalize_char(c) in self.unlocked_chars for c in SYMBOLS_CHARS):
                        goal_met = False

                    if goal_met:
                        new_checks.append(loc_id)

            elif player_list:
                for p_name in player_list:
                    draw_prefix = f"{p_name} Draw "
                    discard_prefix = f"{p_name} Discard "
                    if loc_name.startswith(draw_prefix):
                        try:
                            req_idx = int(loc_name[len(draw_prefix):])
                            if self.player_draws_collected.get(p_name, 0) >= req_idx:
                                new_checks.append(loc_id)
                        except ValueError:
                            pass
                        break
                    elif loc_name.startswith(discard_prefix):
                        try:
                            req_idx = int(loc_name[len(discard_prefix):])
                            if self.player_discards_collected.get(p_name, 0) >= req_idx:
                                new_checks.append(loc_id)
                        except ValueError:
                            pass
                        break

        return new_checks

    async def check_babel_locations(self):
        """Evaluates location logic and sends checks explicitly to the background Babel server."""
        if not self.babel_ws:
            return
            
        # Ensure all IDs are strict integers so the JSON perfectly matches AP protocols
        new_checks = [int(loc_id) for loc_id in self._evaluate_babel_logic()]
        
        if new_checks:
            package = [{"cmd": "LocationChecks", "locations": new_checks}]
            
            # Log the raw package so we can see exactly what IDs are being sent to the server!
            logger.info(f"[Babel] Firing LocationChecks package: {package}")
            
            await self.babel_ws.send(json.dumps(package))
            self.babel_checked_locations.update(new_checks)
            logger.info(f"[Babel] Auto-checked {len(new_checks)} location(s) on the background slot!")

            victory_loc_id = LOCATION_NAME_TO_ID.get("Full Alphabet")
            if victory_loc_id in new_checks:
                status_pkg = [{"cmd": "StatusUpdate", "status": 30}]
                await self.babel_ws.send(json.dumps(status_pkg))
                logger.info("[Babel] Goal condition met! Sent CLIENT_GOAL status update.")

    async def connect_babel(self):
        url = self.server_address
        if url and not (url.startswith("ws://") or url.startswith("wss://")):
            url = f"ws://{url}"

        ssl_context = None
        if url.startswith("wss://"):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        while True:
            try:
                self.babel_initialized = False
                async with websockets.connect(url, ssl=ssl_context) as ws:
                    self.babel_ws = ws
                    connect_package = [{
                        "cmd": "Connect",
                        "password": self.babel_password,
                        "name": self.babel_slot,
                        "version": {"major": 0, "minor": 6, "build": 7, "class": "Version"},
                        "tags": ["AP"],  # <--- PROMOTED TO A FULL GAME CLIENT!
                        "items_handling": 7,
                        "game": game_name,
                        "uuid": str(uuid.uuid4())
                    }]
                    await ws.send(json.dumps(connect_package))
                    
                    async for message in ws:
                        packages = json.loads(message)
                        is_initial_sync = any(pkg.get("cmd") == "Connected" for pkg in packages)
                        for package in packages:
                            cmd = package.get("cmd")
                            
                            if cmd == "Connected":
                                logger.info(f"[Babel] Successfully connected to background Babel slot: {self.babel_slot}")
                                self.babel_checked_locations = set(package.get("checked_locations", []))
                                self.babel_missing_locations = set(package.get("missing_locations", []))
                                self.babel_slot_data = package.get("slot_data", {}) or {}
                                self.clues_collected = 0
                                self.babel_initialized = True

                                # Register dynamic milestone locations from slot_data
                                milestone_interval = int(self.babel_slot_data.get("milestone_interval", 0))
                                milestone_cache_size = int(self.babel_slot_data.get("milestone_cache_size", 0))
                                if milestone_interval > 0 and milestone_cache_size > 0:
                                    register_milestone_locations(
                                        int(self.babel_slot_data.get("clues_in_pool", 100)),
                                        milestone_interval,
                                        milestone_cache_size,
                                        self.babel_slot_data.get("milestone_location_name_to_id"),
                                    )

                                # Register dynamic player card items & locations from slot_data
                                player_list = [
                                    str(p).strip()
                                    for p in self.babel_slot_data.get("player_list", [])
                                    if str(p).strip()
                                ]
                                self.player_draws_collected = {p: 0 for p in player_list}
                                self.player_discards_collected = {p: 0 for p in player_list}
                                if player_list:
                                    card_item_map = self.babel_slot_data.get("card_item_name_to_id")
                                    card_loc_map = self.babel_slot_data.get("card_location_name_to_id")
                                    registered_items = register_player_card_items(player_list, card_item_map)
                                    for name, code in registered_items.items():
                                        babel_item_id_to_name[code] = name
                                    register_player_card_locations(
                                        player_list,
                                        int(self.babel_slot_data.get("num_draws", 100)),
                                        int(self.babel_slot_data.get("num_discards", 100)),
                                        card_loc_map,
                                    )

                                # Automatically unlock disabled character sets so they aren't scrambled
                                if not self.babel_slot_data.get("include_letters", True):
                                    self.unlocked_chars.update(string.ascii_uppercase)
                                if not self.babel_slot_data.get("include_numbers", True):
                                    self.unlocked_chars.update(string.digits)
                                if not self.babel_slot_data.get("include_symbols", True):
                                    self.unlocked_chars.update(self.normalize_char(c) for c in SYMBOLS_CHARS)

                                await self.check_babel_locations()
                                if hasattr(self, "ui") and self.ui and hasattr(self.ui, "update_hints"):
                                    self.ui.update_hints()
                                
                            elif cmd == "RoomUpdate":
                                if "checked_locations" in package:
                                    self.babel_checked_locations.update(package["checked_locations"])
                            
                            elif cmd == "ReceivedItems":
                                player_list = [
                                    str(p).strip()
                                    for p in self.babel_slot_data.get("player_list", [])
                                    if str(p).strip()
                                ]
                                if package.get("index", 0) == 0:
                                    self.clues_collected = 0
                                    self.player_draws_collected = {p: 0 for p in player_list}
                                    self.player_discards_collected = {p: 0 for p in player_list}

                                for item in package.get("items", []):
                                    # Raw background websocket packages are dicts, not NetworkItems!
                                    item_id = item.get("item", 0)
                                    
                                    # EXCLUSIVELY look up items belonging to Tower of Babel
                                    item_name = babel_item_id_to_name.get(item_id)
                                    
                                    if item_name == "Clue of the Cosmos":
                                        self.clues_collected += 1
                                        if not is_initial_sync:
                                            self._output_babel_clue()
                                    elif item_name and item_name.endswith(" Draw") and item_name[:-5] in player_list:
                                        p_name = item_name[:-5]
                                        self.player_draws_collected[p_name] = self.player_draws_collected.get(p_name, 0) + 1
                                        if not is_initial_sync:
                                            self._output_babel_card(p_name, "Draw")
                                    elif item_name and item_name.endswith(" Discard") and item_name[:-8] in player_list:
                                        p_name = item_name[:-8]
                                        self.player_discards_collected[p_name] = self.player_discards_collected.get(p_name, 0) + 1
                                        if not is_initial_sync:
                                            self._output_babel_card(p_name, "Discard")
                                    elif item_name and item_name != "Victory":
                                        char_part = item_name.split(" ", 1)[-1].strip() if " " in item_name else item_name.strip()
                                        char_norm = self.normalize_char(char_part)
                                        
                                        if char_norm and char_norm not in self.unlocked_chars:
                                            self.unlocked_chars.add(char_norm)
                                            
                                            if not is_initial_sync:
                                                self._output_babel_unlock(char_norm)
                                                
                                self.babel_initialized = True
                                await self.check_babel_locations()
                                
                                # Force the Kivy Hint Tab to dynamically redraw
                                if hasattr(self, "ui") and self.ui and hasattr(self.ui, "update_hints"):
                                    self.ui.update_hints()
                            elif cmd == "ConnectionRefused":
                                logger.error(f"[Babel] Connection refused: {', '.join(package.get('errors', []))}")
                                return
                                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[Babel] Connection dropped. Reconnecting... ({e})")
                await asyncio.sleep(5)

    def get_babel_goal_progress(self) -> tuple[int, int, str]:
        """Returns (current, total, label_text) for the Babel progress bar."""
        if not self.babel_slot or not self.babel_initialized:
            return 0, 1, "Babel Goal: Not Connected (use /babel \"<slot_name>\")"

        goal = self.babel_slot_data.get("goal", Goal.option_full_language_unlock)
        if goal == Goal.option_mysteries_of_the_cosmos:
            clues_to_goal = int(self.babel_slot_data.get("clues_to_goal", 100))
            clues_in_pool = int(self.babel_slot_data.get("clues_in_pool", 100))
            max_clues = max(1, clues_in_pool)
            goal_clues = max(1, min(clues_to_goal, max_clues))
            current = min(self.clues_collected, max_clues)
            interval = int(self.babel_slot_data.get("milestone_interval", 0))
            cache_size = int(self.babel_slot_data.get("milestone_cache_size", 0))
            if interval > 0 and cache_size > 0:
                next_milestone = ((self.clues_collected // interval) + 1) * interval
                if next_milestone <= max_clues:
                    return (
                        current,
                        max_clues,
                        f"Clues: {self.clues_collected}/{max_clues} (Goal: {goal_clues} | Next Cache: {next_milestone})",
                    )
                else:
                    return (
                        current,
                        max_clues,
                        f"Clues: {self.clues_collected}/{max_clues} (Goal: {goal_clues} | All Caches Unlocked)",
                    )
            return current, max_clues, f"Clues: {self.clues_collected}/{max_clues} (Goal: {goal_clues})"
        else:
            inc_letters = self.babel_slot_data.get("include_letters", True)
            inc_numbers = self.babel_slot_data.get("include_numbers", True)
            inc_symbols = self.babel_slot_data.get("include_symbols", True)

            required_chars = set()
            if inc_letters:
                required_chars.update(string.ascii_uppercase)
            if inc_numbers:
                required_chars.update(string.digits)
            if inc_symbols:
                required_chars.update(self.normalize_char(c) for c in SYMBOLS_CHARS)

            target = max(1, len(required_chars))
            current = sum(1 for c in required_chars if c in self.unlocked_chars)
            return current, target, f"Symbols Unlocked: {current} / {target}"

    def make_gui(self):
        ui = super().make_gui()

        class BabelManager(ui):
            base_title = "Tower of Babel Multi-Client"

            def build(self):
                container = super().build()
                from kivymd.uix.boxlayout import MDBoxLayout
                from kivymd.uix.divider import MDDivider
                from kivymd.uix.gridlayout import MDGridLayout
                from kivymd.uix.label import MDLabel
                from kivymd.uix.progressindicator import MDLinearProgressIndicator
                from kivymd.uix.scrollview import MDScrollView
                from kivy.graphics import Color, InstructionGroup, Rectangle
                from kivy.metrics import dp, sp
                from kivy.utils import escape_markup

                self._escape_markup = escape_markup
                self._last_hand_state = None
                self._hand_row_widgets: dict[str, dict[str, Any]] = {}
                self._last_symbols_state = None
                self._symbol_cell_widgets: dict[str, tuple[MDBoxLayout, MDLabel]] = {}
                self._symbol_section_headers: dict[str, MDLabel] = {}
                self._last_milestone_bar_state = None

                self.babel_status_row = MDBoxLayout(
                    orientation="horizontal",
                    size_hint_y=None,
                    height=dp(26),
                    spacing=dp(10),
                    padding=(dp(10), dp(2)),
                )
                self.babel_progress_label = MDLabel(
                    text="Babel Goal: Not Connected (use /babel \"<slot_name>\")",
                    size_hint_x=None,
                    width=dp(340),
                    font_size=sp(13),
                    valign="center",
                )
                self.babel_progressbar = MDLinearProgressIndicator(
                    size_hint_y=None,
                    height=dp(8),
                    pos_hint={"center_y": 0.5},
                    max=1,
                    value=0,
                )
                self._milestone_canvas_group = InstructionGroup()
                self.babel_progressbar.canvas.after.add(self._milestone_canvas_group)
                self.babel_progressbar.bind(
                    pos=lambda *_: self._refresh_milestone_markers(force=True),
                    size=lambda *_: self._refresh_milestone_markers(force=True),
                )
                self.babel_status_row.add_widget(self.babel_progress_label)
                self.babel_status_row.add_widget(self.babel_progressbar)

                # Insert the Babel progress row right below the primary connect bar / progressbar at the top
                target_index = max(0, len(self.grid.children) - 2)
                self.grid.add_widget(self.babel_status_row, index=target_index)

                # Build the "Player Hands" tab
                self.hands_tab_layout = MDBoxLayout(
                    orientation="vertical",
                    padding=(dp(12), dp(10)),
                    spacing=dp(8),
                )

                self.hands_summary_label = MDLabel(
                    text="Connect a Babel slot using /babel \"<slot_name>\" to view player hands.",
                    size_hint_y=None,
                    height=dp(28),
                    font_size=sp(14),
                    markup=True,
                    valign="center",
                )
                self.hands_tab_layout.add_widget(self.hands_summary_label)

                # Table column header
                self.hands_header_row = MDBoxLayout(
                    orientation="horizontal",
                    size_hint_y=None,
                    height=dp(30),
                    spacing=dp(8),
                    padding=(dp(6), dp(2)),
                )
                for col_title, col_weight in (
                    ("[b]Player[/b]", 0.28),
                    ("[b]Current Hand[/b]", 0.18),
                    ("[b]Starting Hand[/b]", 0.18),
                    ("[b]Draws Found[/b]", 0.18),
                    ("[b]Discards Found[/b]", 0.18),
                ):
                    self.hands_header_row.add_widget(
                        MDLabel(
                            text=col_title,
                            markup=True,
                            size_hint_x=col_weight,
                            font_size=sp(13),
                            valign="center",
                        )
                    )
                self.hands_tab_layout.add_widget(self.hands_header_row)
                self.hands_tab_layout.add_widget(MDDivider(size_hint_y=None, height=dp(1)))

                self.hands_scroll = MDScrollView(do_scroll_x=False)
                self.hands_rows_container = MDBoxLayout(
                    orientation="vertical",
                    size_hint_y=None,
                    spacing=dp(4),
                    padding=(dp(2), dp(4)),
                )
                self.hands_rows_container.bind(minimum_height=self.hands_rows_container.setter("height"))
                self.hands_scroll.add_widget(self.hands_rows_container)
                self.hands_tab_layout.add_widget(self.hands_scroll)

                self.hands_tab = self.add_client_tab("Player Hands", self.hands_tab_layout)
                self.log_panels["Player Hands"] = self.hands_tab.content

                # Build the "Symbols Unlocked" tab
                self.symbols_tab_layout = MDBoxLayout(
                    orientation="vertical",
                    padding=(dp(14), dp(10)),
                    spacing=dp(10),
                )

                self.symbols_summary_label = MDLabel(
                    text=(
                        "Babel Cipher Tracker   |   "
                        "[b][color=ff4dff]Vibrant[/color][/b] = Unlocked   •   "
                        "[color=5c6270]Dull[/color] = Locked"
                    ),
                    size_hint_y=None,
                    height=dp(26),
                    font_size=sp(14),
                    markup=True,
                    valign="center",
                )
                self.symbols_tab_layout.add_widget(self.symbols_summary_label)
                self.symbols_tab_layout.add_widget(MDDivider(size_hint_y=None, height=dp(1)))

                self.symbols_scroll = MDScrollView(do_scroll_x=False)
                self.symbols_sections_container = MDBoxLayout(
                    orientation="vertical",
                    size_hint_y=None,
                    spacing=dp(14),
                    padding=(dp(4), dp(6)),
                )
                self.symbols_sections_container.bind(
                    minimum_height=self.symbols_sections_container.setter("height")
                )

                sections_spec = [
                    ("Letters", "Letters (A–Z)", list(string.ascii_uppercase), 13),
                    ("Numbers", "Numbers (0–9)", list(string.digits), 10),
                    ("Symbols", "Punctuation & Symbols", list(SYMBOLS_LIST), 10),
                ]

                for sec_key, sec_title, char_list, num_cols in sections_spec:
                    sec_header = MDLabel(
                        text=f"[b]{sec_title}[/b]",
                        size_hint_y=None,
                        height=dp(24),
                        font_size=sp(13),
                        markup=True,
                        valign="center",
                    )
                    self._symbol_section_headers[sec_key] = sec_header
                    self.symbols_sections_container.add_widget(sec_header)

                    grid = MDGridLayout(
                        cols=num_cols,
                        size_hint_y=None,
                        spacing=dp(6),
                        padding=(dp(2), dp(2)),
                    )
                    grid.bind(minimum_height=grid.setter("height"))

                    for ch in char_list:
                        norm_ch = self.ctx.normalize_char(ch)
                        cell_box = MDBoxLayout(
                            orientation="vertical",
                            size_hint_y=None,
                            height=dp(38),
                            padding=(dp(2), dp(2)),
                            radius=[dp(6), dp(6), dp(6), dp(6)],
                            theme_bg_color="Custom",
                            md_bg_color=(0.15, 0.16, 0.19, 1),
                        )
                        escaped_ch = escape_markup(ch)
                        cell_lbl = MDLabel(
                            text=f"[color=555b66]{escaped_ch}[/color]",
                            markup=True,
                            halign="center",
                            valign="center",
                            font_size=sp(16),
                        )
                        cell_box.add_widget(cell_lbl)
                        grid.add_widget(cell_box)
                        self._symbol_cell_widgets[norm_ch] = (cell_box, cell_lbl, escaped_ch)

                    self.symbols_sections_container.add_widget(grid)

                self.symbols_scroll.add_widget(self.symbols_sections_container)
                self.symbols_tab_layout.add_widget(self.symbols_scroll)

                self.symbols_tab = self.add_client_tab("Symbols Unlocked", self.symbols_tab_layout)
                self.log_panels["Symbols Unlocked"] = self.symbols_tab.content

                return container

            def _refresh_player_hands_ui(self):
                from kivymd.uix.boxlayout import MDBoxLayout
                from kivymd.uix.divider import MDDivider
                from kivymd.uix.label import MDLabel
                from kivy.metrics import dp, sp

                connected = bool(self.ctx.babel_slot and self.ctx.babel_initialized)
                hand_stats = self.ctx.get_player_hand_stats() if connected else []
                state_key = (
                    connected,
                    self.ctx.babel_slot,
                    tuple(
                        (
                            s["player"],
                            s["current_hand"],
                            s["starting_hand"],
                            s["draws"],
                            s["max_draws"],
                            s["discards"],
                            s["max_discards"],
                        )
                        for s in hand_stats
                    ),
                )
                if state_key == self._last_hand_state:
                    return
                self._last_hand_state = state_key

                if not connected:
                    self.hands_summary_label.text = (
                        "Babel Slot: Not Connected — run [b]/babel \"<slot_name>\"[/b] to track Player Hands."
                    )
                    self.hands_rows_container.clear_widgets()
                    self._hand_row_widgets.clear()
                    return

                if not hand_stats:
                    slot_escaped = self._escape_markup(str(self.ctx.babel_slot))
                    self.hands_summary_label.text = (
                        f"Connected to [b]{slot_escaped}[/b] — No players configured in 'player_list' for this slot."
                    )
                    self.hands_rows_container.clear_widgets()
                    self._hand_row_widgets.clear()
                    return

                starting_hand = hand_stats[0]["starting_hand"]
                summary_parts = [
                    f"{self._escape_markup(s['player'])}: [b]{s['current_hand']}[/b]"
                    for s in hand_stats
                ]
                self.hands_summary_label.text = (
                    f"Formula: Starting Hand ({starting_hand}) + Draws - Discards   |   "
                    + "  •  ".join(summary_parts)
                )

                current_players = [s["player"] for s in hand_stats]
                if list(self._hand_row_widgets.keys()) != current_players:
                    self.hands_rows_container.clear_widgets()
                    self._hand_row_widgets.clear()
                    for stat in hand_stats:
                        p_name = stat["player"]
                        row = MDBoxLayout(
                            orientation="horizontal",
                            size_hint_y=None,
                            height=dp(32),
                            spacing=dp(8),
                            padding=(dp(6), dp(2)),
                        )
                        lbl_player = MDLabel(markup=True, size_hint_x=0.28, font_size=sp(13), valign="center")
                        lbl_hand = MDLabel(markup=True, size_hint_x=0.18, font_size=sp(14), valign="center")
                        lbl_start = MDLabel(markup=True, size_hint_x=0.18, font_size=sp(13), valign="center")
                        lbl_draws = MDLabel(markup=True, size_hint_x=0.18, font_size=sp(13), valign="center")
                        lbl_discards = MDLabel(markup=True, size_hint_x=0.18, font_size=sp(13), valign="center")

                        row.add_widget(lbl_player)
                        row.add_widget(lbl_hand)
                        row.add_widget(lbl_start)
                        row.add_widget(lbl_draws)
                        row.add_widget(lbl_discards)

                        self.hands_rows_container.add_widget(row)
                        self.hands_rows_container.add_widget(MDDivider(size_hint_y=None, height=dp(1)))
                        self._hand_row_widgets[p_name] = {
                            "player": lbl_player,
                            "hand": lbl_hand,
                            "start": lbl_start,
                            "draws": lbl_draws,
                            "discards": lbl_discards,
                        }

                for stat in hand_stats:
                    p_name = stat["player"]
                    widgets = self._hand_row_widgets.get(p_name)
                    if not widgets:
                        continue
                    escaped_name = self._escape_markup(p_name)
                    widgets["player"].text = f"[b]{escaped_name}[/b]"
                    widgets["hand"].text = f"[b][color=da70d6]{stat['current_hand']}[/color][/b]"
                    widgets["start"].text = str(stat["starting_hand"])
                    widgets["draws"].text = f"[color=00e5ff]+{stat['draws']}[/color] / {stat['max_draws']}"
                    widgets["discards"].text = f"[color=ff8080]-{stat['discards']}[/color] / {stat['max_discards']}"

            def _refresh_symbols_unlocked_ui(self):
                connected = bool(self.ctx.babel_slot and self.ctx.babel_initialized)
                unlocked_snapshot = frozenset(self.ctx.unlocked_chars)
                inc_letters = bool(self.ctx.babel_slot_data.get("include_letters", True))
                inc_numbers = bool(self.ctx.babel_slot_data.get("include_numbers", True))
                inc_symbols = bool(self.ctx.babel_slot_data.get("include_symbols", True))

                state_key = (
                    connected,
                    self.ctx.babel_slot,
                    unlocked_snapshot,
                    inc_letters,
                    inc_numbers,
                    inc_symbols,
                )
                if state_key == self._last_symbols_state:
                    return
                self._last_symbols_state = state_key

                letters_norm = [self.ctx.normalize_char(c) for c in string.ascii_uppercase]
                numbers_norm = [self.ctx.normalize_char(c) for c in string.digits]
                symbols_norm = [self.ctx.normalize_char(c) for c in SYMBOLS_LIST]

                letters_unlocked = sum(1 for c in letters_norm if c in unlocked_snapshot)
                numbers_unlocked = sum(1 for c in numbers_norm if c in unlocked_snapshot)
                symbols_unlocked = sum(1 for c in symbols_norm if c in unlocked_snapshot)
                total_unlocked = letters_unlocked + numbers_unlocked + symbols_unlocked
                total_chars = len(letters_norm) + len(numbers_norm) + len(symbols_norm)

                if not connected:
                    self.symbols_summary_label.text = (
                        "Babel Slot: Not Connected — run [b]/babel \"<slot_name>\"[/b]   |   "
                        "[b][color=ff4dff]Vibrant[/color][/b] = Unlocked   •   "
                        "[color=555b66]Dull[/color] = Locked"
                    )
                else:
                    slot_escaped = self._escape_markup(str(self.ctx.babel_slot))
                    self.symbols_summary_label.text = (
                        f"Connected: [b]{slot_escaped}[/b]   |   "
                        f"Total Unlocked: [b][color=00f0ff]{total_unlocked} / {total_chars}[/color][/b]   |   "
                        "[b][color=ff4dff]Vibrant[/color][/b] = Unlocked   •   "
                        "[color=555b66]Dull[/color] = Locked"
                    )

                self._symbol_section_headers["Letters"].text = (
                    f"[b]Letters (A–Z)[/b] — [color=00f0ff]{letters_unlocked} / {len(letters_norm)}[/color]"
                    + ("" if inc_letters else "  [color=8892a0](Auto-Unlocked)[/color]")
                )
                self._symbol_section_headers["Numbers"].text = (
                    f"[b]Numbers (0–9)[/b] — [color=00f0ff]{numbers_unlocked} / {len(numbers_norm)}[/color]"
                    + ("" if inc_numbers else "  [color=8892a0](Auto-Unlocked)[/color]")
                )
                self._symbol_section_headers["Symbols"].text = (
                    f"[b]Punctuation & Symbols[/b] — [color=00f0ff]{symbols_unlocked} / {len(symbols_norm)}[/color]"
                    + ("" if inc_symbols else "  [color=8892a0](Auto-Unlocked)[/color]")
                )

                for norm_ch, (cell_box, cell_lbl, escaped_ch) in self._symbol_cell_widgets.items():
                    if norm_ch in unlocked_snapshot:
                        # Vibrant glowing magenta/cyan appearance for unlocked characters
                        cell_box.md_bg_color = (0.28, 0.10, 0.36, 1)
                        cell_lbl.text = f"[b][color=ff55ff]{escaped_ch}[/color][/b]"
                    else:
                        # Dull muted appearance for locked characters
                        cell_box.md_bg_color = (0.14, 0.15, 0.18, 1)
                        cell_lbl.text = f"[color=505662]{escaped_ch}[/color]"

            def _refresh_milestone_markers(self, force: bool = False):
                from kivy.graphics import Color, Rectangle
                from kivy.metrics import dp

                if not hasattr(self, "_milestone_canvas_group"):
                    return

                connected = bool(self.ctx.babel_slot and self.ctx.babel_initialized)
                goal = self.ctx.babel_slot_data.get("goal", Goal.option_full_language_unlock)
                interval = int(self.ctx.babel_slot_data.get("milestone_interval", 0))
                cache_size = int(self.ctx.babel_slot_data.get("milestone_cache_size", 0))
                clues_to_goal = int(self.ctx.babel_slot_data.get("clues_to_goal", 100))
                clues_in_pool = int(self.ctx.babel_slot_data.get("clues_in_pool", 100))
                max_clues = max(1, clues_in_pool)
                goal_clues = max(1, min(clues_to_goal, max_clues))
                bar_pos = (round(self.babel_progressbar.x, 1), round(self.babel_progressbar.y, 1))
                bar_size = (round(self.babel_progressbar.width, 1), round(self.babel_progressbar.height, 1))

                state_key = (
                    connected,
                    goal,
                    interval,
                    cache_size,
                    goal_clues,
                    max_clues,
                    self.ctx.clues_collected,
                    bar_pos,
                    bar_size,
                )
                if not force and state_key == self._last_milestone_bar_state:
                    return
                self._last_milestone_bar_state = state_key

                self._milestone_canvas_group.clear()
                if (
                    not connected
                    or goal != Goal.option_mysteries_of_the_cosmos
                    or self.babel_progressbar.width <= 0
                ):
                    return

                bar_x = self.babel_progressbar.x
                bar_w = self.babel_progressbar.width
                bar_cy = self.babel_progressbar.center_y
                tick_h = dp(14)
                tick_w = dp(2.5)
                outline_h = dp(16)
                outline_w = dp(4.5)

                # 1. Draw Milestone Cache markers across the full clues_in_pool bar length
                if interval > 0 and cache_size > 0:
                    for m in range(interval, max_clues + 1, interval):
                        ratio = m / max_clues
                        if ratio <= 0.0 or ratio > 1.0:
                            continue
                        px = bar_x + ratio * bar_w

                        # Dark outline behind the tick so it contrasts cleanly against the bar
                        self._milestone_canvas_group.add(Color(0.07, 0.08, 0.10, 0.95))
                        self._milestone_canvas_group.add(
                            Rectangle(
                                pos=(px - outline_w / 2.0, bar_cy - outline_h / 2.0),
                                size=(outline_w, outline_h),
                            )
                        )

                        # Vibrant cyan if unlocked, warm gold if upcoming
                        if self.ctx.clues_collected >= m:
                            self._milestone_canvas_group.add(Color(0.0, 0.95, 1.0, 1.0))
                        else:
                            self._milestone_canvas_group.add(Color(1.0, 0.78, 0.20, 0.95))
                        self._milestone_canvas_group.add(
                            Rectangle(
                                pos=(px - tick_w / 2.0, bar_cy - tick_h / 2.0),
                                size=(tick_w, tick_h),
                            )
                        )

                # 2. Draw the Goal indicator marker at goal_clues / max_clues (taller & distinct)
                goal_ratio = goal_clues / max_clues
                if 0.0 < goal_ratio <= 1.0:
                    goal_px = bar_x + goal_ratio * bar_w
                    goal_tick_h = dp(18)
                    goal_tick_w = dp(3.5)
                    goal_outline_h = dp(20)
                    goal_outline_w = dp(5.5)

                    self._milestone_canvas_group.add(Color(0.05, 0.05, 0.08, 0.98))
                    self._milestone_canvas_group.add(
                        Rectangle(
                            pos=(goal_px - goal_outline_w / 2.0, bar_cy - goal_outline_h / 2.0),
                            size=(goal_outline_w, goal_outline_h),
                        )
                    )

                    # Bright emerald green when goal is met, vibrant magenta while working toward goal
                    if self.ctx.clues_collected >= goal_clues:
                        self._milestone_canvas_group.add(Color(0.15, 1.0, 0.45, 1.0))
                    else:
                        self._milestone_canvas_group.add(Color(1.0, 0.25, 0.85, 1.0))
                    self._milestone_canvas_group.add(
                        Rectangle(
                            pos=(goal_px - goal_tick_w / 2.0, bar_cy - goal_tick_h / 2.0),
                            size=(goal_tick_w, goal_tick_h),
                        )
                    )

            def update_texts(self, dt):
                super().update_texts(dt)
                if hasattr(self, "babel_progressbar") and hasattr(self, "babel_progress_label"):
                    current, target, label_text = self.ctx.get_babel_goal_progress()
                    self.babel_progressbar.max = target
                    self.babel_progressbar.value = current
                    self.babel_progress_label.text = label_text
                    self._refresh_milestone_markers()
                if hasattr(self, "hands_rows_container"):
                    self._refresh_player_hands_ui()
                if hasattr(self, "_symbol_cell_widgets"):
                    self._refresh_symbols_unlocked_ui()

        return BabelManager

    def _scrambled_item_name(self, *args, **kwargs) -> str:
        """Safely catches any arguments AP passes, fetches the string, and scrambles it."""
        original_text = self._orig_item_get_name(*args, **kwargs)
        return self.scramble_raw_string(str(original_text))

    def _scrambled_loc_name(self, *args, **kwargs) -> str:
        """Safely catches any arguments AP passes, fetches the string, and scrambles it."""
        original_text = self._orig_loc_get_name(*args, **kwargs)
        return self.scramble_raw_string(str(original_text))

    def normalize_char(self, char: str) -> str:
        if not char:
            return ""
        normalized = unicodedata.normalize('NFD', str(char))
        return "".join([c for c in normalized if not unicodedata.combining(c)]).upper()

    def scramble_raw_string(self, text: str) -> str:
        """Scrambles a raw string for Kivy GUI elements like the Hint Tab."""
        if not text:
            return text
        result = ""
        for char in text:
            if char.isspace() or self.normalize_char(char) in self.unlocked_chars:
                result += char
            else:
                # Removed string.punctuation to prevent Kivy markup crashes (no accidental '[' or ']')
                result += random.choice(string.ascii_letters + string.digits)
        return result

    def scramble_text_to_nodes(self, text: str, original_color: str = None) -> list:
        """Scrambles text nodes for the console, preserving Archipelago's native colors."""
        nodes = []
        for char in text:
            if char.isspace() or self.normalize_char(char) in self.unlocked_chars:
                # Use the extracted item/location color, defaulting to white for standard text
                nodes.append({"type": "color", "color": original_color or "white", "text": char})
            else:
                scrambled_char = random.choice(string.ascii_letters + string.digits)
                # Unrelated color for scrambled text
                nodes.append({"type": "color", "color": "salmon", "text": scrambled_char})
        return nodes
    
    def on_package(self, cmd: str, args: dict[str, Any]) -> None:
        #logger.info(f"[Babel DEBUG] Received package cmd: {cmd}")
        
        # Allow the original client to process the package first
        super().on_package(cmd, args)
        
        # Intercept the LocationInfo package coming from the PRIMARY server
        if cmd == "LocationInfo":
            logger.info("[Babel] Intercepted LocationInfo from primary server!")
                
            for loc in args.get("locations", []):
                # ADDED: Output the raw NetworkItem to the console for debugging
                #logger.info(f"[Babel DEBUG] Raw NetworkItem: {loc}")
                
                # We are only receiving native packets now, so we simply parse the class object
                item_id = loc.item
                location_id = loc.location
                player_id = loc.player
                flags = loc.flags
                location_player = self.slot
                
                # 1. Save to your internal dictionary for the Kivy UI Tab
                loc_dict = {
                    "item": item_id,
                    "location": location_id,
                    "player": player_id,
                    "flags": flags
                }
                if loc_dict not in self.babel_private_hints:
                    self.babel_private_hints.append(loc_dict)
                    logger.info(f"[Babel] Data saved for Location {location_id}")

                # 2. Build standard AP nodes for the console output
                nodes = [
                    {"text": "[Babel Scout] ", "color": "green"},
                    # Render the world owner (e.g., "GaldanFFX's ")
                    {"type": "player_id", "player": location_player, "text": str(location_player)},
                    {"text": "'s "},
                    # Render the location (e.g., "Pokedex - Kadabra")
                    {"type": "location_id", "location": location_id, "text": str(location_id)},
                    {"text": " contains "},
                    # Render the item (e.g., "Aerodactyl Tile")
                    {"type": "item_id", "item": item_id, "flags": flags, "player": player_id, "text": str(item_id)},
                    {"text": " belonging to "},
                    # Render the receiver (e.g., "GaldanFFX")
                    {"type": "player_id", "player": player_id, "text": str(player_id)},
                    {"text": ".\n"}
                ]
                
                # 3. Fire it through your PrintJSON pipeline
                package = {
                    "cmd": "PrintJSON",
                    "data": nodes,
                    "type": "BabelHint"
                }
                self.on_print_json(package)
            
            # 4. Force Kivy UI update
            if hasattr(self, "ui") and self.ui and hasattr(self.ui, "update_hints"):
                self.ui.update_hints()
                
    def resolve_raw_ap_node(self, node: dict) -> dict:
        """PHASE 1: Converts a raw AP node into the correct English string, ignoring numeric fallbacks."""
        resolved = node.copy()
        node_type = resolved.get("type")
        
        # Multiworld Fix: Safely attempt to get the numeric player slot
        try:
            node_player = int(resolved.get("player", self.slot))
        except (ValueError, TypeError):
            # If the server sends a name string instead of a slot ID, fallback safely
            node_player = self.slot

        game_name = ""
        if hasattr(self, "slot_info") and node_player in self.slot_info:
            game_name = self.slot_info[node_player].game

        # 1. Force Item IDs to translate into English text
        if node_type in ("item_id", "item_name"):
            # ... [Keep the rest of your existing function below this] ...
            try:
                item_id = int(resolved.get("item", resolved.get("text", 0)))
                if hasattr(self, '_orig_item_get_name'):
                    resolved["text"] = self._orig_item_get_name(item_id, game_name)
                elif hasattr(self.item_names, 'lookup_in_game'):
                    resolved["text"] = self.item_names.lookup_in_game(item_id, game_name)
                else:
                    resolved["text"] = self.item_names.get(item_id, str(item_id))
            except ValueError:
                resolved["text"] = str(resolved.get("text", ""))
                
            # --- COLOR INJECTION BASED ON FLAGS ---
            flags = int(resolved.get("flags", 0))
            
            if flags == 0:
                resolved["color"] = "cyan"     # Nothing special / Filler
            elif flags & 0b001: 
                resolved["color"] = "plum"  # Logical advancement / Progression
            elif flags & 0b010:
                resolved["color"] = "blue"     # Useful
            elif flags & 0b100:
                resolved["color"] = "red"      # Trap
            else:
                resolved["color"] = "cyan"     # Fallback
                
        # 2. Force Location IDs to translate into English text
        elif node_type in ("location_id", "location_name"):
            try:
                loc_id = int(resolved.get("location", resolved.get("text", 0)))
                if hasattr(self, '_orig_loc_get_name'):
                    resolved["text"] = self._orig_loc_get_name(loc_id, game_name)
                elif hasattr(self.location_names, 'lookup_in_game'):
                    resolved["text"] = self.location_names.lookup_in_game(loc_id, game_name)
                else:
                    resolved["text"] = self.location_names.get(loc_id, str(loc_id))
            except ValueError:
                resolved["text"] = str(resolved.get("text", ""))
                
            # Native AP locations are typically green
            if "color" not in resolved:
                resolved["color"] = "green"
                
        # 3. Resolve Player nodes to text so they can be safely scrambled
        elif node_type in ("player_id", "player_name"):
            player_val = resolved.get("player", resolved.get("text", ""))
            
            try:
                # If it's a numeric ID, look up the name in the client's dictionary
                player_num = int(player_val)
                resolved["text"] = self.player_names.get(player_num, f"Player {player_num}")
            except (ValueError, TypeError):
                # If it's already a string (like 'DanB_DS'), just use it directly
                resolved["text"] = str(player_val)
                
            # Downgrade to standard text and color it yellow so Kivy handles it safely
            resolved["type"] = "text"
            resolved["color"] = "yellow"
        elif node_type == "player_name":
            pass # player_name nodes are already string-safe natively
        # 4. Standard text strings (like " sent " or " to ")
        else:
            resolved["text"] = str(resolved.get("text", ""))
            
        return resolved
        
    def on_print_json(self, args: dict):
        msg_type = args.get("type", "")
        
        # Never scramble our own Babel notification messages
        if msg_type in ["BabelUnlock", "ServerChat","CommandResult","Join","Part","Tutorial","TagsChanged","AdminCommandResult"]:
            super().on_print_json(args)
            return

        # =========================================================================
        # PHASE 1: Convert ALL raw input into exactly what would print to the console
        # =========================================================================
        raw_nodes = args.get("data", [])
        
        resolved_nodes = [self.resolve_raw_ap_node(node) for node in raw_nodes]

        # =========================================================================
        # PHASE 2: Run the finalized English text through the scrambling engine
        # =========================================================================
        new_data = []
        
        if msg_type == "Chat":
            # For chat, collapse all resolved nodes into one string to find the colon
            full_text = "".join([n.get("text", "") for n in resolved_nodes])
            name_color = next((n.get("color") for n in resolved_nodes if n.get("color")), None)
            
            name_part, sep, msg_part = full_text.partition(": ")
            if msg_part:
                sender_node = {"text": name_part + sep}
                if name_color:
                    sender_node["color"] = name_color
                new_data.append(sender_node)
                new_data.extend(self.scramble_text_to_nodes(msg_part))
            else:
                new_data.extend(self.scramble_text_to_nodes(full_text))
                
        else:
            # For Hints, ItemSends, etc., scramble the resolved text node-by-node
            for node in resolved_nodes:
                # Because player_id nodes were converted to "text" in Phase 1, 
                # they will now be fully scrambled here alongside items and locations!
                new_data.extend(self.scramble_text_to_nodes(node.get("text", ""), node.get("color")))
                
        args["data"] = new_data
        super().on_print_json(args)
    
    async def scout_locations_silently(self, location_ids: list[int], target_slot: int):
        """Sends a private scout package over the primary connection."""
        package = {
            "cmd": "LocationScouts",
            "locations": location_ids,
            "create_as_hint": 0,
            "player": target_slot
        }
        
        logger.info(f"[Babel] Firing silent scout via primary connection: {location_ids}")
        # Use the primary connection instead of the background websocket
        await self.send_msgs([package])

def launch_tower_of_babel_client(*args):
    async def main(parsed_args):
        ctx = BabelContext(parsed_args.connect, parsed_args.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        
        await ctx.exit_event.wait()
        await ctx.shutdown()

    import colorama
    parser = get_base_parser(description="Tower of Babel Multi-Client")
    parsed_args, _ = parser.parse_known_args(args)
    colorama.init()
    
    Utils.init_logging("Tower of Babel Multi-Client", exception_logger="Client")
    
    asyncio.run(main(parsed_args))
    colorama.deinit()