"""
Ranking de videos de una búsqueda: decide cuáles son "los mejores".

Cada video recibe tres componentes entre 0 y 1 y un total ponderado (pesos en config.py):

    relevancia   ¿habla de lo que se buscó?   similitud de embeddings, de [MINIMA, MAXIMA] a [0, 1]
    interaccion  ¿le gustó al público?         (likes+coment.+compartidos+guardados) / (vistas+suavizado)
    alcance      ¿lo vio mucha gente?          log10(vistas) / log10(VISTAS_REFERENCIA)

    total = PESO_RELEVANCIA·relevancia + PESO_INTERACCION·interaccion + PESO_ALCANCE·alcance

Se usan escalas fijas (no relativas al grupo) para que el puntaje de un video signifique
lo mismo en cualquier búsqueda y se pueda explicar en la app.
"""
import math

from app.core import config
from app.services.embeddings import similitudes
from app.utils.texto import texto_para_embedding


def _limitar(valor: float) -> float:
    """Recorta un valor al rango [0, 1]."""
    return max(0.0, min(1.0, valor))


def puntuar(video: dict, similitud: float) -> dict:
    """Calcula el puntaje de un video a partir de su similitud y sus estadísticas."""
    st = video["estadisticas"]
    vistas = st["vistas"] or 0
    interacciones = sum(st[k] or 0 for k in ("likes", "comentarios", "compartidos", "guardados"))

    rango = config.SIMILITUD_MAXIMA - config.SIMILITUD_MINIMA
    relevancia = _limitar((similitud - config.SIMILITUD_MINIMA) / rango)
    tasa = interacciones / (vistas + config.SUAVIZADO_VISTAS)
    interaccion = _limitar(tasa / config.TASA_INTERACCION_REFERENCIA)
    alcance = _limitar(math.log10(vistas + 1) / math.log10(config.VISTAS_REFERENCIA))

    total = (
        config.PESO_RELEVANCIA * relevancia
        + config.PESO_INTERACCION * interaccion
        + config.PESO_ALCANCE * alcance
    )
    return {
        "relevancia": round(relevancia, 3),
        "interaccion": round(interaccion, 3),
        "alcance": round(alcance, 3),
        "total": round(total, 3),
    }


def ordenar(consulta: str, videos: list[dict], cantidad: int) -> list[dict]:
    """
    Agrega "puntaje" a cada video y devuelve los `cantidad` mejores, de mayor a menor.

    Bloqueante (calcula embeddings): llamarla con asyncio.to_thread.
    """
    textos = [texto_para_embedding(v["descripcion"], v["hashtags"]) for v in videos]
    for video, sim in zip(videos, similitudes(consulta, textos)):
        video["puntaje"] = puntuar(video, sim)
    return sorted(videos, key=lambda v: v["puntaje"]["total"], reverse=True)[:cantidad]
