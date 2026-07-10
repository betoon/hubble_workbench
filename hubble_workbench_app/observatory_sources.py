MULTI_TELESCOPE_SOURCES = [
    {
        "name": "Hubble",
        "code": "HST",
        "kind": "space telescope",
        "status": "active",
        "role": "Visible/near-UV imaging and legacy HLA enhanced products.",
        "activation": "Already available through MAST/HLA workflows.",
    },
    {
        "name": "James Webb",
        "code": "JWST",
        "kind": "space telescope",
        "status": "active",
        "role": "Infrared imaging and high-quality i2d/calibrated products.",
        "activation": "Already available through MAST product workflows.",
    },
    {
        "name": "Chandra",
        "code": "CHANDRA",
        "kind": "space telescope",
        "status": "planned",
        "role": "X-ray context layer for energetic sources and galaxy clusters.",
        "activation": "Needs Chandra archive search, product selection, and X-ray overlay handling.",
    },
    {
        "name": "Pan-STARRS",
        "code": "PANSTARRS",
        "kind": "survey",
        "status": "planned",
        "role": "Optical sky-survey context and color-reference layer.",
        "activation": "Needs survey cutout retrieval, registration, and color-reference handling.",
    },
    {
        "name": "DSS",
        "code": "DSS",
        "kind": "survey",
        "status": "planned",
        "role": "Broad reference imagery for target identification and framing.",
        "activation": "Needs reference image retrieval, registration, and framing controls.",
    },
]


def active_sources():
    return [source for source in MULTI_TELESCOPE_SOURCES if source["status"] == "active"]


def planned_sources():
    return [source for source in MULTI_TELESCOPE_SOURCES if source["status"] != "active"]


def planned_activation_lines():
    lines = []
    for source in planned_sources():
        lines.append(f"- {source['name']} ({source['code']}): {source.get('activation', 'Needs implementation plan.')}")
    return lines


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


def source_next_action(summary, source):
    observations = source_observation_count(summary, source)
    products = source_product_count(summary, source)
    rgb = source_rgb_counts(summary, source)
    missing = [channel for channel in ("blue", "green", "red") if not rgb[channel]]
    if not observations:
        return "search this source when useful for the target"
    if not products:
        return "get products for this source"
    if missing:
        return "look for missing " + ", ".join(missing) + " coverage"
    return "ready for RGB review"


def source_layer_state(summary, source):
    rgb = source_rgb_counts(summary, source)
    return {
        "name": source["name"],
        "code": source["code"],
        "kind": source["kind"],
        "status": source["status"],
        "role": source["role"],
        "activation": source.get("activation", ""),
        "observations": source_observation_count(summary, source),
        "products": source_product_count(summary, source),
        "rgb": rgb,
        "rgb_complete": all(rgb[channel] for channel in ("blue", "green", "red")),
        "next_action": source_next_action(summary, source),
    }


def project_state(summary=None):
    active = [source_layer_state(summary, source) for source in active_sources()]
    planned = [source_layer_state(summary, source) for source in planned_sources()]
    active_with_observations = sum(1 for source in active if source["observations"])
    active_ready_for_rgb = sum(1 for source in active if source["rgb_complete"])
    return {
        "active_sources": active,
        "planned_sources": planned,
        "active_with_observations": active_with_observations,
        "active_ready_for_rgb": active_ready_for_rgb,
    }


def project_checklist_lines(summary=None):
    state = project_state(summary)
    lines = []
    if not summary or not summary.get("observations"):
        lines.append("- Search Hubble or JWST for the target.")
        lines.append("- Get products after observations are loaded.")
        lines.append("- Re-run Observatory Explorer to refresh the project plan.")
        return lines

    if not state["active_with_observations"]:
        lines.append("- Review mission names; loaded observations do not match Hubble or JWST yet.")

    for source in state["active_sources"]:
        if not source["observations"]:
            lines.append(f"- Optional: search {source['name']} if the project needs its wavelength coverage.")
        elif not source["products"]:
            lines.append(f"- Get products for {source['name']}.")
        elif not source["rgb_complete"]:
            missing = ", ".join(channel for channel in ("blue", "green", "red") if not source["rgb"][channel])
            lines.append(f"- Improve {source['name']} RGB coverage: missing {missing}.")
        else:
            lines.append(f"- Review {source['name']} RGB candidates and choose the best set.")

    if state["active_ready_for_rgb"]:
        lines.append("- Try an RGB composition with the ready source before adding planned context layers.")
    else:
        lines.append("- Build at least one complete active-source RGB layer before moving to planned context layers.")
    return lines


