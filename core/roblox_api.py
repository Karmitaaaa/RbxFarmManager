"""Llamadas mínimas a la API oficial de Roblox (solo dominios *.roblox.com).

La cookie solo se envía a roblox.com para pedir un ticket de inicio de sesión de un solo uso,
igual que hace el navegador al pulsar "Jugar". Ningún dato se envía a terceros.
"""
import logging

import requests

log = logging.getLogger(__name__)

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
TIMEOUT = 15


class RobloxAuthError(Exception):
    """Cookie inválida o caducada: reintentar no sirve."""


class RobloxApiError(Exception):
    """Fallo temporal de red o de la API."""


def _session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Referer": "https://www.roblox.com/",
        "Origin": "https://www.roblox.com",
        "Accept": "application/json",
    })
    s.cookies.set(".ROBLOSECURITY", cookie.strip(), domain=".roblox.com")
    return s


def _post_with_csrf(s: requests.Session, url: str, **kwargs) -> requests.Response:
    r = s.post(url, timeout=TIMEOUT, **kwargs)
    token = r.headers.get("x-csrf-token")
    if r.status_code == 403 and token:
        s.headers["X-CSRF-TOKEN"] = token
        r = s.post(url, timeout=TIMEOUT, **kwargs)
    return r


def get_authenticated_user(cookie: str) -> dict:
    """Devuelve {"id", "name", "displayName"} de la cuenta de la cookie."""
    try:
        r = _session(cookie).get("https://users.roblox.com/v1/users/authenticated", timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise RobloxApiError(f"Sin conexión con Roblox: {exc}") from exc
    if r.status_code == 401:
        raise RobloxAuthError("La cookie no es válida o ha caducado")
    if not r.ok:
        raise RobloxApiError(f"Roblox respondió {r.status_code}")
    return r.json()


def resolve_user_id(username: str) -> int:
    """Nombre de usuario -> ID (dato público, no necesita cookie)."""
    try:
        r = requests.post("https://users.roblox.com/v1/usernames/users", timeout=TIMEOUT,
                          headers={"User-Agent": USER_AGENT},
                          json={"usernames": [username], "excludeBannedUsers": False})
    except requests.RequestException as exc:
        raise RobloxApiError(f"Sin conexión con Roblox: {exc}") from exc
    data = r.json().get("data") if r.ok else None
    if not data:
        raise RobloxApiError(f"No existe el usuario «{username}»")
    return int(data[0]["id"])


def fetch_headshot(user_id: int, size: str = "150x150") -> bytes:
    """Descarga la foto (headshot) del avatar en PNG con fondo transparente."""
    try:
        r = requests.get("https://thumbnails.roblox.com/v1/users/avatar-headshot", timeout=TIMEOUT,
                         headers={"User-Agent": USER_AGENT},
                         params={"userIds": user_id, "size": size, "format": "Png", "isCircular": "false"})
        items = r.json().get("data") if r.ok else None
        url = items[0].get("imageUrl") if items and items[0].get("state") == "Completed" else None
        if not url:
            raise RobloxApiError("La foto del avatar aún no está disponible")
        img = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        raise RobloxApiError(f"Sin conexión con Roblox: {exc}") from exc
    if not img.ok or not img.content.startswith(b"\x89PNG"):
        raise RobloxApiError("Respuesta de imagen no válida")
    return img.content


def game_info(place_id: int) -> dict:
    """Nombre y datos públicos de un juego a partir de su PlaceId."""
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(f"https://apis.roblox.com/universes/v1/places/{place_id}/universe",
                         headers=headers, timeout=TIMEOUT)
        universe_id = r.json().get("universeId") if r.ok else None
        if not universe_id:
            raise RobloxApiError("No se encontró ese juego")
        r = requests.get("https://games.roblox.com/v1/games", params={"universeIds": universe_id},
                         headers=headers, timeout=TIMEOUT)
        data = r.json().get("data") if r.ok else None
    except requests.RequestException as exc:
        raise RobloxApiError(f"Sin conexión con Roblox: {exc}") from exc
    if not data:
        raise RobloxApiError("No se encontró ese juego")
    game = data[0]
    return {"name": game.get("name", ""), "universe_id": universe_id,
            "playing": game.get("playing", 0), "creator": (game.get("creator") or {}).get("name", "")}


def fetch_game_icon(place_id: int, size: str = "256x256") -> bytes:
    """Icono cuadrado del juego en PNG."""
    try:
        r = requests.get("https://thumbnails.roblox.com/v1/places/gameicons", timeout=TIMEOUT,
                         headers={"User-Agent": USER_AGENT},
                         params={"placeIds": place_id, "returnPolicy": "PlaceHolder", "size": size,
                                 "format": "Png", "isCircular": "false"})
        items = r.json().get("data") if r.ok else None
        url = items[0].get("imageUrl") if items and items[0].get("state") == "Completed" else None
        if not url:
            raise RobloxApiError("El icono del juego aún no está disponible")
        img = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        raise RobloxApiError(f"Sin conexión con Roblox: {exc}") from exc
    if not img.ok or not img.content.startswith(b"\x89PNG"):
        raise RobloxApiError("Respuesta de imagen no válida")
    return img.content


def get_auth_ticket(cookie: str) -> str:
    try:
        r = _post_with_csrf(_session(cookie), "https://auth.roblox.com/v1/authentication-ticket", json={})
    except requests.RequestException as exc:
        raise RobloxApiError(f"Sin conexión con Roblox: {exc}") from exc
    ticket = r.headers.get("rbx-authentication-ticket")
    if ticket:
        return ticket
    if r.status_code == 401:
        raise RobloxAuthError("La cookie no es válida o ha caducado")
    raise RobloxApiError(f"No se obtuvo ticket (HTTP {r.status_code})")


def resolve_share_link(cookie: str, code: str) -> tuple[int, str]:
    """Convierte un enlace roblox.com/share?code=...&type=Server en (placeId, linkCode)."""
    try:
        r = _post_with_csrf(_session(cookie), "https://apis.roblox.com/sharelinks/v1/resolve-link",
                            json={"linkId": code, "linkType": "Server"})
    except requests.RequestException as exc:
        raise RobloxApiError(f"Sin conexión con Roblox: {exc}") from exc
    if r.status_code == 401:
        raise RobloxAuthError("La cookie no es válida o ha caducado")
    if not r.ok:
        raise RobloxApiError(f"No se pudo resolver el enlace (HTTP {r.status_code})")
    data = r.json().get("privateServerInviteData") or {}
    if not data.get("placeId") or not data.get("linkCode"):
        raise RobloxApiError("El enlace compartido no es de un servidor privado válido")
    return int(data["placeId"]), str(data["linkCode"])
