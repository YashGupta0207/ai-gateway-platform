import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:8000/api/v1/gateway/ws/live?token=test_token&provider=azure"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to /ws/live")
            
            # Send stop command
            stop_msg = json.dumps({"text": "stop"})
            await websocket.send(stop_msg)
            print("Sent stop message")
            
            # Wait for connection to close
            try:
                msg = await websocket.recv()
                print(f"Received: {msg}")
            except websockets.exceptions.ConnectionClosed:
                print("Connection closed successfully")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
