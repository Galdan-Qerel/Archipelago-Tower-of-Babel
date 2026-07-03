import asyncio
import random
import string
import unicodedata

import ModuleUpdate
ModuleUpdate.update()

from CommonClient import CommonContext, server_loop, gui_enabled, ClientCommandProcessor, get_base_parser
from .Game import game_name  # <-- Import your exact internal game name

class BabelCommandProcessor(ClientCommandProcessor):
    def _cmd_unlocked(self):
        """View the symbols you have unlocked so far. (Usage: /unlocked)"""
        if self.ctx.unlocked_chars:
            self.output(f"Unlocked symbols: {', '.join(sorted(self.ctx.unlocked_chars))}")
        else:
            self.output("No symbols unlocked yet.")

class BabelContext(CommonContext):
    command_processor = BabelCommandProcessor
    game = game_name  # <-- Use the imported variable instead of a hardcoded string
    items_handling = 0b111 # Receive all items from the server
    tags = {"AP"}
    

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.unlocked_chars = set()

    def normalize_char(self, char: str) -> str:
        normalized = unicodedata.normalize('NFD', char)
        return "".join([c for c in normalized if not unicodedata.combining(c)]).upper()

    def scramble_text(self, text: str) -> str:
        result = []
        for char in text:
            if char.isspace() or self.normalize_char(char) in self.unlocked_chars:
                # Unlocked: Magenta Kivy Markup
                result.append(f"[color=#FF00FF]{char}[/color]")
            else:
                # Scrambled: Teal Kivy Markup
                scrambled_char = random.choice(string.ascii_letters + string.digits + string.punctuation)
                result.append(f"[color=#00FFFF]{scrambled_char}[/color]")
        return "".join(result)

    def on_print_json(self, args: dict):
        """Intercepts incoming server messages to apply the Babel scrambling."""
        if args.get("type") == "Chat":
            parts = args.get("data", [])
            full_text = "".join([str(p.get("text", "")) for p in parts])
            name, _, msg = full_text.partition(": ")
            
            if msg:
                self.output(f"[Chat] {name}: {self.scramble_text(msg)}")
            else:
                self.output(f"[Chat] {self.scramble_text(name)}")
        else:
            # Let Archipelago handle system messages normally
            super().on_print_json(args)

    def on_package(self, cmd: str, args: dict):
        """Fires whenever the client receives a network package."""
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
    """The APQuest-style native launcher function."""
    async def main(parsed_args):
        ctx = BabelContext(parsed_args.connect, parsed_args.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        
        # This triggers Archipelago's native Kivy Text GUI
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        
        await ctx.exit_event.wait()
        await ctx.shutdown()

    import colorama
    parser = get_base_parser(description="Tower of Babel Client")
    parsed_args, _ = parser.parse_known_args(args)
    colorama.init()
    asyncio.run(main(parsed_args))
    colorama.deinit()