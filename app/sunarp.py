#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consulta de datos vehiculares por PLACA en SUNARP.

El backend de SUNARP (API directa, sin scraping de HTML) exige un token
Cloudflare Turnstile. Ese Turnstile no se auto-resuelve en un navegador
automatizado (probado con Playwright y patchright, headless y visible), asi
que lo resolvemos con 2captcha: la key va en TWOCAPTCHA_API_KEY (.env).

La respuesta trae los datos del vehiculo como una imagen PNG (base64), no
como campos de texto, mas una posible alerta de robo.
"""

import re
import warnings

import requests
import urllib3

from .captcha import resolver_turnstile

warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SITEKEY    = "0x4AAAAAACFzt4Xn8T1Jg9ZS"
PAGE_URL   = "https://consultavehicular.sunarp.gob.pe/consulta-vehicular/inicio"
API_BASE   = "https://api-gateway.sunarp.gob.pe:9443/sunarp/multiservicios"
API_ID     = "70574c7d9194834316a156b1d68fdb90"
ENDPOINT   = f"{API_BASE}/multiservicio-consvehicular/consulta/getDatosVehiculo"

HEADERS = {
    "X-IBM-Client-Id": API_ID,
    "Content-Type": "application/json",
}


def normalizar_placa(placa: str) -> str:
    return re.sub(r"[\s\-]", "", placa).upper()


def _llamar_api(placa: str, token: str) -> dict | None:
    """
    Llama al endpoint de SUNARP con el token de Turnstile.
    Devuelve el dict de la respuesta, o None si hubo error HTTP.
    """
    try:
        r = requests.post(
            ENDPOINT,
            headers=HEADERS,
            json={
                "numPlaca":   placa,
                "regPubId":   None,
                "oficRegId":  None,
                "ipAddress":  "0.0.0.0",
                "appVersion": "1.0",
                "dG9rZW4":    token,
            },
            timeout=30,
            verify=False,
        )
        r.raise_for_status()
        return r.json()
    except requests.HTTPError:
        return None


# ── Función principal ─────────────────────────────────────────────────────────

def _parsear_respuesta(data: dict) -> dict:
    if data.get("cod") != 1:
        return {"sin_resultados": True}

    modelo = data.get("model") or {}
    imagen_b64 = modelo.get("imagen")
    if not imagen_b64:
        return {"sin_resultados": True}

    # SUNARP devuelve los datos del vehiculo renderizados en una imagen PNG,
    # no como campos estructurados. Tambien puede traer una alerta de robo.
    return {
        "sin_resultados": False,
        "imagen_b64": imagen_b64,
        "alerta_robo": modelo.get("msgAlertaRobo") or "",
    }


def consultar(placa: str) -> dict:
    placa = normalizar_placa(placa)
    if not placa:
        raise ValueError("La placa esta vacia.")

    # El Turnstile de SUNARP no se auto-resuelve en un navegador automatizado
    # (ni headless ni visible), asi que resolvemos directamente con 2captcha.
    print("  -> [SUNARP] Resolviendo Turnstile con 2captcha...")
    token = resolver_turnstile(SITEKEY, PAGE_URL)
    data = _llamar_api(placa, token)
    if data:
        return _parsear_respuesta(data)

    return {"sin_resultados": True}


def main():
    import argparse
    import base64
    import json
    import sys

    parser = argparse.ArgumentParser(description="Consulta Vehicular SUNARP")
    parser.add_argument("placa")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        resultado = consultar(args.placa)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if resultado.get("sin_resultados"):
        print("Sin informacion para esta placa.")
        sys.exit(0)

    if args.json:
        copia = {k: v for k, v in resultado.items() if k != "imagen_b64"}
        print(json.dumps(copia, ensure_ascii=False, indent=2))
    else:
        print(f"\n===== SUNARP - PLACA {normalizar_placa(args.placa)} =====")
        if resultado.get("alerta_robo"):
            print(f"  ALERTA: {resultado['alerta_robo']}")

        if resultado.get("imagen_b64"):
            fname = f"sunarp_{normalizar_placa(args.placa)}.png"
            with open(fname, "wb") as f:
                f.write(base64.b64decode(resultado["imagen_b64"]))
            print(f"  Imagen con los datos guardada en: {fname}")
        print("========================================\n")


if __name__ == "__main__":
    main()
