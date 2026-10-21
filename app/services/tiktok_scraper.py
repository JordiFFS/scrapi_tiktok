"""
Extractor de datos públicos de TikTok con Crawlee + Playwright.
Uso académico: bajo volumen, solo perfiles públicos, autores de comentarios anonimizados.

Cómo funciona (todo en UNA sola página, como navegaría una persona):
  1. Abre el perfil en un Chromium real y escucha las respuestas de red que TikTok hace a
     su propia API: /api/post/item_list/ -> videos, /api/comment/list/ -> comentarios.
  2. Lee el JSON incrustado con los datos del usuario y hace scroll hasta juntar los videos pedidos.
  3. Si se piden comentarios, hace clic en cada video de la cuadrícula: TikTok lo abre como
     ventana sobre el perfil y pide sus comentarios. Se hace scroll en esa lista si faltan,
     se cierra la ventana y se pasa al siguiente.

Por qué así y no abriendo la URL de cada video: abrir /video/{id} directamente provocaba
rechazos de TikTok (ERR_HTTP_RESPONSE_CODE_FAILURE) y no cargaba comentarios.

Todas las esperas son "hasta que llegue el dato o se acabe el tiempo máximo" (ver config.py),
así no se pierde tiempo cuando TikTok responde rápido.
"""
import logging
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from crawlee import ConcurrencySettings, Request
from crawlee.crawlers import (
    PlaywrightCrawler,
    PlaywrightCrawlingContext,
    PlaywrightPreNavCrawlingContext,
)
from crawlee.storage_clients import MemoryStorageClient
from playwright.async_api import Page

from app.core import config
from app.services.navegador import correr_con_limite
from app.utils.cronometro import Cronometro
from app.utils.esperas import esperar_hasta
from app.utils.formato import ahora_iso
from app.utils.normalizadores import (
    normalizar_comentario,
    normalizar_perfil,
    normalizar_video,
)

