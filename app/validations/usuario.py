"""
Validaciones del nombre de usuario que envía la app.

Los rangos numéricos (max_videos, max_comentarios) los valida FastAPI con Query(ge=, le=)
directamente en app/routes/perfil.py; aquí va lo que necesita lógica propia.
"""
from fastapi import HTTPException


def normalizar_usuario(usuario: str) -> str:
    """
    Limpia el usuario tal como lo escribió la persona.

    La gente suele buscar por nombre sin "@", con espacios o mayúsculas. Todas estas
    entradas terminan en el mismo valor (y por tanto en la misma entrada de caché):

        "MiUsuario"  ->  "miusuario"
        "@miusuario" ->  "miusuario"
        " @MiUsuario " -> "miusuario"

    Lanza 400 si después de limpiar no queda nada.
    """
    limpio = usuario.strip().lstrip("@").lower()
    if not limpio:
        raise HTTPException(status_code=400, detail="Debes indicar un nombre de usuario.")
    return limpio
