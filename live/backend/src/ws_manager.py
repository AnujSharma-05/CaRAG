import asyncio
import json
from fastapi import WebSocket
from typing import Dict, Set

class ConnectionManager:
    def __init__(self):
        # user_connections: maps user_id -> WebSocket
        self.user_connections: Dict[int, WebSocket] = {}
        # group_rooms: maps group_id -> set of user_id
        self.group_rooms: Dict[int, Set[int]] = {}

    async def connect(self, user_id: int, group_id: int, websocket: WebSocket):
        await websocket.accept()

        # Handle 'last device wins' - close existing connection for this user
        if user_id in self.user_connections:
            old_ws = self.user_connections[user_id]
            try:
                await old_ws.send_text(json.dumps({"event": "replaced", "message": "Connected from another device."}))
                await old_ws.close()
            except Exception:
                pass
        
        self.user_connections[user_id] = websocket

        # Register in group room
        if group_id not in self.group_rooms:
            self.group_rooms[group_id] = set()
        self.group_rooms[group_id].add(user_id)

    async def disconnect(self, user_id: int, group_id: int):
        if user_id in self.user_connections:
            del self.user_connections[user_id]
        
        if group_id in self.group_rooms and user_id in self.group_rooms[group_id]:
            self.group_rooms[group_id].remove(user_id)
            if not self.group_rooms[group_id]:  # clean up empty rooms
                del self.group_rooms[group_id]

    async def broadcast_to_group(self, group_id: int, message: dict):
        if group_id not in self.group_rooms:
            return
            
        disconnected_users = set()
        msg_str = json.dumps(message)
        
        for user_id in self.group_rooms[group_id]:
            ws = self.user_connections.get(user_id)
            if ws:
                try:
                    await ws.send_text(msg_str)
                except Exception:
                    # Connection is dead
                    disconnected_users.add(user_id)
            else:
                disconnected_users.add(user_id)
                
        # Clean up dead connections
        for user_id in disconnected_users:
            await self.disconnect(user_id, group_id)

    async def heartbeat_loop(self):
        """Runs in background to ping all connections and prune dead ones."""
        while True:
            await asyncio.sleep(30)
            
            users_to_ping = list(self.user_connections.items())
            dead_users = []
            
            for user_id, ws in users_to_ping:
                try:
                    await asyncio.wait_for(ws.send_text(json.dumps({"event": "ping"})), timeout=5.0)
                except Exception:
                    dead_users.append(user_id)
            
            for user_id in dead_users:
                # We don't know the exact group_id here easily without searching,
                # let's find it.
                group_ids_to_remove_from = [g for g, users in self.group_rooms.items() if user_id in users]
                for g_id in group_ids_to_remove_from:
                    await self.disconnect(user_id, g_id)
                
                if user_id in self.user_connections:
                    try:
                        await self.user_connections[user_id].close()
                    except Exception:
                        pass
                    del self.user_connections[user_id]

manager = ConnectionManager()
