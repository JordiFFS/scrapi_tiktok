"""
Punto de entrada de la TikTok Data API.

Ejecutar:  python main.py   ->  http://localhost:8000/docs

Este archivo solo crea la aplicación, configura CORS y registra los endpoints.
El resto del código está organizado en la carpeta app/ (ver app/__init__.py).
"""
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import config
from app.routes import busqueda, extracciones, perfil, salud
from app.services import embeddings
from app.services.cola_extracciones import cola

# Muestra en consola los tiempos por etapa del scraper (logger "tiktok_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """
    Al arrancar: inicia el trabajador de la cola de extracciones y carga el modelo de
    embeddings en segundo plano (la API ya responde mientras tanto).
    """
    cola.iniciar()
    embeddings.cargar_en_segundo_plano()
    yield
    cola.detener()


app = FastAPI(
    title="TikTok Data API (académica)",
    description="Datos públicos de perfiles, posts, estadísticas y comentarios de TikTok.",
    version="1.3.0",
    lifespan=ciclo_de_vida,
)

# Permite que la app móvil (o cualquier cliente) consuma la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Registro de endpoints (cada router vive en app/routes/)
app.include_router(salud.router)
app.include_router(perfil.router)
app.include_router(busqueda.router)
app.include_router(extracciones.router)


if __name__ == "__main__":
    # Sin reload: el modo reload puede romper Playwright
    uvicorn.run(app, host=config.HOST, port=config.PORT)
