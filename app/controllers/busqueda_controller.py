"""
Controller de la búsqueda por tema: "los mejores videos sobre X".

    1. Buscar en caché.
    2. Convertir la búsqueda en hashtags (utils/texto.py).
    3. Juntar candidatos de esos hashtags (services/tiktok_busqueda.py) — un navegador a la vez.
    4. Ordenarlos con embeddings + estadísticas (services/ranking.py).
    5. Guardar en caché y responder.
"""
import asyncio

from fastapi import HTTPException

from app.core import config
from app.services import ranking, tiktok_busqueda
from app.services.cache import CacheMemoria
from app.services.navegador import lock_navegador
from app.utils.formato import ahora_iso
from app.utils.texto import generar_hashtags

_cache = CacheMemoria(config.CACHE_SEGUNDOS)


def _recortar(datos: dict, max_resultados: int, desde_cache: bool) -> dict:
    """
    Arma la respuesta con los `max_resultados` primeros de la lista ya ordenada.

    La caché guarda TODOS los candidatos ordenados por consulta: pedir 10 y luego 20
    no vuelve a abrir TikTok.
    """
    resultados = datos["resultados"][:max_resultados]
    return {
        "desde_cache": desde_cache,
        **datos,
        "total_resultados": len(resultados),
        "resultados": resultados,
    }


def desde_cache(consulta: str, max_resultados: int) -> dict | None:
    """Respuesta guardada para esta búsqueda, o None. No abre el navegador (lo usa la cola)."""
    guardado = _cache.obtener(consulta)
    return _recortar(guardado, max_resultados, desde_cache=True) if guardado else None


async def buscar(consulta: str, max_resultados: int, refrescar: bool) -> dict:
    """
    Devuelve los `max_resultados` mejores videos para `consulta` (ya normalizada).

    Errores: 404 si ningún hashtag devolvió videos, 502 si falla la extracción o pasa
    EXTRACCION_TIEMPO_MAX_SEG.
    """
    if not refrescar and (guardado := desde_cache(consulta, max_resultados)):
        return guardado

    hashtags = generar_hashtags(consulta, config.BUSQUEDA_MAX_HASHTAGS)

    async with lock_navegador:
        try:
            candidatos, usados = await tiktok_busqueda.buscar_candidatos(
                hashtags, config.BUSQUEDA_MAX_CANDIDATOS
            )
        except TimeoutError:  # el scraper pasó de EXTRACCION_TIEMPO_MAX_SEG y se detuvo
            raise HTTPException(
                status_code=502,
                detail=f"La búsqueda superó {config.EXTRACCION_TIEMPO_MAX_SEG} s y se canceló. Intenta de nuevo.",
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Error al buscar videos: {e}")

    if not candidatos:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No se encontraron videos para '{consulta}' (hashtags probados: {', '.join(hashtags)}). "
                "Si el tema es común, TikTok puede estar limitando las consultas: intenta en unos minutos."
            ),
        )

    # El ranking usa CPU (embeddings): se ejecuta en otro hilo para no congelar la API.
    # Se ordenan todos los candidatos; el recorte se hace al responder.
    ordenados = await asyncio.to_thread(ranking.ordenar, consulta, candidatos, len(candidatos))

    datos = {
        "consulta": consulta,
        "hashtags_usados": usados,
        "fecha_extraccion": ahora_iso(),
        "total_candidatos": len(candidatos),
        "resultados": ordenados,
    }
    _cache.guardar(consulta, datos)
    return _recortar(datos, max_resultados, desde_cache=False)
