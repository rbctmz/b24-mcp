# mcp_ws_test.py
import asyncio
import json
import websockets
from typing import Any


async def main():
    uri = "ws://127.0.0.1:8000/mcp"
    # Some static type-checkers (mypy/pyright) may reject a plain string
    # as the `origin` parameter type. Cast to `Any` to satisfy the checker
    # while preserving runtime behavior.
    origin: Any = "http://localhost"
    async with websockets.connect(uri, origin=origin) as ws:
        # send initialize
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        await ws.send(json.dumps(init))
        resp = await ws.recv()
        print("Received:", resp)


if __name__ == "__main__":
    asyncio.run(main())