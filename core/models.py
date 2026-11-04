"""Modelos de datos compartidos."""
import time
import uuid
from dataclasses import asdict, dataclass, field

LOGIN_COOKIE = "cookie"
LOGIN_CURRENT = "current"
LOGIN_METHODS = {
    LOGIN_COOKIE: "Sesión guardada (recomendado)",
    LOGIN_CURRENT: "Sesión ya abierta en Roblox",
}


@dataclass
class Account:
    alias: str
    username: str = ""
    login_method: str = LOGIN_COOKIE
    cookie: str = ""            # secreto: solo vive en el baúl cifrado y en memoria
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    macro_profile: str = ""     # perfil de macro asociado
    clicker_preset: str = ""    # preset de autoclicker asociado
    auto_macro: bool = False    # reproducir la macro al entrar en juego
    anti_afk: bool = True       # anti-AFK activado por defecto en sus instancias
    user_id: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    @property
    def initials(self) -> str:
        name = (self.alias or self.username or "?").strip()
        parts = name.replace("_", " ").split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return name[:2].upper()


@dataclass
class LaunchTarget:
    place_id: int = 0
    job_id: str = ""
    private_link_code: str = ""
    share_code: str = ""        # enlaces nuevos roblox.com/share?code=...&type=Server
    raw: str = ""

    @property
    def label(self) -> str:
        if self.private_link_code or self.share_code:
            return f"Place {self.place_id or '?'} (privado)"
        if self.job_id:
            return f"Place {self.place_id} / {self.job_id[:8]}…"
        return f"Place {self.place_id}"


# Estados de instancia
ST_LAUNCHING = "Lanzando"
ST_OPEN = "Abierto"
ST_INGAME = "En juego"
ST_DISCONNECTED = "Desconectado"
ST_ERROR = "Error"
ST_CLOSED = "Cerrado"
ST_WAIT_RECONNECT = "Reconectando"
ST_WAIT_NET = "Sin internet"
ST_FAILED = "Fallido"
ST_STOPPED = "Detenido"

ACTIVE_STATES = {ST_LAUNCHING, ST_OPEN, ST_INGAME}


@dataclass
class Instance:
    account: Account
    target: LaunchTarget
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    pid: int | None = None
    hwnd: int | None = None
    status: str = ST_LAUNCHING
    detail: str = ""
    started_at: float = 0.0
    joined_at: float = 0.0
    retries: int = 0
    next_retry_at: float = 0.0
    anti_afk: bool = True
    auto_reconnect: bool = True
    cpu: float = 0.0
    ram_mb: float = 0.0
    next_afk_at: float = 0.0
    last_afk_at: float = 0.0
    log_path: str | None = None
    log_offset: int = 0
    last_disconnect_at: float = 0.0
    user_closed: bool = False
    macro_running: bool = False
    profile_id: str = ""        # perfil de juego con el que se lanzó (si hay)
    profile_name: str = ""


@dataclass
class GameProfile:
    """Un juego configurado: a dónde entrar, con qué cuentas y qué automatización usar."""
    name: str
    link: str = ""              # PlaceId o enlace (juego, servidor privado o /share)
    job_id: str = ""
    private_code: str = ""
    place_id: int = 0
    account_ids: list[str] = field(default_factory=list)
    macro_profile: str = ""
    clicker_preset: str = ""
    auto_run: bool = False      # iniciar macro/autoclicker al entrar en juego
    anti_afk: bool = True
    auto_reconnect: bool = True
    notes: str = ""
    last_played: float = 0.0
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GameProfile":
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)
