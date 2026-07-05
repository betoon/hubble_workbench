MULTI_TELESCOPE_SOURCES = [
    {
        "name": "Hubble",
        "code": "HST",
        "kind": "space telescope",
        "status": "active",
        "role": "Visible/near-UV imaging and legacy HLA enhanced products.",
    },
    {
        "name": "James Webb",
        "code": "JWST",
        "kind": "space telescope",
        "status": "active",
        "role": "Infrared imaging and high-quality i2d/calibrated products.",
    },
    {
        "name": "Chandra",
        "code": "CHANDRA",
        "kind": "space telescope",
        "status": "planned",
        "role": "X-ray context layer for energetic sources and galaxy clusters.",
    },
    {
        "name": "Pan-STARRS",
        "code": "PANSTARRS",
        "kind": "survey",
        "status": "planned",
        "role": "Optical sky-survey context and color-reference layer.",
    },
    {
        "name": "DSS",
        "code": "DSS",
        "kind": "survey",
        "status": "planned",
        "role": "Broad reference imagery for target identification and framing.",
    },
]


def active_sources():
    return [source for source in MULTI_TELESCOPE_SOURCES if source["status"] == "active"]


def planned_sources():
    return [source for source in MULTI_TELESCOPE_SOURCES if source["status"] != "active"]


def source_status_lines():
    lines = []
    for source in MULTI_TELESCOPE_SOURCES:
        status = "active" if source["status"] == "active" else "planned"
        lines.append(f"- {source['name']} ({source['code']}): {status} - {source['role']}")
    return lines