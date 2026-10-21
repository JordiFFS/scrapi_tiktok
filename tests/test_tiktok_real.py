"""
Pruebas REALES contra TikTok (abren el navegador). Solo corren con:

    pytest --tiktok

Se limitan a una extracción de perfil y una búsqueda (bajo volumen, ver CLAUDE.md).
Si fallan, puede ser TikTok limitando o un cambio interno de la página, no solo un bug.
"""
import asyncio

import pytest

from app.schemas.busqueda import RespuestaBusqueda
from app.schemas.perfil import RespuestaPerfil
from app.services import ranking, tiktok_busqueda, tiktok_scraper

pytestmark = pytest.mark.tiktok

USUARIO_PRUEBA = "jordifiallos"


def test_perfil_real():
    datos = asyncio.run(tiktok_scraper.extraer_perfil(USUARIO_PRUEBA, 5, True, 10))
    assert datos["perfil"] is not None, "TikTok no devolvió el perfil (¿bloqueo/captcha?)"
    assert datos["perfil"]["usuario"] == USUARIO_PRUEBA
    assert datos["total_videos_extraidos"] >= 1
    RespuestaPerfil(desde_cache=False, **datos)            # cumple el contrato con la app
    con_comentarios = [v for v in datos["videos"] if (v["estadisticas"]["comentarios"] or 0) > 0]
    if con_comentarios:
        assert any(v["comentarios"] for v in con_comentarios), "hay videos con comentarios pero no se extrajo ninguno"
        c = next(v for v in con_comentarios if v["comentarios"])["comentarios"][0]
        assert len(c["autor_anonimo"]) == 12


def test_busqueda_real():
    candidatos, usados = asyncio.run(tiktok_busqueda.buscar_candidatos(["uñas"], 30))
    assert candidatos, "ningún video (¿TikTok limitando? esperar unos minutos)"
    assert usados == ["uñas"]
    mejores = ranking.ordenar("uñas", candidatos, 5)        # usa el modelo de embeddings real
    RespuestaBusqueda(desde_cache=False, consulta="uñas", hashtags_usados=usados, fecha_extraccion="x",
                      total_candidatos=len(candidatos), total_resultados=len(mejores), resultados=mejores)
    assert all(v["creador"]["usuario"] for v in mejores)
