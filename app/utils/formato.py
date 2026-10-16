"""
Funciones auxiliares genéricas (no saben nada de TikTok ni de FastAPI).
"""
import hashlib
from datetime import datetime, timezone


def anonimizar(valor: str | None) -> str | None:
    """
    Convierte un identificador (ej. nombre de usuario) en un hash corto e irreversible.

    Se usa para cumplir la LOPDP: permite saber si dos comentarios son del mismo autor
    sin exponer quién es. Devuelve los primeros 12 caracteres del SHA-256, o None si no hay valor.
    """
    if not valor:
        return None
    return hashlib.sha256(valor.encode()).hexdigest()[:12]


def fecha_iso(timestamp) -> str | None:
    """
    Convierte un timestamp Unix (segundos, como los manda TikTok) a texto ISO 8601 en UTC.

    Ejemplo: 1728584400 -> "2024-10-10T18:20:00+00:00". Devuelve None si el valor no es válido.
    """
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def ahora_iso() -> str:
    """Fecha y hora actual en UTC, formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat()