log = logging.getLogger("tiktok_api")


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
    run_id = uuid.uuid4().hex  # hace única la URL de esta corrida (evita deduplicación de Crawlee)
    crono = Cronometro(usuario)  # mide cada etapa y la muestra en consola

    # Acumuladores que llena el listener de red
    perfil: dict | None = None
    videos: dict[str, dict] = {}            # id_video -> video (en el orden en que llegan)
    hay_mas_videos = True                    # "hasMore" de la última lista de videos
    comentarios: dict[str, list] = {}       # id_video -> comentarios capturados
    hay_mas_comentarios: dict[str, bool] = {}  # id_video -> "has_more" de su última respuesta

    paginas: set = set()  # páginas abiertas (ver correr_con_limite)

    crawler = PlaywrightCrawler(
        headless=config.HEADLESS,
        browser_type="chromium",
        storage_client=MemoryStorageClient(),  # nada se guarda en disco
        concurrency_settings=ConcurrencySettings(  # una página a la vez (bajo volumen)
            min_concurrency=1, desired_concurrency=1, max_concurrency=1
        ),
        max_requests_per_crawl=1,  # solo la página del perfil; los videos se abren con clic
        max_request_retries=1,
        request_handler_timeout=timedelta(minutes=5),
    )

    @crawler.pre_navigation_hook
    async def escuchar_red(context: PlaywrightPreNavCrawlingContext) -> None:
        """
        Antes de navegar:
          - (opcional) bloquea imágenes, videos y fuentes para que la página cargue más rápido;
          - registra un listener que captura las respuestas JSON de TikTok.
        """
        paginas.add(context.page)  # para poder cerrarla si se agota el tiempo
        if config.BLOQUEAR_RECURSOS:
            async def filtrar(route):
                """Cancela imágenes, videos y fuentes; deja pasar todo lo demás."""
                if route.request.resource_type in config.TIPOS_BLOQUEADOS:
                    await route.abort()
                else:
                    await route.continue_()

            await context.page.route("**/*", filtrar)

        async def on_response(response):
            """Captura las respuestas de la API interna de TikTok: lista de videos y comentarios."""
            nonlocal hay_mas_videos
            url = response.url
            try:
                if "/api/post/item_list/" in url:
                    data = await response.json()
                    for v in data.get("itemList") or []:
                        if len(videos) < max_videos and v.get("id"):
                            videos.setdefault(v["id"], normalizar_video(v, usuario))
                    hay_mas_videos = bool(data.get("hasMore"))
                elif "/api/comment/list/" in url:
                    # El id del video viene en la URL; así se registra aunque la lista llegue vacía
                    vid = parse_qs(urlparse(url).query).get("aweme_id", [""])[0]
                    data = await response.json()
                    lista = comentarios.setdefault(vid, [])
                    for c in data.get("comments") or []:
                        if len(lista) < max_comentarios:
                            lista.append(normalizar_comentario(c))
                    hay_mas_comentarios[vid] = bool(data.get("has_more"))
            except Exception:
                pass  # respuestas que no son JSON o cambian de formato

        context.page.on("response", on_response)

    async def cargar_comentarios(page: Page, video: dict) -> None:
        """
        Abre un video desde la cuadrícula del perfil, junta sus comentarios y lo cierra.

        Se detiene en cuanto tiene los pedidos, TikTok dice que no hay más (has_more = 0)
        o un scroll no trae nada nuevo dentro del tiempo máximo.
        """
        vid = video["id"]
        # No pedir más de los que el video tiene (commentCount incluye respuestas, es un tope)
        objetivo = min(max_comentarios, video["estadisticas"]["comentarios"] or max_comentarios)

        await page.locator(f'[data-e2e="user-post-item"] a[href*="/video/{vid}"]').first.click()

        if await esperar_hasta(lambda: vid in comentarios, config.ESPERA_MAX_COMENTARIOS_MS):
            for _ in range(config.INTENTOS_SCROLL_COMENTARIOS):
                antes = len(comentarios[vid])
                if antes >= objetivo or not hay_mas_comentarios.get(vid):
                    break
                # Llevar el último comentario a la vista hace que TikTok pida la siguiente página
                ultimo = page.locator('[data-e2e="comment-level-1"]').last
                await ultimo.scroll_into_view_if_needed()
                await page.mouse.wheel(0, 1500)
                if not await esperar_hasta(
                    lambda: len(comentarios[vid]) > antes, config.ESPERA_MAX_MAS_COMENTARIOS_MS
                ):
                    break
        else:
            log.warning("[%s] el video %s no devolvió comentarios a tiempo", usuario, vid)

        # Cerrar la ventana del video y volver a la cuadrícula
        cerrar = page.locator('[data-e2e="browse-close"]')
        if await cerrar.count():
            await cerrar.first.click()
        else:
            await page.keyboard.press("Escape")
        await page.wait_for_url(lambda u: "/video/" not in u, timeout=5000)

    @crawler.router.default_handler
    async def pagina_perfil(context: PlaywrightCrawlingContext) -> None:
        """Página del perfil: datos del usuario, scroll para videos y clic en cada video."""
        nonlocal perfil
        page = context.page
        crono.marca("navegador + perfil abiertos")

        # El JSON del perfil (~180 KB) puede leerse a medio descargar ("Unterminated string"):
        # esperar a que el HTML esté completo y, si aun así llega cortado, releerlo unos instantes.
        # count() no espera: si TikTok mostró un captcha o bloqueo (sin el JSON) no se pierden
        # 30 s por intento en text_content().
        await page.wait_for_load_state("domcontentloaded")
        datos = page.locator("#__UNIVERSAL_DATA_FOR_REHYDRATION__")
        for intento in range(config.INTENTOS_LEER_PERFIL):
            if await datos.count():
                perfil = normalizar_perfil(await datos.first.text_content() or "")
                if perfil:
                    break
            if intento < config.INTENTOS_LEER_PERFIL - 1:
                await page.wait_for_timeout(500)
        crono.marca("perfil leído" if perfil else "perfil NO encontrado")
        if not perfil:
            return

        # Videos: no esperar más de los que la cuenta tiene
        objetivo = min(max_videos, perfil["total_videos"] or max_videos)
        await esperar_hasta(lambda: len(videos) > 0, config.ESPERA_MAX_VIDEOS_MS)
        for _ in range(config.INTENTOS_SCROLL_PERFIL):
            antes = len(videos)
            if antes >= objetivo or not hay_mas_videos:
                break
            await page.mouse.wheel(0, 3000)
            await esperar_hasta(lambda: len(videos) > antes, config.ESPERA_MAX_SCROLL_PERFIL_MS)
        crono.marca(f"videos listos ({len(videos)})")

        if not (con_comentarios and max_comentarios > 0):
            return

        for video in list(videos.values()):
            # Saltar videos sin comentarios según sus estadísticas: no hace falta abrirlos
            if video["estadisticas"]["comentarios"] == 0:
                continue
            try:
                await cargar_comentarios(page, video)
            except Exception as e:  # un video que falla no arruina toda la extracción
                log.warning("[%s] no se pudieron leer comentarios de %s: %s", usuario, video["id"], e)
                await page.keyboard.press("Escape")
            crono.marca(f"video {video['id'][-6:]} ({len(comentarios.get(video['id'], []))} coment.)")
            await page.wait_for_timeout(config.PAUSA_ENTRE_VIDEOS_MS)

    await correr_con_limite(
        crawler,
        [Request.from_url(f"https://www.tiktok.com/@{usuario}", unique_key=f"perfil-{usuario}-{run_id}")],
        paginas,
        config.EXTRACCION_TIEMPO_MAX_SEG,
    )
    crono.marca("navegador cerrado")

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
