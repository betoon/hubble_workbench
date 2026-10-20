from pathlib import Path

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
        "status": "wizard",
        "role": "X-ray context layer for energetic sources and galaxy clusters.",
        "activation": "Curated images and public Chandra Archive searches are available in Image Wizard, with local FITS image overlays in Explorer.",
    },
    {
        "name": "Pan-STARRS",
        "code": "PANSTARRS",
        "kind": "survey",
        "status": "wizard",
        "role": "Optical sky-survey context and color-reference layer.",
        "activation": "Image Wizard provides survey cutout retrieval and registration. Explorer coverage and local FITS image overlays are available.",
    },
    {
        "name": "DSS",
        "code": "DSS",
        "kind": "survey",
        "status": "wizard",
        "role": "Broad reference imagery for target identification and framing.",
        "activation": "Image Wizard provides reference image retrieval, registration and framing. Explorer coverage and local FITS image overlays are available.",
    },
]


MULTI_TELESCOPE_SOURCES.extend([
    {"name": name, "code": name.upper(), "kind": "survey", "status": "wizard",
     "role": role, "activation": "Available in Image Wizard; Explorer coverage and local FITS image overlays are available."}
    for name, role in [("WISE", "Infrared survey context."),
                       ("Spitzer", "IRAC infrared imaging."),
                       ("GALEX", "Ultraviolet context; two bands do not form an automatic RGB set.")]
])


def wizard_source_states(records=None, channels=None):
    """Describe loaded Wizard records without mixing them into MAST readiness."""
    records, channels = records or [], channels or {}
    result = []
    for source in MULTI_TELESCOPE_SOURCES:
        rows = [r for r in records if str(r.get("source", "")).upper() in source_names(source)]
        # Repeated catalog records should not inflate the project counts.
        rows = list({r.get("key") or r.get("url") or repr(r): r for r in rows}.values())
        keys = {r.get("key") for r in rows if r.get("key")}
        assigned = [c for c in ("red", "green", "blue", "luminance")
                    if isinstance(channels.get(c), dict) and channels[c].get("key") in keys]
        downloaded = sum(bool(r.get("local_path")) and Path(r["local_path"]).is_file() for r in rows)
        missing = sum(bool(r.get("local_path")) and not Path(r["local_path"]).is_file() for r in rows)
        result.append({"name": source["name"], "code": source["code"],
                       "available": True, "records": len(rows), "downloaded": downloaded,
                       "missing_files": missing, "assigned_channels": assigned,
                       "targets": sorted({str(r.get("target", "")) for r in rows}),
                       "bands": sorted({str(r.get("band", "")) for r in rows})})
    return result


def wizard_project_lines(states):
    lines = ["Image Wizard project (separate from MAST search results):"]
    for source in states:
        if not source["records"]:
            lines.append(f"- {source['name']}: available; no Wizard records loaded.")
            continue
        assignments = ", ".join(source["assigned_channels"]) or "none"
        lines.append(f"- {source['name']}: {source['records']} records; "
                     f"{source['downloaded']} local files available; "
                     f"{source['missing_files']} missing saved files; assigned channels: {assignments}.")
        lines.append("  Targets: " + ", ".join(source["targets"]) + "; bands: " + ", ".join(source["bands"]))
        if source["missing_files"]:
            lines.append("  Re-download missing files in Image Wizard before offline composition.")
        if len(source["bands"]) < 3:
            lines.append("  Fewer than three distinct bands; preview or assign overlapping sources manually.")
    lines.append("- Review assignments and valid sky overlap in Image Wizard before building RGB.")
    return lines


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
        status = "active" if source["status"] == "active" else "Image Wizard and Explorer image overlays available"
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


