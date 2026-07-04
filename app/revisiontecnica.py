#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consulta de Certificados de Inspeccion Tecnica Vehicular (CITV) por PLACA en el MTC.
Tiene captcha de 6 digitos, resuelto con pytesseract.
"""

import argparse
import base64
import json
import platform
import re
import sys
import os
import urllib.parse

import cv2
import numpy as np
import pytesseract
from playwright.sync_api import sync_playwright

from .navegador import crear_pagina

URL_PAGINA = "https://rec.mtc.gob.pe/Citv/ArConsultaCitv"

if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def normalizar_placa(placa: str) -> str:
    return re.sub(r"[\s\-]", "", placa).upper()


def _fetch_captcha_raw(page):
    return page.evaluate("""
        async () => {
            try {
                const r = await fetch('/CITV/refrescarCaptcha');
                const t = await r.text();
                return {status: r.status, body: t};
            } catch(e) {
                return {status: -1, body: String(e)};
            }
        }
    """)


def resolver_captcha(page, diagnostico=False):
    res = _fetch_captcha_raw(page)
    status = res.get("status") if isinstance(res, dict) else None
    body = (res.get("body") if isinstance(res, dict) else "") or ""

    if status != 200:
        if diagnostico:
            print(f"  [RT] captcha status={status} body[:150]={body[:150]!r}", flush=True)
        return ""

    try:
        b64 = (json.loads(body) or {}).get("orResult")
    except Exception:
        if diagnostico:
            print(f"  [RT] captcha respuesta no-JSON body[:150]={body[:150]!r}", flush=True)
        return ""

    if not b64:
        if diagnostico:
            print(f"  [RT] captcha orResult vacio", flush=True)
        return ""

    raw = base64.b64decode(b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return ""
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    config = "--psm 8 -c tessedit_char_whitelist=0123456789"
    texto = pytesseract.image_to_string(binary, config=config).strip().replace(" ", "").replace("\n", "")
    return texto


def buscar(page, placa, captcha):
    params = urllib.parse.urlencode({"pArrParametros": f"1|{placa}||{captcha}"})
    return page.evaluate(f"""
        async () => {{
            try {{
                const r = await fetch('/CITV/JrCITVConsultarFiltro?{params}');
                if (!r.ok) return null;
                return await r.json();
            }} catch(e) {{
                return null;
            }}
        }}
    """)


def consultar(placa: str, max_intentos: int = 15):
    placa = normalizar_placa(placa)
    if not placa:
        raise ValueError("La placa esta vacia.")

    with sync_playwright() as p:
        browser, page = crear_pagina(p, headless=True)
        try:
            page.goto(URL_PAGINA, wait_until="domcontentloaded", timeout=30000)

            titulo0 = page.title()
            print(f"  [RT] pagina cargada title={titulo0[:60]!r}", flush=True)

            if "attention required" in titulo0.lower():
                raise RuntimeError(
                    "El MTC esta bloqueando las consultas de revision tecnica desde "
                    "este servidor (Cloudflare)."
                )

            # Esperar a que Cloudflare pase su challenge JS (~12s max)
            cf_ok = False
            for i in range(12):
                res = _fetch_captcha_raw(page)
                if res.get("status") == 200:
                    cf_ok = True
                    print(f"  [RT] Cloudflare paso tras ~{i}s", flush=True)
                    break
                page.wait_for_timeout(1000)

            if not cf_ok:
                titulo = page.title()
                print(f"  [RT] Cloudflare NO paso, title={titulo[:60]!r}", flush=True)
                raise RuntimeError(
                    "Cloudflare bloqueo la consulta de revision tecnica. "
                    "Intenta nuevamente en unos segundos."
                )

            for intento in range(max_intentos):
                texto = resolver_captcha(page, diagnostico=(intento < 3))
                if len(texto) != 6:
                    page.wait_for_timeout(1000)
                    continue

                data = buscar(page, placa, texto)
                if intento < 3:
                    print(f"  [RT] intento {intento} captcha='{texto}' -> "
                          f"data={'None' if data is None else str(data)[:150]!r}", flush=True)

                if data is None or data.get("orCodigo") == "-1":
                    page.wait_for_timeout(1000)
                    continue

                if not data.get("orStatus"):
                    raise RuntimeError("Ocurrio un error al consultar el servicio del MTC.")

                resultado = data.get("orResult") or []
                if not resultado:
                    return {"sin_resultados": True}

                parsed = json.loads(resultado[0])
                if not parsed:
                    return {"sin_resultados": True}
                return parsed

            raise RuntimeError("No se pudo resolver el captcha del MTC tras varios intentos.")
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="Consulta de CITV (revision tecnica) por placa - MTC")
    parser.add_argument("placa", help="Placa a consultar (ej: ABC123)")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    args = parser.parse_args()

    try:
        resultado = consultar(args.placa)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)

    if isinstance(resultado, dict) and resultado.get("sin_resultados"):
        if args.json:
            print(json.dumps({"sin_resultados": True}, ensure_ascii=False))
        else:
            placa_norm = normalizar_placa(args.placa)
            print(f"\n===== REVISION TECNICA (CITV) PARA LA PLACA {placa_norm} =====")
            print("  No se encontro informacion de revision tecnica para esta placa.")
            print("===================================================\n")
        sys.stdout.flush()
        os._exit(0)

    registros = resultado if isinstance(resultado, list) else [resultado]
    ultimo = registros[0] if registros else {}

    if args.json:
        print(json.dumps(ultimo, ensure_ascii=False, indent=2))
        sys.stdout.flush()
        os._exit(0)

    placa_norm = normalizar_placa(args.placa)
    print(f"\n===== REVISION TECNICA (CITV) PARA LA PLACA {placa_norm} =====")
    if not ultimo:
        print("  No se encontro informacion de revision tecnica para esta placa.")
    else:
        print(f"  Certificado : {ultimo.get('NRO_CERTI', '')}")
        print(f"  Inicio      : {ultimo.get('REVISIONVIGENCIAINICIO', '')}")
        print(f"  Fin         : {ultimo.get('REVISIONVIGENCIAFINAL', '')}")
        print(f"  Resultado   : {ultimo.get('RESULTADO', '')}")
        estado = ultimo.get("ESTADO", "")
        if estado:
            print(f"  Estado      : {estado}")
        obs = ultimo.get("OBSERVACION", "")
        if obs:
            print(f"  Observacion : {obs}")
    print("===================================================\n")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
