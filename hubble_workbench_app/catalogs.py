from .paths import MESSIER_LIST_PATH


def messier_radius(description):
    text = description.lower()
    if "planetary nebula" in text or "double star" in text or "asterism" in text:
        return "0.05 deg"
    if "andromeda galaxy" in text or "triangulum galaxy" in text:
        return "0.12 deg"
    if "galaxy" in text:
        return "0.10 deg"
    if "nebula" in text:
        return "0.08 deg"
    if "cluster" in text:
        return "0.08 deg"
    return "0.08 deg"


def load_messier_gallery_items(existing_items):
    if not MESSIER_LIST_PATH.exists():
        return []
    existing_targets = {target.upper().strip() for _label, target, _radius in existing_items}
    items = []
    try:
        lines = MESSIER_LIST_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in lines:
        line = line.strip()
        if not line.startswith("M") or ":" not in line:
            continue
        target, details = line.split(":", 1)
        target = target.strip().upper()
        if not target[1:].isdigit() or target in existing_targets:
            continue
        description = details.strip().split("[", 1)[0].strip()
        name = description
        constellation = ""
        if " - " in description:
            name, constellation = [part.strip() for part in description.rsplit(" - ", 1)]
        label = f"{target} - {name}"
        if constellation:
            label = f"{label} ({constellation})"
        items.append((label, target, messier_radius(description)))
    return items


TARGET_GALLERY = [
    ("M51 - Whirlpool Galaxy", "M51", "0.10 deg"),
    ("M57 - Ring Nebula", "M57", "0.05 deg"),
    ("M27 - Dumbbell Nebula", "M27", "0.08 deg"),
    ("M1 - Crab Nebula", "M1", "0.05 deg"),
    ("M13 - Great Hercules Cluster", "M13", "0.08 deg"),
    ("M31 - Andromeda Galaxy", "M31", "0.12 deg"),
    ("M33 - Triangulum Galaxy", "M33", "0.12 deg"),
    ("M16 - Eagle Nebula", "M16", "0.12 deg"),
    ("M16 - Pillars of Creation / Fingers of God", "M16", "0.08 deg"),
    ("M17 - Omega Nebula", "M17", "0.10 deg"),
    ("M20 - Trifid Nebula", "M20", "0.08 deg"),
    ("M42 - Orion Nebula", "M42", "0.12 deg"),
    ("M64 - Black Eye Galaxy", "M64", "0.08 deg"),
    ("M82 - Cigar Galaxy", "M82", "0.08 deg"),
    ("M87 - Virgo A Galaxy", "M87", "0.08 deg"),
    ("M104 - Sombrero Galaxy", "M104", "0.08 deg"),
    ("NGC 1300 - Barred Spiral Galaxy", "NGC 1300", "0.08 deg"),
    ("NGC 3372 - Carina Nebula", "NGC 3372", "0.12 deg"),
    ("NGC 4038 - Antennae Galaxies", "NGC 4038", "0.10 deg"),
    ("NGC 5194 - Whirlpool Galaxy Core", "NGC 5194", "0.08 deg"),
    ("NGC 6302 - Butterfly Nebula", "NGC 6302", "0.05 deg"),
    ("NGC 6543 - Cat's Eye Nebula", "NGC 6543", "0.05 deg"),
    ("NGC 6611 - Eagle Nebula Cluster", "NGC 6611", "0.08 deg"),
    ("NGC 6720 - Ring Nebula", "NGC 6720", "0.05 deg"),
    ("NGC 6822 - Barnard's Galaxy", "NGC 6822", "0.10 deg"),
    ("NGC 604 - Star-forming Region", "NGC 604", "0.08 deg"),
    ("HH 901 - Carina Pillar", "HH 901", "0.04 deg"),
    ("M101 - Pinwheel Galaxy", "M101", "0.20 deg"),
]
TARGET_GALLERY.extend(load_messier_gallery_items(TARGET_GALLERY))

JWST_TARGET_GALLERY = [
    ("Carina Nebula - Cosmic Cliffs", "NGC 3324", "0.08 deg"),
    ("Stephan's Quintet", "Stephan's Quintet", "0.08 deg"),
    ("Southern Ring Nebula", "NGC 3132", "0.05 deg"),
    ("Tarantula Nebula", "30 Doradus", "0.10 deg"),
    ("Pillars of Creation", "M16", "0.08 deg"),
    ("Orion Bar", "M42", "0.08 deg"),
    ("Phantom Galaxy", "M74", "0.12 deg"),
    ("Cartwheel Galaxy", "ESO 350-40", "0.12 deg"),
    ("Jupiter", "Jupiter", "0.05 deg"),
    ("Uranus", "Uranus", "0.05 deg"),
    ("Neptune", "Neptune", "0.05 deg"),
]

