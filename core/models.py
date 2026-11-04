"""Modelos de datos compartidos."""
import time
import uuid
from dataclasses import asdict, dataclass, field

from utils.i18n import N_, t

LOGIN_COOKIE = "cookie"
LOGIN_CURRENT = "current"
LOGIN_METHODS = {
    LOGIN_COOKIE: N_("Sesión guardada (recomendado)"),
    LOGIN_CURRENT: N_("Sesión ya abierta en Roblox"),
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
            return t("Place {0} (privado)", self.place_id or "?")
        if self.job_id:
            return f"Place {self.place_id} / {self.job_id[:8]}…"
        return f"Place {self.place_id}"


# Estados de instancia
ST_LAUNCHING = N_("Lanzando")
ST_OPEN = N_("Abierto")
ST_INGAME = N_("En juego")
ST_DISCONNECTED = N_("Desconectado")
ST_ERROR = N_("Error")
ST_CLOSED = N_("Cerrado")
ST_WAIT_RECONNECT = N_("Reconectando")
ST_WAIT_NET = N_("Sin internet")
ST_FAILED = N_("Fallido")
ST_STOPPED = N_("Detenido")

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
