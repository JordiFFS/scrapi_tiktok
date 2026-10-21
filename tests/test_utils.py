"""
Pruebas de app/utils/: funciones puras (formato, normalizadores, redes, texto, esperas, cronómetro).
"""
import asyncio
import json
import logging

from app.utils.cronometro import Cronometro
from app.utils.esperas import esperar_hasta
from app.utils.formato import ahora_iso, anonimizar, fecha_iso
from app.utils.normalizadores import (
    normalizar_comentario,
    normalizar_perfil,
    normalizar_video,
    normalizar_video_busqueda,
)
from app.utils.redes_sociales import detectar_redes
from app.utils.texto import generar_hashtags, sin_tildes, sin_tildes_conservando_enie, texto_para_embedding
from tests.conftest import item_tiktok


# ---------- formato ----------

def test_anonimizar_es_hash_corto_y_estable():
    h = anonimizar("usuario_x")
    assert len(h) == 12 and h == anonimizar("usuario_x")
    assert h != anonimizar("usuario_y")
    assert "usuario" not in h


def test_anonimizar_vacio():
    assert anonimizar(None) is None and anonimizar("") is None


def test_fecha_iso():
    assert fecha_iso(1728584400) == "2024-10-10T18:20:00+00:00"
    assert fecha_iso("1728584400") == "2024-10-10T18:20:00+00:00"
    assert fecha_iso(None) is None and fecha_iso("abc") is None


def test_ahora_iso_en_utc():
    assert ahora_iso().endswith("+00:00")


# ---------- normalizadores ----------

def _pagina_perfil(user: dict, stats: dict) -> str:
    return json.dumps({"__DEFAULT_SCOPE__": {"webapp.user-detail": {"userInfo": {"user": user, "stats": stats}}}})


def test_normalizar_perfil_completo():
    raw = _pagina_perfil(
        {"uniqueId": "jordifiallos", "nickname": "Jordi", "signature": "IG: @jordi.f",
         "avatarLarger": "https://a.jpg", "verified": False, "privateAccount": False,
         "bioLink": {"link": "https://youtube.com/@jordif"}},
        {"followerCount": 74, "followingCount": 10, "heartCount": 500, "videoCount": 7},
    )
    p = normalizar_perfil(raw)
    assert p["usuario"] == "jordifiallos" and p["seguidores"] == 74 and p["total_videos"] == 7
    assert p["enlace_bio"] == "https://youtube.com/@jordif"
    assert p["redes_en_biografia"] == {"instagram": "jordi.f", "youtube": "jordif"}


def test_normalizar_perfil_sin_bio():
    p = normalizar_perfil(_pagina_perfil({"uniqueId": "a"}, {}))
    assert p["enlace_bio"] is None and p["redes_en_biografia"] == {} and p["seguidores"] is None


def test_normalizar_perfil_invalido_devuelve_none():
    assert normalizar_perfil("no es json") is None
    assert normalizar_perfil("{}") is None                       # página de captcha / bloqueo
    assert normalizar_perfil(json.dumps({"__DEFAULT_SCOPE__": {}})) is None


def test_normalizar_video():
    v = normalizar_video(item_tiktok(2), "jordifiallos")
    assert v["url"] == "https://www.tiktok.com/@jordifiallos/video/7000000000000000002"
    assert v["fecha"] == "2024-10-10T18:20:00+00:00"
    assert v["hashtags"] == ["uñas", "fyp"]
    assert v["estadisticas"] == {"vistas": 3000, "likes": 200, "comentarios": 2, "compartidos": 1, "guardados": 2}
    assert v["comentarios"] == [] and v["duracion_seg"] == 15 and v["musica"] == "sonido original"


def test_normalizar_video_con_campos_faltantes():
    v = normalizar_video({"id": "1"}, "u")
    assert v["portada"] is None and v["hashtags"] == [] and v["estadisticas"]["vistas"] is None


def test_normalizar_video_busqueda_muestra_creador():
    v = normalizar_video_busqueda(item_tiktok(1, "creador1"))
    assert v["creador"] == {"usuario": "creador1", "nombre": "Creador1", "verificado": False, "seguidores": 501}
    assert "/@creador1/video/" in v["url"]


