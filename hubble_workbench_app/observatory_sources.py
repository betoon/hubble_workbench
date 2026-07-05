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
    return source_count(summary, source, "by_mission")


def source_product_count(summary, source):
    return source_count(summary, source, "products_by_mission")


def source_rgb_counts(summary, source):
    if not summary:
        return {"blue": 0, "green": 0, "red": 0}
    mission_counts = summary.get("channels_by_mission", {}) or {}
    combined = {"blue": 0, "green": 0, "red": 0}
    for mission in source_names(source):
        counts = mission_counts.get(mission, {}) or {}
        for channel in combined:
            combined[channel] += counts.get(channel, 0)
    return combined


def source_count(summary, source, key):
    if not summary:
        return 0
    counts = summary.get(key, {}) or {}
    total = 0
    for mission in source_names(source):
        total += counts.get(mission, 0)
    return total


def source_names(source):
    return {str(source["code"]).upper(), str(source["name"]).upper()}


def layer_readiness_line(summary, source):
    observations = source_observation_count(summary, source)
    products = source_product_count(summary, source)
    rgb = source_rgb_counts(summary, source)
    missing = [channel for channel in ("blue", "green", "red") if not rgb[channel]]
    pieces = [
        f"observations={observations}",
        f"products={products}",
        f"RGB blue={rgb['blue']}, green={rgb['green']}, red={rgb['red']}",
    ]
    if not observations:
        next_step = "next: search this source when useful for the target"
    elif not products:
        next_step = "next: get products for this source"
    elif missing:
        next_step = "next: look for missing " + ", ".join(missing) + " coverage"
    else:
        next_step = "next: ready for RGB review"
    pieces.append(next_step)
    return f"- {source['name']} ({source['code']}): " + "; ".join(pieces)


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

    lines.append("Layer readiness:")
    for source in active:
        lines.append(layer_readiness_line(summary, source))

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