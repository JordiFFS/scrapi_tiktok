"""
Cronómetro para medir cuánto tarda cada etapa de una extracción.

Escribe en la consola (logger "tiktok_api") líneas como:

    [jordifiallos] perfil cargado            +6.2s  (total 6.2s)
    [jordifiallos] videos listos (5)         +3.1s  (total 9.3s)

Sirve para saber dónde se va el tiempo antes de optimizar.
"""
import logging
import time

log = logging.getLogger("tiktok_api")


class Cronometro:
    def __init__(self, etiqueta: str):
        self.etiqueta = etiqueta
        self.inicio = self.ultimo = time.perf_counter()

    def marca(self, etapa: str) -> None:
        """Registra la etapa con el tiempo desde la marca anterior y el total acumulado."""
        ahora = time.perf_counter()
        log.info(
            "[%s] %-28s +%.1fs  (total %.1fs)",
            self.etiqueta, etapa, ahora - self.ultimo, ahora - self.inicio,
        )
        self.ultimo = ahora

    def total(self) -> float:
        """Segundos transcurridos desde que se creó el cronómetro."""
        return time.perf_counter() - self.inicio
