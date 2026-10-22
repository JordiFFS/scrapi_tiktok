"""
Pruebas de los endpoints (routes + controllers + schemas) por HTTP, con TikTok simulado.

Comprueban códigos de estado, el contrato JSON con la app móvil, la caché y la cola.
"""
import time

from app.core import config
from app.services import analisis


def _esperar(cliente, id_, max_seg=5) -> dict:
    """Consulta GET /api/extracciones/{id} como lo haría la app, hasta que termine."""
    for _ in range(int(max_seg / 0.05)):
        datos = cliente.get(f"/api/extracciones/{id_}").json()
        if datos["estado"] in ("completada", "error"):
            return datos
        time.sleep(0.05)
    raise AssertionError(f"la extracción no terminó: {datos}")


# ---------- salud y documentación ----------

def test_salud(cliente):
    r = cliente.get("/api/salud")
    assert r.status_code == 200 and r.json() == {"estado": "ok"}


def test_docs_y_openapi(cliente):
    assert cliente.get("/docs").status_code == 200
    rutas = cliente.get("/openapi.json").json()["paths"]
    assert {"/api/salud", "/api/perfil/{usuario}", "/api/busqueda",
            "/api/extracciones", "/api/extracciones/{id_extraccion}"} <= set(rutas)


def test_cors(cliente):
    r = cliente.get("/api/salud", headers={"Origin": "http://10.0.2.2"})
    assert r.headers["access-control-allow-origin"] == "*"


# ---------- GET /api/perfil/{usuario} ----------

def test_perfil_ok_y_contrato(cliente):
    r = cliente.get("/api/perfil/@JordiFiallos", params={"max_videos": 2})
    assert r.status_code == 200
    d = r.json()
    assert d["desde_cache"] is False and d["usuario"] == "jordifiallos"
    assert set(d) == {"desde_cache", "usuario", "fecha_extraccion", "perfil", "total_videos_extraidos", "videos"}
    assert d["total_videos_extraidos"] == 2 == len(d["videos"])
    v = d["videos"][0]
    assert set(v["estadisticas"]) == {"vistas", "likes", "comentarios", "compartidos", "guardados"}
    assert v["comentarios"][0]["autor_anonimo"] == "abcdef123456"
    assert {"enlace_bio", "redes_en_biografia"} <= set(d["perfil"])


def test_perfil_segunda_vez_sale_de_cache(cliente, tiktok_falso):
    cliente.get("/api/perfil/jordifiallos")
    d = cliente.get("/api/perfil/JORDIFIALLOS").json()      # mismo usuario normalizado
    assert d["desde_cache"] is True and tiktok_falso.llamadas_perfil == ["jordifiallos"]


def test_perfil_refrescar_ignora_cache(cliente, tiktok_falso):
    cliente.get("/api/perfil/jordifiallos")
    d = cliente.get("/api/perfil/jordifiallos", params={"refrescar": True}).json()
    assert d["desde_cache"] is False and len(tiktok_falso.llamadas_perfil) == 2


def test_perfil_sin_comentarios(cliente):
    d = cliente.get("/api/perfil/jordifiallos", params={"comentarios": False}).json()
    assert all(v["comentarios"] == [] for v in d["videos"])


def test_perfil_errores(cliente):
    assert cliente.get("/api/perfil/@").status_code == 400
    assert cliente.get("/api/perfil/noexiste").status_code == 404
    r = cliente.get("/api/perfil/explota")
    assert r.status_code == 502 and "navegador cerrado" in r.json()["detail"]


def test_extraccion_que_tarda_demasiado_da_502(cliente):
    # "lento" hace que los fakes lancen TimeoutError, como correr_con_limite al agotarse el tiempo
    r = cliente.get("/api/perfil/lento")
    assert r.status_code == 502 and "superó" in r.json()["detail"]
    r = cliente.get("/api/busqueda", params={"q": "lento"})
    assert r.status_code == 502 and "superó" in r.json()["detail"]


def test_perfil_limites_de_parametros(cliente):
    assert cliente.get("/api/perfil/x", params={"max_videos": 0}).status_code == 422
    assert cliente.get("/api/perfil/x", params={"max_videos": config.VIDEOS_MAXIMO + 1}).status_code == 422
    assert cliente.get("/api/perfil/x", params={"max_comentarios": config.COMENTARIOS_MAXIMO + 1}).status_code == 422


# ---------- GET /api/busqueda ----------