def layer_readiness_line(summary, source):
    state = source_layer_state(summary, source)
    rgb = state["rgb"]
    pieces = [
        f"observations={state['observations']}",
        f"products={state['products']}",
        f"RGB blue={rgb['blue']}, green={rgb['green']}, red={rgb['red']}",
        f"next: {state['next_action']}",
    ]
    return f"- {state['name']} ({state['code']}): " + "; ".join(pieces)




def composition_strategy_lines(summary=None):
    state = project_state(summary)
    lines = []
    ready = [source for source in state["active_sources"] if source["rgb_complete"]]
    observed = [source for source in state["active_sources"] if source["observations"]]
    product_sources = [source for source in state["active_sources"] if source["products"]]

    lines.append("Composition Strategy:")
    if ready:
        names = ", ".join(source["name"] for source in ready)
        lines.append(f"- Build the first polished RGB layer from: {names}.")
        lines.append("- Prefer drizzled, mosaic, combined, HLA, or JWST i2d products for sharper alignment and cleaner detail.")
    elif product_sources:
        names = ", ".join(source["name"] for source in product_sources)
        lines.append(f"- Products are loaded for {names}, but at least one RGB channel is still missing.")
        lines.append("- Use Find Better Sources or Get All Products before composing the final RGB image.")
    elif observed:
        names = ", ".join(source["name"] for source in observed)
        lines.append(f"- Observations are loaded for {names}; get products next so real image layers can be evaluated.")
    else:
        lines.append("- Start by searching Hubble or JWST and loading products for the target.")

    if len(observed) > 1:
        lines.append("- Compare Hubble visible/near-UV structure with JWST infrared structure before choosing the final color mapping.")
    elif observed:
        missing = [source["name"] for source in state["active_sources"] if not source["observations"]]
        if missing:
            lines.append("- Search " + ", ".join(missing) + " when the target needs broader wavelength coverage.")

    lines.append("- Use the sky mosaic to check whether the chosen layers overlap before downloading or composing.")
    lines.append("- Treat planned Chandra, Pan-STARRS, and DSS layers as future context overlays until their retrieval and registration tools are active.")
    return lines


def project_plan_lines(summary=None):
    lines = []
    state = project_state(summary)

    lines.append("Active search sources:")
    for source in state["active_sources"]:
        if source["observations"]:
            status = f"current observations loaded: {source['observations']}"
        else:
            status = "ready for normal MAST searching"
        lines.append(f"- {source['name']} ({source['code']}): {source['role']} [{status}]")

    lines.append("Layer readiness:")
    for source in active_sources():
        lines.append(layer_readiness_line(summary, source))

    lines.append("Planned context layers:")
    for source in state["planned_sources"]:
        lines.append(f"- {source['name']} ({source['code']}): {source['role']} [planned]")
        if source.get("activation"):
            lines.append(f"  Activation needed: {source['activation']}")

    lines.append("Project guidance:")
    if not summary or not summary.get("observations"):
        lines.append("- Start with a Hubble or JWST search, then use products and RGB tools to build the first project layer.")
    elif state["active_with_observations"] > 1:
        lines.append("- Multiple active telescope sources are loaded. Compare filters, exposure, and product quality before composing.")
    elif state["active_with_observations"]:
        lines.append("- One active telescope source is loaded. Search the other active source when the target needs broader wavelength coverage.")
    else:
        lines.append("- Observations are loaded, but they do not match the active source registry yet. Review mission names before composing.")
    lines.append("- Keep planned context layers visible here until their search/download workflows are added.")

    lines.append("Project checklist:")
    lines.extend(project_checklist_lines(summary))
    return lines