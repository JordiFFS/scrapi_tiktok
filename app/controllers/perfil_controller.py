"""
Controller del perfil: coordina el caso de uso "obtener datos de un perfil".

No sabe de URLs ni de parámetros HTTP (eso es de routes/) ni de cómo se navega
TikTok (eso es de services/). Solo decide el orden y los errores:

    1. Buscar en caché.
    2. Si no está, extraer (una extracción a la vez).
    3. Traducir fallos a códigos HTTP (404 / 502, también si pasa EXTRACCION_TIEMPO_MAX_SEG).
    4. Guardar en caché y responder.
"""
from fastapi import HTTPException

from app.core import config
from app.services import tiktok_scraper
from app.services.cache import CacheMemoria
from app.services.navegador import lock_navegador

_cache = CacheMemoria(config.CACHE_SEGUNDOS)


def _clave(usuario: str, max_videos: int, comentarios: bool, max_comentarios: int) -> str:
    """Clave de caché: la misma consulta con los mismos parámetros comparte resultado."""
    return f"{usuario}|{max_videos}|{comentarios}|{max_comentarios}"


def desde_cache(usuario: str, max_videos: int, comentarios: bool, max_comentarios: int) -> dict | None:
    """Respuesta guardada para estos parámetros, o None. No abre el navegador (lo usa la cola)."""
    guardado = _cache.obtener(_clave(usuario, max_videos, comentarios, max_comentarios))
    return {"desde_cache": True, **guardado} if guardado else None


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
    clave = _clave(usuario, max_videos, comentarios, max_comentarios)

    if not refrescar and (guardado := desde_cache(usuario, max_videos, comentarios, max_comentarios)):
        return guardado

    async with lock_navegador:  # un navegador a la vez (compartido con la búsqueda)
        try:
            datos = await tiktok_scraper.extraer_perfil(usuario, max_videos, comentarios, max_comentarios)
        except TimeoutError:  # el scraper pasó de EXTRACCION_TIEMPO_MAX_SEG y se detuvo
            raise HTTPException(
                status_code=502,
                detail=f"La extracción superó {config.EXTRACCION_TIEMPO_MAX_SEG} s y se canceló. Intenta de nuevo.",
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Error al extraer datos: {e}")

    if datos["perfil"] is None:
        raise HTTPException(
            status_code=404,
            detail="No se encontró el perfil, es privado o TikTok bloqueó la solicitud.",
        )

    _cache.guardar(clave, datos)
    return {"desde_cache": False, **datos}
