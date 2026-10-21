# TikTok Data API (uso académico)

API REST en Python que extrae datos **públicos** de TikTok (perfiles, posts, estadísticas,
comentarios y búsqueda por tema) y los devuelve en **JSON** para una app móvil.
No guarda archivos: todo vive en memoria.

> ¿Cómo está hecho por dentro y qué herramientas usa? → [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md)

---

## 1. Requisitos

| Necesitas | Versión | Para qué |
|---|---|---|
| Python | 3.11 o superior (probado con 3.14) | Ejecutar la API |
| Conexión a internet | — | Abrir TikTok y descargar el modelo la primera vez |
| Espacio en disco | ~1.5 GB | Chromium de Playwright (~300 MB) + modelo de embeddings (~1 GB) |
| RAM | 4 GB libres recomendado | Navegador + modelo cargado |

## 2. Instalación (una sola vez)

```bash
# 1) Crear el entorno virtual
python -m venv venv

# 2) Activarlo (elige tu terminal)
source venv/bin/activate.fish     # fish
source venv/bin/activate          # bash / zsh
venv\Scripts\activate             # Windows

# 3) Instalar dependencias y el navegador Chromium que usa Playwright
pip install -r requirements.txt
playwright install chromium
```

## 3. Levantar la API

```bash
python main.py
```

Verás en consola `Uvicorn running on http://0.0.0.0:8000`. Luego comprueba:

| Qué | URL |
|---|---|
| ¿Está viva? | http://localhost:8000/api/salud → `{"estado":"ok"}` |
| Documentación interactiva (probar endpoints desde el navegador) | http://localhost:8000/docs |
| Perfil de prueba | http://localhost:8000/api/perfil/jordifiallos?max_videos=5 |
| Búsqueda de prueba | http://localhost:8000/api/busqueda?q=uñas |

**La primera vez** que arranca descarga el modelo de embeddings (~1 GB, a `~/.cache/fastembed`).
La API responde mientras tanto; la primera búsqueda espera a que termine la descarga.

Por defecto se abre una **ventana de Chromium** cuando se extrae algo: es normal. Si aparece un
captcha, resuélvelo a mano en esa ventana.

Para detener la API: **Ctrl+C** (si hay una extracción en curso, Crawlee pide un segundo Ctrl+C).

### Variables de entorno (opcionales)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `HEADLESS` | `false` | `true` = navegador oculto (TikTok lo bloquea con más frecuencia) |
| `PORT` | `8000` | Puerto de la API |
| `HOST` | `0.0.0.0` | Interfaz de red (`0.0.0.0` permite conectarse desde el celular) |
| `EXTRACCION_TIEMPO_MAX_SEG` | `180` | Tiempo máximo de una extracción; si se pasa, se cierra el navegador y responde `502` |
| `BLOQUEAR_RECURSOS` | `false` | `true` = no descarga imágenes/videos/fuentes (sin beneficio medido) |
| `MODELO_CACHE` | `~/.cache/fastembed` | Carpeta donde se guarda el modelo de embeddings |

```bash
env HEADLESS=true PORT=9000 python main.py     # fish
HEADLESS=true PORT=9000 python main.py         # bash / zsh
```

## 4. Conectar la app móvil

| Desde | URL base |
|---|---|
| Navegador en la misma PC | `http://localhost:8000` |
| Emulador de Android | `http://10.0.2.2:8000` |
| Celular físico (misma red Wi-Fi) | `http://<IP-de-tu-PC>:8000`, ej. `http://192.168.1.10:8000` |

Para el celular físico: averigua la IP con `ip addr` (Linux) o `ipconfig` (Windows) y permite el
puerto 8000 en el firewall si hace falta.

**Forma recomendada para la app:** usar las extracciones asíncronas (sección 6.3): la app recibe
un `id` al instante y consulta el estado, en vez de esperar 10–40 s con la conexión abierta.

## 5. Pruebas

```bash
pip install -r requirements-dev.txt
pytest              # 74 pruebas, ~6 s, SIN tocar TikTok (scrapers simulados)
pytest --tiktok     # además 2 pruebas reales: perfil jordifiallos y búsqueda #uñas (abre el navegador)
```

