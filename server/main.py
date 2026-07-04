import os
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from . import auth, db, captcha as cap

app = FastAPI(title="Caltimeria API")

_APP_SECRET = os.getenv("APP_SECRET", "")
_ADMIN_KEY  = os.getenv("ADMIN_KEY", "")


# ── helpers ──────────────────────────────────────────────────────────────────

def verificar_app(request: Request):
    if request.headers.get("X-App-Secret") != _APP_SECRET:
        raise HTTPException(status_code=401, detail="App secret inválido")


def verificar_admin(request: Request):
    if request.headers.get("X-Admin-Key") != _ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Clave de administrador incorrecta")


def usuario_del_token(request: Request) -> dict:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")
    return auth.validar_token(header[7:])


# ── modelos ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str

class RegistroRequest(BaseModel):
    nombre: str
    email: str
    password: str

class ActivarRequest(BaseModel):
    usuario_id: int
    plan_id: int
    dias: int

class CaptchaRequest(BaseModel):
    sitekey: str
    pageurl: str

class HistorialRequest(BaseModel):
    placa: str
    fuente: str
    resultado: dict


# ── auth ──────────────────────────────────────────────────────────────────────

@app.post("/auth/login")
def auth_login(req: LoginRequest):
    return auth.login(req.email, req.password)

@app.post("/auth/registro")
def auth_registro(req: RegistroRequest):
    return auth.registrar(req.email, req.password, req.nombre)

@app.get("/auth/validate")
def auth_validate(usuario: dict = Depends(usuario_del_token)):
    return {"ok": True, "sub": usuario["sub"], "email": usuario["email"]}


# ── captcha (protegido por APP_SECRET) ────────────────────────────────────────

@app.post("/captcha/turnstile")
def captcha_turnstile(req: CaptchaRequest, _: None = Depends(verificar_app)):
    token = cap.resolver_turnstile(req.sitekey, req.pageurl)
    return {"token": token}

@app.post("/captcha/recaptcha")
def captcha_recaptcha(req: CaptchaRequest, _: None = Depends(verificar_app)):
    token = cap.resolver_recaptcha_v2(req.sitekey, req.pageurl)
    return {"token": token}


# ── historial ─────────────────────────────────────────────────────────────────

@app.post("/historial/guardar")
def historial_guardar(req: HistorialRequest, usuario: dict = Depends(usuario_del_token)):
    db.guardar_consulta(int(usuario["sub"]), req.placa, req.fuente, req.resultado)
    return {"ok": True}

@app.get("/historial")
def historial_get(usuario: dict = Depends(usuario_del_token)):
    return db.obtener_historial(int(usuario["sub"]))


# ── admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin/usuarios")
def admin_usuarios(request: Request):
    verificar_admin(request)
    return {"usuarios": db.listar_usuarios(), "planes": db.listar_planes()}

@app.post("/admin/activar")
def admin_activar(req: ActivarRequest, request: Request):
    verificar_admin(request)
    db.activar_usuario(req.usuario_id, req.plan_id, req.dias)
    return {"ok": True}


# ── health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}
