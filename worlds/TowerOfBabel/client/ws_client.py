import asyncio
import json
import websockets
import uuid
import traceback

SERVER_HOST = "archipelago.gg"
SERVER_PORT = 55291   # your room port

class APWSClient:
    def __init__(self, name="TowerOfBabelClient", password=None):
        self.name = name
        self.password = password
        self.uuid = str(uuid.uuid4())
        self.ws = None

    async def connect(self):
        uri = f"ws://{SERVER_HOST}:{SERVER_PORT}"

        print(f"[AP] Connecting to {uri} with subprotocol 'archipelago'...")

        # THIS IS THE CRITICAL FIX
        self.ws = await websockets.connect(
            uri,
            subprotocols=["archipelago"]
        )

        print("[AP] Connected. Sending Connect packet...")

        await self.send({
            "cmd": "Connect",
            "password": self.password,
            "name": self.name,
            "uuid": self.uuid,
            "version": [0, 4, 0],
            "tags": ["AP", "TextOnly"],
            "items_handling": 0,
            "slot_data_request": True,
            "data_package_request": True,
            "game": "Generic"
        })

        await self.listen_loop()

    async def send(self, packet: dict):
        await self.ws.send(json.dumps(packet))

    async def listen_loop(self):
        try:
            async for raw in self.ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    print("[DEBUG] Invalid JSON:", raw)
                    continue

                await self.handle_message(msg)

        except websockets.ConnectionClosed:
            print("[AP] Server closed connection.")
        except Exception:
            traceback.print_exc()

    async def handle_message(self, msg: dict):
        cmd = msg.get("cmd")

        if cmd == "RoomInfo":
            print("[AP] RoomInfo received.")
            print(json.dumps(msg, indent=2))

            await self.send({
                "cmd": "ConnectUpdate",
                "items_handling": 0,
                "death_link": False
            })

        elif cmd == "SlotData":
            print("[AP] SlotData received.")
            print(json.dumps(msg, indent=2))

        elif cmd == "DataPackage":
            print("[AP] DataPackage received.")

        elif cmd == "Connected":
            print("[AP] FULLY CONNECTED TO ARCHIPELAGO!")
            print(json.dumps(msg, indent=2))

        elif cmd == "Print":
            print(f"[AP] {msg.get('text', '')}")

        elif cmd == "ReceivedItems":
            print("[AP] Received Items:")
            print(json.dumps(msg, indent=2))

        else:
            print(f"[AP] Unknown packet: {msg}")


async def repl(client: APWSClient):
    print("\nType AP commands (sent as Say packets). Example: !help, !status\n")
    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, input)
            line = line.strip()
            if not line:
                continue

            await client.send({
                "cmd": "Say",
                "text": line
            })

        except KeyboardInterrupt:
            print("Exiting client.")
            break
        except Exception:
            traceback.print_exc()


async def main():
    client = APWSClient()
    await asyncio.gather(
        client.connect(),
        repl(client)
    )

if __name__ == "__main__":
    asyncio.run(main())
