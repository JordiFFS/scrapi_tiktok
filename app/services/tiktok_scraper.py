"""
Extractor de datos públicos de TikTok con Crawlee + Playwright.
Uso académico: bajo volumen, solo perfiles públicos, autores de comentarios anonimizados.

Cómo funciona:
  1. Abre un Chromium real y escucha las respuestas de red que TikTok hace a su propia API
     (/api/post/item_list/ -> videos, /api/comment/list/ -> comentarios).
  2. En la página del perfil lee el JSON incrustado con los datos del usuario y hace scroll
     hasta juntar los videos pedidos.
  3. Si se piden comentarios, visita la página de cada video y hace scroll en el panel
     para que TikTok cargue los comentarios (que también se capturan desde la red).
"""
import uuid
from datetime import timedelta

from crawlee import ConcurrencySettings, Request
from crawlee.crawlers import (
    PlaywrightCrawler,
    PlaywrightCrawlingContext,
    PlaywrightPreNavCrawlingContext,
)
from crawlee.storage_clients import MemoryStorageClient

from app.core import config
from app.utils.formato import ahora_iso
from app.utils.normalizadores import (
    normalizar_comentario,
    normalizar_perfil,
    normalizar_video,
)


async def extraer_perfil(
    usuario: str,
    max_videos: int = config.VIDEOS_POR_DEFECTO,
    con_comentarios: bool = True,
    max_comentarios: int = config.COMENTARIOS_POR_DEFECTO,
) -> dict:
    """
    Extrae perfil, videos recientes y (opcionalmente) comentarios de un usuario.

    Devuelve un dict con: usuario, fecha_extraccion, perfil (None si no se pudo leer),
    total_videos_extraidos y videos[]. No lanza error si el perfil no existe:
    eso lo decide el controller mirando si "perfil" es None.
    """
    usuario = usuario.lstrip("@")
    run_id = uuid.uuid4().hex  # hace únicas las URLs de esta corrida (evita deduplicación de Crawlee)

    # Acumuladores que llenan los handlers y el listener de red
    perfil: dict | None = None
    videos: dict[str, dict] = {}         # id_video -> video
    comentarios: dict[str, list] = {}    # id_video -> lista de comentarios

    crawler = PlaywrightCrawler(
        headless=config.HEADLESS,
        browser_type="chromium",
        storage_client=MemoryStorageClient(),  # nada se guarda en disco
        concurrency_settings=ConcurrencySettings(  # una página a la vez (bajo volumen)
            min_concurrency=1, desired_concurrency=1, max_concurrency=1
        ),
        max_requests_per_crawl=max_videos + 1,  # perfil + una página por video
        max_request_retries=1,
        request_handler_timeout=timedelta(minutes=3),
    )

    @crawler.pre_navigation_hook
    async def escuchar_red(context: PlaywrightPreNavCrawlingContext) -> None:
        """Antes de navegar: registra un listener que captura las respuestas JSON de TikTok."""

        async def on_response(response):
            url = response.url
            try:
                if "/api/post/item_list/" in url:
                    data = await response.json()
                    for v in data.get("itemList") or []:
                        if len(videos) < max_videos and v.get("id"):
                            videos.setdefault(v["id"], normalizar_video(v, usuario))
                elif "/api/comment/list/" in url:
                    data = await response.json()
                    for c in data.get("comments") or []:
                        lista = comentarios.setdefault(str(c.get("aweme_id")), [])
                        if len(lista) < max_comentarios:
                            lista.append(normalizar_comentario(c))
            except Exception:
                pass  # respuestas que no son JSON o cambian de formato

        context.page.on("response", on_response)

    @crawler.router.default_handler
    async def pagina_perfil(context: PlaywrightCrawlingContext) -> None:
        """Página del perfil: lee los datos del usuario y hace scroll para cargar videos."""
        nonlocal perfil
        page = context.page
        await page.wait_for_timeout(config.ESPERA_CARGA_MS)

        raw = await page.locator("#__UNIVERSAL_DATA_FOR_REHYDRATION__").text_content()
        perfil = normalizar_perfil(raw or "")

        intentos = 0
        while len(videos) < max_videos and intentos < config.INTENTOS_SCROLL_PERFIL:
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(config.ESPERA_SCROLL_PERFIL_MS)
            intentos += 1

        # Encola la página de cada video para cargar sus comentarios
        if con_comentarios and max_comentarios > 0:
            await context.add_requests([
                Request.from_url(v["url"], label="VIDEO", unique_key=f"{vid}-{run_id}")
                for vid, v in list(videos.items())[:max_videos]
            ])

    @crawler.router.handler("VIDEO")
    async def pagina_video(context: PlaywrightCrawlingContext) -> None:
        """Página de un video: hace scroll en el panel de comentarios hasta tener suficientes."""
        page = context.page
        vid = context.request.url.rstrip("/").split("/")[-1]
        await page.wait_for_timeout(config.ESPERA_CARGA_MS)
        await page.mouse.move(1000, 450)  # sobre el panel de comentarios (lado derecho)
        for _ in range(config.INTENTOS_SCROLL_VIDEO):
            if len(comentarios.get(vid, [])) >= max_comentarios:
                break
            await page.mouse.wheel(0, 2000)
            await page.wait_for_timeout(config.ESPERA_SCROLL_VIDEO_MS)

    await crawler.run([
        Request.from_url(f"https://www.tiktok.com/@{usuario}", unique_key=f"perfil-{usuario}-{run_id}")
    ])

    # Une cada video con los comentarios capturados para él
    lista_videos = list(videos.values())
    for v in lista_videos:
        v["comentarios"] = comentarios.get(v["id"], [])

    return {
        "usuario": usuario,
        "fecha_extraccion": ahora_iso(),
        "perfil": perfil,
        "total_videos_extraidos": len(lista_videos),
        "videos": lista_videos,
    }
