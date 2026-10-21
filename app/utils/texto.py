"""
Funciones de texto para la búsqueda: convertir lo que escribe la persona en hashtags
y preparar la descripción de un video para calcular su embedding.
"""
import re
import unicodedata

# Palabras que no aportan al hashtag ("uñas PARA boda" -> #uñasboda).
# "unas" NO está a propósito: mucha gente escribe "unas" en vez de "uñas".
_PALABRAS_VACIAS = {
    "de", "del", "la", "las", "el", "los", "un", "una", "unos", "y", "o", "en", "con",
    "para", "por", "mi", "mis", "tu", "tus", "su", "sus", "a", "al", "que", "como",
}

# Hashtags genéricos que se usan para ganar alcance y no dicen nada del contenido
_HASHTAGS_GENERICOS = {
    "fyp", "foryou", "foryoupage", "parati", "paratii", "viral", "viralvideo", "xyzbca",
    "trending", "tiktok", "fy", "fypシ", "fypage", "4u", "capcut",
}


def sin_tildes(texto: str) -> str:
    """Quita tildes y convierte la ñ en n: "uñas acrílicas" -> "unas acrilicas"."""
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def sin_tildes_conservando_enie(texto: str) -> str:
    """Quita tildes de las vocales pero deja la ñ: "uñas acrílicas" -> "uñas acrilicas"."""
    return "".join(sin_tildes(c) if c not in "ñÑ" else c for c in texto)


def generar_hashtags(consulta: str, maximo: int) -> list[str]:
    """
    Convierte la búsqueda en hashtags a visitar, del más específico al más general:
    todas las palabras juntas, luego cada pareja seguida y al final cada palabra sola.

        "uñas acrílicas"         -> ["uñasacrilicas", "unasacrilicas", "uñas", "unas", "acrilicas"]
        "uñas"                   -> ["uñas", "unas"]
        "fuerza ecuador cabello" -> ["fuerzaecuadorcabello", "fuerzaecuador", "ecuadorcabello",
                                     "fuerza", "ecuador", "cabello"]

    Con 3+ palabras la combinación completa casi nunca existe como hashtag; las parejas y
    las palabras sueltas sí, y el ranking con embeddings se encarga de dejar arriba lo que
    habla del tema completo. El buscador deja de visitar hashtags al juntar suficientes videos.

    Las tildes de las vocales se quitan porque así escribe la gente los hashtags
    (#uñasacrilicas, no #uñasacrílicas); la ñ se conserva y luego se prueba sin ella,
    porque en TikTok #uñas y #unas son hashtags distintos.
    """
    palabras = [p for p in re.findall(r"\w+", consulta.lower()) if p not in _PALABRAS_VACIAS]
    variantes = []
    if len(palabras) > 1:
        variantes.append("".join(palabras))
    if len(palabras) > 2:
        variantes += [a + b for a, b in zip(palabras, palabras[1:])]
    variantes += palabras
    candidatos = []
    for v in variantes:
        con_enie = sin_tildes_conservando_enie(v)
        candidatos += [con_enie, sin_tildes(con_enie)]
    return list(dict.fromkeys(candidatos))[:maximo]  # sin repetidos, en orden


def texto_para_embedding(descripcion: str | None, hashtags: list[str]) -> str:
    """
    Arma el texto que "lee" el modelo de embeddings para un video.

    Quita "#", hashtags genéricos (#fyp, #viral...), emojis y mayúsculas porque confunden
    al modelo (medido: con emoji la similitud bajaba de 0.82 a 0.39 en MiniLM):
        "Uñas rosas 💅 #uñas #fyp"  ->  "uñas rosas uñas"
    """
    desc = re.sub(r"#\S+", " ", descripcion or "")  # los hashtags se agregan limpios abajo
    etiquetas = [h for h in hashtags if h.lower() not in _HASHTAGS_GENERICOS]
    texto = " ".join([desc, *etiquetas]).lower()
    texto = re.sub(r"[^\w\s.,!?¿¡'-]", " ", texto)  # fuera emojis y símbolos
    return re.sub(r"\s+", " ", texto).strip()
