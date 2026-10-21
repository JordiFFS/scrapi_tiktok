"""
Detecta las redes sociales que el DUEÑO del perfil escribió públicamente en su biografía
o en su enlace de bio.

Solo se lee lo que la persona publicó. No se buscan cuentas en otras redes ni se adivinan
identidades: eso sería vincular datos personales sin consentimiento (LOPDP).

Reconoce dos formas de escribirlo:
    - Enlaces:  instagram.com/usuario, youtube.com/@canal, x.com/usuario, facebook.com/pagina
    - Prefijos: "IG: @usuario", "insta usuario", "YT: @canal", "X: @usuario", "FB: pagina"
"""
import re

# Nombre de usuario: empieza con letra, número o "_" y puede tener punto y guion
# (así "youtube.com/watch" no se lee como el usuario ".com")
_NOMBRE = r"@?([A-Za-z0-9_][A-Za-z0-9._-]{1,49})"
# Palabra de enlace opcional entre la red y el usuario: "mi insta ES @usuario", "IG EN @usuario"
_CONECTOR = r"(?:(?:es|is|en)\s+)?"

# Evita que el dominio sea el final de otro ("netflix.com" no es "x.com"); sí acepta "www."
_INICIO_DOMINIO = r"(?<![A-Za-z0-9-])"
# Prefijo seguido de fin de palabra ("igualdad" no es "ig") y separador opcional
_SEPARADOR = r"\b\s*[:：\-]?\s*"

# red -> patrones; el primer grupo de cada patrón es el nombre de usuario.
# En las alternativas va primero la palabra larga ("instagram" antes que "insta").
_PATRONES: dict[str, list[re.Pattern]] = {
    "instagram": [
        re.compile(_INICIO_DOMINIO + r"instagram\.com/" + _NOMBRE, re.I),
        re.compile(r"\b(?:instagram|insta|ig)" + _SEPARADOR + _CONECTOR + _NOMBRE, re.I),
    ],
    "youtube": [
        re.compile(_INICIO_DOMINIO + r"youtube\.com/(?:@|c/|channel/|user/)?([A-Za-z0-9._-]{2,50})", re.I),
        re.compile(r"\b(?:youtube|yt)" + _SEPARADOR + _CONECTOR + _NOMBRE, re.I),
    ],
    "x": [
        re.compile(_INICIO_DOMINIO + r"(?:twitter|x)\.com/" + _NOMBRE, re.I),
        # "x" solo con dos puntos ("X: @usuario"), para no confundirlo con texto normal
        re.compile(r"(?:\btwitter" + _SEPARADOR + r"|(?<![A-Za-z0-9])x\s*[:：]\s*)" + _CONECTOR + _NOMBRE, re.I),
    ],
    "facebook": [
        re.compile(_INICIO_DOMINIO + r"(?:facebook|fb)\.com/" + _NOMBRE, re.I),
        re.compile(r"\b(?:facebook|fb)" + _SEPARADOR + _CONECTOR + _NOMBRE, re.I),
    ],
}

# Palabras que pueden seguir a un prefijo o dominio y no son nombres de usuario ("youtube channel", "fb page")
_NO_SON_USUARIOS = {
    "com", "www", "http", "https", "channel", "page", "link", "below", "abajo",
    "es", "mi", "me", "is", "and", "aqui", "aquí", "en", "por",
    # rutas de los sitios que no son cuentas (youtube.com/watch, instagram.com/reel/...)
    "watch", "shorts", "playlist", "embed", "results", "feed", "live", "hashtag",
    "reel", "reels", "stories", "explore", "share", "sharer", "intent", "home", "groups",
}


def detectar_redes(*textos: str | None) -> dict[str, str]:
    """
    Busca menciones a Instagram, YouTube, X y Facebook en los textos dados
    (normalmente la biografía y el enlace de bio).

    Devuelve un dict red -> usuario, solo con las redes encontradas, por ejemplo:
        detectar_redes("IG: @jordi.fiallos | yt: jordif") -> {"instagram": "jordi.fiallos", "youtube": "jordif"}
    Si no encuentra nada devuelve {}.
    """
    texto = " ".join(t for t in textos if t)
    redes: dict[str, str] = {}
    for red, patrones in _PATRONES.items():
        for patron in patrones:
            for coincidencia in patron.finditer(texto):
                nombre = coincidencia.group(1).rstrip("._-")
                if nombre.lower() not in _NO_SON_USUARIOS:
                    redes[red] = nombre
                    break
            if red in redes:
                break
    return redes
