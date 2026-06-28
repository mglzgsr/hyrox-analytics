# Hyrox Analytics — CLAUDE.md

Dashboard personal de seguimiento de entrenamientos Hyrox. FastAPI + SQLite + HTML/JS vanilla.

## Infraestructura
- **Producción**: `/opt/hyrox`, servicio `hyrox-dashboard`, puerto 8003, `hyrox.mglzgsr.com`
- **Deploy**: push a `main` → GitHub Actions runner self-hosted → `git pull` + `pip install` + `systemctl restart`
- **DB**: `/opt/hyrox/data/hyrox.db` (ruta configurable vía `DB_PATH` env var)
- **Acceso**: Cloudflare Zero Trust Tunnel (autenticación por email, sin login propio)
- **Servidor compartido** con `finances` y `family-plan` (mismo LXC, 3.5GB RAM)
- **Runner**: usuario `hyrox`, instalado en `/opt/hyrox/actions-runner`

## Archivos clave
- `main.py` — FastAPI app, todos los endpoints, job store en memoria para imports async
- `database.py` — SQLite CRUD + queries de analytics; `STATIONS` define el orden canónico de las 8 estaciones
- `parser.py` — parser de export.xml de Apple Health (streaming iterparse, soporta ZIP)
- `frontend/index.html` — SPA completa (HTML + CSS + JS inline)

## Estructura Hyrox
- 8 rondas de: carrera (1km oficial, 600m en entrenamiento) + estación
- Estaciones en orden fijo: SkiErg → Sled Push → Sled Pull → Burpee Broad Jump → Rowing → Farmers Carry → Sandbag Lunges → Wall Balls
- El Apple Watch graba como `HKWorkoutActivityTypeHighIntensityIntervalTraining`
- Los splits se guardan como `HKWorkoutEventTypeMarker`

## Import de sesiones
Tres vías, en orden de preferencia:

1. **Mac → parsear local → subir JSON** (recomendado): el export.xml de 2.7GB es demasiado grande para subir y para parsear en el servidor con poca RAM. Se parsea en el Mac con el script que muestra el modal, genera `hyrox_sessions.json` en el mismo directorio que el XML, se sube ese JSON pequeño vía `POST /api/import/upload-parsed`.

2. **Ruta en servidor**: si el XML ya está en `/opt/hyrox/data/`, el import usa un job async (thread de fondo) con polling cada 2s. Devuelve `job_id` inmediatamente para evitar el timeout de 100s de Cloudflare.

3. **Subir archivo**: solo viable para archivos <500MB.

- Los domingos se pre-seleccionan automáticamente en el wizard
- Cada sesión se configura: tipo (completa/entrenamiento), estación inicial, splits run/station/omitir
- Duplicados detectados por fecha — checkboxes deshabilitados, no se pueden reimportar
- Apple Health JSON (Health Auto Export) no incluye splits — inútil para Hyrox, necesita el XML

## Base de datos — tablas
- **sessions**: `id, date, duration_s, session_type (full/training), notes, created_at`
  - `date` es UNIQUE — evita duplicados por fecha
- **segments**: `id, session_id, position, type (run/station), label, duration_s, distance_m`
  - `(session_id, position)` UNIQUE

## API endpoints
```
GET    /api/sessions
GET    /api/sessions/{id}
POST   /api/sessions
PUT    /api/sessions/{id}              ← UPDATE in-place, preserva el ID (no delete+insert)
DELETE /api/sessions/{id}
GET    /api/sessions/{id}/heatmap      ← pct vs media personal por segmento
POST   /api/import/upload-parsed       ← acepta JSON pre-parseado en Mac (evita subir 2.7GB)
POST   /api/import/parse-path          ← ruta local en servidor, devuelve job_id inmediatamente
GET    /api/import/jobs/{job_id}       ← polling: {status: running|done|error, result?, error?}
POST   /api/import/parse               ← upload directo, también async via job_id
GET    /api/stats/stations
GET    /api/stats/stations/{label}
GET    /api/stats/trends               ← últimas 3 sesiones vs anteriores, % mejora
GET    /api/stats/runs
GET    /api/stats/runs/{distance_m}
GET    /api/stats/estimate             ← estimado carrera completa (medias + mejores)
GET    /api/stations                   ← lista canónica de las 8 estaciones
DELETE /api/database                   ← reset completo
```

## Dashboard
Orden de secciones: KPIs → Heatmap última sesión → Tendencia estaciones → Carreras → Progresión/Ranking → Tiempo total/Estimado

- **KPIs**: sesiones totales, última completa, mejor tiempo, promedio (solo `full`)
- **Heatmap última sesión**: bloques coloreados vs media personal (verde=mejor, rojo=peor)
- **Tendencia estaciones**: últimas 3 sesiones vs anteriores con % mejora/empeoramiento
- **Carreras**: stats por distancia + estimado ritmo/km
- **Progresión por estación**: gráfica temporal; **Ranking**: tiempo medio con barra proporcional
- **Tiempo total por sesión**: gráfica (naranja=completa, azul dashed=entrenamiento)
- **Estimado carrera completa**: bloques medios + mejores; totales en `hh:mm:ss` via `fmtLong()`
- **Comparador**: dos sesiones lado a lado, carrera normalizada a ritmo/km (no tiempo bruto)

## Tipos de sesión
- `full`: carrera completa (8 runs + 8 estaciones) — cuenta para KPIs y estimado total
- `training`: entrenamiento parcial — solo cuenta para stats de estaciones y carreras

## Decisiones técnicas
- **Parser streaming**: `iterparse` para manejar exports de 2.7GB sin OOM
- **Import async con job store**: Cloudflare corta conexiones a los 100s. Todos los endpoints de import devuelven `job_id` inmediatamente; el frontend hace polling cada 2s. Jobs en dict en memoria — se pierden al reiniciar el servicio, aceptable porque el usuario re-importa.
- **PUT preserva ID**: `UPDATE` + `DELETE segments` + re-insert. Antes era delete+recreate, lo que rompía el fetch posterior al devolver el ID antiguo como 404.
- **Normalización carreras a 1km**: comparador y estimado usan `duration_s / distance_m * 1000` para comparar sesiones de 600m vs 1km de forma justa.
- **`renderDashboard` es async**: necesario para `await renderRaceEstimate()`. Todos los callers usan `await showPage()`.
- **Cloudflare cachea HTML**: tras deploy, hacer Purge Everything en CF → Caching, o hard reload (Cmd+Shift+R). Añadir Cache Rule bypass para HTML si es frecuente.
- **Migración automática**: `ALTER TABLE ADD COLUMN session_type` con try/except en `init_db` — permite añadir columnas sin romper DBs existentes.
- **Sin Docker**: venv directo en LXC, igual que `finances` y `family-plan`
