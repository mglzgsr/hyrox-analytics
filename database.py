import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "data/hyrox.db")

STATIONS = [
    "SkiErg",
    "Sled Push",
    "Sled Pull",
    "Burpee Broad Jump",
    "Rowing",
    "Farmers Carry",
    "Sandbag Lunges",
    "Wall Balls",
]


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL UNIQUE,
            started_at  TEXT,
            duration_s  INTEGER NOT NULL,
            session_type TEXT NOT NULL DEFAULT 'training' CHECK(session_type IN ('full', 'training')),
            notes       TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS segments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            position     INTEGER NOT NULL,
            type         TEXT NOT NULL CHECK(type IN ('run', 'station')),
            label        TEXT NOT NULL,
            duration_s   INTEGER NOT NULL,
            distance_m   INTEGER,
            UNIQUE(session_id, position)
        );
    """)
    # migrations
    for stmt in [
        "ALTER TABLE sessions ADD COLUMN session_type TEXT NOT NULL DEFAULT 'training' CHECK(session_type IN ('full', 'training'))",
        "ALTER TABLE sessions ADD COLUMN started_at TEXT",
    ]:
        try:
            conn.execute(stmt)
            conn.commit()
        except Exception:
            pass
    conn.close()


def get_sessions():
    conn = get_db()
    rows = conn.execute("""
        SELECT s.*, COUNT(sg.id) as segment_count
        FROM sessions s
        LEFT JOIN segments sg ON sg.session_id = s.id
        GROUP BY s.id
        ORDER BY s.date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session(session_id):
    conn = get_db()
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        conn.close()
        return None
    segments = conn.execute(
        "SELECT * FROM segments WHERE session_id = ? ORDER BY position", (session_id,)
    ).fetchall()
    conn.close()
    return {**dict(session), "segments": [dict(s) for s in segments]}


def update_session(session_id, duration_s, segments, notes=None, session_type='training'):
    conn = get_db()
    conn.execute(
        "UPDATE sessions SET duration_s = ?, notes = ?, session_type = ? WHERE id = ?",
        (duration_s, notes, session_type, session_id),
    )
    conn.execute("DELETE FROM segments WHERE session_id = ?", (session_id,))
    conn.executemany(
        "INSERT INTO segments (session_id, position, type, label, duration_s, distance_m) VALUES (?,?,?,?,?,?)",
        [(session_id, s["position"], s["type"], s["label"], s["duration_s"], s.get("distance_m")) for s in segments],
    )
    conn.commit()
    conn.close()


def save_session(date, duration_s, segments, notes=None, session_type='training', started_at=None):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO sessions (date, started_at, duration_s, notes, session_type) VALUES (?, ?, ?, ?, ?)",
            (date, started_at, duration_s, notes, session_type),
        )
        session_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO segments (session_id, position, type, label, duration_s, distance_m) VALUES (?,?,?,?,?,?)",
            [(session_id, s["position"], s["type"], s["label"], s["duration_s"], s.get("distance_m")) for s in segments],
        )
        conn.commit()
        return session_id
    except sqlite3.IntegrityError:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_session(session_id):
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def merge_sessions(session_id_a, session_id_b):
    """Fusiona dos sesiones. La más antigua (por date, luego id) absorbe a la otra."""
    conn = get_db()
    try:
        a = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id_a,)).fetchone()
        b = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id_b,)).fetchone()
        if not a or not b:
            raise ValueError("Sesión no encontrada")

        # Determinar orden: usar started_at si ambas lo tienen, sino date, luego id
        def sort_key(s):
            return (s["started_at"] or s["date"], s["id"])

        if sort_key(a) <= sort_key(b):
            first, second = dict(a), dict(b)
        else:
            first, second = dict(b), dict(a)

        segs_first = conn.execute(
            "SELECT * FROM segments WHERE session_id = ? ORDER BY position", (first["id"],)
        ).fetchall()
        segs_second = conn.execute(
            "SELECT * FROM segments WHERE session_id = ? ORDER BY position", (second["id"],)
        ).fetchall()

        merged_segs = [dict(s) for s in segs_first] + [dict(s) for s in segs_second]
        for i, s in enumerate(merged_segs, start=1):
            s["position"] = i

        total_duration = sum(s["duration_s"] for s in merged_segs)
        # Si alguna es 'full', la sesión fusionada es 'full'
        merged_type = "full" if first["session_type"] == "full" or second["session_type"] == "full" else "training"

        conn.execute(
            "UPDATE sessions SET duration_s = ?, session_type = ? WHERE id = ?",
            (total_duration, merged_type, first["id"]),
        )
        conn.execute("DELETE FROM segments WHERE session_id = ?", (first["id"],))
        conn.executemany(
            "INSERT INTO segments (session_id, position, type, label, duration_s, distance_m) VALUES (?,?,?,?,?,?)",
            [(first["id"], s["position"], s["type"], s["label"], s["duration_s"], s.get("distance_m")) for s in merged_segs],
        )
        conn.execute("DELETE FROM sessions WHERE id = ?", (second["id"],))
        conn.commit()
        return first["id"]
    finally:
        conn.close()


