"""
Controller del perfil: coordina el caso de uso "obtener datos de un perfil".

No sabe de URLs ni de parámetros HTTP (eso es de routes/) ni de cómo se navega
TikTok (eso es de services/). Solo decide el orden y los errores:

    1. Buscar en caché.
    2. Si no está, extraer (una extracción a la vez).
    3. Traducir fallos a códigos HTTP (404 / 502).
    4. Guardar en caché y responder.
"""
import asyncio

from fastapi import HTTPException

from app.core import config
from app.services import tiktok_scraper
from app.services.cache import CacheMemoria

_cache = CacheMemoria(config.CACHE_SEGUNDOS)
_lock = asyncio.Lock()  # una extracción a la vez (más respetuoso con TikTok)


async def obtener_perfil(
    usuario: str,
    max_videos: int,
    comentarios: bool,
    max_comentarios: int,
    refrescar: bool,
) -> dict:
    """
    Devuelve el perfil con sus videos, desde caché o extrayéndolo.

    `usuario` debe venir ya normalizado (ver app/validations/usuario.py).
    La respuesta incluye "desde_cache" para que la app sepa si el dato es reciente.
    """
    clave = f"{usuario}|{max_videos}|{comentarios}|{max_comentarios}"

    if not refrescar and (guardado := _cache.obtener(clave)):
        return {"desde_cache": True, **guardado}

    async with _lock:
        try:
            datos = await tiktok_scraper.extraer_perfil(usuario, max_videos, comentarios, max_comentarios)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Error al extraer datos: {e}")

    if datos["perfil"] is None:
        raise HTTPException(
            status_code=404,
            detail="No se encontró el perfil, es privado o TikTok bloqueó la solicitud.",
        )

    _cache.guardar(clave, datos)
    return {"desde_cache": False, **datos}
