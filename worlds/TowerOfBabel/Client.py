import asyncio
import random
import string
import unicodedata
import logging
import websockets
import json
import uuid

import ModuleUpdate
ModuleUpdate.update()

import Utils
from CommonClient import CommonContext, server_loop, gui_enabled, ClientCommandProcessor, get_base_parser
from .Game import game_name

# Import your local manual items dictionary and invert it so we can look up Names by ID
from .Items import item_name_to_id
babel_item_id_to_name = {v: k for k, v in item_name_to_id.items()}

logger = logging.getLogger("Client")

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

class BabelContext(CommonContext):
    command_processor = BabelCommandProcessor
    game = ""  
    items_handling = 0b111 
    tags = {"AP","TextOnly"}

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.unlocked_chars = set()
        
        self.babel_slot = None
        self.babel_password = ""
        self.babel_task = None
        self.babel_ws = None

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    async def connect_babel(self):
        """Secondary background task to connect exclusively to the Tower of Babel slot."""
        url = self.server_address
        if url and not (url.startswith("ws://") or url.startswith("wss://")):
            url = f"ws://{url}"

        while True:
            try:
                async with websockets.connect(url) as ws:
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
                            
                            elif cmd == "ReceivedItems":
                                for item in packet.get("items", []):
                                    item_id = item.get("item")
                                    # BYPASS the server map and use our local Python dictionary!
                                    item_name = babel_item_id_to_name.get(item_id)
                                    
                                    if item_name:
                                        char_part = item_name.split(" ", 1)[-1] if " " in item_name else item_name
                                        self.unlocked_chars.add(self.normalize_char(char_part))
                            
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

    def scramble_text_to_nodes(self, text: str) -> list:
        nodes = []
        for char in text:
            if char.isspace() or self.normalize_char(char) in self.unlocked_chars:
                nodes.append({"type": "color", "color": "magenta", "text": char})
            else:
                scrambled_char = random.choice(string.ascii_letters + string.digits + string.punctuation)
                nodes.append({"type": "color", "color": "cyan", "text": scrambled_char})
        return nodes

    def on_print_json(self, args: dict):
        if args.get("type") == "Chat":
            parts = args.get("data", [])
            full_text = "".join([str(p.get("text", "")) for p in parts])
            name_part, sep, msg_part = full_text.partition(": ")
            
            new_data = []
            if msg_part:
                new_data.append({"text": name_part + sep})
                new_data.extend(self.scramble_text_to_nodes(msg_part))
            else:
                new_data.extend(self.scramble_text_to_nodes(full_text))
                
            args["data"] = new_data
            
        super().on_print_json(args)

def launch(*args):
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