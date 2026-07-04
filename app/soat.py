#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consulta de vigencia de SOAT por PLACA en APESEG.
Tiene captcha de 6 caracteres alfanumericos, resuelto con easyocr.
"""

import argparse
import base64
import json
import re
import sys
import os

import cv2
import numpy as np
import easyocr
from playwright.sync_api import sync_playwright

from .navegador import crear_pagina

URL = "https://www.apeseg.org.pe/consultas-soat/"
IFRAME_SELECTOR = "iframe[src*='consulta-soat']"

_reader = None


def normalizar_placa(placa: str) -> str:
    return re.sub(r"[\s\-]", "", placa).upper()


def obtener_reader():
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _reader


def resolver_captcha(frame):
    img_el = frame.wait_for_selector("img.captcha-img", timeout=15000)
    src = img_el.get_attribute("src")
    b64 = src.split(",", 1)[1]
    data = base64.b64decode(b64)
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    reader = obtener_reader()
    resultados = reader.readtext(binary, detail=0, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
    texto = "".join(resultados).strip().replace(" ", "").replace("\n", "")
    return texto


def ir_al_formulario(page):
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    iframe_el = page.wait_for_selector(IFRAME_SELECTOR, timeout=15000)
    frame = iframe_el.content_frame()
    page.wait_for_timeout(2000)
    return frame


def extraer_resultados(frame):
    resultados = {
        "estado": "",
        "vigente": False,
        "inicio": "",
        "fin": "",
        "sin_resultados": False,
    }

    tabla = frame.query_selector(".resultados .tabla")
    if not tabla:
        resultados["sin_resultados"] = True
        return resultados

    datos = {}
    for fila in tabla.query_selector_all("tr"):
        th = fila.query_selector("th")
        td = fila.query_selector("td")
        if not th or not td:
            continue
        clave = th.inner_text().strip()
        datos[clave] = td.inner_text().strip()
        if clave == "Estado":
            span = td.query_selector("span")
            if span:
                clases = span.get_attribute("class") or ""
                resultados["vigente"] = "no-vigente" not in clases

    resultados["estado"] = datos.get("Estado", "")
    resultados["inicio"] = datos.get("Inicio", "")
    resultados["fin"] = datos.get("Fin", "")

    if not resultados["estado"]:
        resultados["sin_resultados"] = True

    return resultados


def consultar(placa: str, headless: bool = True, max_intentos: int = 25):
    placa = normalizar_placa(placa)
    if not placa:
        raise ValueError("La placa esta vacia.")

    with sync_playwright() as p:
        browser, page = crear_pagina(p, headless=headless)
        try:
            frame = ir_al_formulario(page)

            frame.fill("#placa", placa)

            for _ in range(max_intentos):
                texto = resolver_captcha(frame)
                if len(texto) != 6:
                    frame.click("img.captcha-img")
                    page.wait_for_timeout(1500)
                    continue

                frame.fill("#captcha", texto)
                frame.click("button[type=submit]")
                page.wait_for_timeout(2500)

                if frame.query_selector(".form-error"):
                    continue

                return extraer_resultados(frame)

            raise RuntimeError("No se pudo resolver el captcha tras varios intentos.")
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="Consulta de vigencia de SOAT por placa - APESEG")
    parser.add_argument("placa", help="Placa a consultar (ej: ABC123)")
    parser.add_argument("--ver-navegador", action="store_true", help="Mostrar la ventana de Chrome")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    args = parser.parse_args()

    headless = not args.ver_navegador

    try:
        resultados = consultar(args.placa, headless=headless)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)

    if args.json:
        print(json.dumps(resultados, ensure_ascii=False, indent=2))
        sys.stdout.flush()
        os._exit(0)

    print(f"\n===== SOAT PARA LA PLACA {normalizar_placa(args.placa)} =====")
    if resultados["sin_resultados"]:
        print("  No se encontro informacion de SOAT para esta placa.")
    else:
        print(f"  Estado : {resultados['estado']} ({'VIGENTE' if resultados['vigente'] else 'NO VIGENTE'})")
        print(f"  Inicio : {resultados['inicio']}")
        print(f"  Fin    : {resultados['fin']}")
    print("===================================================\n")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
