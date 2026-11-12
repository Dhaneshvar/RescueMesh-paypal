from fastapi import WebSocket


class LiveEvents:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def publish(self, event: str, payload: dict):
        dead = []
        for socket in self.connections:
            try:
                await socket.send_json({"event": event, "payload": payload})
            except Exception:
                dead.append(socket)
        for socket in dead:
            self.disconnect(socket)


events = LiveEvents()
