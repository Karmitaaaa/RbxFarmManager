"""Cifrado local: Fernet (AES-128-CBC + HMAC) con clave derivada por scrypt, o Windows DPAPI.

Formato del sobre (JSON):
  {"app": "RbxFarmManager", "v": 1, "mode": "password"|"dpapi", "kdf": {...}, "data": "..."}
"""
import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

APP_TAG = "RbxFarmManager"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1


class WrongPassword(Exception):
    pass


class BadFile(Exception):
    pass


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def derive_key(password: str, salt: bytes, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=n, r=r, p=p)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def seal(plaintext: bytes, mode: str, password: str | None = None) -> bytes:
    envelope = {"app": APP_TAG, "v": 1, "mode": mode}
    if mode == "password":
        if not password:
            raise ValueError("Se necesita contraseña maestra")
        salt = os.urandom(16)
        envelope["kdf"] = {"name": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P, "salt": _b64e(salt)}
        envelope["data"] = Fernet(derive_key(password, salt)).encrypt(plaintext).decode("ascii")
    elif mode == "dpapi":
        import win32crypt
        blob = win32crypt.CryptProtectData(plaintext, APP_TAG, None, None, None, 0)
        envelope["data"] = _b64e(blob)
    else:
        raise ValueError(f"Modo desconocido: {mode}")
    return json.dumps(envelope).encode("utf-8")


def read_envelope(raw: bytes) -> dict:
    try:
        env = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadFile("El archivo no es un contenedor válido de RbxFarm Manager") from exc
    if env.get("app") != APP_TAG or "data" not in env:
        raise BadFile("El archivo no es un contenedor válido de RbxFarm Manager")
    return env


def unseal(raw: bytes, password: str | None = None) -> bytes:
    env = read_envelope(raw)
    if env["mode"] == "password":
        kdf = env["kdf"]
        key = derive_key(password or "", _b64d(kdf["salt"]), kdf["n"], kdf["r"], kdf["p"])
        try:
            return Fernet(key).decrypt(env["data"].encode("ascii"))
        except InvalidToken as exc:
            raise WrongPassword("Contraseña incorrecta") from exc
    if env["mode"] == "dpapi":
        import win32crypt
        try:
            _, data = win32crypt.CryptUnprotectData(_b64d(env["data"]), None, None, None, 0)
        except Exception as exc:
            raise WrongPassword("DPAPI no pudo descifrar (¿otro usuario de Windows u otro equipo?)") from exc
        return data
    raise BadFile(f"Modo desconocido: {env['mode']}")
