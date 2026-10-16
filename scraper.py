"""
Extractor de datos públicos de TikTok con Crawlee + Playwright.
Uso académico: bajo volumen, solo perfiles públicos, autores de comentarios anonimizados.
"""
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from crawlee import ConcurrencySettings, Request
from crawlee.crawlers import (
    PlaywrightCrawler,
    PlaywrightCrawlingContext,
    PlaywrightPreNavCrawlingContext,
)
from crawlee.storage_clients import MemoryStorageClient

# TikTok suele bloquear el modo headless; déjalo en false mientras desarrollas.
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"


# ---------- Normalizadores (convierten el JSON de TikTok en un formato limpio) ----------

def _anonimizar(valor: str | None) -> str | None:
    if not valor:
        return None
    return hashlib.sha256(valor.encode()).hexdigest()[:12]


def _fecha(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _perfil(raw: str) -> dict | None:
    try:
        info = json.loads(raw)["__DEFAULT_SCOPE__"]["webapp.user-detail"]["userInfo"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return None
    u, s = info.get("user", {}), info.get("stats", {})
    return {
        "usuario": u.get("uniqueId"),
        "nombre": u.get("nickname"),
        "biografia": u.get("signature"),
        "avatar": u.get("avatarLarger"),
        "verificado": u.get("verified"),
        "privado": u.get("privateAccount"),
        "seguidores": s.get("followerCount"),
        "siguiendo": s.get("followingCount"),
        "likes_totales": s.get("heartCount"),
        "total_videos": s.get("videoCount"),
    }


def _video(v: dict, usuario: str) -> dict:
    st = v.get("stats", {})
    return {
        "id": v.get("id"),
        "url": f"https://www.tiktok.com/@{usuario}/video/{v.get('id')}",
        "descripcion": v.get("desc"),
        "fecha": _fecha(v.get("createTime")),
        "portada": (v.get("video") or {}).get("cover"),
        "duracion_seg": (v.get("video") or {}).get("duration"),
        "musica": (v.get("music") or {}).get("title"),
        "hashtags": [t.get("hashtagName") for t in v.get("textExtra") or [] if t.get("hashtagName")],
        "estadisticas": {
            "vistas": st.get("playCount"),
            "likes": st.get("diggCount"),
            "comentarios": st.get("commentCount"),
            "compartidos": st.get("shareCount"),
            "guardados": st.get("collectCount"),
        },
        "comentarios": [],
    }


def _comentario(c: dict) -> dict:
    return {
        "id": c.get("cid"),
        "texto": c.get("text"),
        "fecha": _fecha(c.get("create_time")),
        "likes": c.get("digg_count"),
        "respuestas": c.get("reply_comment_total"),
        "autor_anonimo": _anonimizar((c.get("user") or {}).get("unique_id")),
    }


# ---------- Crawler ----------

async def extraer_perfil(
    usuario: str,
    max_videos: int = 10,
    con_comentarios: bool = True,
    max_comentarios: int = 20,
) -> dict:
    usuario = usuario.lstrip("@")
    run_id = uuid.uuid4().hex
    perfil: dict | None = None
    videos: dict[str, dict] = {}
    comentarios: dict[str, list] = {}

    crawler = PlaywrightCrawler(
        headless=HEADLESS,
        browser_type="chromium",
        storage_client=MemoryStorageClient(),  # nada se guarda en disco
        concurrency_settings=ConcurrencySettings(min_concurrency=1, desired_concurrency=1, max_concurrency=1),  # una página a la vez
        max_requests_per_crawl=max_videos + 1,
        max_request_retries=1,
        request_handler_timeout=timedelta(minutes=3),
    )

    # Antes de navegar: escuchar las respuestas JSON internas de TikTok
    @crawler.pre_navigation_hook
    async def escuchar_red(context: PlaywrightPreNavCrawlingContext) -> None:
        async def on_response(response):
            url = response.url
            try:
                if "/api/post/item_list/" in url:
                    data = await response.json()
                    for v in data.get("itemList") or []:
                        if len(videos) < max_videos and v.get("id"):
                            videos.setdefault(v["id"], _video(v, usuario))
                elif "/api/comment/list/" in url:
                    data = await response.json()
                    for c in data.get("comments") or []:
                        lista = comentarios.setdefault(str(c.get("aweme_id")), [])
                        if len(lista) < max_comentarios:
                            lista.append(_comentario(c))
            except Exception:
                pass  # respuestas que no son JSON o cambian de formato

        context.page.on("response", on_response)

    # Página de perfil: datos del usuario + últimos videos
    @crawler.router.default_handler
    async def pagina_perfil(context: PlaywrightCrawlingContext) -> None:
        nonlocal perfil
        page = context.page
        await page.wait_for_timeout(4000)

        raw = await page.locator("#__UNIVERSAL_DATA_FOR_REHYDRATION__").text_content()
        perfil = _perfil(raw or "")

        intentos = 0
        while len(videos) < max_videos and intentos < 8:
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(2500)
            intentos += 1

        if con_comentarios and max_comentarios > 0:
            await context.add_requests([
                Request.from_url(v["url"], label="VIDEO", unique_key=f"{vid}-{run_id}")
                for vid, v in list(videos.items())[:max_videos]
            ])

    # Página de cada video: cargar comentarios
    @crawler.router.handler("VIDEO")
    async def pagina_video(context: PlaywrightCrawlingContext) -> None:
        page = context.page
        vid = context.request.url.rstrip("/").split("/")[-1]
        await page.wait_for_timeout(4000)
        await page.mouse.move(1000, 450)  # sobre el panel de comentarios (lado derecho)
        for _ in range(5):
            if len(comentarios.get(vid, [])) >= max_comentarios:
                break
            await page.mouse.wheel(0, 2000)
            await page.wait_for_timeout(2000)

    await crawler.run([
        Request.from_url(f"https://www.tiktok.com/@{usuario}", unique_key=f"perfil-{usuario}-{run_id}")
    ])

    lista_videos = list(videos.values())
    for v in lista_videos:
        v["comentarios"] = comentarios.get(v["id"], [])

    return {
        "usuario": usuario,
        "fecha_extraccion": datetime.now(timezone.utc).isoformat(),
        "perfil": perfil,
        "total_videos_extraidos": len(lista_videos),
        "videos": lista_videos,
    }
