"""
Esperas "inteligentes": seguir apenas se cumple una condición, con un tiempo máximo.
"""
import asyncio
from typing import Callable


async def esperar_hasta(condicion: Callable[[], bool], max_ms: int, paso_ms: int = 200) -> bool:
    """
    Revisa `condicion()` cada `paso_ms` hasta que sea verdadera o pasen `max_ms`.

    Devuelve True si se cumplió y False si se acabó el tiempo. Reemplaza a las esperas
    fijas: si el dato llega en 0.5 s, se sigue a los 0.5 s y no a los 4 s.
    """
    transcurrido = 0
    while not condicion():
        if transcurrido >= max_ms:
            return False
        await asyncio.sleep(paso_ms / 1000)
        transcurrido += paso_ms
    return True
