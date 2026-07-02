import asyncio, json, websockets, uuid, random, string, unicodedata, os
# ANSI Escape Codes
TEAL = "\033[36m"
MAGENTA = "\033[35m"
RESET = "\033[0m"

class APClient:
    def __init__(self, name, game, url, password="", silent=False, babel_client=None):
        self.name = name
        self.game = game
        self.url = url
        self.password = password
        self.silent = silent
        self.babel_client = babel_client
        self.inventory = []
        self.item_map = self.load_items_json()
        self.websocket = None

    def load_items_json(self):
        """Reconstructs ID mapping using the game's starting_index."""
        # 1. Load starting_index from game.json
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        try:
            with open(os.path.join(data_dir, 'game.json'), 'r') as f:
                game_data = json.load(f)
                start_id = int(game_data.get("starting_index", 1))
        except:
            start_id = 1

        # 2. Map items from items.json
        items_path = os.path.join(data_dir, 'items.json')
        try:
            with open(items_path, 'r') as f:
                content = json.load(f)
                items_list = content.get("data", [])
                
                mapping = {}
                current_id = start_id
                for item in items_list:
                    # Map the calculated ID to the name
                    mapping[current_id] = item["name"]
                    current_id += 1
                return mapping
        except Exception as e:
            print(f"[{self.name}] Error loading items: {e}")
            return {}
    def get_item_name(self, item_id):
        return self.item_map.get(item_id, f"Unknown {item_id}")

    def normalize_char(self, char):
        normalized = unicodedata.normalize('NFD', char)
        return "".join([c for c in normalized if not unicodedata.combining(c)]).upper()

    def scramble_text(self, text):
        if not self.babel_client:
            return TEAL + "".join(random.choice(string.ascii_letters + string.digits + string.punctuation) 
                                 if not char.isspace() else char for char in text) + RESET

        unlocked_chars = set()
        for item in self.babel_client.inventory:
            name = item.get("item", "")
            char_part = name.split(" ", 1)[-1] if " " in name else name
            unlocked_chars.add(self.normalize_char(char_part))

        result = []
        for char in text:
            if char.isspace() or self.normalize_char(char) in unlocked_chars:
                # Unlocked: Magenta
                result.append(f"{MAGENTA}{char}{RESET}")
            else:
                # Scrambled: Teal
                result.append(f"{TEAL}{random.choice(string.ascii_letters + string.digits + string.punctuation)}{RESET}")
        
        return "".join(result)

    def handle_local_command(self, cmd_text):
        if cmd_text.startswith("/unlocked"):
            symbols = {name.split(" ", 1)[-1] if " " in name else name for item in self.babel_client.inventory for name in [item["item"]]}
            print(f"[System] Unlocked symbols: {', '.join(sorted(symbols))}")

    async def listen_for_input(self):
        loop = asyncio.get_running_loop()
        while True:
            user_input = await loop.run_in_executor(None, input, "> ")
            if user_input.startswith("/"):
                self.handle_local_command(user_input)
            elif user_input.strip() and self.websocket:
                await self.websocket.send(json.dumps([{"cmd": "Say", "text": user_input}]))

    def handle_print(self, packet):
        msg_type = packet.get("type", "Unknown")
        parts = packet.get("data", [])
        if msg_type == "Chat":
            full = "".join([str(p.get("text", "")) for p in parts])
            name, _, msg = full.partition(": ")
            print(f"[Chat] {name}: {self.scramble_text(msg) if msg else self.scramble_text(name)}")
        else:
            print("".join([str(p.get("text", "")) for p in parts]))

    async def run(self):
        while True:
            try:
                print(f"[{self.name}] Connecting to {self.url}...")
                async with websockets.connect(self.url) as ws:
                    self.websocket = ws
                    print(f"[{self.name}] Connected!")
                    await ws.send(json.dumps([{"cmd": "Connect", "password": self.password, "name": self.name, 
                        "version": {"major": 0, "minor": 6, "build": 7, "class": "Version"}, 
                        "tags": ["TextOnly"], "items_handling": 7, "game": self.game, "uuid": str(uuid.uuid4())}]))
                    
                    async for message in ws:
                        for packet in json.loads(message):
                            cmd = packet.get("cmd")
                            # No changes needed here, as long as item_map uses the IDs from Items.py
                            if cmd == "ReceivedItems":
                                for item in packet.get("items", []):
                                    raw_id = item.get("item")
                                    # Now raw_id (e.g., 5906513) will exist in self.item_map
                                    if raw_id in self.item_map:
                                        name = self.item_map.get(raw_id)
                                        self.inventory.append({"item": name})
                                        print(f"[{self.name}] Unlocked: {name}")
                                    else:
                                        # Silently ignore foreign items
                                        pass
                            elif cmd == "PrintJSON" and not self.silent:
                                self.handle_print(packet)
            except Exception as e:
                print(f"[{self.name}] Connection error: {e}. Retrying...")
                await asyncio.sleep(5)

async def main():
    await asyncio.sleep(1)
    URL = "wss://archipelago.gg:55291"
    babel = APClient("Manual_TowerofBa", "Manual_TowerofBabel_Galdan", URL, silent=True)
    main_client = APClient("GaldanFF10", "Final Fantasy X", URL, babel_client=babel)
    
    await asyncio.gather(babel.run(), main_client.run(), main_client.listen_for_input())

if __name__ == "__main__":
    asyncio.run(main())