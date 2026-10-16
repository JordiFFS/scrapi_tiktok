"""
Punto de entrada de la TikTok Data API.

Ejecutar:  python main.py   ->  http://localhost:8000/docs

Este archivo solo crea la aplicación, configura CORS y registra los endpoints.
El resto del código está organizado en la carpeta app/ (ver app/__init__.py).
"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import config
from app.routes import perfil, salud

app = FastAPI(
    title="TikTok Data API (académica)",
    description="Datos públicos de perfiles, posts, estadísticas y comentarios de TikTok.",
    version="1.1.0",
)

# Permite que la app móvil (o cualquier cliente) consuma la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Registro de endpoints (cada router vive en app/routes/)
app.include_router(salud.router)
app.include_router(perfil.router)


if __name__ == "__main__":
    # Sin reload: el modo reload puede romper Playwright
    uvicorn.run(app, host=config.HOST, port=config.PORT)
