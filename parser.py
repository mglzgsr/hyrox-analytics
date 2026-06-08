import xml.etree.ElementTree as ET
import zipfile
import io
from datetime import datetime


def parse_date(s):
    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")


def fmt_date(s):
    return s[:10]


def extract_hyrox_sessions(source):
    """
    source: path string (xml or zip) or file-like object.
    Streams the XML to avoid loading large files into memory.
    """
    if isinstance(source, str):
        if source.endswith(".zip"):
            # stream xml from inside zip
            zf = zipfile.ZipFile(source)
            stream = zf.open("apple_health_export/export.xml")
        else:
            stream = open(source, "rb")
    elif hasattr(source, "read"):
        stream = source
    else:
        stream = source

    sessions = []
    context = ET.iterparse(stream, events=("end",))

    for _, elem in context:
        if elem.tag != "Workout":
            continue
        if "HighIntensityIntervalTraining" not in elem.attrib.get("workoutActivityType", ""):
            elem.clear()
            continue

        markers = [
            e for e in elem.findall("WorkoutEvent")
            if e.attrib.get("type") == "HKWorkoutEventTypeMarker"
        ]

        if len(markers) < 4:
            elem.clear()
            continue

        start = parse_date(elem.attrib["startDate"])
        end = parse_date(elem.attrib["endDate"])
        total_s = int((end - start).total_seconds())
        date_str = fmt_date(elem.attrib["startDate"])

        marker_dates = [parse_date(m.attrib["date"]) for m in markers]

        # compute splits between consecutive markers (and from start to first marker)
        splits = []
        prev = start
        for md in marker_dates:
            s = int((md - prev).total_seconds())
            splits.append(s)
            prev = md
        # last split: from last marker to end
        splits.append(int((end - prev).total_seconds()))

        # filter out 0s misclicks
        splits = [s for s in splits if s > 2]

        sessions.append({
            "date": date_str,
            "duration_s": total_s,
            "splits": splits,
        })

        elem.clear()

    return sessions
