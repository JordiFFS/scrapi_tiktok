"""
Busca videos por tema usando las páginas PÚBLICAS de hashtags de TikTok (/tag/{hashtag}).

Por qué hashtags: la búsqueda libre (/search?q=) exige iniciar sesión y devuelve vacío;
las páginas de hashtag no. Al abrirlas, TikTok pide /api/challenge/item_list/ (~30 videos
por página) con el mismo formato que los videos de un perfil.

Cómo funciona:
  1. Se abre el primer hashtag (el más específico) y se capturan sus videos.
  2. Se hace scroll para pedir más páginas, hasta BUSQUEDA_PAGINAS_POR_HASHTAG.
  3. Si todavía faltan candidatos, se encola el siguiente hashtag (más general).

Ojo (medido): en la PRIMERA página que abre el navegador, TikTok suele responder item_list
con 200 pero cuerpo vacío (todavía no tiene sus cookies). Recargar la misma pestaña no
siempre basta; abrir el hashtag otra vez como página NUEVA sí funcionó en todas las pruebas.
Por eso un hashtag vacío se reintenta una sola vez antes de pasar al siguiente.
Aquí solo se JUNTAN candidatos; ordenarlos es trabajo de services/ranking.py.
"""
import logging
import uuid
from datetime import timedelta
from urllib.parse import quote

from crawlee import ConcurrencySettings, Request
from crawlee.crawlers import (
    PlaywrightCrawler,
    PlaywrightCrawlingContext,
    PlaywrightPreNavCrawlingContext,
)
from crawlee.storage_clients import MemoryStorageClient

from app.core import config
from app.services.navegador import correr_con_limite
from app.utils.cronometro import Cronometro
from app.utils.esperas import esperar_hasta
from app.utils.normalizadores import normalizar_video_busqueda

log = logging.getLogger("tiktok_api")


async def buscar_candidatos(hashtags: list[str], max_candidatos: int) -> tuple[list[dict], list[str]]:
    """
    Junta hasta `max_candidatos` videos (sin repetir) recorriendo los hashtags en orden.

    Devuelve (videos, hashtags_usados). `hashtags_usados` son los que aportaron al menos
    un video, para que la app pueda mostrar de dónde salieron los resultados.
    """
    run_id = uuid.uuid4().hex
    crono = Cronometro("#" + (hashtags[0] if hashtags else "?"))

    videos: dict[str, dict] = {}          # id -> video (sin duplicados entre hashtags)
    aportes: dict[str, int] = {}          # hashtag -> videos nuevos que aportó
    hay_mas = {"valor": True}             # "hasMore" de la última página recibida
    respuestas = {"cuenta": 0, "vacia": False}  # páginas recibidas / ¿llegó una vacía?

    paginas: set = set()  # páginas abiertas (ver correr_con_limite)

    crawler = PlaywrightCrawler(
        headless=config.HEADLESS,
        browser_type="chromium",
        storage_client=MemoryStorageClient(),
        concurrency_settings=ConcurrencySettings(min_concurrency=1, desired_concurrency=1, max_concurrency=1),
        max_requests_per_crawl=len(hashtags) + 1,  # +1: un reintento por respuesta vacía
        max_request_retries=1,
        request_handler_timeout=timedelta(minutes=2),
    )

    @crawler.pre_navigation_hook
    async def escuchar_red(context: PlaywrightPreNavCrawlingContext) -> None:
        """Captura cada página de videos que TikTok pide para el hashtag abierto."""
        paginas.add(context.page)  # para poder cerrarla si se agota el tiempo
        hashtag = context.request.user_data["hashtag"]
        respuestas["cuenta"] = 0
        respuestas["vacia"] = False
        hay_mas["valor"] = True

        async def on_response(response):
            """Guarda los videos de cada página de /api/challenge/item_list/ (sin repetir)."""
            if "/api/challenge/item_list/" not in response.url:
                return
            try:
                data = await response.json()
            except Exception:
                respuestas["vacia"] = True  # 200 sin cuerpo: TikTok aún no entrega datos
                return
            for v in data.get("itemList") or []:
                # Sin autor no se puede armar la URL del video (quedaría ".../@/video/id")
                autor = (v.get("author") or {}).get("uniqueId")
                if len(videos) < max_candidatos and v.get("id") and autor and v["id"] not in videos:
                    videos[v["id"]] = normalizar_video_busqueda(v)
                    aportes[hashtag] = aportes.get(hashtag, 0) + 1
            hay_mas["valor"] = bool(data.get("hasMore"))
            respuestas["cuenta"] += 1

        context.page.on("response", on_response)

    reintento_usado = {"valor": False}

    def solicitud(indice: int, reintento: bool = False) -> Request:
        """Request de Crawlee para el hashtag número `indice` (o su reintento)."""
        h = hashtags[indice]
        return Request.from_url(
            f"https://www.tiktok.com/tag/{quote(h)}",
            unique_key=f"tag-{h}-{run_id}{'-reintento' if reintento else ''}",
            user_data={"hashtag": h, "indice": indice},
        )

    @crawler.router.default_handler
    async def pagina_hashtag(context: PlaywrightCrawlingContext) -> None:
        """Página de un hashtag: espera la primera página de videos y hace scroll por más."""
        page = context.page
        hashtag = context.request.user_data["hashtag"]
        indice = context.request.user_data["indice"]

        # Seguir apenas llegue algo: videos (cuenta > 0) o una respuesta vacía
        await esperar_hasta(
            lambda: respuestas["cuenta"] > 0 or respuestas["vacia"], config.ESPERA_MAX_VIDEOS_MS
        )
        llego = respuestas["cuenta"] > 0
        if not llego and respuestas["vacia"] and not reintento_usado["valor"]:
            # Respuesta vacía (navegador "frío"): reabrir este mismo hashtag como página nueva
            reintento_usado["valor"] = True
            crono.marca(f"#{hashtag}: respuesta vacía, reintentando")
            await context.add_requests([solicitud(indice, reintento=True)])
            return
        if not llego:
            log.warning("[#%s] no devolvió videos (no existe, está vacío o hubo bloqueo)", hashtag)

        while (
            llego
            and len(videos) < max_candidatos
            and hay_mas["valor"]
            and respuestas["cuenta"] < config.BUSQUEDA_PAGINAS_POR_HASHTAG
        ):
            antes = respuestas["cuenta"]
            await page.mouse.wheel(0, 4000)
            if not await esperar_hasta(lambda: respuestas["cuenta"] > antes, config.ESPERA_MAX_SCROLL_PERFIL_MS):
                break
        crono.marca(f"#{hashtag}: +{aportes.get(hashtag, 0)} videos (total {len(videos)})")

        # ¿Faltan candidatos? -> pasar al siguiente hashtag, más general
        if len(videos) < max_candidatos and indice + 1 < len(hashtags):
            await context.add_requests([solicitud(indice + 1)])

    if hashtags:
        await correr_con_limite(crawler, [solicitud(0)], paginas, config.EXTRACCION_TIEMPO_MAX_SEG)
    crono.marca("navegador cerrado")

    return list(videos.values()), [h for h in hashtags if aportes.get(h)]
