"""
Paquete principal de la TikTok Data API.

Organización (cada carpeta tiene una sola responsabilidad):

    core/         Configuración global (variables de entorno, límites, caché).
    routes/       Endpoints HTTP: definen la URL, los parámetros y la documentación.
    controllers/  Lógica del caso de uso: une validación + caché + scraper y decide los errores.
    services/     Trabajo "pesado" o externo: el scraper de TikTok y la caché en memoria.
    validations/  Reglas para limpiar y validar lo que envía el usuario.
    schemas/      Modelos Pydantic que describen el JSON de respuesta (contrato con la app móvil).
    utils/        Funciones pequeñas y puras: convertir el JSON de TikTok, fechas, anonimización.

Flujo de una petición:
    routes  ->  validations  ->  controllers  ->  services (caché / scraper)  ->  utils  ->  schemas
"""