def get_station_stats():
    conn = get_db()
    rows = conn.execute("""
        SELECT
            sg.label,
            COUNT(*) as count,
            MIN(sg.duration_s) as best_s,
            MAX(sg.duration_s) as worst_s,
            AVG(sg.duration_s) as avg_s
        FROM segments sg
        JOIN sessions s ON s.id = sg.session_id
        WHERE sg.type = 'station'
        GROUP BY sg.label
        ORDER BY sg.label
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_station_history(label):
    conn = get_db()
    rows = conn.execute("""
        SELECT s.date, sg.duration_s, sg.position
        FROM segments sg
        JOIN sessions s ON s.id = sg.session_id
        WHERE sg.type = 'station' AND sg.label = ?
        ORDER BY s.date ASC
    """, (label,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_run_stats():
    """Stats de carreras agrupadas por distancia, con estimado a 1km."""
    conn = get_db()
    rows = conn.execute("""
        SELECT
            sg.distance_m,
            COUNT(*) as count,
            MIN(sg.duration_s) as best_s,
            MAX(sg.duration_s) as worst_s,
            AVG(sg.duration_s) as avg_s,
            AVG(CAST(sg.duration_s AS REAL) / sg.distance_m) as avg_pace_per_m
        FROM segments sg
        JOIN sessions s ON s.id = sg.session_id
        WHERE sg.type = 'run' AND sg.distance_m IS NOT NULL AND sg.distance_m > 0
        GROUP BY sg.distance_m
        ORDER BY sg.distance_m
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_station_trends():
    """Para cada estación: media últimas 3 sesiones vs media anteriores."""
    conn = get_db()
    rows = conn.execute("""
        SELECT sg.label, sg.duration_s, s.date
        FROM segments sg
        JOIN sessions s ON s.id = sg.session_id
        WHERE sg.type = 'station'
        ORDER BY sg.label, s.date ASC
    """).fetchall()
    conn.close()

    from collections import defaultdict
    by_station = defaultdict(list)
    for r in rows:
        by_station[r['label']].append(r['duration_s'])

    result = []
    for label, times in by_station.items():
        if len(times) < 2:
            result.append({'label': label, 'trend': 0, 'pct': 0, 'recent_avg': times[-1], 'prev_avg': times[-1]})
            continue
        recent = times[-min(3, len(times)):]
        prev = times[:-min(3, len(times))] or times[:1]
        recent_avg = sum(recent) / len(recent)
        prev_avg = sum(prev) / len(prev)
        pct = round((recent_avg - prev_avg) / prev_avg * 100, 1)
        result.append({'label': label, 'trend': -1 if pct < 0 else 1 if pct > 0 else 0,
                       'pct': abs(pct), 'recent_avg': round(recent_avg), 'prev_avg': round(prev_avg)})
    return result


def get_session_heatmap(session_id):
    """Segmentos con color relativo a la media personal."""
    conn = get_db()
    segs = conn.execute(
        "SELECT * FROM segments WHERE session_id = ? ORDER BY position", (session_id,)
    ).fetchall()

    # get personal avg per label
    avgs = conn.execute("""
        SELECT sg.label, AVG(sg.duration_s) as avg_s
        FROM segments sg
        JOIN sessions s ON s.id = sg.session_id
        WHERE sg.type = 'station'
        GROUP BY sg.label
    """).fetchall()
    conn.close()

    avg_map = {r['label']: r['avg_s'] for r in avgs}
    result = []
    for sg in segs:
        sg = dict(sg)
        if sg['type'] == 'station' and sg['label'] in avg_map:
            avg = avg_map[sg['label']]
            sg['pct_vs_avg'] = round((sg['duration_s'] - avg) / avg * 100, 1)
        else:
            sg['pct_vs_avg'] = None
        result.append(sg)
    return result


def get_run_history(distance_m):
    conn = get_db()
    rows = conn.execute("""
        SELECT s.date, sg.duration_s,
               CAST(sg.duration_s AS REAL) / sg.distance_m as pace_per_m
        FROM segments sg
        JOIN sessions s ON s.id = sg.session_id
        WHERE sg.type = 'run' AND sg.distance_m = ?
        ORDER BY s.date ASC
    """, (distance_m,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