def project_state(summary=None, wizard_records=None, wizard_channels=None):
    active = [source_layer_state(summary, source) for source in active_sources()]
    planned = [source_layer_state(summary, source) for source in planned_sources()]
    active_with_observations = sum(1 for source in active if source["observations"])
    active_ready_for_rgb = sum(1 for source in active if source["rgb_complete"])
    return {
        "wizard_sources": wizard_source_states(wizard_records, wizard_channels),
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
        lines.append("- Try an RGB composition with the ready source before adding additional context layers.")
    else:
        lines.append("- Build at least one complete active-source RGB layer before moving to additional context layers.")
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
    lines.append("- Use Image Wizard for Chandra, Pan-STARRS, DSS, WISE, Spitzer and GALEX retrieval and alignment; Explorer image overlays are available for downloaded FITS files.")
    return lines


def composition_readiness_state(summary=None):
    state = project_state(summary)
    summary = summary or {}
    source_rows = []
    for source in state["active_sources"]:
        rgb = source["rgb"]
        score = 0
        notes = []
        if source["observations"]:
            score += 20
        else:
            notes.append("needs observations")
        if source["products"]:
            score += 20
        else:
            notes.append("needs products")
        channel_score = 0
        for channel in ("blue", "green", "red"):
            if rgb[channel]:
                channel_score += 10
            else:
                notes.append(f"needs {channel} coverage")
        score += channel_score
        if source["rgb_complete"]:
            score += 15
            notes.append("complete RGB coverage")
        source_rows.append({
            "name": source["name"],
            "code": source["code"],
            "score": score,
            "observations": source["observations"],
            "products": source["products"],
            "rgb": rgb,
            "rgb_complete": source["rgb_complete"],
            "notes": notes,
            "next_action": source["next_action"],
        })

    source_rows.sort(key=lambda item: (-item["score"], item["name"]))
    best = source_rows[0] if source_rows else None
    score = best["score"] if best else 0
    if state["active_with_observations"] > 1:
        score += 10
    if summary.get("enhanced_products") or summary.get("hla_products") or summary.get("rgb_sets"):
        score += 10
    score = min(100, score)

    if score >= 90:
        status = "excellent - ready to try a polished composition"
    elif score >= 70:
        status = "strong - one or two refinements could improve the final image"
    elif score >= 45:
        status = "promising - useful data is present but the layer set is incomplete"
    elif score:
        status = "early - gather products and color coverage before composing"
    else:
        status = "not started - search and load products first"

    next_actions = []
    if not summary.get("observations"):
        next_actions.append("Search Hubble or JWST for the target.")
    elif not summary.get("products"):
        next_actions.append("Load products so image layers can be evaluated.")
    elif best and not best["rgb_complete"]:
        missing = ", ".join(channel for channel in ("blue", "green", "red") if not best["rgb"][channel])
        next_actions.append(f"Improve {best['name']} color coverage: missing {missing}.")
    elif best:
        next_actions.append(f"Use {best['name']} as the first image layer and compare other sources against it.")
    if state["active_with_observations"] < len(state["active_sources"]):
        missing_sources = [source["name"] for source in state["active_sources"] if not source["observations"]]
        if missing_sources:
            next_actions.append("Search " + ", ".join(missing_sources) + " when broader wavelength coverage would help.")

    return {
        "score": score,
        "status": status,
        "best_source": best,
        "sources": source_rows,
        "next_actions": next_actions,
    }


def composition_readiness_lines(summary=None):
    readiness = composition_readiness_state(summary)
    lines = ["Image Build Readiness:"]
    lines.append(f"- Overall readiness: {readiness['score']}/100 ({readiness['status']}).")
    best = readiness.get("best_source")
    if best:
        rgb = best["rgb"]
        lines.append(
            f"- Best starting layer: {best['name']} ({best['code']}) with "
            f"observations={best['observations']}, products={best['products']}, "
            f"RGB blue={rgb['blue']}, green={rgb['green']}, red={rgb['red']}."
        )
    else:
        lines.append("- Best starting layer: none yet.")
    for source in readiness["sources"]:
        rgb = source["rgb"]
        lines.append(
            f"- {source['name']}: {source['score']}/85 layer score; "
            f"RGB blue={rgb['blue']}, green={rgb['green']}, red={rgb['red']}; "
            f"next: {source['next_action']}."
        )
    lines.append("Next actions:")
    for action in readiness["next_actions"] or ["Review the current layers and try a test composition."]:
        lines.append(f"- {action}")
    return lines

def project_plan_lines(summary=None, wizard_records=None, wizard_channels=None):
    lines = []
    state = project_state(summary, wizard_records, wizard_channels)

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

    lines.append("Additional archive layers (images available in Image Wizard):")
    for source in state["planned_sources"]:
        lines.append(f"- {source['name']} ({source['code']}): {source['role']} [available] coverage and image overlays")
        if source.get("activation"):
            lines.append(f"  Integration status: {source['activation']}")

    lines.extend(wizard_project_lines(state["wizard_sources"]))

    lines.append("Project guidance:")
    if not summary or not summary.get("observations"):
        lines.append("- Start with a Hubble or JWST search, then use products and RGB tools to build the first project layer.")
    elif state["active_with_observations"] > 1:
        lines.append("- Multiple active telescope sources are loaded. Compare filters, exposure, and product quality before composing.")
    elif state["active_with_observations"]:
        lines.append("- One active telescope source is loaded. Search the other active source when the target needs broader wavelength coverage.")
    else:
        lines.append("- Observations are loaded, but they do not match the active source registry yet. Review mission names before composing.")
    lines.append("- Use Image Wizard for the additional archives; this Explorer plan tracks the MAST workflow separately.")

    lines.append("Project checklist:")
    lines.extend(project_checklist_lines(summary))
    return lines