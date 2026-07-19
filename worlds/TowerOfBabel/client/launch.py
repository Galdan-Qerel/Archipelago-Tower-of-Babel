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
import re
import difflib
import ssl  # Added SSL module to handle certificate bypassing
from typing import Any

import ModuleUpdate
ModuleUpdate.update()

import Utils
from CommonClient import CommonContext, server_loop, gui_enabled, ClientCommandProcessor, get_base_parser
from ..Game import game_name

# Import your local manual items dictionary and invert it so we can look up Names by ID
from ..items import ITEM_NAME_TO_ID
babel_item_id_to_name = {v: k for k, v in ITEM_NAME_TO_ID.items()}
from ..locations import LOCATION_NAME_TO_ID


logger = logging.getLogger("Client")

# -----------------------------
# SPOILER LOG PARSER LOGIC
# -----------------------------
def parse_item_links(line: str) -> list:
    raw = line.split("Item Links:", 1)[1].strip()
    if not raw:
        return []
    raw = "[" + raw + "]"
    try:
        data = ast.literal_eval(raw)
    except Exception:
        return []

    names = []
    for entry in data:
        if isinstance(entry, dict) and "name" in entry:
            names.append(str(entry["name"]))
    return names

def load_spoiler_log(spoiler_file: str):
    locations = {}
    worlds = set()
    itemlinks = set()
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

            if line.startswith("Item Links:"):
                extracted = parse_item_links(line)
                for name in extracted:
                    itemlinks.add(name)
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

    return locations, sorted(worlds), sorted(itemlinks)

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
        self.ctx.babel_task = asyncio.create_task(self.ctx.connect_babel())
        self.output(f"Connecting background Babel slot to '{slot_name}'...")
        
    def _cmd_unlocked(self):
        """View the symbols you have unlocked so far. (Usage: /unlocked)"""
        if not self.ctx.babel_slot:
            self.output("Babel slot not configured. Please use '/babel \"<slot_name>\" [password]' first.")
            return
            
        if self.ctx.unlocked_chars:
            self.output(f"Unlocked symbols: {', '.join(sorted(self.ctx.unlocked_chars))}")
        else:
            self.output("No symbols unlocked yet.")

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
            locations, valid_worlds, valid_itemlinks = load_spoiler_log(self.ctx.spoiler_log_path)
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
                    
                    # 2. Resolve the Sender's Player ID
                    if hasattr(self.ctx, "player_names"):
                        for p_id, p_name in self.ctx.player_names.items():
                            if p_name == sender_name:
                                sender_id = p_id
                                break
                    # Fallback for different AP versions
                    if not sender_id and hasattr(self.ctx, "slot_info"):
                        for s_id, s_data in self.ctx.slot_info.items():
                            if getattr(s_data, "name", "") == sender_name:
                                sender_id = s_id
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
                import asyncio
                for loc_str, loc_id, target_slot in unfound_locs:
                    if loc_id and target_slot == self.ctx.slot:
                        # LOCAL: Fire normal silent scout using our own connection
                        asyncio.create_task(self.ctx.scout_locations_silently([loc_id], target_slot))
                    elif loc_id and target_slot:
                        # REMOTE: Fire the ghost client to sneak in, get the flags, and feed our UI!
                        asyncio.create_task(self.ghost_scout_location(loc_id, target_slot))
                    else:
                        # FALLBACK: Only print raw text if the ID literally could not be found
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
            

        # 3. Fire the scout request with the exact packet structure requested
        packet = {
            "cmd": "LocationScouts",
            "locations": [location_id],
            "create_as_hint": 0, # Stays off the web tracker
        }
        
        # 4. Wrap the async send_msgs call in a task so it fires from the synchronous command processor
        import asyncio
        asyncio.create_task(self.ctx.send_msgs([packet]))
        
        self.output(f"[Babel] Scouting '{location_name}' (Targeting slot {target_slot})...")
    
    async def ghost_scout_location(self, location_id: int, target_slot: int):
        """Spawns a temporary silent websocket to scout a remote location, then injects the colored node."""
        import websockets
        import json
        import uuid
        import ssl
        import asyncio

        # Resolve the exact name of the slot we need to impersonate
        target_name = self.ctx.player_names.get(target_slot, f"Player {target_slot}")
        
        url = self.ctx.server_address
        if url and not (url.startswith("ws://") or url.startswith("wss://")):
            url = f"ws://{url}"

        ssl_context = None
        if url.startswith("wss://"):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        try:
            async with websockets.connect(url, ssl=ssl_context) as ws:
                # 1. Authenticate silently as the TARGET player using the Tracker tag
                connect_package = [{
                    "cmd": "Connect",
                    "password": self.ctx.password if self.ctx.password else "", 
                    "name": target_name,
                    "version": {"major": 0, "minor": 6, "build": 7, "class": "Version"},
                    "tags": ["Tracker"],  # Prevents join/leave spam in the main chat
                    "items_handling": 0,
                    "game": self.ctx.slot_info[target_slot].game,
                    "uuid": str(uuid.uuid4())
                }]
                await ws.send(json.dumps(connect_package))

                # 2. Wait for connection, fire scout, catch response, and disconnect
                async for message in ws:
                    for package in json.loads(message):
                        cmd = package.get("cmd")
                        
                        if cmd == "Connected":
                            # We are in! Ask for the specific location flag silently.
                            scout_pkg = [{
                                "cmd": "LocationScouts",
                                "locations": [location_id],
                                "create_as_hint": 0
                            }]
                            await ws.send(json.dumps(scout_pkg))
                            
                        elif cmd == "LocationInfo":
                            # INJECT: Add the target slot so the UI knows whose world this is!
                            for loc_dict in package.get("locations", []):
                                loc_dict["location_player"] = target_slot

                            # We got the colored network item! Pipe it directly to the UI.
                            if hasattr(self, "on_package"):
                                self.on_package("LocationInfo", package)
                            else:
                                self.ctx.on_package("LocationInfo", package)
                                
                            return
                            
                        elif cmd == "ConnectionRefused":
                            self.output(f"[Babel Error] Ghost scout failed. Slot '{target_name}' rejected the connection.")
                            return
                            
        except Exception as e:
            self.output(f"[Babel Error] Ghost scout crashed: {e}")
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
        
        self.babel_checked_locations = set() 
        self.babel_slot = None
        self.babel_password = ""
        self.babel_task = None
        self.babel_ws = None
        self.spoiler_log_path = None  
        self.babel_initialized = False

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

    def _evaluate_babel_logic(self):
        new_checks = []
        for loc_name, loc_id in LOCATION_NAME_TO_ID.items():
            if loc_id in self.babel_checked_locations:
                continue

            if loc_name.startswith("Found "):
                char_req = self.normalize_char(loc_name[6:])
                if char_req in self.unlocked_chars:
                    new_checks.append(loc_id)
                    
            elif loc_name == "Full Alphabet":
                if all(c in self.unlocked_chars for c in string.ascii_uppercase):
                    new_checks.append(loc_id)
                    
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
                        for package in json.loads(message):
                            cmd = package.get("cmd")
                            
                            if cmd == "Connected":
                                logger.info(f"[Babel] Successfully connected to background Babel slot: {self.babel_slot}")
                                self.babel_checked_locations = set(package.get("checked_locations", []))
                                await self.check_babel_locations()
                                
                            elif cmd == "RoomUpdate":
                                if "checked_locations" in package:
                                    self.babel_checked_locations.update(package["checked_locations"])
                            
                            elif cmd == "ReceivedItems":
                                for item in package.get("items", []):
                                    # Raw background websocket packages are dicts, not NetworkItems!
                                    item_id = item.get("item", 0)
                                    
                                    # EXCLUSIVELY look up items belonging to Tower of Babel
                                    item_name = babel_item_id_to_name.get(item_id)
                                    
                                    if item_name:
                                        char_part = item_name.split(" ", 1)[-1].strip() if " " in item_name else item_name.strip()
                                        char_norm = self.normalize_char(char_part)
                                        
                                        if char_norm and char_norm not in self.unlocked_chars:
                                            self.unlocked_chars.add(char_norm)
                                            
                                            if self.babel_initialized:
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

    def make_gui(self):
        ui = super().make_gui()
        class BabelManager(ui):
            base_title = "Tower of Babel Multi-Client"
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
        logger.info(f"[Babel DEBUG] Received package cmd: {cmd}")
        
        # Allow the original client to process the package first
        super().on_package(cmd, args)
        
        # Intercept the LocationInfo package coming from the PRIMARY server
        # Intercept the LocationInfo package coming from the PRIMARY server
        if cmd == "LocationInfo":
            logger.info("[Babel] Intercepted LocationInfo from primary server!")
            
            if not hasattr(self, "babel_private_hints"):
                self.babel_private_hints = []
                
            for loc in args.get("locations", []):
                # ADDED: Output the raw NetworkItem to the console for debugging
                logger.info(f"[Babel DEBUG] Raw NetworkItem: {loc}")
                
                # Multiworld Fix: Safely handle BOTH dicts (Ghost Client) and objects (Main Client)
                if isinstance(loc, dict):
                    item_id = loc.get("item", 0)
                    location_id = loc.get("location", 0)
                    player_id = loc.get("player", 0)
                    flags = loc.get("flags", 0)
                    # Get the injected owner, or fallback to our own slot
                    location_player = loc.get("location_player", self.slot)
                else:
                    item_id = loc.item
                    location_id = loc.location
                    player_id = loc.player
                    flags = loc.flags
                    # If it's a native object from the main client, it's always our own world
                    location_player = self.slot
                
                # 1. Save to your internal dictionary for the Kivy UI Tab
                loc_dict = {
                    "item": item_id,
                    "location": location_id,
                    "player": player_id,
                    "flags": flags
                }
                if loc_dict not in getattr(self, "babel_private_hints", []):
                    if not hasattr(self, "babel_private_hints"):
                        self.babel_private_hints = []
                    self.babel_private_hints.append(loc_dict)

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
        
        # LOGGING STEP 1: What did the server actually send us?
        #logger.info(f"\n[PIPELINE - 1. RAW INPUT]:\n{raw_nodes}")
        
        resolved_nodes = [self.resolve_raw_ap_node(node) for node in raw_nodes]

        # LOGGING STEP 2: Did our dictionary successfully translate the IDs to English?
        resolved_string = "".join([n.get("text", "") for n in resolved_nodes])
        #logger.info(f"[PIPELINE - 2. RESOLVED TEXT]:\n{resolved_string}")

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