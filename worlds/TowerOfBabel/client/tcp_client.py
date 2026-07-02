import asyncio
import json
import struct
import sys
import traceback
import uuid

SERVER_HOST = "archipelago.gg"
SERVER_PORT = 55291   # your room port

def encode_packet(packet: dict) -> bytes:
    raw = json.dumps(packet).encode("utf-8")
    return struct.pack(">I", len(raw)) + raw

async def read_packet(reader: asyncio.StreamReader) -> dict:
    length_bytes = await reader.readexactly(4)
    (length,) = struct.unpack(">I", length_bytes)
    payload = await reader.readexactly(length)
    return json.loads(payload.decode("utf-8"))

class APClient:
    def __init__(self, name="GaldanJohto", password=None):
        self.name = name
        self.password = password
        self.reader = None
        self.writer = None
        self.uuid = str(uuid.uuid4())

    async def connect(self):
        print(f"[AP] Connecting to {SERVER_HOST}:{SERVER_PORT}...")
        self.reader, self.writer = await asyncio.open_connection(
            SERVER_HOST, SERVER_PORT
        )
        print("[AP] Connected. Sending Connect packet...")

        await self.send({
            "cmd": "Connect",
            "password": self.password,
            "name": self.name,
            "uuid": self.uuid,
            "version": [0, 6, 7],
            "tags": ["AP", "TextOnly"],
            "items_handling": 0,
            "slot": 1,  # REQUIRED
            "game": "Pokemon Crystal",  # REQUIRED
            "slot_data_request": True,
            "data_package_request": True
        })

        await self.listen_loop()

    async def send(self, packet: dict):
        self.writer.write(encode_packet(packet))
        await self.writer.drain()

    async def listen_loop(self):
        try:
            while True:
                try:
                    msg = await read_packet(self.reader)
                except asyncio.IncompleteReadError:
                    print("[AP] Server closed connection.")
                    break
                except Exception:
                    traceback.print_exc()
                    break

                await self.handle_message(msg)

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


async def repl(client: APClient):
    print("\nType AP commands (sent as Say packets). Example: !help, !status\n")
    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
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
    client = APClient()
    await asyncio.gather(
        client.connect(),
        repl(client)
    )

if __name__ == "__main__":
    asyncio.run(main())
