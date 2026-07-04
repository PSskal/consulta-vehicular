#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consulta de papeletas e impuestos vehiculares por PLACA en SAT Lima.
Extracción directa de Totales para evitar filas ocultas duplicadas.
"""

import argparse
import json
import re
import sys
import os

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from .navegador import crear_pagina
from .captcha import resolver_recaptcha_v2

URL = "https://www.sat.gob.pe/pagosenlinea/"

SELECT_TIPO_ID = "strTipDoc"
INPUT_DATO_ID = "strNumDoc"
PLACA_VALUE = "3"

# sitekey del reCAPTCHA v2 de SAT Lima (data-sitekey del widget).
RECAPTCHA_SITEKEY = "6Ldy_wsTAAAAAGYM08RRQAMvF96g9O_SNQ9_hFIJ"


def normalizar_placa(placa: str) -> str:
    return re.sub(r"[\s\-]", "", placa).upper()


def limpiar_texto_monto(texto: str) -> str:
    """Extrae solo el número de textos como 'TOTAL:   S/ 2,767.00'"""
    # Busca todo lo que sea dígito, coma o punto
    numeros = re.findall(r'[\d\.,]+', texto)
    return numeros[0] if numeros else "0.00"


def seleccionar_placa(page):
    page.wait_for_selector(f"#{SELECT_TIPO_ID}", timeout=15000)
    page.select_option(f"#{SELECT_TIPO_ID}", value=PLACA_VALUE)
    page.eval_on_selector(
        f"#{SELECT_TIPO_ID}",
        "el => el.dispatchEvent(new Event('change', {bubbles:true}))",
    )
    page.wait_for_timeout(500)


def escribir_placa(page, placa: str):
    page.wait_for_selector(f"#{INPUT_DATO_ID}", timeout=15000)
    page.eval_on_selector(f"#{INPUT_DATO_ID}", "el => el.removeAttribute('maxlength')")
    page.fill(f"#{INPUT_DATO_ID}", placa)

    actual = page.eval_on_selector(f"#{INPUT_DATO_ID}", "el => el.value") or ""
    if actual.upper() != placa.upper():
        page.eval_on_selector(
            f"#{INPUT_DATO_ID}",
            "(el, valor) => {"
            "  el.value = valor;"
            "  el.dispatchEvent(new Event('input', {bubbles:true}));"
            "  el.dispatchEvent(new Event('change', {bubbles:true}));"
            "}",
            placa,
        )


def procesar_captcha(page):
    """Resuelve el reCAPTCHA v2 con 2captcha e inyecta el token en la pagina.

    reCAPTCHA se valida en el servidor de SAT contra el parametro
    g-recaptcha-response, asi que basta con poner el token en el textarea
    oculto. Ademas sobreescribimos grecaptcha.getResponse() por si el JS del
    formulario lo consulta antes de enviar.
    """
    print("\n  → Resolviendo reCAPTCHA v2 con 2captcha (puede tardar ~30s)...")
    token = resolver_recaptcha_v2(RECAPTCHA_SITEKEY, URL)
    print("  → Token de reCAPTCHA obtenido, inyectando en la pagina...")

    page.evaluate(
        """
        (token) => {
            let ta = document.getElementById('g-recaptcha-response');
            if (!ta) {
                ta = document.createElement('textarea');
                ta.id = 'g-recaptcha-response';
                ta.name = 'g-recaptcha-response';
                ta.style.display = 'none';
                document.body.appendChild(ta);
            }
            ta.value = token;
            if (window.grecaptcha) {
                window.grecaptcha.getResponse = () => token;
            }
        }
        """,
        token,
    )


def clic_buscar(page):
    print("  → Haciendo clic en el botón Buscar...")
    page.eval_on_selector(
        "button[onclick='BuscarContribuyentes()']",
        "el => el.click()",
    )


def extraer_resultados(page):
    resultados = {
        "impuesto_vehicular": {"total_web": "0.00"},
        "papeletas": {"items": [], "total_web": "0.00"}
    }

    try:
        page.wait_for_selector("#Paso3", timeout=15000)
        page.wait_for_timeout(2000)
    except PlaywrightTimeoutError:
        print("  → No se detectó la tabla de resultados.")
        return resultados

    # Si la placa no tiene deuda, SAT muestra un aviso "No registra deuda
    # pendiente" en vez de la tabla. Es un resultado válido (todo en 0.00).
    cuerpo = page.evaluate("() => document.body.innerText") or ""
    if "no registra deuda" in cuerpo.lower():
        print("  → SAT: no registra deuda pendiente.")
        return resultados

    print("  → Extrayendo datos robustos y comprobando totales...")

    # --- 1. EXTRACCIÓN DE IMPUESTO VEHICULAR (Solo el TOTAL general) ---
    total_imp = page.query_selector("#divImpVehicular div.montoconcepto")
    if total_imp:
        resultados["impuesto_vehicular"]["total_web"] = limpiar_texto_monto(total_imp.inner_text())

    # --- 2. EXTRACCIÓN DE PAPELETAS (Items + TOTAL general) ---
    div_papeletas = page.query_selector("#divPapeletas")
    if div_papeletas:
        total_pap = div_papeletas.query_selector("div.montoconcepto")
        if total_pap:
            resultados["papeletas"]["total_web"] = limpiar_texto_monto(total_pap.inner_text())

        # Desplegar para leer las filas (solo dentro de papeletas para evitar basura)
        for btn in div_papeletas.query_selector_all("i.fa-plus"):
            try:
                btn.evaluate("el => el.click()")
                page.wait_for_timeout(200)
            except Exception:
                pass

        # Leer filas de papeletas
        filas_pap = div_papeletas.query_selector_all("div.row.gridtree-row[data-id]")
        for fila in filas_pap:
            try:
                falta_el = fila.query_selector(
                    "xpath=.//div[contains(@class, 'text-left') and contains(@class, 'item-center')]"
                )
                if not falta_el:
                    continue
                falta = falta_el.inner_text().strip().replace("\n", " ")

                fecha = "No encontrada"
                for col in fila.query_selector_all("div.item-center"):
                    texto = col.inner_text().strip()
                    if "/" in texto and len(texto) == 10:
                        fecha = texto
                        break

                monto_el = fila.query_selector("span.monto")
                monto = monto_el.inner_text().strip() if monto_el else "0.00"

                resultados["papeletas"]["items"].append({
                    "Falta": falta,
                    "Fecha": fecha,
                    "Monto": monto
                })
            except Exception:
                continue

    return resultados


def consultar(placa: str, headless: bool = True):
    placa = normalizar_placa(placa)
    if not placa:
        raise ValueError("La placa está vacía.")

    with sync_playwright() as p:
        browser, page = crear_pagina(p, headless=headless)
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            seleccionar_placa(page)
            escribir_placa(page, placa)
            procesar_captcha(page)
            clic_buscar(page)

            print("  → Esperando a que cargue la tabla de resultados...")
            return extraer_resultados(page)
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="Consulta papeletas e impuestos por placa en SAT Lima")
    parser.add_argument("placa", help="Placa a consultar (ej: ABC123)")
    parser.add_argument("--ver-navegador", action="store_true", help="Mostrar la ventana de Chrome")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    args = parser.parse_args()

    try:
        resultados = consultar(args.placa, headless=not args.ver_navegador)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        os._exit(1)

    tiene_impuestos = resultados["impuesto_vehicular"]["total_web"] != "0.00"
    tiene_papeletas = resultados["papeletas"]["total_web"] != "0.00"

    if not tiene_impuestos and not tiene_papeletas:
        print(f"\nNo se encontraron deudas para la placa {normalizar_placa(args.placa)}.")
        os._exit(0)

    if args.json:
        print(json.dumps(resultados, ensure_ascii=False, indent=2))
    else:
        print(f"\n===== RESULTADOS PARA LA PLACA {normalizar_placa(args.placa)} =====")

        if tiene_impuestos:
            print(f"\n[ IMPUESTO VEHICULAR ]")
            print(f"  -> Total Adeudado (según web): S/ {resultados['impuesto_vehicular']['total_web']}")

        if tiene_papeletas:
            items = resultados["papeletas"]["items"]
            print(f"\n[ PAPELETAS ] - {len(items)} registro(s) encontrados:")

            suma_calculada = 0.0

            for i, r in enumerate(items, 1):
                print(f"  --- Papeleta {i} ---")
                print(f"  Falta: {r['Falta']}")
                print(f"  Fecha: {r['Fecha']}")
                print(f"  Monto: S/ {r['Monto']}")

                # Sumar para comprobación (quitando comas si existen)
                valor_limpio = r['Monto'].replace(',', '')
                try:
                    suma_calculada += float(valor_limpio)
                except:
                    pass

            print(f"  -----------------------------")
            print(f"  -> Suma de items extraídos   : S/ {suma_calculada:,.2f}")
            print(f"  -> Total Oficial (según web) : S/ {resultados['papeletas']['total_web']}")

        print("===================================================\n")


if __name__ == "__main__":
    main()
    os._exit(0)
