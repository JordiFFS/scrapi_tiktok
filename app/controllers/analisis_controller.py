"""
Controller del análisis: "Big Five del creador + sentimiento de sus comentarios".

    1. Buscar el análisis en su propia caché (1 hora).
    2. Obtener el perfil con el MISMO controller de /api/perfil: si ya fue extraído (caché),
       no se vuelve a abrir TikTok; si no, se extrae con el navegador (lock, 404, 502...).
    3. Ejecutar los modelos en otro hilo (asyncio.to_thread): usan CPU varios segundos y,
       si corrieran en el hilo principal, la API dejaría de responder a todos mientras tanto.
    4. Guardar en caché y responder.

La lógica de IA está en app/services/analisis.py; aquí solo se decide el orden y los errores.
"""
import asyncio
import logging

from fastapi import HTTPException

from app.controllers import perfil_controller
from app.core import config
from app.services import analisis
from app.services.cache import CacheMemoria

log = logging.getLogger("tiktok_api")

_cache = CacheMemoria(config.CACHE_SEGUNDOS)

# Un análisis a la vez: cada uno usa todos los núcleos y ~2-3 GB de RAM con los modelos;
# dos en paralelo no terminan antes y podrían quedarse sin memoria.
_lock_analisis = asyncio.Lock()


def _clave(usuario: str, max_videos: int, comentarios: bool, max_comentarios: int) -> str:
    """Misma clave que el perfil: el análisis depende de exactamente los mismos datos."""
    return f"{usuario}|{max_videos}|{comentarios}|{max_comentarios}"


def desde_cache(usuario: str, max_videos: int, comentarios: bool, max_comentarios: int) -> dict | None:
    """Análisis guardado para estos parámetros, o None. No ejecuta nada (lo usa la cola)."""
    guardado = _cache.obtener(_clave(usuario, max_videos, comentarios, max_comentarios))
    return {"desde_cache": True, **guardado} if guardado else None


async def analizar(
    usuario: str,
    max_videos: int,
    comentarios: bool,
    max_comentarios: int,
    refrescar: bool,
) -> dict:
    """
    Devuelve el análisis del perfil, desde caché o calculándolo.

    `refrescar=True` vuelve a extraer el perfil de TikTok y a analizarlo.
    Errores: los del perfil (404/502) y 503 si los modelos no se pudieron cargar o fallaron.
    """
    clave = _clave(usuario, max_videos, comentarios, max_comentarios)
    if not refrescar and (guardado := desde_cache(usuario, max_videos, comentarios, max_comentarios)):
        return guardado

    datos = await perfil_controller.obtener_perfil(usuario, max_videos, comentarios, max_comentarios, refrescar)

    async with _lock_analisis:
        try:
            resultado = await asyncio.to_thread(analisis.analizar_perfil, datos)
        except Exception as e:  # sin internet en la 1.ª descarga, falta de RAM, etc.
            log.exception("[%s] falló el análisis", usuario)
            raise HTTPException(status_code=503, detail=f"No se pudo ejecutar el análisis: {e}")

    _cache.guardar(clave, resultado)
    return {"desde_cache": False, **resultado}
