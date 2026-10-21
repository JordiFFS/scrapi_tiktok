"""
Caché en memoria con tiempo de expiración (TTL).

Sirve para no volver a abrir el navegador si se pide el mismo perfil varias veces seguidas.
Se pierde al reiniciar el servidor (limitación conocida, ver CLAUDE.md).
"""
import time


class CacheMemoria:
    """Diccionario clave -> (momento_guardado, datos) que ignora entradas vencidas."""

    def __init__(self, ttl_segundos: int):
        """`ttl_segundos`: cuánto vive cada entrada antes de considerarse vencida."""
        self.ttl = ttl_segundos
        self._datos: dict[str, tuple[float, dict]] = {}

    def obtener(self, clave: str) -> dict | None:
        """Devuelve los datos guardados si existen y no han vencido; si no, None."""
        entrada = self._datos.get(clave)
        if entrada and time.time() - entrada[0] < self.ttl:
            return entrada[1]
        return None

    def guardar(self, clave: str, datos: dict) -> None:
        """Guarda (o reemplaza) los datos con la hora actual."""
        self._datos[clave] = (time.time(), datos)
