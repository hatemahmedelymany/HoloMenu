import asyncio
import json
import websockets
import sys

async def run_client():
    url = "ws://127.0.0.1:8766"
    print(f"Connecting to gesture engine at {url}...")
    try:
        async with websockets.connect(url) as ws:
            # Helper to wait for a specific event type and value
            async def wait_for_mode(expected_mode):
                print(f"Waiting for engine_mode -> {expected_mode}...")
                while True:
                    msg = await ws.recv()
                    print(f"Received: {msg}")
                    event = json.loads(msg)
                    if event.get("event") == "engine_mode" and event.get("mode") == expected_mode:
                        return event

            # 1. Receive initial mode
            await wait_for_mode("idle")

            # 2. Send start_order
            print("Sending cmd: start_order")
            await ws.send(json.dumps({"cmd": "start_order"}))

            # 3. Wait/receive mode transition
            await wait_for_mode("active")

            # Sleep briefly
            await asyncio.sleep(2)

            # 4. Send end_session
            print("Sending cmd: end_session")
            await ws.send(json.dumps({"cmd": "end_session"}))

            # 5. Receive mode transition
            await wait_for_mode("idle")

            print("SUCCESS: WebSocket gesture engine baseline simulation completed.")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_client())
