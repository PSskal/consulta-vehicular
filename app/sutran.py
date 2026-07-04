#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consulta de record de infracciones por PLACA en SUTRAN.

El captcha de esta web (4 letras) se genera a partir del parametro
"numAleatorio" en la URL de la imagen (iframe#iimage) y ese mismo valor
es la respuesta correcta. No requiere OCR.
"""

import argparse
import json
import re
import sys
import os

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from .navegador import crear_pagina

URL = "https://webexterno.sutran.gob.pe/WebExterno/Pages/frmRecordInfracciones.aspx"

INPUT_PLACA_ID = "txtPlaca"
INPUT_CAPTCHA_ID = "TxtCodImagen"
BOTON_BUSCAR_ID = "BtnBuscar"
CAPTCHA_IFRAME_ID = "iimage"

MAX_INTENTOS = 4


def normalizar_placa(placa: str) -> str:
    return re.sub(r"[\s\-]", "", placa).upper()


def obtener_codigo_captcha(page) -> str:
    iframe = page.wait_for_selector(f"#{CAPTCHA_IFRAME_ID}", timeout=15000)
    src = iframe.get_attribute("src")
    match = re.search(r"numAleatorio=([A-Za-z0-9]+)", src or "")
    return match.group(1).upper() if match else None


def extraer_resultados(page):
    resultados = {"items": [], "sin_resultados": False}

    mensaje_el = page.query_selector("#LblMensaje")
    if mensaje_el:
        mensaje = mensaje_el.inner_text().strip()
        if "no se encontraron" in mensaje.lower():
            resultados["sin_resultados"] = True
            return resultados

    tabla = page.query_selector("#gvDeudas")
    if tabla:
        headers = [th.inner_text().strip().lower() for th in tabla.query_selector_all("th")]

        idx_numero = next((i for i, h in enumerate(headers) if "mero" in h), None)
        idx_fecha = next((i for i, h in enumerate(headers) if "fecha" in h), None)
        idx_clasif = next((i for i, h in enumerate(headers) if "clasifica" in h), None)

        for fila in tabla.query_selector_all("tr"):
            celdas = [td.inner_text().strip() for td in fila.query_selector_all("td")]
            if not celdas or not any(celdas):
                continue

            numero = celdas[idx_numero] if idx_numero is not None and idx_numero < len(celdas) else ""
            fecha = celdas[idx_fecha] if idx_fecha is not None and idx_fecha < len(celdas) else ""
            clasificacion = celdas[idx_clasif] if idx_clasif is not None and idx_clasif < len(celdas) else ""

            if not numero and not fecha and not clasificacion:
                continue

            resultados["items"].append({
                "Numero de documento": numero,
                "Fecha": fecha,
                "Clasificacion": clasificacion,
            })

    if not resultados["items"]:
        resultados["sin_resultados"] = True

    return resultados


def consultar(placa: str, headless: bool = True, max_intentos: int = MAX_INTENTOS):
    placa = normalizar_placa(placa)
    if not placa:
        raise ValueError("La placa esta vacia.")

    with sync_playwright() as p:
        browser, page = crear_pagina(p, headless=headless)
        try:
            for intento in range(1, max_intentos + 1):
                page.goto(URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                codigo = obtener_codigo_captcha(page)
                if not codigo:
                    print(f"  -> [Intento {intento}] No se pudo leer el captcha, reintentando...")
                    continue

                page.fill(f"#{INPUT_PLACA_ID}", placa)
                page.fill(f"#{INPUT_CAPTCHA_ID}", codigo)
                page.click(f"#{BOTON_BUSCAR_ID}")

                try:
                    page.wait_for_load_state("load", timeout=15000)
                except PlaywrightTimeoutError:
                    pass
                page.wait_for_timeout(2000)

                mensaje_el = page.query_selector("#LblMensaje")
                mensaje_error = mensaje_el.inner_text().strip() if mensaje_el else ""

                if "incorrecto" in mensaje_error.lower() or "código de la imagen" in mensaje_error.lower():
                    print(f"  -> [Intento {intento}] Captcha rechazado, reintentando...")
                    continue

                print(f"  -> Busqueda realizada (captcha '{codigo}').")
                return extraer_resultados(page)

            raise RuntimeError(f"No se pudo completar la busqueda tras {max_intentos} intentos.")
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="Record de infracciones por placa - SUTRAN")
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

    print(f"\n===== RECORD DE INFRACCIONES - PLACA {normalizar_placa(args.placa)} =====")
    if resultados["sin_resultados"] or not resultados["items"]:
        print("  No se encontraron infracciones pendientes.")
    else:
        for i, item in enumerate(resultados["items"], 1):
            print(f"  --- Infraccion {i} ---")
            for clave, valor in item.items():
                print(f"  {clave}: {valor}")
    print("===================================================\n")
    os._exit(0)


if __name__ == "__main__":
    main()
