"""
Embeddings con un modelo LOCAL (fastembed + ONNX, sin PyTorch ni APIs externas).

Un embedding convierte un texto en un vector de 768 números; textos con significado
parecido quedan cerca. Así "uñas acrílicas para novia" y "manicura de boda" se reconocen
como relacionados aunque no compartan palabras.

El modelo (paraphrase-multilingual-mpnet-base-v2) se descarga una sola vez (~1 GB) a
config.MODELO_CACHE y se carga en memoria al arrancar la API (ver main.py), para que la
primera búsqueda no tarde de más.
"""
import logging
import threading

import numpy as np
from fastembed import TextEmbedding

from app.core import config

log = logging.getLogger("tiktok_api")

_modelo: TextEmbedding | None = None
_lock_carga = threading.Lock()  # evita cargar el modelo dos veces si llegan dos peticiones juntas


def cargar_modelo() -> TextEmbedding:
    """Devuelve el modelo, cargándolo (y descargándolo la primera vez) si hace falta."""
    global _modelo
    with _lock_carga:
        if _modelo is None:
            log.info("Cargando modelo de embeddings %s ...", config.MODELO_EMBEDDINGS)
            _modelo = TextEmbedding(config.MODELO_EMBEDDINGS, cache_dir=config.MODELO_CACHE)
            log.info("Modelo de embeddings listo")
    return _modelo


def cargar_en_segundo_plano() -> None:
    """
    Carga el modelo en un hilo aparte al arrancar la API, sin bloquearla.

    El hilo es "daemon": Ctrl+C no se queda esperando a que termine la descarga.
    Si falla (p. ej. sin internet) se registra el error y se reintenta en la primera búsqueda.
    """
    def cargar() -> None:
        """Carga el modelo y registra el error en vez de dejar caer el hilo."""
        try:
            cargar_modelo()
        except Exception:
            log.exception("No se pudo cargar el modelo de embeddings; se reintentará en la primera búsqueda")

    threading.Thread(target=cargar, name="carga-embeddings", daemon=True).start()


def similitudes(consulta: str, textos: list[str]) -> list[float]:
    """
    Similitud coseno entre la consulta y cada texto (de -1 a 1; con mpnet en la práctica ~0.5
    para el mismo tema general y ~0.9 casi idéntico, ver SIMILITUD_MINIMA/MAXIMA en config).

    Es una función bloqueante (usa CPU): llamarla con asyncio.to_thread desde código async.
    """
    if not textos:
        return []
    vectores = np.array(list(cargar_modelo().embed([consulta, *textos])))
    vectores /= np.linalg.norm(vectores, axis=1, keepdims=True)  # normalizar -> producto punto = coseno
    return (vectores[1:] @ vectores[0]).tolist()
