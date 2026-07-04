import json
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

_URL = os.getenv("NEON_DATABASE_URL")


def get_connection():
    return psycopg2.connect(_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def buscar_usuario(email: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, password_hash, nombre, activo FROM usuarios WHERE email = %s",
                (email,),
            )
            return cur.fetchone()


def obtener_suscripcion_activa(usuario_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.id, s.fin, s.consultas_usadas, p.nombre AS plan, p.limite_consultas
                FROM suscripciones s
                JOIN planes p ON p.id = s.plan_id
                WHERE s.usuario_id = %s AND s.fin > NOW()
                ORDER BY s.fin DESC LIMIT 1
                """,
                (usuario_id,),
            )
            return cur.fetchone()


def guardar_consulta(usuario_id: int, placa: str, fuente: str, resultado: dict):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO consultas (usuario_id, placa, fuente, resultado_json) VALUES (%s, %s, %s, %s)",
                (usuario_id, placa.upper(), fuente, json.dumps(resultado, ensure_ascii=False)),
            )
        conn.commit()


def crear_usuario(email: str, password_hash: str, nombre: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usuarios (email, password_hash, nombre, activo) VALUES (%s, %s, %s, FALSE) RETURNING id",
                (email, password_hash, nombre),
            )
            row = cur.fetchone()
        conn.commit()
    return row["id"]


def email_existe(email: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM usuarios WHERE email = %s", (email,))
            return cur.fetchone() is not None


def listar_usuarios():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.email, u.nombre, u.activo, u.fecha_registro,
                       s.fin AS suscripcion_fin, p.nombre AS plan
                FROM usuarios u
                LEFT JOIN suscripciones s ON s.usuario_id = u.id AND s.fin > NOW()
                LEFT JOIN planes p ON p.id = s.plan_id
                ORDER BY u.fecha_registro DESC
                """
            )
            return [dict(r) for r in cur.fetchall()]


def activar_usuario(usuario_id: int, plan_id: int, dias: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET activo = TRUE WHERE id = %s", (usuario_id,))
            cur.execute(
                """
                INSERT INTO suscripciones (usuario_id, plan_id, inicio, fin)
                VALUES (%s, %s, NOW(), NOW() + INTERVAL '1 day' * %s)
                ON CONFLICT DO NOTHING
                """,
                (usuario_id, plan_id, dias),
            )
        conn.commit()


def listar_planes():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, nombre, limite_consultas FROM planes ORDER BY id")
            return [dict(r) for r in cur.fetchall()]


def obtener_historial(usuario_id: int, limit: int = 50):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT placa, fuente, fecha, resultado_json
                FROM consultas
                WHERE usuario_id = %s
                ORDER BY fecha DESC
                LIMIT %s
                """,
                (usuario_id, limit),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]
