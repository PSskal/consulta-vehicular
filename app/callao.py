#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consulta de papeletas por PLACA en la Municipalidad del Callao.
Resuelve el captcha de 3 digitos con OCR (aislando el texto azul del
fondo con ruido y leyendo cada captcha en un canvas limpio).
"""

import argparse
import base64
import json
import platform
import re
import sys
import os
from urllib.parse import urlparse, parse_qs

import cv2
import numpy as np
import pytesseract
from playwright.sync_api import sync_playwright

from .navegador import crear_pagina

URL = "https://pagopapeletascallao.pe/"

INPUT_PLACA_ID = "valor_busqueda"
INPUT_CAPTCHA_ID = "captcha"
BOTON_BUSCAR_ID = "idBuscar"

MAX_INTENTOS_CAPTCHA = 6

if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def normalizar_placa(placa: str) -> str:
    return re.sub(r"[\s\-]", "", placa).upper()


def _leer_captcha_b64(page) -> str:
    img_el = page.wait_for_selector('img[alt="captcha"]', timeout=15000)
    src = img_el.get_attribute("src")
    return src.split(",", 1)[1]


def resolver_captcha(page):
    """Decodifica el captcha (3 digitos azules sobre fondo con ruido) y lo lee con OCR."""
    png_bytes = base64.b64decode(_leer_captcha_b64(page))
    arr = np.frombuffer(png_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    b, g, r = cv2.split(img)
    azul = cv2.subtract(b, cv2.max(r, g))
    _, binaria = cv2.threshold(azul, 35, 255, cv2.THRESH_BINARY)

    contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cajas = [cv2.boundingRect(c) for c in contornos if cv2.boundingRect(c)[2] * cv2.boundingRect(c)[3] >= 15]
    cajas.sort(key=lambda c: c[0])

    if len(cajas) != 3:
        return None

    escala = 6
    pad = 20
    alto_max = max(h for (_, _, _, h) in cajas) * escala
    ancho_total = sum(w for (_, _, w, _) in cajas) * escala + pad * (len(cajas) + 1)
    canvas = np.zeros((alto_max + pad * 2, ancho_total), dtype=np.uint8)

    x_cursor = pad
    for (x, y, w, h) in cajas:
        recorte = binaria[y:y + h, x:x + w]
        recorte = cv2.resize(recorte, (w * escala, h * escala), interpolation=cv2.INTER_CUBIC)
        canvas[pad:pad + h * escala, x_cursor:x_cursor + w * escala] = recorte
        x_cursor += w * escala + pad

    canvas_inv = cv2.bitwise_not(canvas)
    config = "--psm 8 -c tessedit_char_whitelist=0123456789"
    texto = pytesseract.image_to_string(canvas_inv, config=config)
    digitos = "".join(ch for ch in texto if ch.isdigit())

    return digitos if len(digitos) == 3 else None


def extraer_resultados(page):
    resultados = {
        "total_web": "0.00",
        "items": [],
        "suma_calculada": "0.00",
        "sin_resultados": False,
    }

    total_el = page.query_selector("#suma-valores")
    if total_el:
        numeros = re.findall(r"\d[\d,]*\.\d+", total_el.inner_text())
        if numeros:
            resultados["total_web"] = numeros[0]

    if page.query_selector(".table-responsive .alert-info"):
        resultados["sin_resultados"] = True
        return resultados

    tabla = page.query_selector("#dataTable")
    if tabla:
        headers = [th.inner_text().strip().lower() for th in tabla.query_selector_all("thead th")]

        idx_codigo = next((i for i, h in enumerate(headers) if "digo" in h), None)
        idx_fecha = next((i for i, h in enumerate(headers) if "fecha" in h), None)
        idx_total = next((i for i, h in enumerate(headers) if h == "total"), None)

        suma = 0.0
        for fila in tabla.query_selector_all("tbody tr"):
            celdas = [td.inner_text().strip() for td in fila.query_selector_all("td")]
            if not celdas:
                continue

            codigo = celdas[idx_codigo] if idx_codigo is not None and idx_codigo < len(celdas) else ""
            fecha = celdas[idx_fecha] if idx_fecha is not None and idx_fecha < len(celdas) else ""
            total_raw = celdas[idx_total] if idx_total is not None and idx_total < len(celdas) else ""

            match_total = re.search(r"\d[\d,]*\.\d+", total_raw)
            total = match_total.group(0) if match_total else "0.00"

            resultados["items"].append({"Codigo": codigo, "Fecha": fecha, "Total": total})

            try:
                suma += float(total.replace(",", ""))
            except ValueError:
                pass

        resultados["suma_calculada"] = f"{suma:,.2f}"

    return resultados


def consultar(placa: str, headless: bool = True, max_intentos: int = MAX_INTENTOS_CAPTCHA):
    placa = normalizar_placa(placa)
    if not placa:
        raise ValueError("La placa esta vacia.")

    with sync_playwright() as p:
        browser, page = crear_pagina(p, headless=headless)
        try:
            for intento in range(1, max_intentos + 1):
                page.goto(URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                codigo = resolver_captcha(page)
                if not codigo:
                    print(f"  -> [Intento {intento}] No se pudo leer el captcha, reintentando...")
                    continue

                page.fill(f"#{INPUT_PLACA_ID}", placa)
                page.fill(f"#{INPUT_CAPTCHA_ID}", codigo)
                page.click(f"#{BOTON_BUSCAR_ID}")
                page.wait_for_timeout(3000)

                qs = parse_qs(urlparse(page.url).query)
                if "error" in qs:
                    print(f"  -> [Intento {intento}] Captcha '{codigo}' incorrecto, reintentando...")
                    continue

                print(f"  -> Captcha resuelto en el intento {intento} ('{codigo}').")
                return extraer_resultados(page)

            raise RuntimeError(f"No se pudo resolver el captcha tras {max_intentos} intentos.")
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="Consulta de papeletas por placa - Municipalidad del Callao")
    parser.add_argument("placa", help="Placa a consultar (ej: ABC123)")
    parser.add_argument("--ver-navegador", action="store_true", help="Mostrar la ventana de Chrome")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    args = parser.parse_args()

    try:
        resultados = consultar(args.placa, headless=not args.ver_navegador)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        os._exit(1)

    if args.json:
        print(json.dumps(resultados, ensure_ascii=False, indent=2))
        os._exit(0)

    print(f"\n===== RESULTADOS PARA LA PLACA {normalizar_placa(args.placa)} =====")
    if resultados["sin_resultados"] or not resultados["items"]:
        print("  No hay papeletas registradas para esta placa.")
    else:
        for i, item in enumerate(resultados["items"], 1):
            print(f"  --- Papeleta {i} ---")
            print(f"  Codigo: {item['Codigo']}")
            print(f"  Fecha : {item['Fecha']}")
            print(f"  Total : S/ {item['Total']}")
        print(f"\n  -> Suma de papeletas: S/ {resultados['suma_calculada']}")
    print("===================================================\n")
    os._exit(0)


if __name__ == "__main__":
    main()
