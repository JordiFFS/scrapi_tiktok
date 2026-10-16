# TikTok Data API (uso académico)

API REST en Python que extrae datos **públicos** de un perfil de TikTok con **Crawlee + Playwright** y los devuelve en **JSON** (sin guardar archivos), lista para consumir desde una interfaz gráfica.

## Instalación

```bash
python -m venv venv
source venv/bin/activate.fish   # fish  (bash: source venv/bin/activate · Windows: venv\Scripts\activate)
pip install -r requirements.txt
playwright install chromium
```

## Ejecutar

```bash
python main.py
```

- Documentación interactiva: http://localhost:8000/docs
- Prueba: http://localhost:8000/api/perfil/nombre_usuario?max_videos=5&max_comentarios=10

## Estructura

```
main.py                 punto de entrada (crea la app y registra endpoints)
app/
  core/          configuración (variables de entorno, límites, tiempos)
  routes/        endpoints HTTP
  controllers/   lógica de cada caso de uso
  services/      scraper de TikTok y caché
  validations/   limpieza/validación de entradas
  schemas/       modelos de la respuesta JSON
  utils/         normalizadores y funciones auxiliares
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/salud` | Verifica que la API esté activa |
| GET | `/api/perfil/{usuario}` | Perfil, últimos posts, estadísticas y comentarios (el usuario va con o sin `@`) |

Parámetros de `/api/perfil/{usuario}`:

| Parámetro | Por defecto | Descripción |
|---|---|---|
| `max_videos` | 10 (máx. 30) | Posts recientes a extraer |
| `comentarios` | true | Incluir comentarios |
| `max_comentarios` | 20 (máx. 100) | Comentarios por post |
| `refrescar` | false | Ignorar la caché de 15 min |

## Respuesta (ejemplo)

```json
{
  "desde_cache": false,
  "usuario": "nombre_usuario",
  "fecha_extraccion": "2026-10-16T14:00:00+00:00",
  "perfil": {
    "usuario": "nombre_usuario", "nombre": "Nombre", "biografia": "...",
    "avatar": "https://...", "verificado": true, "privado": false,
    "seguidores": 12500, "siguiendo": 80, "likes_totales": 340000, "total_videos": 120
  },
  "total_videos_extraidos": 1,
  "videos": [{
    "id": "7412345678901234567",
    "url": "https://www.tiktok.com/@nombre_usuario/video/7412345678901234567",
    "descripcion": "...", "fecha": "2026-10-10T18:20:00+00:00",
    "portada": "https://...", "duracion_seg": 32, "musica": "sonido original",
    "hashtags": ["ecuador", "quito"],
    "estadisticas": { "vistas": 45000, "likes": 3200, "comentarios": 150, "compartidos": 40, "guardados": 90 },
    "comentarios": [
      { "id": "...", "texto": "...", "fecha": "...", "likes": 12, "respuestas": 2, "autor_anonimo": "a1b2c3d4e5f6" }
    ]
  }]
}
```

## Consumir desde la interfaz

```javascript
const res = await fetch("http://localhost:8000/api/perfil/nombre_usuario?max_videos=5");
const datos = await res.json();
console.log(datos.perfil.seguidores, datos.videos);
```

Desde una app móvil en emulador Android usa `http://10.0.2.2:8000`; en un celular físico usa la IP local de tu PC (ej. `http://192.168.1.10:8000`).

## Notas

- La primera petición abre un navegador real: ~3 s para el perfil y ~2–7 s por cada video con comentarios (los videos sin comentarios no se abren). Las siguientes salen de la caché.
- Se abre una ventana de Chromium: si aparece un captcha, resuélvelo a mano. Para modo oculto: `HEADLESS=true` (TikTok lo bloquea con más frecuencia).
- Errores: `400` usuario vacío; `404` perfil inexistente, privado o bloqueado; `502` fallo durante la extracción.
- Los nombres de los campos internos de TikTok pueden cambiar; si algo deja de llegar, revisa la pestaña **Network** del navegador (`/api/post/item_list/`, `/api/comment/list/`).
- Uso académico: perfiles públicos, bajo volumen, autores de comentarios anonimizados (LOPDP Ecuador).
