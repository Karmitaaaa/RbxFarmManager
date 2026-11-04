"""Política de reconexión (espera progresiva) y detección de desconexiones."""
import random
import socket

# Marcas que el cliente escribe en su log de texto (%LOCALAPPDATA%\Roblox\logs)
JOIN_MARKERS = (
    "serverId:",
    "Replicator created",
    "Connection accepted from",
    "game_join_loadtime",
)
JOINING_MARKERS = ("! Joining game", "initiateTeleport")
DISCONNECT_MARKERS = (
    "Time to disconnect replication data",
    "Disconnection Notification",
    "Lost connection with reason",
    "Sending disconnect with reason",
    "Connection lost",
)


def classify_log_line(line: str) -> str | None:
    if any(m in line for m in DISCONNECT_MARKERS):
        return "disconnect"
    if any(m in line for m in JOIN_MARKERS):
        return "joined"
    if any(m in line for m in JOINING_MARKERS):
        return "joining"
    return None


def backoff_delay(attempt: int, base_s: float, max_s: float) -> float:
    """attempt empieza en 0: base, base*2, base*4, ... con un poco de azar para no sincronizar."""
    delay = min(base_s * (2 ** attempt), max_s)
    return round(delay + random.uniform(0, min(5.0, delay * 0.2)), 1)


def internet_ok(timeout: float = 3.0) -> bool:
    for host in ("www.roblox.com", "1.1.1.1"):
        try:
            port = 443 if not host[0].isdigit() else 53
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False