def test_normalizar_comentario_anonimiza_autor():
    c = normalizar_comentario({"cid": "9", "text": "hola", "create_time": 1728584400, "digg_count": 3,
                               "reply_comment_total": 1, "user": {"unique_id": "persona_real"}})
    assert c["autor_anonimo"] == anonimizar("persona_real")
    assert "persona_real" not in json.dumps(c)
    assert c["texto"] == "hola" and c["likes"] == 3 and c["respuestas"] == 1


# ---------- redes sociales ----------

def test_detectar_redes_prefijos():
    assert detectar_redes("IG: @jordi.fiallos | yt: jordif") == {"instagram": "jordi.fiallos", "youtube": "jordif"}
    assert detectar_redes("mi insta es @ana_23") == {"instagram": "ana_23"}
    assert detectar_redes("X: @jordi") == {"x": "jordi"}
    assert detectar_redes("FB: mipagina") == {"facebook": "mipagina"}


def test_detectar_redes_enlaces():
    assert detectar_redes(None, "https://instagram.com/ana.") == {"instagram": "ana"}
    assert detectar_redes("twitter.com/pepe facebook.com/pepe.oficial") == {"x": "pepe", "facebook": "pepe.oficial"}


def test_detectar_redes_sin_falsos_positivos():
    assert detectar_redes("") == {} and detectar_redes(None, None) == {}
    assert detectar_redes("me gusta el box y la música") == {}
    assert detectar_redes("youtube channel abajo") == {}
    # palabras que empiezan como un prefijo ("ig", "insta") no son cuentas
    assert detectar_redes("igualdad en la iglesia, instalaciones eléctricas") == {}
    # dominios que terminan en "x" y rutas que no son cuentas
    assert detectar_redes(None, "https://www.netflix.com/title/123") == {}
    assert detectar_redes(None, "https://youtube.com/watch?v=abc") == {}
    assert detectar_redes(None, "https://www.instagram.com/reel/abc") == {}


def test_detectar_redes_nombre_completo_de_la_red():
    assert detectar_redes("Instagram: @jordi") == {"instagram": "jordi"}
    assert detectar_redes(None, "https://www.x.com/pepe") == {"x": "pepe"}


# ---------- texto ----------

def test_sin_tildes():
    assert sin_tildes("uñas acrílicas") == "unas acrilicas"
    assert sin_tildes_conservando_enie("uñas acrílicas") == "uñas acrilicas"


def test_generar_hashtags():
    assert generar_hashtags("uñas acrílicas", 3) == ["uñasacrilicas", "unasacrilicas", "uñas"]
    assert generar_hashtags("uñas", 3) == ["uñas", "unas"]
    assert generar_hashtags("uñas para boda", 3) == ["uñasboda", "unasboda", "uñas"]
    assert generar_hashtags("pan casero", 3) == ["pancasero", "pan", "casero"]   # sin ñ/tildes no hay duplicados
    # 3+ palabras: juntas, parejas seguidas y cada palabra sola (la combinación completa casi nunca existe)
    assert generar_hashtags("fuerza ecuador cabello", 6) == [
        "fuerzaecuadorcabello", "fuerzaecuador", "ecuadorcabello", "fuerza", "ecuador", "cabello"]
    assert generar_hashtags("de la", 3) == []                          # solo palabras vacías
    assert generar_hashtags("de la", 3) == []
    assert len(generar_hashtags("uñas acrílicas", 2)) == 2


def test_texto_para_embedding_limpia():
    assert texto_para_embedding("Uñas rosas 💅 #uñas #fyp", ["uñas", "fyp"]) == "uñas rosas uñas"
    assert texto_para_embedding(None, []) == ""


# ---------- esperas ----------

def test_esperar_hasta_se_cumple_rapido():
    estado = {"listo": False}

    async def probar():
        asyncio.get_running_loop().call_later(0.05, estado.update, {"listo": True})
        return await esperar_hasta(lambda: estado["listo"], max_ms=2000, paso_ms=10)

    assert asyncio.run(probar()) is True


def test_esperar_hasta_se_acaba_el_tiempo():
    assert asyncio.run(esperar_hasta(lambda: False, max_ms=50, paso_ms=10)) is False


# ---------- cronómetro ----------

def test_cronometro_registra_etapas(caplog):
    with caplog.at_level(logging.INFO, logger="tiktok_api"):
        c = Cronometro("prueba")
        c.marca("etapa uno")
    assert "[prueba] etapa uno" in caplog.text
    assert c.total() >= 0
