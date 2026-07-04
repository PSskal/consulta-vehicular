import os
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

_SERVER = os.getenv("SERVER_URL", "").rstrip("/")
_ADMIN_KEY = os.getenv("ADMIN_KEY", "")

from .satlima import consultar as consultar_satlima
from .callao import consultar as consultar_callao
from .sutran import consultar as consultar_sutran
from .atu import consultar as consultar_atu
from .soat import consultar as consultar_soat
from .revisiontecnica import consultar as consultar_revisiontecnica
from .sunarp import consultar as consultar_sunarp
import requests as _req

app = FastAPI(title="Consulta Vehicular")
executor = ThreadPoolExecutor(max_workers=7)


async def ejecutar(func, placa, **kwargs):
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, lambda: func(placa, **kwargs))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar: {e}")


REGISTRO_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crear cuenta — Consulta Vehicular</title>
<style>
  :root {
    --bg: #eef1f6; --surface: #ffffff; --border: #e5e9f0; --text: #1a1f2b;
    --text-muted: #6b7280; --primary: #4f46e5; --primary-hover: #4338ca;
    --primary-soft: #eef0fe; --success: #16a34a; --success-soft: #ecfdf3;
    --success-border: #bbf3cf; --danger: #dc2626; --danger-soft: #fef2f2;
    --danger-border: #fbd5d5; --radius: 16px;
    --shadow: 0 1px 2px rgba(16,24,40,.04), 0 8px 24px -8px rgba(16,24,40,.10);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif;
    background: radial-gradient(900px 480px at 12% -8%, #e7e9ff 0%, transparent 60%),
                radial-gradient(900px 480px at 100% 0%, #e3f6ec 0%, transparent 55%), var(--bg);
    color: var(--text); min-height: 100vh;
    display: flex; align-items: center; justify-content: center; padding: 24px;
  }
  .card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 40px 36px; width: 100%; max-width: 420px; box-shadow: var(--shadow);
  }
  .eyebrow {
    display: inline-flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600;
    letter-spacing: .04em; text-transform: uppercase; color: var(--primary);
    background: var(--primary-soft); padding: 5px 12px; border-radius: 999px; margin-bottom: 14px;
  }
  .eyebrow::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--primary); }
  h1 { font-size: 24px; font-weight: 700; letter-spacing: -.02em; margin-bottom: 6px; }
  p.sub { color: var(--text-muted); font-size: 14px; margin-bottom: 28px; }
  label { font-size: 13px; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 6px; }
  input {
    width: 100%; padding: 12px 16px; border: 1.5px solid var(--border); border-radius: 10px;
    font-size: 15px; color: var(--text); background: #fbfbfd; margin-bottom: 16px;
    transition: border-color .15s, box-shadow .15s;
  }
  input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 4px var(--primary-soft); }
  button {
    width: 100%; padding: 13px; background: var(--primary); color: white; border: none;
    border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer;
    transition: background .15s; box-shadow: 0 4px 14px -4px rgba(79,70,229,.55);
  }
  button:hover { background: var(--primary-hover); }
  button:disabled { background: #c6cad3; box-shadow: none; cursor: not-allowed; }
  .msg { padding: 10px 14px; border-radius: 10px; font-size: 13px; margin-bottom: 16px; display: none; border: 1px solid; }
  .msg.error { background: var(--danger-soft); border-color: var(--danger-border); color: var(--danger); }
  .msg.ok    { background: var(--success-soft); border-color: var(--success-border); color: var(--success); }
  .link { text-align: center; margin-top: 18px; font-size: 13px; color: var(--text-muted); }
  .link a { color: var(--primary); text-decoration: none; font-weight: 600; }
</style>
</head>
<body>
<div class="card">
  <span class="eyebrow">Registro</span>
  <h1>Crear cuenta</h1>
  <p class="sub">Tu cuenta será activada por un administrador tras confirmar tu pago.</p>
  <div class="msg" id="msg"></div>
  <label>Nombre completo</label>
  <input type="text" id="nombre" placeholder="Tu nombre" />
  <label>Correo electrónico</label>
  <input type="email" id="email" placeholder="tu@correo.com" />
  <label>Contraseña</label>
  <input type="password" id="password" placeholder="Mínimo 6 caracteres" />
  <button id="btn" onclick="registrar()">Crear cuenta</button>
  <p class="link">¿Ya tienes cuenta? <a href="/login">Inicia sesión</a></p>
</div>
<script>
async function registrar() {
  const nombre = document.getElementById('nombre').value.trim();
  const email  = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  const btn = document.getElementById('btn');
  const msgEl = document.getElementById('msg');
  msgEl.style.display = 'none';
  if (!nombre || !email || !password) { mostrar('error', 'Completa todos los campos'); return; }
  btn.disabled = true; btn.textContent = 'Creando cuenta...';
  try {
    const resp = await fetch('/auth/registro', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({nombre, email, password})
    });
    const data = await resp.json();
    if (!resp.ok) { mostrar('error', data.detail || 'Error al registrar'); return; }
    mostrar('ok', data.mensaje);
    btn.textContent = 'Cuenta creada';
  } catch(e) {
    mostrar('error', 'Error de conexión: ' + e.message);
    btn.disabled = false; btn.textContent = 'Crear cuenta';
  }
}
function mostrar(tipo, txt) {
  const el = document.getElementById('msg');
  el.className = 'msg ' + tipo; el.textContent = txt; el.style.display = 'block';
}
</script>
</body>
</html>"""

ADMIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Panel Admin — Consulta Vehicular</title>
<style>
  :root {
    --bg: #eef1f6; --surface: #ffffff; --border: #e5e9f0; --text: #1a1f2b;
    --text-muted: #6b7280; --primary: #4f46e5; --primary-hover: #4338ca;
    --primary-soft: #eef0fe; --success: #16a34a; --success-soft: #ecfdf3;
    --success-border: #bbf3cf; --danger: #dc2626; --danger-soft: #fef2f2;
    --danger-border: #fbd5d5; --radius: 16px;
    --shadow: 0 1px 2px rgba(16,24,40,.04), 0 8px 24px -8px rgba(16,24,40,.10);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: "Segoe UI", -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 40px 20px; }
  .wrap { max-width: 900px; margin: 0 auto; }
  h1 { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
  p.sub { color: var(--text-muted); font-size: 14px; margin-bottom: 28px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 24px; box-shadow: var(--shadow); margin-bottom: 20px; }
  table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
  th { background: #f8f9fb; padding: 10px 12px; text-align: left; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
  td { padding: 10px 12px; border-bottom: 1px solid #f1f2f5; vertical-align: middle; }
  tr:last-child td { border-bottom: none; }
  .badge { padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
  .badge.activo   { background: var(--success-soft); color: var(--success); }
  .badge.inactivo { background: var(--danger-soft);  color: var(--danger); }
  .badge.plan     { background: var(--primary-soft); color: var(--primary); }
  select, input[type=number] {
    padding: 6px 10px; border: 1.5px solid var(--border); border-radius: 8px;
    font-size: 13px; background: #fbfbfd; color: var(--text);
  }
  button.act {
    padding: 6px 14px; background: var(--primary); color: white; border: none;
    border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer;
  }
  button.act:hover { background: var(--primary-hover); }
  .login-wrap { min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  .login-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 36px; width: 360px; box-shadow: var(--shadow); }
  .login-card h2 { margin-bottom: 20px; font-size: 20px; }
  .login-card input { width: 100%; padding: 11px 14px; border: 1.5px solid var(--border); border-radius: 10px; font-size: 14px; margin-bottom: 14px; }
  .login-card button { width: 100%; padding: 12px; background: var(--primary); color: white; border: none; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; }
  #err { color: var(--danger); font-size: 13px; margin-bottom: 10px; display: none; }
</style>
</head>
<body>

<div class="login-wrap" id="login-screen">
  <div class="login-card">
    <h2>🔐 Panel Admin</h2>
    <p id="err"></p>
    <input type="password" id="admin-key" placeholder="Clave de administrador" />
    <button onclick="entrarAdmin()">Entrar</button>
  </div>
</div>

<div class="wrap" id="admin-panel" style="display:none">
  <h1>Panel de Administración</h1>
  <p class="sub">Gestiona los usuarios y sus suscripciones</p>
  <div class="card">
    <table id="tabla-usuarios">
      <thead><tr><th>Nombre</th><th>Email</th><th>Estado</th><th>Plan activo</th><th>Vence</th><th>Activar</th></tr></thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
</div>

<script>
let _key = '';
let _planes = [];

async function entrarAdmin() {
  const k = document.getElementById('admin-key').value.trim();
  const resp = await fetch('/admin/usuarios', {headers: {'X-Admin-Key': k}});
  if (!resp.ok) { const e = document.getElementById('err'); e.textContent = 'Clave incorrecta'; e.style.display='block'; return; }
  _key = k;
  const data = await resp.json();
  _planes = data.planes;
  renderTabla(data.usuarios);
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('admin-panel').style.display = 'block';
}

function renderTabla(usuarios) {
  const tb = document.getElementById('tbody');
  tb.innerHTML = '';
  for (const u of usuarios) {
    const estado = u.activo
      ? '<span class="badge activo">Activo</span>'
      : '<span class="badge inactivo">Inactivo</span>';
    const plan = u.plan ? '<span class="badge plan">' + u.plan + '</span>' : '—';
    const vence = u.suscripcion_fin ? new Date(u.suscripcion_fin).toLocaleDateString('es-PE') : '—';
    const selectPlan = '<select id="plan-' + u.id + '">' +
      _planes.map(p => '<option value="' + p.id + '">' + p.nombre + ' (' + (p.limite_consultas || '∞') + ')</option>').join('') +
      '</select>';
    const dias = '<input type="number" id="dias-' + u.id + '" value="30" min="1" max="365" style="width:64px">';
    const btn = '<button class="act" onclick="activar(' + u.id + ')">Activar</button>';
    tb.innerHTML += '<tr><td>' + (u.nombre||'—') + '</td><td>' + u.email + '</td><td>' + estado + '</td><td>' + plan + '</td><td>' + vence + '</td><td style="display:flex;gap:6px;align-items:center">' + selectPlan + dias + ' días ' + btn + '</td></tr>';
  }
}

async function activar(id) {
  const plan_id = document.getElementById('plan-' + id).value;
  const dias = document.getElementById('dias-' + id).value;
  const resp = await fetch('/admin/activar', {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-Admin-Key': _key},
    body: JSON.stringify({usuario_id: id, plan_id: parseInt(plan_id), dias: parseInt(dias)})
  });
  if (resp.ok) {
    const data = await fetch('/admin/usuarios', {headers: {'X-Admin-Key': _key}}).then(r => r.json());
    renderTabla(data.usuarios);
  } else {
    alert('Error al activar');
  }
}

document.getElementById('admin-key').addEventListener('keydown', e => { if (e.key === 'Enter') entrarAdmin(); });
</script>
</body>
</html>"""

LOGIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Iniciar sesión — Consulta Vehicular</title>
<style>
  :root {
    --bg: #eef1f6; --surface: #ffffff; --border: #e5e9f0; --text: #1a1f2b;
    --text-muted: #6b7280; --primary: #4f46e5; --primary-hover: #4338ca;
    --primary-soft: #eef0fe; --danger: #dc2626; --danger-soft: #fef2f2;
    --danger-border: #fbd5d5; --radius: 16px;
    --shadow: 0 1px 2px rgba(16,24,40,.04), 0 8px 24px -8px rgba(16,24,40,.10);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif;
    background: radial-gradient(900px 480px at 12% -8%, #e7e9ff 0%, transparent 60%),
                radial-gradient(900px 480px at 100% 0%, #e3f6ec 0%, transparent 55%), var(--bg);
    color: var(--text); min-height: 100vh;
    display: flex; align-items: center; justify-content: center; padding: 24px;
  }
  .card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 40px 36px; width: 100%; max-width: 420px; box-shadow: var(--shadow);
  }
  .eyebrow {
    display: inline-flex; align-items: center; gap: 8px;
    font-size: 12px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
    color: var(--primary); background: var(--primary-soft);
    padding: 5px 12px; border-radius: 999px; margin-bottom: 14px;
  }
  .eyebrow::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--primary); }
  h1 { font-size: 24px; font-weight: 700; letter-spacing: -.02em; margin-bottom: 6px; }
  p.sub { color: var(--text-muted); font-size: 14px; margin-bottom: 28px; }
  label { font-size: 13px; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 6px; }
  input {
    width: 100%; padding: 12px 16px; border: 1.5px solid var(--border); border-radius: 10px;
    font-size: 15px; color: var(--text); background: #fbfbfd; margin-bottom: 16px;
    transition: border-color .15s, box-shadow .15s;
  }
  input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 4px var(--primary-soft); }
  button {
    width: 100%; padding: 13px; background: var(--primary); color: white;
    border: none; border-radius: 10px; font-size: 15px; font-weight: 600;
    cursor: pointer; transition: background .15s;
    box-shadow: 0 4px 14px -4px rgba(79,70,229,.55);
  }
  button:hover { background: var(--primary-hover); }
  button:disabled { background: #c6cad3; box-shadow: none; cursor: not-allowed; }
  .error {
    background: var(--danger-soft); border: 1px solid var(--danger-border); color: var(--danger);
    padding: 10px 14px; border-radius: 10px; font-size: 13px; margin-bottom: 16px; display: none;
  }
</style>
</head>
<body>
<div class="card">
  <span class="eyebrow">Acceso</span>
  <h1>Consulta Vehicular</h1>
  <p class="sub">Ingresa tus credenciales para continuar</p>
  <div class="error" id="error-msg"></div>
  <label>Correo electrónico</label>
  <input type="email" id="email" placeholder="tu@correo.com" autocomplete="username" />
  <label>Contraseña</label>
  <input type="password" id="password" placeholder="••••••••" autocomplete="current-password" />
  <button id="btn" onclick="iniciarSesion()">Ingresar</button>
  <p style="text-align:center;margin-top:18px;font-size:13px;color:var(--text-muted)">
    ¿No tienes cuenta? <a href="/registro" style="color:var(--primary);text-decoration:none;font-weight:600">Regístrate</a>
  </p>
</div>
<script>
document.addEventListener('keydown', e => { if (e.key === 'Enter') iniciarSesion(); });

async function iniciarSesion() {
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  const btn = document.getElementById('btn');
  const errEl = document.getElementById('error-msg');
  errEl.style.display = 'none';
  if (!email || !password) { mostrarError('Completa todos los campos'); return; }
  btn.disabled = true; btn.textContent = 'Verificando...';
  try {
    const resp = await fetch('/auth/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email, password})
    });
    const data = await resp.json();
    if (!resp.ok) { mostrarError(data.detail || 'Error al iniciar sesión'); return; }
    localStorage.setItem('cv_token', data.token);
    localStorage.setItem('cv_plan', data.plan);
    window.location.href = '/';
  } catch(e) {
    mostrarError('Error de conexión: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Ingresar';
  }
}

function mostrarError(msg) {
  const el = document.getElementById('error-msg');
  el.textContent = msg; el.style.display = 'block';
}
</script>
</body>
</html>"""

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Consulta Vehicular</title>
<style>
  :root {
    --bg: #eef1f6;
    --surface: #ffffff;
    --border: #e5e9f0;
    --text: #1a1f2b;
    --text-muted: #6b7280;
    --primary: #4f46e5;
    --primary-hover: #4338ca;
    --primary-soft: #eef0fe;
    --success: #16a34a;
    --success-soft: #ecfdf3;
    --success-border: #bbf3cf;
    --danger: #dc2626;
    --danger-soft: #fef2f2;
    --danger-border: #fbd5d5;
    --warning: #d97706;
    --warning-soft: #fffbeb;
    --warning-border: #fde6b2;
    --radius: 16px;
    --shadow: 0 1px 2px rgba(16,24,40,.04), 0 8px 24px -8px rgba(16,24,40,.10);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif;
    background:
      radial-gradient(900px 480px at 12% -8%, #e7e9ff 0%, transparent 60%),
      radial-gradient(900px 480px at 100% 0%, #e3f6ec 0%, transparent 55%),
      var(--bg);
    color: var(--text);
    padding: 48px 20px;
    min-height: 100vh;
  }

  .top {
    max-width: 1020px; margin: 0 auto 28px; background: var(--surface);
    border: 1px solid var(--border); border-radius: var(--radius);
    padding: 32px 36px; box-shadow: var(--shadow);
  }
  .eyebrow {
    display: inline-flex; align-items: center; gap: 8px;
    font-size: 12px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
    color: var(--primary); background: var(--primary-soft);
    padding: 5px 12px; border-radius: 999px; margin-bottom: 14px;
  }
  .eyebrow::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--primary); }
  h1 { font-size: 28px; font-weight: 700; letter-spacing: -.02em; margin-bottom: 6px; }
  .subtitle { color: var(--text-muted); margin-bottom: 26px; font-size: 14.5px; }

  .input-row { display: flex; gap: 12px; }
  input[type=text] {
    flex: 1; padding: 14px 18px; border: 1.5px solid var(--border); border-radius: 12px;
    font-size: 20px; text-transform: uppercase; letter-spacing: 3px; font-weight: 700;
    color: var(--text); background: #fbfbfd; transition: border-color .15s, box-shadow .15s;
  }
  input[type=text]::placeholder { color: #b6bac4; letter-spacing: 2px; }
  input[type=text]:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 4px var(--primary-soft); background: var(--surface); }
  button {
    padding: 14px 30px; background: var(--primary); color: white;
    border: none; border-radius: 12px; font-size: 15.5px; font-weight: 600;
    cursor: pointer; white-space: nowrap; transition: background .15s, transform .1s, box-shadow .15s;
    box-shadow: 0 4px 14px -4px rgba(79,70,229,.55);
  }
  button:hover { background: var(--primary-hover); }
  button:active { transform: translateY(1px); }
  button:disabled { background: #c6cad3; cursor: not-allowed; box-shadow: none; }

  .grid {
    max-width: 1020px; margin: 0 auto; display: grid;
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 20px;
  }

  .card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 22px 24px; box-shadow: var(--shadow);
    transition: transform .15s ease, box-shadow .15s ease;
  }
  .card:hover { transform: translateY(-2px); box-shadow: 0 4px 6px rgba(16,24,40,.05), 0 14px 28px -10px rgba(16,24,40,.16); }

  .card-head { display: flex; align-items: center; gap: 10px; padding-bottom: 12px; border-bottom: 1px solid var(--border); margin-bottom: 14px; }
  .card-dot { width: 9px; height: 9px; border-radius: 50%; flex: none; }
  .card-logo {
    width: 26px; height: 26px; flex: none; object-fit: contain; border-radius: 6px;
    background: #fff; padding: 2px;
  }
  .card h2 { font-size: 15.5px; font-weight: 600; color: var(--text); }

  .status {
    display: flex; align-items: center; gap: 8px;
    padding: 10px 14px; border-radius: 10px; margin-bottom: 14px;
    font-size: 13px; font-weight: 500; border: 1px solid transparent; line-height: 1.45;
  }
  .status.idle    { background: #f6f7f9; color: var(--text-muted); border-color: var(--border); }
  .status.loading { background: var(--warning-soft); border-color: var(--warning-border); color: var(--warning); }
  .status.error   { background: var(--danger-soft);  border-color: var(--danger-border);  color: var(--danger); }
  .status.ok      { background: var(--success-soft); border-color: var(--success-border); color: var(--success); }

  .total-badge {
    display: inline-block; background: var(--primary-soft); color: var(--primary);
    padding: 6px 16px; border-radius: 999px; font-weight: 700; font-size: 17px;
  }
  .sin-deuda { color: var(--success); font-size: 13.5px; padding: 4px 0; }
  .vigente { color: var(--success); font-weight: 700; }
  .no-vigente { color: var(--danger); font-weight: 700; }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th {
    background: #f8f9fb; padding: 9px 10px; text-align: left; color: var(--text-muted);
    font-weight: 600; border-bottom: 1px solid var(--border);
  }
  td { padding: 9px 10px; border-bottom: 1px solid #f1f2f5; color: var(--text); }
  tr:last-child td { border-bottom: none; }
  .total-row { text-align: right; margin-top: 14px; font-size: 13.5px; color: var(--text-muted); }

  .ficha { font-size: 14px; }
  .ficha div { padding: 6px 0; border-bottom: 1px dashed var(--border); }
  .ficha div:last-child { border-bottom: none; }
  .ficha b { color: var(--text-muted); font-weight: 600; margin-right: 4px; }

  .spinner {
    display: inline-block; width: 12px; height: 12px; border: 2px solid var(--warning);
    border-top-color: transparent; border-radius: 50%; animation: spin .7s linear infinite;
    flex: none;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .user-bar {
    max-width: 1020px; margin: 0 auto 16px;
    display: flex; align-items: center; gap: 10px;
    font-size: 13px; color: var(--text-muted);
  }
  .plan-badge {
    background: var(--primary-soft); color: var(--primary);
    padding: 3px 10px; border-radius: 999px; font-weight: 600; font-size: 12px;
  }
  .logout-btn {
    margin-left: auto; padding: 6px 14px; background: transparent;
    border: 1px solid var(--border); color: var(--text-muted);
    border-radius: 8px; font-size: 13px; font-weight: 500; box-shadow: none; cursor: pointer;
  }
  .logout-btn:hover { background: var(--danger-soft); color: var(--danger); border-color: var(--danger-border); }

  .historial-wrap {
    max-width: 1020px; margin: 24px auto 0;
  }
  .hist-toggle {
    width: 100%; text-align: left; background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 14px 20px; font-size: 14px; font-weight: 600;
    color: var(--text); cursor: pointer; box-shadow: var(--shadow); box-sizing: border-box;
  }
  .hist-toggle:hover { background: #f8f9fb; }
  .historial-panel {
    background: var(--surface); border: 1px solid var(--border); border-top: none;
    border-radius: 0 0 var(--radius) var(--radius); padding: 20px 24px; box-shadow: var(--shadow);
  }
</style>
</head>
<body>

<div class="top">
  <span class="eyebrow">Consulta por placa</span>
  <h1>Consulta Vehicular</h1>
  <p class="subtitle">SAT Lima, Callao, SUTRAN, ATU, SOAT y Revision Tecnica (CITV) en un solo lugar</p>
  <div class="input-row">
    <input type="text" id="placa" placeholder="Ej: ABC123" maxlength="10" />
    <button id="btn" onclick="consultarTodo()">Consultar Todo</button>
  </div>
</div>

<div class="user-bar">
  <span>👤 <span id="user-email"></span></span>
  <span class="plan-badge" id="user-plan"></span>
  <button class="logout-btn" onclick="cerrarSesion()">Cerrar sesión</button>
</div>

<div class="grid">
  <div class="card">
    <div class="card-head">
      <span class="card-dot" id="dot-sunarp" style="background:#b91c1c"></span>
      <img class="card-logo" src="https://www.gob.pe/rails/active_storage/representations/redirect/eyJfcmFpbHMiOnsiZGF0YSI6NTQxMywicHVyIjoiYmxvYl9pZCJ9fQ==--2ef58cb7736fd93ded72b0b975789e3462ebbfa4/eyJfcmFpbHMiOnsiZGF0YSI6eyJmb3JtYXQiOiJwbmciLCJyZXNpemVfdG9fbGltaXQiOltudWxsLDQ4XX0sInB1ciI6InZhcmlhdGlvbiJ9fQ==--830247c4bafe7cadca50817d8559bf1a09e3aa28/sunarp.png" alt="" onload="document.getElementById('dot-sunarp').style.display='none'" onerror="this.style.display='none'">
      <h2>SUNARP (Datos del Vehiculo)</h2>
    </div>
    <div class="status idle" id="status-sunarp">Esperando consulta.</div>
    <div id="content-sunarp"></div>
  </div>

  <div class="card">
    <div class="card-head">
      <span class="card-dot" id="dot-satlima" style="background:#d97706"></span>
      <img class="card-logo" src="https://www.sat.gob.pe/PagosEnlinea/Images/Logo_PagosEnLinea.png" alt="" onload="document.getElementById('dot-satlima').style.display='none'" onerror="this.style.display='none'">
      <h2>SAT Lima (Impuesto y Papeletas)</h2>
    </div>
    <div class="status idle" id="status-satlima">Esperando consulta. El captcha se resuelve automaticamente (puede tardar ~30s).</div>
    <div id="content-satlima"></div>
  </div>

  <div class="card">
    <div class="card-head">
      <span class="card-dot" id="dot-callao" style="background:#2563eb"></span>
      <img class="card-logo" src="https://www.gob.pe/rails/active_storage/representations/redirect/eyJfcmFpbHMiOnsiZGF0YSI6NTc2NTksInB1ciI6ImJsb2JfaWQifX0=--9fbda8a1d7c51d06aafc98a16a604d008e74e5f0/eyJfcmFpbHMiOnsiZGF0YSI6eyJmb3JtYXQiOiJwbmciLCJyZXNpemVfdG9fbGltaXQiOltudWxsLDQ4XX0sInB1ciI6InZhcmlhdGlvbiJ9fQ==--830247c4bafe7cadca50817d8559bf1a09e3aa28/logo-municallao-usar.png" alt="" onload="document.getElementById('dot-callao').style.display='none'" onerror="this.style.display='none'">
      <h2>Callao (Papeletas)</h2>
    </div>
    <div class="status idle" id="status-callao">Esperando consulta.</div>
    <div id="content-callao"></div>
  </div>

  <div class="card">
    <div class="card-head">
      <span class="card-dot" id="dot-sutran" style="background:#0d9488"></span>
      <img class="card-logo" src="https://www.gob.pe/rails/active_storage/representations/redirect/eyJfcmFpbHMiOnsiZGF0YSI6MTI0MDYsInB1ciI6ImJsb2JfaWQifX0=--e322b64911c42e8e695fa74e96516cff327f7507/eyJfcmFpbHMiOnsiZGF0YSI6eyJmb3JtYXQiOiJwbmciLCJyZXNpemVfdG9fbGltaXQiOltudWxsLDQ4XX0sInB1ciI6InZhcmlhdGlvbiJ9fQ==--830247c4bafe7cadca50817d8559bf1a09e3aa28/logo_sutran20.png" alt="" onload="document.getElementById('dot-sutran').style.display='none'" onerror="this.style.display='none'">
      <h2>SUTRAN (Infracciones)</h2>
    </div>
    <div class="status idle" id="status-sutran">Esperando consulta.</div>
    <div id="content-sutran"></div>
  </div>

  <div class="card">
    <div class="card-head">
      <span class="card-dot" id="dot-atu" style="background:#7c3aed"></span>
      <img class="card-logo" src="https://www.gob.pe/rails/active_storage/representations/redirect/eyJfcmFpbHMiOnsiZGF0YSI6MTE4NzcsInB1ciI6ImJsb2JfaWQifX0=--9a9890747e1f4d8d601f164756815e9571fb3005/eyJfcmFpbHMiOnsiZGF0YSI6eyJmb3JtYXQiOiJwbmciLCJyZXNpemVfdG9fbGltaXQiOltudWxsLDQ4XX0sInB1ciI6InZhcmlhdGlvbiJ9fQ==--830247c4bafe7cadca50817d8559bf1a09e3aa28/Logo-Atu-.png" alt="" onload="document.getElementById('dot-atu').style.display='none'" onerror="this.style.display='none'">
      <h2>ATU (Infracciones)</h2>
    </div>
    <div class="status idle" id="status-atu">Esperando consulta.</div>
    <div id="content-atu"></div>
  </div>

  <div class="card">
    <div class="card-head">
      <span class="card-dot" id="dot-soat" style="background:#16a34a"></span>
      <img class="card-logo" src="https://www.apeseg.org.pe/wp-content/uploads/2025/03/image-7.png" alt="" onload="document.getElementById('dot-soat').style.display='none'" onerror="this.style.display='none'">
      <h2>SOAT (Vigencia)</h2>
    </div>
    <div class="status idle" id="status-soat">Esperando consulta.</div>
    <div id="content-soat"></div>
  </div>

  <div class="card">
    <div class="card-head"><span class="card-dot" style="background:#4f46e5"></span><h2>Revision Tecnica (CITV)</h2></div>
    <div class="status idle" id="status-revisiontecnica">Esperando consulta.</div>
    <div id="content-revisiontecnica"></div>
  </div>
</div>

<div class="historial-wrap">
  <button class="hist-toggle" onclick="toggleHistorial(this)">▼ &nbsp;Historial de consultas</button>
  <div class="historial-panel" id="historial-panel" style="display:none">
    <div id="historial-content"></div>
  </div>
</div>

<script>
// --- AUTH ---
function getToken() { return localStorage.getItem('cv_token'); }

function getPayload() {
  const t = getToken();
  if (!t) return null;
  try { return JSON.parse(atob(t.split('.')[1])); } catch { return null; }
}

(function checkAuth() {
  const p = getPayload();
  if (!p || p.exp * 1000 < Date.now()) {
    localStorage.removeItem('cv_token');
    window.location.href = '/login';
    return;
  }
  document.getElementById('user-email').textContent = p.email;
  const plan = localStorage.getItem('cv_plan') || '';
  if (plan) document.getElementById('user-plan').textContent = plan.toUpperCase();
})();

function cerrarSesion() {
  localStorage.removeItem('cv_token');
  localStorage.removeItem('cv_plan');
  window.location.href = '/login';
}

// --- HISTORIAL ---
async function toggleHistorial(btn) {
  const panel = document.getElementById('historial-panel');
  const abierto = panel.style.display !== 'none';
  panel.style.display = abierto ? 'none' : 'block';
  btn.textContent = (abierto ? '▼' : '▲') + '  Historial de consultas';
  if (!abierto) cargarHistorial();
}

async function cargarHistorial() {
  const cont = document.getElementById('historial-content');
  cont.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Cargando...</p>';
  try {
    const resp = await fetch('/historial', {headers: {'Authorization': 'Bearer ' + getToken()}});
    if (resp.status === 401) { cerrarSesion(); return; }
    const data = await resp.json();
    if (!data.length) {
      cont.innerHTML = '<p class="sin-deuda">Sin consultas registradas aún.</p>';
      return;
    }
    let html = '<table><thead><tr><th>Placa</th><th>Fuente</th><th>Fecha</th></tr></thead><tbody>';
    for (const r of data) {
      const fecha = new Date(r.fecha).toLocaleString('es-PE');
      html += '<tr><td><b>' + esc(r.placa) + '</b></td><td>' + esc(r.fuente) + '</td><td>' + fecha + '</td></tr>';
    }
    html += '</tbody></table>';
    cont.innerHTML = html;
  } catch(e) {
    cont.innerHTML = '<p class="sin-deuda">Error cargando historial.</p>';
  }
}

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function setEstado(fuente, clase, texto) {
  const el = document.getElementById('status-' + fuente);
  el.className = 'status ' + clase;
  el.innerHTML = clase === 'loading' ? '<span class="spinner"></span>' + texto : texto;
}

function tablaDeuda(items, campos, totalLabel, total) {
  if (!items.length) return '<p class="sin-deuda">Sin registros pendientes</p>';
  let html = '<table><thead><tr>';
  for (const c of campos) html += '<th>' + esc(c) + '</th>';
  html += '</tr></thead><tbody>';
  for (const it of items) {
    html += '<tr>';
    for (const c of campos) html += '<td>' + esc(it[c]) + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  if (total !== undefined) {
    html += '<p class="total-row">' + esc(totalLabel) + ': <span class="total-badge">S/ ' + esc(total) + '</span></p>';
  }
  return html;
}

const renderizar = {
  satlima(data) {
    const div = document.getElementById('content-satlima');
    const totalImp = data.impuesto_vehicular.total_web;
    const impHtml = (totalImp === '0.00')
      ? '<p class="sin-deuda">Sin deuda de impuesto vehicular</p>'
      : '<span class="total-badge">S/ ' + esc(totalImp) + '</span>';
    const pap = data.papeletas;
    const papHtml = tablaDeuda(pap.items, ['Falta', 'Fecha', 'Monto'], 'Total oficial', pap.total_web);
    div.innerHTML = '<p><b>Impuesto Vehicular:</b></p>' + impHtml +
                    '<p style="margin-top:14px"><b>Papeletas:</b></p>' + papHtml;
  },

  callao(data) {
    const div = document.getElementById('content-callao');
    if (data.sin_resultados) {
      div.innerHTML = '<p class="sin-deuda">Sin papeletas pendientes</p>';
      return;
    }
    div.innerHTML = tablaDeuda(data.items, ['Codigo', 'Fecha', 'Total'], 'Total oficial', data.suma_calculada);
  },

  sutran(data) {
    const div = document.getElementById('content-sutran');
    if (data.sin_resultados) {
      div.innerHTML = '<p class="sin-deuda">No se encontraron infracciones</p>';
      return;
    }
    div.innerHTML = tablaDeuda(data.items, ['Numero de documento', 'Fecha', 'Clasificacion']);
  },

  atu(data) {
    const div = document.getElementById('content-atu');
    if (data.sin_resultados) {
      div.innerHTML = '<p class="sin-deuda">Sin infracciones registradas</p>';
      return;
    }
    div.innerHTML = tablaDeuda(data.items, ['Codigo', 'Fecha', 'Total'], 'Total oficial', data.suma_calculada);
  },

  soat(data) {
    const div = document.getElementById('content-soat');
    if (data.sin_resultados) {
      div.innerHTML = '<p class="sin-deuda">Sin informacion de SOAT para esta placa</p>';
      return;
    }
    const clase = data.vigente ? 'vigente' : 'no-vigente';
    const etiqueta = data.vigente ? 'VIGENTE' : 'NO VIGENTE';
    div.innerHTML = '<div class="ficha">' +
      '<div><b>Estado:</b> ' + esc(data.estado) + ' (<span class="' + clase + '">' + etiqueta + '</span>)</div>' +
      '<div><b>Inicio:</b> ' + esc(data.inicio) + '</div>' +
      '<div><b>Fin:</b> ' + esc(data.fin) + '</div>' +
      '</div>';
  },

  sunarp(data) {
    const div = document.getElementById('content-sunarp');
    if (data.sin_resultados) {
      div.innerHTML = '<p class="sin-deuda">Sin informacion de SUNARP para esta placa</p>';
      return;
    }
    let html = '';
    if (data.alerta_robo) {
      html += '<div class="status error" style="margin-bottom:12px">⚠ ' + esc(data.alerta_robo) + '</div>';
    }
    if (data.imagen_b64) {
      html += '<img src="data:image/png;base64,' + data.imagen_b64 + '" style="width:100%;border-radius:8px;border:1px solid var(--border)">';
    }
    div.innerHTML = html;
  },

  revisiontecnica(data) {
    const div = document.getElementById('content-revisiontecnica');
    const u = data.ultimo;
    if (data.sin_resultados || !u) {
      div.innerHTML = '<p class="sin-deuda">Sin informacion de revision tecnica para esta placa</p>';
      return;
    }
    let html = '<div class="ficha">' +
      '<div><b>Certificado:</b> ' + esc(u.NRO_CERTI) + '</div>' +
      '<div><b>Inicio:</b> ' + esc(u.REVISIONVIGENCIAINICIO) + '</div>' +
      '<div><b>Fin:</b> ' + esc(u.REVISIONVIGENCIAFINAL) + '</div>' +
      '<div><b>Resultado:</b> ' + esc(u.RESULTADO) + '</div>';
    if (u.ESTADO) html += '<div><b>Estado:</b> ' + esc(u.ESTADO) + '</div>';
    if (u.OBSERVACION) html += '<div><b>Observacion:</b> ' + esc(u.OBSERVACION) + '</div>';
    html += '</div>';
    div.innerHTML = html;
  },
};

async function consultarFuente(fuente, placa) {
  setEstado(fuente, 'loading', 'Consultando...');
  document.getElementById('content-' + fuente).innerHTML = '';
  try {
    const resp = await fetch('/consultar/' + fuente, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + getToken()},
      body: JSON.stringify({placa})
    });
    if (resp.status === 401) { cerrarSesion(); return; }
    const data = await resp.json();
    if (!resp.ok) {
      setEstado(fuente, 'error', 'Error: ' + (data.detail || 'No se pudo consultar'));
      return;
    }
    renderizar[fuente](data);
    setEstado(fuente, 'ok', 'Consulta completada');
  } catch (e) {
    setEstado(fuente, 'error', 'Error de conexion: ' + e.message);
  }
}

function consultarTodo() {
  const placa = document.getElementById('placa').value.trim().toUpperCase();
  if (!placa) { alert('Ingresa una placa'); return; }

  const btn = document.getElementById('btn');
  btn.disabled = true;

  const fuentes = ['sunarp', 'satlima', 'callao', 'sutran', 'atu', 'soat', 'revisiontecnica'];
  Promise.allSettled(fuentes.map(f => consultarFuente(f, placa))).finally(() => {
    btn.disabled = false;
  });
}

document.getElementById('placa').addEventListener('keydown', e => {
  if (e.key === 'Enter') consultarTodo();
});
</script>
</body>
</html>"""


class PlacaRequest(BaseModel):
    placa: str


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


def usuario_actual(request: Request) -> dict:
    """Valida el JWT contra el servidor remoto."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        r = _req.get(f"{_SERVER}/auth/validate", headers={"Authorization": header}, timeout=8)
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
        return r.json()
    except _req.RequestException:
        raise HTTPException(status_code=503, detail="No se pudo conectar al servidor de autenticación")


async def _guardar_bg(token: str, placa: str, fuente: str, resultado: dict):
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, lambda: _req.post(
            f"{_SERVER}/historial/guardar",
            json={"placa": placa, "fuente": fuente, "resultado": resultado},
            headers={"Authorization": f"Bearer {token}"},
            timeout=8,
        ))
    except Exception:
        pass


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return LOGIN_HTML


def _proxy(method: str, path: str, request: Request, body=None):
    """Reenvía una petición al servidor remoto conservando headers relevantes."""
    headers = {}
    if "Authorization" in request.headers:
        headers["Authorization"] = request.headers["Authorization"]
    if "X-Admin-Key" in request.headers:
        headers["X-Admin-Key"] = request.headers["X-Admin-Key"]
    try:
        r = _req.request(method, f"{_SERVER}{path}", json=body, headers=headers, timeout=10)
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except _req.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Servidor no disponible: {e}")


@app.post("/auth/login")
async def auth_login(req: LoginRequest, request: Request):
    return _proxy("POST", "/auth/login", request, req.model_dump())


@app.get("/registro", response_class=HTMLResponse)
def registro_page():
    return REGISTRO_HTML


@app.post("/auth/registro")
async def auth_registro(req: RegistroRequest, request: Request):
    return _proxy("POST", "/auth/registro", request, req.model_dump())


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return ADMIN_HTML


@app.get("/admin/usuarios")
async def admin_usuarios(request: Request):
    return _proxy("GET", "/admin/usuarios", request)


@app.post("/admin/activar")
async def admin_activar(req: ActivarRequest, request: Request):
    return _proxy("POST", "/admin/activar", request, req.model_dump())


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.get("/historial")
async def historial_ep(request: Request, usuario: dict = Depends(usuario_actual)):
    return _proxy("GET", "/historial", request)


def _token_de(request: Request) -> str:
    return request.headers.get("Authorization", "Bearer ")[7:]


@app.post("/consultar/satlima")
async def consultar_satlima_ep(req: PlacaRequest, request: Request, _: dict = Depends(usuario_actual)):
    resultado = await ejecutar(consultar_satlima, req.placa)
    asyncio.create_task(_guardar_bg(_token_de(request), req.placa, "satlima", resultado))
    return resultado


@app.post("/consultar/callao")
async def consultar_callao_ep(req: PlacaRequest, request: Request, _: dict = Depends(usuario_actual)):
    resultado = await ejecutar(consultar_callao, req.placa)
    asyncio.create_task(_guardar_bg(_token_de(request), req.placa, "callao", resultado))
    return resultado


@app.post("/consultar/sutran")
async def consultar_sutran_ep(req: PlacaRequest, request: Request, _: dict = Depends(usuario_actual)):
    resultado = await ejecutar(consultar_sutran, req.placa)
    asyncio.create_task(_guardar_bg(_token_de(request), req.placa, "sutran", resultado))
    return resultado


@app.post("/consultar/atu")
async def consultar_atu_ep(req: PlacaRequest, request: Request, _: dict = Depends(usuario_actual)):
    resultado = await ejecutar(consultar_atu, req.placa)
    asyncio.create_task(_guardar_bg(_token_de(request), req.placa, "atu", resultado))
    return resultado


@app.post("/consultar/soat")
async def consultar_soat_ep(req: PlacaRequest, request: Request, _: dict = Depends(usuario_actual)):
    resultado = await ejecutar(consultar_soat, req.placa)
    asyncio.create_task(_guardar_bg(_token_de(request), req.placa, "soat", resultado))
    return resultado


@app.post("/consultar/sunarp")
async def consultar_sunarp_ep(req: PlacaRequest, request: Request, _: dict = Depends(usuario_actual)):
    resultado = await ejecutar(consultar_sunarp, req.placa)
    asyncio.create_task(_guardar_bg(_token_de(request), req.placa, "sunarp", resultado))
    return resultado


@app.post("/consultar/revisiontecnica")
async def consultar_revisiontecnica_ep(req: PlacaRequest, request: Request, _: dict = Depends(usuario_actual)):
    try:
        loop = asyncio.get_event_loop()
        registros = await loop.run_in_executor(executor, lambda: consultar_revisiontecnica(req.placa))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar: {e}")

    ultimo = registros[0] if registros else None
    resultado = {"ultimo": ultimo, "sin_resultados": not registros}
    asyncio.create_task(_guardar_bg(_token_de(request), req.placa, "revisiontecnica", resultado))
    return resultado
