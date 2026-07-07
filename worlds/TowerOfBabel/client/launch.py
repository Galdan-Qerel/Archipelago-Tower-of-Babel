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

import ModuleUpdate
ModuleUpdate.update()

import Utils
from CommonClient import CommonContext, server_loop, gui_enabled, ClientCommandProcessor, get_base_parser
from ..Game import game_name

# Import your local manual items dictionary and invert it so we can look up Names by ID
from ..items import ITEM_NAME_TO_ID
babel_item_id_to_name = {v: k for k, v in ITEM_NAME_TO_ID.items()}

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
    def _cmd_babel(self, slot_name: str = "", password: str = ""):
        """Configure the Babel slot for unlocked data. Usage: /babel "<slot_name>" [password]"""
        if not slot_name:
            self.output("Please provide a slot name. Usage: /babel \"<slot_name>\" [password]")
            return
            
        if not self.ctx.server_address:
            self.output("Please connect the main client first using /connect")
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
            locs = locations[full_query]
            if len(locs) > 10:
                self.output(f"Found {len(locs)} locations for '{full_query}'. Only showing the first 10:")
                locs = locs[:10]
            for loc in locs:
                self._output_babelhint_result(full_query, loc)
            return
            
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
        
        packet = {
            "cmd": "PrintJSON",
            "data": nodes,
            "type": "BabelHint"
        }
        self.ctx.on_print_json(packet)

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
        if hasattr(self.item_names, 'get_name'):
            self._orig_item_get_name = self.item_names.get_name
            self.item_names.get_name = self._scrambled_item_name
            
        if hasattr(self.location_names, 'get_name'):
            self._orig_loc_get_name = self.location_names.get_name
            self.location_names.get_name = self._scrambled_loc_name

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def _output_babel_unlock(self, char_norm: str):
        nodes = [
            {"text": "[Babel] ", "color": "yellow"},
            {"text": "Data Translated! You can now read the character: "},
            {"text": char_norm, "color": "magenta"}
        ]
        packet = {
            "cmd": "PrintJSON",
            "data": nodes,
            "type": "BabelUnlock"
        }
        self.on_print_json(packet)

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
        if not self.babel_ws:
            return
            
        new_checks = self._evaluate_babel_logic()
        
        if new_checks:
            packet = [{"cmd": "LocationChecks", "locations": new_checks}]
            await self.babel_ws.send(json.dumps(packet))
            self.babel_checked_locations.update(new_checks)
            logger.info(f"[Babel] Auto-checked {len(new_checks)} location(s)!")

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
                    connect_packet = [{
                        "cmd": "Connect",
                        "password": self.babel_password,
                        "name": self.babel_slot,
                        "version": {"major": 0, "minor": 6, "build": 0, "class": "Version"},
                        "tags": ["TextOnly"],
                        "items_handling": 7,
                        "game": game_name,
                        "uuid": str(uuid.uuid4())
                    }]
                    await ws.send(json.dumps(connect_packet))
                    
                    async for message in ws:
                        for packet in json.loads(message):
                            cmd = packet.get("cmd")
                            
                            if cmd == "Connected":
                                logger.info(f"[Babel] Successfully connected to background Babel slot: {self.babel_slot}")
                                self.babel_checked_locations = set(packet.get("checked_locations", []))
                                await self.check_babel_locations()
                                
                            elif cmd == "RoomUpdate":
                                if "checked_locations" in packet:
                                    self.babel_checked_locations.update(packet["checked_locations"])
                            
                            elif cmd == "ReceivedItems":
                                for item in packet.get("items", []):
                                    item_id = item.get("item")
                                    item_name = babel_item_id_to_name.get(item_id)
                                    
                                    if item_name:
                                        char_part = item_name.split(" ", 1)[-1] if " " in item_name else item_name
                                        char_norm = self.normalize_char(char_part)
                                        
                                        if char_norm not in self.unlocked_chars:
                                            self.unlocked_chars.add(char_norm)
                                            
                                            if self.babel_initialized:
                                                self._output_babel_unlock(char_norm)
                                                
                                self.babel_initialized = True
                                await self.check_babel_locations()
                                
                                # Force the Kivy Hint Tab to dynamically redraw with the newly readable text!
                                if hasattr(self, "ui") and self.ui and hasattr(self.ui, "update_hints"):
                                    self.ui.update_hints()
                            
                            elif cmd == "ConnectionRefused":
                                logger.error(f"[Babel] Connection refused: {', '.join(packet.get('errors', []))}")
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

    def normalize_char(self, char: str) -> str:
        normalized = unicodedata.normalize('NFD', char)
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
                result += random.choice(string.ascii_letters + string.digits + string.punctuation)
        return result

    def _scrambled_item_name(self, code: int) -> str:
        return self.scramble_raw_string(self._orig_item_get_name(code))

    def _scrambled_loc_name(self, code: int) -> str:
        return self.scramble_raw_string(self._orig_loc_get_name(code))

    def scramble_text_to_nodes(self, text: str, original_color: str = None) -> list:
        """Scrambles text nodes for the console, preserving Archipelago's native colors for readable text."""
        nodes = []
        for char in text:
            if char.isspace() or self.normalize_char(char) in self.unlocked_chars:
                # Retains original item/player coloring for letters you have unlocked
                nodes.append({"type": "color", "color": original_color or "magenta", "text": char})
            else:
                scrambled_char = random.choice(string.ascii_letters + string.digits + string.punctuation)
                nodes.append({"type": "color", "color": "cyan", "text": scrambled_char})
        return nodes

    def on_print_json(self, args: dict):
        msg_type = args.get("type", "")
        
        # Intercept Chat, Native Server Hints, and general Item Sends for the console log
        if msg_type in ("Chat", "Hint", "ItemSend", "BabelHint"):
            new_data = []
            for node in args.get("data", []):
                original_text = str(node.get("text", ""))
                original_color = node.get("color")
                
                # Protect the sender's name block in Chat messages so it is visually clear who is speaking
                if msg_type == "Chat" and original_text.endswith(": "):
                    new_data.append(node)
                    continue
                    
                new_data.extend(self.scramble_text_to_nodes(original_text, original_color))
                
            args["data"] = new_data
            
        super().on_print_json(args)

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