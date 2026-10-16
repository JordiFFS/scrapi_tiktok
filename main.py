"""
API REST que expone los datos extraídos de TikTok en formato JSON.
Ejecutar:  python main.py   ->  http://localhost:8000/docs
"""
import asyncio
import time

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from scraper import extraer_perfil

app = FastAPI(
    title="TikTok Data API (académica)",
    description="Datos públicos de perfiles, posts, estadísticas y comentarios de TikTok.",
    version="1.0.0",
)

# Permite que tu interfaz gráfica (React, Vue, etc.) consuma la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

CACHE_SEGUNDOS = 15 * 60          # evita volver a extraer el mismo perfil seguido
_cache: dict[str, tuple[float, dict]] = {}
_lock = asyncio.Lock()            # una extracción a la vez (más respetuoso con TikTok)


@app.get("/api/salud")
async def salud():
    return {"estado": "ok"}


@app.get("/api/perfil/{usuario}")
async def obtener_perfil(
    usuario: str,
    max_videos: int = Query(10, ge=1, le=30, description="Cantidad de posts recientes"),
    comentarios: bool = Query(True, description="Incluir comentarios de cada post"),
    max_comentarios: int = Query(20, ge=0, le=100, description="Comentarios por post"),
    refrescar: bool = Query(False, description="Ignorar caché y volver a extraer"),
):
    # El usuario escribe el nombre tal cual; la "@" y los espacios se quitan aquí
    usuario = usuario.strip().lstrip("@").lower()
    if not usuario:
        raise HTTPException(status_code=400, detail="Debes indicar un nombre de usuario.")

    clave = f"{usuario}|{max_videos}|{comentarios}|{max_comentarios}"
    ahora = time.time()

    if not refrescar and clave in _cache and ahora - _cache[clave][0] < CACHE_SEGUNDOS:
        return {"desde_cache": True, **_cache[clave][1]}

    async with _lock:
        try:
            datos = await extraer_perfil(usuario, max_videos, comentarios, max_comentarios)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Error al extraer datos: {e}")

    if datos["perfil"] is None:
        raise HTTPException(
            status_code=404,
            detail="No se encontró el perfil, es privado o TikTok bloqueó la solicitud.",
        )

    _cache[clave] = (ahora, datos)
    return {"desde_cache": False, **datos}


if __name__ == "__main__":
    # Sin reload: en Windows el modo reload rompe Playwright
    uvicorn.run(app, host="0.0.0.0", port=8000)
