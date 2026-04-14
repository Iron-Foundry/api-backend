from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi import WebSocket


@dataclass
class ClientConnection:
    ws: WebSocket
    verification_code: str


class ConnectionManager:
    def __init__(self) -> None:
        # guild_id (int) -> {conn_id: ClientConnection}
        self._connections: dict[int, dict[UUID, ClientConnection]] = {}

    def connect(self, ws: WebSocket, guild_id: int, verification_code: str) -> UUID:
        conn_id = uuid4()
        self._connections.setdefault(guild_id, {})[conn_id] = ClientConnection(
            ws=ws, verification_code=verification_code
        )
        return conn_id

    def disconnect(self, conn_id: UUID, guild_id: int) -> None:
        self._connections.get(guild_id, {}).pop(conn_id, None)

    def get_conn_id(self, guild_id: int, verification_code: str) -> UUID | None:
        """Return the conn_id for a given verification code, if connected."""
        for conn_id, client in self._connections.get(guild_id, {}).items():
            if client.verification_code == verification_code:
                return conn_id
        return None

    async def broadcast(self, guild_id: int, message: str) -> None:
        dead: list[UUID] = []
        for conn_id, client in list(self._connections.get(guild_id, {}).items()):
            try:
                await client.ws.send_text(message)
            except Exception:
                dead.append(conn_id)
        for conn_id in dead:
            self.disconnect(conn_id, guild_id)

    def connection_count(self, guild_id: int) -> int:
        return len(self._connections.get(guild_id, {}))

    async def send_to(self, conn_id: UUID, guild_id: int, message: str) -> bool:
        client = self._connections.get(guild_id, {}).get(conn_id)
        if client is None:
            return False
        try:
            await client.ws.send_text(message)
            return True
        except Exception:
            self.disconnect(conn_id, guild_id)
            return False


connection_manager = ConnectionManager()
