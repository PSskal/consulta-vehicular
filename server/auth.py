import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException

from . import db

_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
_ALGO = "HS256"
_TTL_HORAS = 24


def hashear(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verificar(password: str, hash_guardado: str) -> bool:
    return bcrypt.checkpw(password.encode(), hash_guardado.encode())


def crear_token(usuario_id: int, email: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=_TTL_HORAS)
    return jwt.encode({"sub": str(usuario_id), "email": email, "exp": exp}, _SECRET, algorithm=_ALGO)


def validar_token(token: str) -> dict:
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada, vuelve a iniciar sesión")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")


def registrar(email: str, password: str, nombre: str) -> dict:
    if db.email_existe(email):
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")
    uid = db.crear_usuario(email, hashear(password), nombre)
    return {"id": uid, "mensaje": "Cuenta creada. Un administrador la activará pronto."}


def login(email: str, password: str) -> dict:
    usuario = db.buscar_usuario(email)
    if not usuario:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    if not usuario["activo"]:
        raise HTTPException(status_code=403, detail="Cuenta desactivada o pendiente de activación")
    if not verificar(password, usuario["password_hash"]):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    suscripcion = db.obtener_suscripcion_activa(usuario["id"])
    if not suscripcion:
        raise HTTPException(status_code=403, detail="Sin suscripción activa")

    limite = suscripcion["limite_consultas"]
    if limite is not None and suscripcion["consultas_usadas"] >= limite:
        raise HTTPException(status_code=403, detail="Límite de consultas alcanzado")

    token = crear_token(usuario["id"], usuario["email"])
    return {
        "token": token,
        "nombre": usuario["nombre"] or email,
        "plan": suscripcion["plan"],
        "fin": suscripcion["fin"].isoformat(),
    }
