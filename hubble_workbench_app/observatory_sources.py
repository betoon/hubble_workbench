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


def source_observation_count(summary, source):
    if not summary:
        return 0
    by_mission = summary.get("by_mission", {}) or {}
    source_names = {source["code"].upper(), source["name"].upper()}
    count = 0
    for mission, mission_count in by_mission.items():
        if str(mission).upper() in source_names:
            count += mission_count
    return count


def project_plan_lines(summary=None):
    lines = []
    active = active_sources()
    planned = planned_sources()

    lines.append("Active search sources:")
    for source in active:
        count = source_observation_count(summary, source)
        if count:
            status = f"current observations loaded: {count}"
        else:
            status = "ready for normal MAST searching"
        lines.append(f"- {source['name']} ({source['code']}): {source['role']} [{status}]")

    lines.append("Planned context layers:")
    for source in planned:
        lines.append(f"- {source['name']} ({source['code']}): {source['role']} [planned]")

    lines.append("Project guidance:")
    active_counts = [source_observation_count(summary, source) for source in active]
    if not summary or not summary.get("observations"):
        lines.append("- Start with a Hubble or JWST search, then use products and RGB tools to build the first project layer.")
    elif sum(1 for count in active_counts if count) > 1:
        lines.append("- Multiple active telescope sources are loaded. Compare filters, exposure, and product quality before composing.")
    elif any(active_counts):
        lines.append("- One active telescope source is loaded. Search the other active source when the target needs broader wavelength coverage.")
    else:
        lines.append("- Observations are loaded, but they do not match the active source registry yet. Review mission names before composing.")
    lines.append("- Keep planned context layers visible here until their search/download workflows are added.")
    return lines