def test_busqueda_ok_y_contrato(cliente, tiktok_falso):
    r = cliente.get("/api/busqueda", params={"q": "#Uñas Acrílicas", "max_resultados": 3})
    assert r.status_code == 200
    d = r.json()
    assert d["consulta"] == "uñas acrílicas" and d["desde_cache"] is False
    assert tiktok_falso.llamadas_busqueda == [["uñasacrilicas", "unasacrilicas", "uñas", "unas", "acrilicas"]]
    assert d["total_candidatos"] == 6 and d["total_resultados"] == 3 == len(d["resultados"])
    totales = [v["puntaje"]["total"] for v in d["resultados"]]
    assert totales == sorted(totales, reverse=True)
    assert all(v["creador"]["usuario"] != "otro" for v in d["resultados"])   # el de pan queda fuera
    assert d["resultados"][0]["comentarios"] == []


def test_busqueda_cache(cliente, tiktok_falso):
    cliente.get("/api/busqueda", params={"q": "uñas"})
    assert cliente.get("/api/busqueda", params={"q": "  UÑAS "}).json()["desde_cache"] is True
    assert len(tiktok_falso.llamadas_busqueda) == 1


def test_busqueda_otro_max_resultados_sale_de_cache(cliente, tiktok_falso):
    cliente.get("/api/busqueda", params={"q": "uñas", "max_resultados": 2})
    d = cliente.get("/api/busqueda", params={"q": "uñas", "max_resultados": 4}).json()
    assert d["desde_cache"] is True and d["total_resultados"] == 4 == len(d["resultados"])
    assert len(tiktok_falso.llamadas_busqueda) == 1


def test_busqueda_errores(cliente):
    assert cliente.get("/api/busqueda", params={"q": "a"}).status_code == 400
    assert cliente.get("/api/busqueda", params={"q": "de la"}).status_code == 400   # sin hashtags posibles
    assert cliente.get("/api/busqueda").status_code == 422
    assert cliente.get("/api/busqueda", params={"q": "uñas", "max_resultados": 0}).status_code == 422
    r = cliente.get("/api/busqueda", params={"q": "vacio"})
    assert r.status_code == 404 and "limitando" in r.json()["detail"]
    assert cliente.get("/api/busqueda", params={"q": "explota"}).status_code == 502


# ---------- /api/analisis ----------

def test_analisis_ok_y_contrato(cliente):
    r = cliente.get("/api/analisis/@Jordifiallos?max_videos=2")
    assert r.status_code == 200
    d = r.json()
    assert d["usuario"] == "jordifiallos" and d["desde_cache"] is False
    assert set(d["big5_creador"]) == {"apertura", "responsabilidad", "extraversion", "amabilidad", "neuroticismo"}
    assert set(d["comentarios"]) == {"total_analizados", "sentimiento", "emociones"}
    assert set(d["modelos"]) == {"big5", "traduccion", "sentimiento", "emociones"}
    assert d["nota"] and "fecha_analisis" in d and "advertencia" in d


def test_analisis_reutiliza_el_perfil_en_cache(cliente, tiktok_falso):
    cliente.get("/api/perfil/jordifiallos")
    assert cliente.get("/api/analisis/jordifiallos").json()["desde_cache"] is False
    assert cliente.get("/api/analisis/jordifiallos").json()["desde_cache"] is True
    assert tiktok_falso.llamadas_perfil == ["jordifiallos"]  # un solo scraping para todo


def test_analisis_refrescar_vuelve_a_extraer(cliente, tiktok_falso):
    cliente.get("/api/analisis/jordifiallos")
    assert cliente.get("/api/analisis/jordifiallos?refrescar=true").json()["desde_cache"] is False
    assert len(tiktok_falso.llamadas_perfil) == 2


def test_analisis_errores(cliente, monkeypatch):
    assert cliente.get("/api/analisis/noexiste").status_code == 404
    assert cliente.get("/api/analisis/explota").status_code == 502
    assert cliente.get("/api/analisis/x?max_videos=31").status_code == 422

    def sin_modelos(datos):
        raise OSError("sin internet para descargar el modelo")

    monkeypatch.setattr(analisis, "analizar_perfil", sin_modelos)
    r = cliente.get("/api/analisis/otro")
    assert r.status_code == 503 and "sin internet" in r.json()["detail"]


# ---------- /api/extracciones ----------

def test_extraccion_perfil_completa(cliente):
    r = cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "@Jordifiallos", "max_videos": 2})
    assert r.status_code == 202
    inicial = r.json()
    assert inicial["estado"] in ("pendiente", "en_proceso", "completada")
    assert inicial["parametros"]["usuario"] == "jordifiallos"
    fin = _esperar(cliente, inicial["id"])
    assert fin["estado"] == "completada" and fin["consultar_de_nuevo_en_seg"] is None
    assert fin["resultado"]["usuario"] == "jordifiallos" and fin["resultado"]["total_videos_extraidos"] == 2


