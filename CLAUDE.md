# Hyrox Analytics — CLAUDE.md

Dashboard personal de seguimiento de entrenamientos Hyrox. FastAPI + SQLite + HTML/JS vanilla.

## Infraestructura
- **Producción**: `/opt/hyrox`, servicio `hyrox-dashboard`, puerto 8003, `hyrox.mglzgsr.com`
- **Deploy**: push a `main` → GitHub Actions runner self-hosted → `git pull` + `pip install` + `systemctl restart`
- **DB**: `/opt/hyrox/data/hyrox.db`
- **Acceso**: Cloudflare Zero Trust Tunnel (sin login propio)
- **Servidor compartido** con `finances` y `family-plan` (mismo LXC)
- **Runner**: usuario `hyrox`, instalado en `/opt/hyrox/actions-runner`

## Archivos clave
- `main.py` — FastAPI app, todos los endpoints
- `database.py` — SQLite CRUD + queries de analytics
- `parser.py` — parser de export.xml de Apple Health (streaming, soporta ZIP)
- `frontend/index.html` — SPA completa (HTML + CSS + JS inline)

## Estructura Hyrox
- 8 rondas de: carrera (1km oficial, 600m en entrenamiento) + estación
- Estaciones en orden fijo: SkiErg → Sled Push → Sled Pull → Burpee Broad Jump → Rowing → Farmers Carry → Sandbag Lunges → Wall Balls
- El Apple Watch graba como `HKWorkoutActivityTypeHighIntensityIntervalTraining`
- Los splits se guardan como `HKWorkoutEventTypeMarker`

## Import de sesiones
- Export desde iPhone: Salud → foto de perfil → Exportar datos de salud
- En el dashboard: + Importar → introducir ruta del export.xml en el servidor
- El parser hace streaming del XML (2.7GB) sin cargarlo en memoria
- Los domingos se pre-seleccionan automáticamente
- Cada sesión se configura: tipo (completa/entrenamiento), estación inicial, splits run/station/omitir

## Base de datos — tablas
- **sessions**: `id, date, duration_s, session_type (full/training), notes, created_at`
- **segments**: `id, session_id, position, type (run/station), label, duration_s, distance_m`

## API endpoints
```
GET    /api/sessions
GET    /api/sessions/{id}
POST   /api/sessions
PUT    /api/sessions/{id}
DELETE /api/sessions/{id}
GET    /api/sessions/{id}/heatmap
POST   /api/import/parse-path     ← ruta local en el servidor (rápido)
POST   /api/import/parse          ← upload directo (lento con archivos grandes)
GET    /api/browse?path=          ← explorador de archivos del servidor
GET    /api/stats/stations
GET    /api/stats/stations/{label}
GET    /api/stats/trends
GET    /api/stats/runs
GET    /api/stats/runs/{distance_m}
GET    /api/stats/estimate        ← estimado carrera completa
DELETE /api/database              ← reset completo
```

## Dashboard
- **KPIs**: sesiones totales, última completa, mejor tiempo, promedio (solo carreras completas)
- **Heatmap última sesión**: bloques coloreados vs media personal (verde=mejor, rojo=peor)
- **Tiempo total por sesión**: gráfica con todas las sesiones (naranja=completa, azul=entrenamiento)
- **Estimado carrera completa**: bloques medios + mejores tiempos para los 16 segmentos
- **Tendencia estaciones**: últimas 3 sesiones vs anteriores con % mejora/empeoramiento
- **Carreras**: stats por distancia + estimado 1km por ritmo
- **Progresión por estación**: gráfica temporal por estación
- **Ranking estaciones**: tiempo medio con barra proporcional
- **Comparador**: dos sesiones lado a lado con diff por segmento

## Tipos de sesión
- `full`: carrera completa (8 runs + 8 estaciones) — cuenta para KPIs y estimado total
- `training`: entrenamiento parcial — solo cuenta para stats de estaciones y carreras

## Decisiones técnicas
- Sin Docker — venv directo en LXC (igual que `finances` y `family-plan`)
- Parser en streaming con `iterparse` para manejar exports de 2.7GB sin OOM
- Import por ruta local en el servidor (evita subir 2.7GB por HTTP)
- PUT de sesión actualiza en lugar de delete+insert para mantener el ID
- Migración automática de columnas con ALTER TABLE + try/except en init_db
