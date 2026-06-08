import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import database as db
from parser import extract_hyrox_sessions

app = FastAPI()
db.init_db()


@app.get("/", response_class=HTMLResponse)
def index():
    with open("frontend/index.html") as f:
        return f.read()


# --- sessions ---

@app.get("/api/sessions")
def list_sessions():
    return db.get_sessions()


@app.get("/api/sessions/{session_id}")
def get_session(session_id: int):
    s = db.get_session(session_id)
    if not s:
        raise HTTPException(404)
    return s


class SegmentIn(BaseModel):
    position: int
    type: str
    label: str
    duration_s: int
    distance_m: Optional[int] = None


class SessionIn(BaseModel):
    date: str
    duration_s: int
    session_type: str = 'training'
    notes: Optional[str] = None
    segments: List[SegmentIn]


@app.post("/api/sessions", status_code=201)
def create_session(body: SessionIn):
    try:
        session_id = db.save_session(
            date=body.date,
            duration_s=body.duration_s,
            segments=[s.model_dump() for s in body.segments],
            notes=body.notes,
            session_type=body.session_type,
        )
        return {"id": session_id}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.put("/api/sessions/{session_id}")
def update_session(session_id: int, body: SessionIn):
    try:
        db.update_session(
            session_id=session_id,
            duration_s=body.duration_s,
            segments=[s.model_dump() for s in body.segments],
            notes=body.notes,
            session_type=body.session_type,
        )
        return {"id": session_id}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: int):
    db.delete_session(session_id)
    return {"ok": True}


# --- import ---

@app.get("/api/browse")
def browse(path: str = ""):
    import pathlib
    base = pathlib.Path(path) if path else pathlib.Path.home()
    if not base.exists() or not base.is_dir():
        raise HTTPException(400, "Ruta no válida")
    entries = []
    try:
        for e in sorted(base.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if e.name.startswith('.'):
                continue
            if e.is_dir() or e.suffix in ('.xml', '.zip'):
                entries.append({"name": e.name, "path": str(e), "is_dir": e.is_dir()})
    except PermissionError:
        pass
    parent = str(base.parent) if base != base.parent else None
    return {"path": str(base), "parent": parent, "entries": entries}


class ParsePathIn(BaseModel):
    path: str

@app.post("/api/import/parse-path")
def parse_path(body: ParsePathIn):
    if not os.path.exists(body.path):
        raise HTTPException(400, f"Archivo no encontrado: {body.path}")
    sessions = extract_hyrox_sessions(body.path)
    existing_dates = {s["date"] for s in db.get_sessions()}
    return [{**s, "already_imported": s["date"] in existing_dates} for s in sessions]

@app.post("/api/import/parse")
async def parse_upload(file: UploadFile = File(...)):
    import tempfile, shutil
    suffix = ".zip" if file.filename and file.filename.endswith(".zip") else ".xml"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        sessions = extract_hyrox_sessions(tmp_path)
    finally:
        os.unlink(tmp_path)
    existing_dates = {s["date"] for s in db.get_sessions()}
    return [{**s, "already_imported": s["date"] in existing_dates} for s in sessions]


# --- admin ---

@app.delete("/api/database")
def reset_database():
    conn = db.get_db()
    conn.executescript("DELETE FROM segments; DELETE FROM sessions;")
    conn.commit()
    conn.close()
    return {"ok": True}


# --- analytics ---

@app.get("/api/stats/stations")
def station_stats():
    return db.get_station_stats()


@app.get("/api/stats/stations/{label}")
def station_history(label: str):
    return db.get_station_history(label)


@app.get("/api/stats/runs")
def run_stats():
    return db.get_run_stats()


@app.get("/api/stats/runs/{distance_m}")
def run_history(distance_m: int):
    return db.get_run_history(distance_m)


@app.get("/api/stats/estimate")
def race_estimate():
    stations = db.get_station_stats()
    runs = db.get_run_stats()

    # best pace per meter across all run distances
    best_pace = min((r["avg_pace_per_m"] for r in runs), default=None) if runs else None
    est_1km_avg = round(best_pace * 1000) if best_pace else None

    # for each of the 8 stations, get avg and best
    station_map_avg = {s["label"]: s["avg_s"] for s in stations}
    station_map_best = {s["label"]: s["best_s"] for s in stations}

    segments = []
    total_avg = 0
    total_best = 0
    for i, name in enumerate(db.STATIONS):
        run_avg = est_1km_avg or 0
        run_best = round(min((r["best_s"] for r in runs), default=0) * 1000 / (runs[0]["distance_m"] if runs else 1000)) if runs else 0
        seg_avg = station_map_avg.get(name)
        seg_best = station_map_best.get(name)
        segments.append({
            "run_label": f"Carrera {i+1} (1km)",
            "run_avg_s": run_avg,
            "run_best_s": run_best,
            "station_label": name,
            "station_avg_s": seg_avg,
            "station_best_s": seg_best,
            "has_data": seg_avg is not None,
        })
        total_avg += run_avg + (seg_avg or 0)
        total_best += run_best + (seg_best or 0)

    return {
        "segments": segments,
        "total_avg_s": round(total_avg),
        "total_best_s": round(total_best),
        "est_1km_s": est_1km_avg,
        "missing_stations": [s["station_label"] for s in segments if not s["has_data"]],
    }


@app.get("/api/stations")
def stations():
    return db.STATIONS