def test_extraccion_busqueda_completa(cliente):
    r = cliente.post("/api/extracciones", json={"tipo": "busqueda", "q": "uñas", "max_resultados": 2})
    fin = _esperar(cliente, r.json()["id"])
    assert fin["estado"] == "completada" and len(fin["resultado"]["resultados"]) == 2
    assert "puntaje" in fin["resultado"]["resultados"][0]


def test_extraccion_pendiente_posicion_y_duplicado(cliente, tiktok_falso):
    tiktok_falso.demora = 0.4
    a = cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "uno"}).json()
    b = cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "dos"}).json()
    b2 = cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "DOS"}).json()
    assert b2["id"] == b["id"]                                  # no repite el trabajo
    assert b["estado"] == "pendiente" and b["posicion_en_cola"] == 1
    assert b["consultar_de_nuevo_en_seg"] == config.EXTRACCIONES_SUGERENCIA_CONSULTA_SEG
    assert cliente.get(f"/api/extracciones/{a['id']}").json()["estado"] == "en_proceso"
    assert _esperar(cliente, b["id"])["estado"] == "completada"


def test_extraccion_refrescar_no_se_une_a_una_normal(cliente, tiktok_falso):
    tiktok_falso.demora = 0.4
    cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "uno"})
    normal = cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "dos"}).json()
    nueva = cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "dos", "refrescar": True}).json()
    assert nueva["id"] != normal["id"]
    assert _esperar(cliente, nueva["id"])["resultado"]["desde_cache"] is False


def test_extraccion_desde_cache_nace_completada(cliente):
    cliente.get("/api/perfil/jordifiallos")
    d = cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "jordifiallos"}).json()
    assert d["estado"] == "completada" and d["resultado"]["desde_cache"] is True


def test_extraccion_errores_dentro_de_la_tarea(cliente):
    no = cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "noexiste"}).json()
    ex = cliente.post("/api/extracciones", json={"tipo": "busqueda", "q": "explota"}).json()
    assert _esperar(cliente, no["id"])["error"]["codigo"] == 404
    assert _esperar(cliente, ex["id"])["error"]["codigo"] == 502


def test_extraccion_solicitudes_invalidas(cliente):
    assert cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "@"}).status_code == 400
    assert cliente.post("/api/extracciones", json={"tipo": "busqueda", "q": "a"}).status_code == 400
    assert cliente.post("/api/extracciones", json={"tipo": "otro"}).status_code == 422
    assert cliente.post("/api/extracciones", json={"tipo": "perfil"}).status_code == 422
    assert cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "x", "max_videos": 31}).status_code == 422


def test_extraccion_cola_llena_429(cliente, tiktok_falso):
    tiktok_falso.demora = 1
    codigos = [cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": f"u{i}"}).status_code
               for i in range(config.EXTRACCIONES_MAX_EN_COLA + 2)]
    assert codigos[: config.EXTRACCIONES_MAX_EN_COLA + 1] == [202] * (config.EXTRACCIONES_MAX_EN_COLA + 1)
    assert codigos[-1] == 429      # 1 en proceso + 10 pendientes; la siguiente se rechaza


def test_extraccion_inexistente_404(cliente):
    assert cliente.get("/api/extracciones/noexiste123").status_code == 404


def test_extraccion_analisis(cliente):
    r = cliente.post("/api/extracciones", json={"tipo": "analisis", "usuario": "@Jordifiallos", "max_videos": 2})
    assert r.status_code == 202 and r.json()["tipo"] == "analisis"
    fin = _esperar(cliente, r.json()["id"])
    assert fin["estado"] == "completada" and "big5_creador" in fin["resultado"]
    # La segunda vez nace completada desde la caché del análisis
    d = cliente.post("/api/extracciones", json={"tipo": "analisis", "usuario": "jordifiallos", "max_videos": 2}).json()
    assert d["estado"] == "completada" and d["resultado"]["desde_cache"] is True


def test_extraccion_analisis_y_perfil_no_se_mezclan(cliente, tiktok_falso):
    tiktok_falso.demora = 0.3
    perfil = cliente.post("/api/extracciones", json={"tipo": "perfil", "usuario": "uno"}).json()
    analisis_ = cliente.post("/api/extracciones", json={"tipo": "analisis", "usuario": "uno"}).json()
    assert perfil["id"] != analisis_["id"]
    assert "videos" in _esperar(cliente, perfil["id"])["resultado"]
    assert "big5_creador" in _esperar(cliente, analisis_["id"])["resultado"]
