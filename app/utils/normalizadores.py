"""
Normalizadores: traducen el JSON interno de TikTok (en inglés, con muchos campos)
al formato limpio y en español que entrega la API.

Si TikTok cambia el nombre de un campo interno, normalmente solo hay que tocar este archivo.
"""
import json

from app.utils.formato import anonimizar, fecha_iso


def normalizar_perfil(raw: str) -> dict | None:
    """
    Extrae los datos del perfil desde el JSON incrustado en la página
    (<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">).

    Devuelve None si el JSON no tiene la forma esperada (perfil inexistente,
    privado sin datos o página de bloqueo/captcha).
    """
    try:
        info = json.loads(raw)["__DEFAULT_SCOPE__"]["webapp.user-detail"]["userInfo"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return None
    u, s = info.get("user", {}), info.get("stats", {})
    return {
        "usuario": u.get("uniqueId"),
        "nombre": u.get("nickname"),
        "biografia": u.get("signature"),
        "avatar": u.get("avatarLarger"),
        "verificado": u.get("verified"),
        "privado": u.get("privateAccount"),
        "seguidores": s.get("followerCount"),
        "siguiendo": s.get("followingCount"),
        "likes_totales": s.get("heartCount"),
        "total_videos": s.get("videoCount"),
    }


def normalizar_video(v: dict, usuario: str) -> dict:
    """
    Convierte un elemento de la respuesta /api/post/item_list/ en un video de la API.

    La lista "comentarios" se deja vacía; el scraper la llena después
    con lo que capture en la página de cada video.
    """
    st = v.get("stats", {})
    return {
        "id": v.get("id"),
        "url": f"https://www.tiktok.com/@{usuario}/video/{v.get('id')}",
        "descripcion": v.get("desc"),
        "fecha": fecha_iso(v.get("createTime")),
        "portada": (v.get("video") or {}).get("cover"),
        "duracion_seg": (v.get("video") or {}).get("duration"),
        "musica": (v.get("music") or {}).get("title"),
        "hashtags": [t.get("hashtagName") for t in v.get("textExtra") or [] if t.get("hashtagName")],
        "estadisticas": {
            "vistas": st.get("playCount"),
            "likes": st.get("diggCount"),
            "comentarios": st.get("commentCount"),
            "compartidos": st.get("shareCount"),
            "guardados": st.get("collectCount"),
        },
        "comentarios": [],
    }


def normalizar_comentario(c: dict) -> dict:
    """
    Convierte un elemento de la respuesta /api/comment/list/ en un comentario de la API.

    El autor NUNCA se expone: solo se guarda su hash en "autor_anonimo".
    """
    return {
        "id": c.get("cid"),
        "texto": c.get("text"),
        "fecha": fecha_iso(c.get("create_time")),
        "likes": c.get("digg_count"),
        "respuestas": c.get("reply_comment_total"),
        "autor_anonimo": anonimizar((c.get("user") or {}).get("unique_id")),
    }
