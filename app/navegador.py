"""
Helper compartido para crear paginas de Playwright con anti-deteccion basica.

Usa el Chromium bundled de Playwright en headless y el Chrome del sistema
cuando se necesita ventana visible. El UA se fija directamente sin necesitar
evaluar la pagina, evitando el TargetClosedError en modo visible.
"""

VIEWPORT = {"width": 1366, "height": 900}

# UA de Chrome 136 en Windows 11 (sin "Headless")
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

STEALTH_JS = "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"


def crear_pagina(p, headless: bool = True):
    """Lanza el navegador y devuelve (browser, page) listos para navegar."""
    launch_kwargs = dict(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--lang=es-PE",
        ],
    )

    # channel="chrome" solo cuando se necesita ventana visible (SAT Lima, depuracion).
    # En headless usamos el Chromium bundled de Playwright para evitar incompatibilidades.
    if not headless:
        launch_kwargs["channel"] = "chrome"

    browser = p.chromium.launch(**launch_kwargs)
    context = browser.new_context(
        locale="es-PE",
        viewport=VIEWPORT,
        user_agent=_UA,
    )
    context.add_init_script(STEALTH_JS)
    page = context.new_page()
    return browser, page
