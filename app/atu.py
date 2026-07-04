#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consulta de infracciones por PLACA en ATU (Autoridad de Transporte Urbano
para Lima y Callao). No requiere captcha.
"""

import argparse
import json
import re
import sys
import os

from playwright.sync_api import sync_playwright

from .navegador import crear_pagina

URL = "https://pasarela.atu.gob.pe/"

SELECT_TIPO_ID = "TipoBusquedaselectElemento"
INPUT_PLACA_ID = "PlacaBusquedainputElemento"
TIPO_BUSQUEDA_PLACA_VALUE = "2"


def normalizar_placa(placa: str) -> str:
    return re.sub(r"[\s\-]", "", placa).upper()


def ir_a_consulta_infracciones(page):
    link = page.locator("xpath=//p[@title='Consulta y Pago de Infracciones']/ancestor::a")
    link.first.evaluate("el => el.click()")
    # El select esta oculto por CSS (Materialize lo reemplaza), asi que
    # esperamos solo su presencia en el DOM, no su visibilidad.
    page.wait_for_selector(f"#{SELECT_TIPO_ID}", state="attached", timeout=15000)
    page.wait_for_timeout(1000)


def seleccionar_busqueda_por_placa(page):
    page.eval_on_selector(
        f"#{SELECT_TIPO_ID}",
        "(el, valor) => { el.value = valor; el.dispatchEvent(new Event('change', {bubbles:true})); }",
        TIPO_BUSQUEDA_PLACA_VALUE,
    )
    page.wait_for_timeout(1000)


def extraer_resultados(page):
    resultados = {
        "items": [],
        "suma_calculada": "0.00",
        "sin_resultados": False,
    }

    mensaje_el = page.query_selector(".swal2-html-container")
    if mensaje_el:
        mensaje = mensaje_el.inner_text().strip()
        if "no cuenta con infracci" in mensaje.lower():
            resultados["sin_resultados"] = True
            boton_ok = page.query_selector(".swal2-confirm")
            if boton_ok:
                boton_ok.click()
            return resultados

    tabla = page.query_selector("#tablePrincipal")
    if tabla:
        headers = [th.inner_text().strip().lower() for th in tabla.query_selector_all("thead th")]

        idx_codigo = next((i for i, h in enumerate(headers) if "acta fiscaliza" in h), None)
        idx_fecha = next((i for i, h in enumerate(headers) if "fecha infracc" in h), None)
        idx_total = next((i for i, h in enumerate(headers) if h == "total a pagar"), None)

        suma = 0.0
        for fila in tabla.query_selector_all("tbody tr"):
            celdas = [td.inner_text().strip() for td in fila.query_selector_all("td")]
            if not celdas or not any(celdas):
                continue
            if len(celdas) == 1:
                continue  # fila "Sin Registros"

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

    if not resultados["items"]:
        resultados["sin_resultados"] = True

    return resultados


def consultar(placa: str, headless: bool = True):
    placa = normalizar_placa(placa)
    if not placa:
        raise ValueError("La placa esta vacia.")

    with sync_playwright() as p:
        browser, page = crear_pagina(p, headless=headless)
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            ir_a_consulta_infracciones(page)
            seleccionar_busqueda_por_placa(page)

            page.fill(f"#{INPUT_PLACA_ID}", placa)

            page.eval_on_selector(
                "#formBusqueda button[type=submit]",
                "el => el.click()",
            )
            page.wait_for_timeout(3000)

            return extraer_resultados(page)
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="Consulta de infracciones por placa - ATU")
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

    print(f"\n===== RESULTADOS PARA LA PLACA {normalizar_placa(args.placa)} =====")
    if resultados["sin_resultados"] or not resultados["items"]:
        print("  No se encontraron infracciones registradas para esta placa.")
    else:
        for i, item in enumerate(resultados["items"], 1):
            print(f"  --- Infraccion {i} ---")
            print(f"  Codigo: {item['Codigo']}")
            print(f"  Fecha : {item['Fecha']}")
            print(f"  Total : S/ {item['Total']}")
        print(f"\n  -> Suma de infracciones: S/ {resultados['suma_calculada']}")
    print("===================================================\n")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