Las reales pueden fallar si TikTok está limitando las consultas: no es necesariamente un bug
(ver "Solución de problemas").

---

## 6. Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/salud` | Verifica que la API esté activa |
| GET | `/api/perfil/{usuario}` | Perfil, últimos posts, estadísticas y comentarios (usuario con o sin `@`) |
| GET | `/api/busqueda?q=...` | Mejores videos sobre un tema (hashtags públicos + ranking) |
| POST | `/api/extracciones` | **Recomendado para la app:** crea una extracción (perfil o búsqueda) y responde con un `id` |
| GET | `/api/extracciones/{id}` | Estado de la extracción y, al terminar, su resultado |

### Errores

| Código | Cuándo |
|---|---|
| `400` | Usuario vacío, búsqueda muy corta/larga o solo con palabras como "de la" |
| `404` | Perfil inexistente/privado/bloqueado, o ningún hashtag devolvió videos |
| `422` | Parámetro fuera de rango (ej. `max_videos=50`) |
| `429` | Más de 10 extracciones esperando en la cola |
| `502` | Falló la extracción o superó `EXTRACCION_TIEMPO_MAX_SEG` |

### 6.1 Perfil — `GET /api/perfil/{usuario}`

| Parámetro | Por defecto | Descripción |
|---|---|---|
| `max_videos` | 10 (máx. 30) | Posts recientes a extraer |
| `comentarios` | true | Incluir comentarios |
| `max_comentarios` | 20 (máx. 100) | Comentarios por post (solo primer nivel) |
| `refrescar` | false | Ignorar la caché de 15 min |

```json
{
  "desde_cache": false,
  "usuario": "nombre_usuario",
  "fecha_extraccion": "2026-10-16T14:00:00+00:00",
  "perfil": {
    "usuario": "nombre_usuario", "nombre": "Nombre", "biografia": "...",
    "avatar": "https://...", "verificado": true, "privado": false,
    "seguidores": 12500, "siguiendo": 80, "likes_totales": 340000, "total_videos": 120,
    "enlace_bio": "https://linktr.ee/nombre_usuario",
    "redes_en_biografia": { "instagram": "nombre.usuario", "youtube": "MiCanal" }
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

- `autor_anonimo`: hash SHA-256 (12 caracteres) del autor del comentario; nunca se muestra quién comentó.
- `redes_en_biografia`: solo las redes que el dueño escribió en su bio o enlace (`instagram`, `youtube`, `x`, `facebook`).

### 6.2 Búsqueda por tema — `GET /api/busqueda?q=uñas acrílicas&max_resultados=10`

La búsqueda libre de TikTok exige iniciar sesión, así que se visitan páginas públicas de hashtags
derivadas de la consulta (`#uñasacrilicas`, `#unasacrilicas`, `#uñas`…), se juntan hasta 60 videos
y se ordenan por:

| Componente | Peso | Qué mide |
|---|---|---|
| `relevancia` | 0.5 | Similitud de significado con la búsqueda (modelo local de embeddings) |
| `interaccion` | 0.3 | (likes + comentarios + compartidos + guardados) / vistas |
| `alcance` | 0.2 | Vistas en escala logarítmica (10 M = 1.0) |

```json
{
  "desde_cache": false, "consulta": "uñas acrílicas",
  "hashtags_usados": ["uñasacrilicas", "unasacrilicas"],
  "fecha_extraccion": "2026-10-16T18:00:00+00:00",
  "total_candidatos": 60, "total_resultados": 10,
  "resultados": [{
    "id": "7094396577250381061", "url": "https://www.tiktok.com/@creador/video/7094396577250381061",
    "descripcion": "...", "hashtags": ["uñas", "uñasacrilicas"], "estadisticas": { "vistas": 2100000, "...": 0 },
    "comentarios": [],
    "creador": { "usuario": "creador", "nombre": "Nombre", "verificado": false, "seguidores": 15000 },
    "puntaje": { "relevancia": 0.79, "interaccion": 1.0, "alcance": 0.9, "total": 0.87 }
  }]
}
```

