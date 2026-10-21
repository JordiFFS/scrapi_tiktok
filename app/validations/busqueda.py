"""
Validación del texto de búsqueda que escribe la persona en la app.
"""
import re

from fastapi import HTTPException

from app.utils.texto import generar_hashtags

LARGO_MINIMO = 2
LARGO_MAXIMO = 60


def normalizar_consulta(consulta: str) -> str:
    """
    Limpia la búsqueda: quita "#", espacios repetidos y pasa a minúsculas.

        "  #Uñas   Acrílicas " -> "uñas acrílicas"

    Lanza 400 si queda muy corta, muy larga, sin letras/números o solo con palabras
    vacías ("de la"), porque de ella no sale ningún hashtag que visitar.
    """
    limpia = re.sub(r"\s+", " ", consulta.replace("#", " ")).strip().lower()
    if not re.search(r"\w", limpia) or len(limpia) < LARGO_MINIMO:
        raise HTTPException(status_code=400, detail=f"La búsqueda debe tener al menos {LARGO_MINIMO} caracteres.")
    if len(limpia) > LARGO_MAXIMO:
        raise HTTPException(status_code=400, detail=f"La búsqueda no puede pasar de {LARGO_MAXIMO} caracteres.")
    if not generar_hashtags(limpia, 1):
        raise HTTPException(
            status_code=400,
            detail="La búsqueda necesita al menos una palabra con contenido (no solo 'de', 'la', 'para'...).",
        )
    return limpia
