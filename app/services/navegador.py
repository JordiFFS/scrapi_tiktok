"""
Recursos compartidos por todos los scrapers.

`lock_navegador` garantiza que haya UN solo navegador extrayendo a la vez, sin importar
si la petición es de perfil o de búsqueda (regla del proyecto: bajo volumen).

`correr_con_limite` ejecuta un crawler de Crawlee con un tiempo máximo REAL. No basta con
asyncio.wait_for: crawler.run() captura la cancelación y espera a que termine la página en
curso, así que un navegador trabado bloquearía la cola para siempre.
"""
import asyncio
import logging
from contextlib import suppress

from crawlee import Request
from crawlee.crawlers import PlaywrightCrawler
from playwright.async_api import Page

log = logging.getLogger("tiktok_api")

lock_navegador = asyncio.Lock()

# Segundos que se le dan al crawler para cerrarse después de pedirle que pare
GRACIA_PARA_CERRAR_SEG = 15


async def correr_con_limite(
    crawler: PlaywrightCrawler, solicitudes: list[Request], paginas: set[Page], segundos: float
) -> None:
    """
    Ejecuta crawler.run(solicitudes) y, si pasa de `segundos`, lo detiene:

      1. crawler.stop(): no abre más páginas;
      2. cierra las páginas abiertas (`paginas`, las registra cada scraper en su
         pre_navigation_hook): cualquier espera de Playwright falla al instante y el
         handler termina;
      3. si aun así no termina en GRACIA_PARA_CERRAR_SEG, se abandona en segundo plano.

    Lanza TimeoutError si se agotó el tiempo (el controller lo convierte en 502).
    """
    corrida = asyncio.create_task(crawler.run(solicitudes))
    terminadas, _ = await asyncio.wait({corrida}, timeout=segundos)
    if terminadas:
        corrida.result()  # propaga el error del crawler, si lo hubo
        return

    log.warning("La extracción superó %s s: se detiene el navegador", segundos)
    crawler.stop(f"tiempo máximo de {segundos} s")
    for pagina in list(paginas):
        with suppress(Exception):  # la página puede estar ya cerrada
            await pagina.close()
    terminadas, _ = await asyncio.wait({corrida}, timeout=GRACIA_PARA_CERRAR_SEG)
    if not terminadas:
        log.warning("El navegador no se cerró a tiempo; se abandona en segundo plano")
        corrida.cancel()
    raise TimeoutError(f"La extracción superó {segundos} s")