`max_resultados`: 10 por defecto (máx. 30). Cambiarlo no vuelve a abrir TikTok si la búsqueda está en caché.

### 6.3 Extracciones asíncronas (recomendado para la app)

```http
POST /api/extracciones
{"tipo": "perfil", "usuario": "jordifiallos", "max_videos": 10, "max_comentarios": 20}
{"tipo": "busqueda", "q": "uñas acrílicas", "max_resultados": 10}
```

Responde `202` al instante:

```json
{ "id": "b2d79cf7bd71", "tipo": "perfil", "estado": "pendiente", "posicion_en_cola": 1,
  "consultar_de_nuevo_en_seg": 3, "resultado": null, "error": null, "...": "..." }
```

Luego `GET /api/extracciones/b2d79cf7bd71` cada `consultar_de_nuevo_en_seg` segundos hasta que `estado` sea:
- `completada` → `resultado` trae exactamente lo mismo que `/api/perfil` o `/api/busqueda`.
- `error` → `error: {"codigo": 404, "detalle": "..."}` (mismos códigos que los endpoints directos).

Se procesa una extracción a la vez; si el dato está en caché nace `completada`; pedir dos veces lo
mismo devuelve el mismo `id`; los resultados se pueden consultar 30 min y se pierden al reiniciar.

```javascript
const API = "http://10.0.2.2:8000";   // emulador Android

async function extraer(solicitud) {
  let ext = await (await fetch(`${API}/api/extracciones`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(solicitud),
  })).json();
  while (ext.estado === "pendiente" || ext.estado === "en_proceso") {
    await new Promise(r => setTimeout(r, ext.consultar_de_nuevo_en_seg * 1000));
    ext = await (await fetch(`${API}/api/extracciones/${ext.id}`)).json();
  }
  if (ext.estado === "error") throw new Error(ext.error.detalle);
  return ext.resultado;
}
```

---

## 7. Tiempos esperados

| Operación | Tiempo aproximado |
|---|---|
| Respuesta desde caché (15 min) | instantánea |
| Perfil sin comentarios | ~5–7 s |
| Perfil con comentarios | ~3 s + 2–7 s por cada video que tenga comentarios |
| Búsqueda por tema | ~10–30 s (según cuántos hashtags existan) |
| Límite duro de cualquier extracción | 180 s (`EXTRACCION_TIEMPO_MAX_SEG`) |

## 8. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| La búsqueda da `404` incluso para temas comunes ("cabello") | TikTok está limitando las listas de hashtags (pasa tras ~8 búsquedas en 20 min) | Esperar 20–30 min; usar la caché; no repetir búsquedas seguidas |
| `404` en un perfil que sí existe | Captcha o bloqueo de TikTok | Usar `HEADLESS=false` y resolver el captcha en la ventana |
| `502 ... superó 180 s` | El navegador se trabó o TikTok no respondió | Reintentar; si se repite, reiniciar la API |
| Ctrl+C no detiene la API | Crawlee intercepta el primer Ctrl+C mientras extrae | Presionar Ctrl+C otra vez |
| `playwright ... Executable doesn't exist` | Falta el navegador | `playwright install chromium` |
| La primera búsqueda tarda mucho | Se está descargando el modelo (~1 GB) | Esperar; solo pasa la primera vez |
| Un campo deja de llegar | TikTok cambió su API interna | Revisar en el navegador la pestaña **Network** (`/api/post/item_list/`, `/api/comment/list/`) |

## 9. Reglas de uso

- Solo datos **públicos**: nada que requiera iniciar sesión, ni cuentas privadas.
- **Bajo volumen**: máximo 30 videos y 100 comentarios por post, una extracción a la vez.
- **Privacidad (LOPDP Ecuador)**: los autores de comentarios siempre van anonimizados. Los creadores
  de videos en la búsqueda sí se muestran (son autores públicos del contenido).
- Proyecto académico (Dispositivos Móviles).
