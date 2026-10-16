# Proyecto: TikTok Data API (académico – Dispositivos Móviles)

## Qué es
API REST en Python que extrae datos **públicos** de perfiles de TikTok y los devuelve en JSON
para una app móvil que los mostrará en una interfaz gráfica.

## Estructura de carpetas
```
main.py                          crea la app, CORS y registra routers (único archivo en la raíz)
app/
  core/config.py                 configuración: HEADLESS, límites, caché, tiempos de espera
  routes/                        endpoints HTTP (ruta, parámetros, docs) → salud.py, perfil.py
  controllers/perfil_controller  caso de uso: caché → scraper (lock) → errores 404/502
  services/tiktok_scraper.py     Crawlee + Playwright; captura /api/post/item_list/, /api/comment/list/
                                 y el JSON #__UNIVERSAL_DATA_FOR_REHYDRATION__
  services/cache.py              caché en memoria con TTL (15 min)
  validations/usuario.py         normaliza el usuario (quita @, espacios, mayúsculas)
  schemas/perfil.py              modelos Pydantic = contrato JSON con la app móvil
  utils/normalizadores.py        JSON de TikTok → formato en español
  utils/formato.py               fechas ISO, anonimización SHA-256
```
Flujo: routes → validations → controllers → services → utils → schemas.
Cada archivo y función lleva docstring en español explicando qué hace.

## Entorno
- Shell: **fish** en Linux. Activar entorno: `source venv/bin/activate.fish`
- Instalar: `pip install -r requirements.txt && playwright install chromium`
- Ejecutar: `python main.py` → docs en http://localhost:8000/docs
- Modo oculto: `env HEADLESS=true python main.py`
- Crawlee 1.x: `ConcurrencySettings` necesita `min`, `desired` y `max_concurrency` coherentes.

## Reglas del proyecto
- **Solo datos públicos.** Nada que requiera iniciar sesión, cuentas privadas ni evasión agresiva de bloqueos.
- **Bajo volumen:** máximo 30 videos y 100 comentarios por post; no subir la concurrencia.
- **Privacidad (LOPDP Ecuador):** los autores de comentarios siempre anonimizados (`autor_anonimo`, hash SHA-256).
  No exponer nombres de usuario de terceros.
- **Sin archivos:** la API responde en JSON; no guardar datasets en disco salvo que se pida.
- Mantener los nombres de campos en **español** y la estructura JSON estable (la app móvil depende de ella).
  Si se cambia un campo, actualizar `app/schemas/perfil.py`, el normalizador y el ejemplo del README.

## Estructura de la respuesta
`GET /api/perfil/{usuario}` → el usuario se escribe sin `@` (si viene con `@`, espacios o
mayúsculas, el backend lo normaliza antes de extraer y de usar la caché).

```
desde_cache            bool
usuario                str     (normalizado, sin @)
fecha_extraccion       str     ISO 8601 UTC
perfil                 obj
  usuario, nombre, biografia, avatar, verificado, privado,
  seguidores, siguiendo, likes_totales, total_videos
total_videos_extraidos int
videos[]
  id, url, descripcion, fecha, portada, duracion_seg, musica, hashtags[]
  estadisticas { vistas, likes, comentarios, compartidos, guardados }
  comentarios[]
    id, texto, fecha, likes, respuestas, autor_anonimo (hash SHA-256, 12 caracteres)
```

Errores: `400` usuario vacío · `404` perfil no encontrado/privado/bloqueado · `502` fallo en la extracción.

## Limitaciones conocidas
Lento (1–3 min por consulta nueva), frágil ante cambios internos de TikTok, captchas/bloqueos,
comentarios solo de primer nivel, datos como foto del momento (sin historial), caché se pierde al reiniciar.

## Pendientes / ideas
- Esquema asíncrono para la app: `POST /api/extracciones` → `GET /api/extracciones/{id}` (estado y resultado).
- Interfaz gráfica móvil que consuma la API (emulador Android: `http://10.0.2.2:8000`).
- Responder y documentar en **español**.
