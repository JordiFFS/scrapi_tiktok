"""
Pruebas de app/validations/: limpieza del usuario y de la búsqueda.
"""
import pytest
from fastapi import HTTPException

from app.validations.busqueda import normalizar_consulta
from app.validations.usuario import normalizar_usuario


@pytest.mark.parametrize("entrada", ["MiUsuario", "@miusuario", " @MiUsuario ", "miusuario"])
def test_normalizar_usuario(entrada):
    assert normalizar_usuario(entrada) == "miusuario"


@pytest.mark.parametrize("entrada", ["", "   ", "@", " @ "])
def test_normalizar_usuario_vacio_da_400(entrada):
    with pytest.raises(HTTPException) as e:
        normalizar_usuario(entrada)
    assert e.value.status_code == 400


def test_normalizar_consulta():
    assert normalizar_consulta("  #Uñas   Acrílicas ") == "uñas acrílicas"


@pytest.mark.parametrize("entrada", ["", "a", "###", "  ", "x" * 61, "!!", "de la"])
def test_normalizar_consulta_invalida_da_400(entrada):
    with pytest.raises(HTTPException) as e:
        normalizar_consulta(entrada)
    assert e.value.status_code == 400
