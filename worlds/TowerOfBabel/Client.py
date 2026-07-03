import asyncio
import random
import string
import unicodedata

import ModuleUpdate
ModuleUpdate.update()

import Utils
from CommonClient import CommonContext, server_loop, gui_enabled, ClientCommandProcessor, get_base_parser
from .Game import game_name

class BabelCommandProcessor(ClientCommandProcessor):
    def _cmd_unlocked(self):
        """View the symbols you have unlocked so far. (Usage: /unlocked)"""
        if self.ctx.unlocked_chars:
            self.output(f"Unlocked symbols: {', '.join(sorted(self.ctx.unlocked_chars))}")
        else:
            self.output("No symbols unlocked yet.")

class BabelContext(CommonContext):
    command_processor = BabelCommandProcessor
    game = game_name  
    items_handling = 0b111 
    tags = {"AP"}

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.unlocked_chars = set()

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def make_gui(self):
        ui = super().make_gui()
        class BabelManager(ui):
            base_title = "Tower of Babel Client"
        return BabelManager

    def normalize_char(self, char: str) -> str:
        normalized = unicodedata.normalize('NFD', char)
        return "".join([c for c in normalized if not unicodedata.combining(c)]).upper()

    def scramble_text_to_nodes(self, text: str) -> list:
        """Converts a string into a list of native Archipelago PrintJSON nodes."""
        nodes = []
        for char in text:
            if char.isspace() or self.normalize_char(char) in self.unlocked_chars:
                # Unlocked: Magenta (Explicitly tell AP it is a color node)
                nodes.append({"type": "color", "color": "magenta", "text": char})
            else:
                # Scrambled: Cyan
                scrambled_char = random.choice(string.ascii_letters + string.digits + string.punctuation)
                nodes.append({"type": "color", "color": "cyan", "text": scrambled_char})
        return nodes

    def on_print_json(self, args: dict):
        """Intercepts the raw JSON packet and injects color nodes before rendering."""
        if args.get("type") == "Chat":
            parts = args.get("data", [])
            full_text = "".join([str(p.get("text", "")) for p in parts])
            
            # Separate the "Player: " prefix from the actual message
            name_part, sep, msg_part = full_text.partition(": ")
            
            new_data = []
            if msg_part:
                # Keep the Player Name in the default white color
                new_data.append({"text": name_part + sep})
                # Add the scrambled, colorized nodes for the message
                new_data.extend(self.scramble_text_to_nodes(msg_part))
            else:
                # If there's no colon (system chat), scramble everything
                new_data.extend(self.scramble_text_to_nodes(full_text))
                
            # Overwrite the original packet's data with our vibrant new nodes!
            args["data"] = new_data
            
        # Hand the mutated packet over to Archipelago to render cleanly
        super().on_print_json(args)

    def on_package(self, cmd: str, args: dict):
        super().on_package(cmd, args)
        if cmd in {"Connected", "ReceivedItems"}:
            self.update_unlocked_chars()

    def update_unlocked_chars(self):
        self.unlocked_chars.clear()
        for network_item in self.items_received:
            item_name = self.item_names.lookup_in_game(network_item.item)
            if item_name:
                char_part = item_name.split(" ", 1)[-1] if " " in item_name else item_name
                self.unlocked_chars.add(self.normalize_char(char_part))


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
    parser = get_base_parser(description="Tower of Babel Client")
    parsed_args, _ = parser.parse_known_args(args)
    colorama.init()
    
    Utils.init_logging("Tower of Babel Client", exception_logger="Client")
    
    asyncio.run(main(parsed_args))
    colorama.deinit()