TELESCOPE_CHOICES = {
    "Hubble / HST": "HST",
    "James Webb / JWST": "JWST",
    "Both HST + JWST": "BOTH",
}

SOLAR_SYSTEM_TARGETS = {
    "MERCURY", "VENUS", "MARS", "JUPITER", "SATURN", "URANUS", "NEPTUNE", "PLUTO",
    "IO", "EUROPA", "GANYMEDE", "CALLISTO", "TITAN", "ENCELADUS", "TRITON",
}

TARGET_ALIASES = {
    "PILLARS OF CREATION": "M16",
    "THE PILLARS OF CREATION": "M16",
    "EAGLE NEBULA": "M16",
    "M 16": "M16",
    "M-16": "M16",
    "COSMIC CLIFFS": "NGC 3324",
    "CARINA COSMIC CLIFFS": "NGC 3324",
    "STEPHANS QUINTET": "Stephan's Quintet",
    "STEPHAN'S QUINTET": "Stephan's Quintet",
    "SOUTHERN RING": "NGC 3132",
    "SOUTHERN RING NEBULA": "NGC 3132",
    "PHANTOM GALAXY": "M74",
    "CARTWHEEL": "ESO 350-40",
    "CARTWHEEL GALAXY": "ESO 350-40",
    "TARANTULA": "30 Doradus",
    "TARANTULA NEBULA": "30 Doradus",
    "ORION BAR": "M42",
}

JWST_NIRCAM_FILTERS = {
    "F070W": 0.70, "F090W": 0.90, "F115W": 1.15, "F140M": 1.40, "F150W": 1.50,
    "F150W2": 1.50, "F162M": 1.62, "F164N": 1.64, "F182M": 1.82, "F187N": 1.87,
    "F200W": 2.00, "F210M": 2.10, "F212N": 2.12, "F250M": 2.50, "F277W": 2.77,
    "F300M": 3.00, "F322W2": 3.22, "F323N": 3.23, "F335M": 3.35, "F356W": 3.56,
    "F360M": 3.60, "F405N": 4.05, "F410M": 4.10, "F430M": 4.30, "F444W": 4.44,
    "F460M": 4.60, "F466N": 4.66, "F470N": 4.70, "F480M": 4.80,
}

JWST_MIRI_FILTERS = {
    "F560W": 5.60, "F770W": 7.70, "F1000W": 10.00, "F1130W": 11.30,
    "F1280W": 12.80, "F1500W": 15.00, "F1800W": 18.00, "F2100W": 21.00,
    "F2550W": 25.50,
}

HST_BLUE_FILTERS = (
    "F225W", "F275W", "F336W", "F390W", "F435W", "F438W", "F439W", "F450W", "F475W"
)
HST_GREEN_FILTERS = (
    "F502N", "F547M", "F550M", "F555W", "F555W;CLEAR2L", "F606W", "F625W"
)
HST_RED_FILTERS = (
    "F656N", "F658N", "F673N", "F675W", "F775W", "F814W", "F850LP", "F105W",
    "F110W", "F125W", "F140W", "F160W"
)
RGB_FILTER_TOKENS = tuple(dict.fromkeys(
    HST_BLUE_FILTERS + HST_GREEN_FILTERS + HST_RED_FILTERS +
    tuple(JWST_NIRCAM_FILTERS.keys()) + tuple(JWST_MIRI_FILTERS.keys())
))

TARGET_RECIPES = {
    "M16": {
        "name": "Eagle Nebula",
        "filters": {"blue": ("F435W", "F438W"), "green": ("F502N", "F555W"), "red": ("F658N", "F656N", "F814W")},
        "preset": "Nebula",
        "stretch": {"low": 0.15, "high": 99.85, "gamma": 1.0, "asinh": 14.0},
    },
    "M51": {
        "name": "Whirlpool Galaxy",
        "filters": {"blue": ("F435W", "F438W"), "green": ("F555W", "F606W"), "red": ("F814W", "F850LP")},
        "preset": "Galaxy",
        "stretch": {"low": 0.2, "high": 99.75, "gamma": 1.05, "asinh": 10.0},
    },
    "M101": {
        "name": "Pinwheel Galaxy",
        "filters": {"blue": ("F435W", "F438W"), "green": ("F555W", "F606W"), "red": ("F814W", "F850LP")},
        "preset": "Galaxy",
        "stretch": {"low": 0.2, "high": 99.75, "gamma": 1.05, "asinh": 10.0},
    },
    "M42": {
        "name": "Orion Nebula",
        "filters": {"blue": ("F435W", "F438W"), "green": ("F502N", "F555W"), "red": ("F658N", "F656N", "F814W")},
        "preset": "Nebula",
        "stretch": {"low": 0.1, "high": 99.9, "gamma": 0.95, "asinh": 16.0},
    },
}



