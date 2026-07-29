import json
import re
import threading
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk

from .paths import PLANETARY_DIR


class PlanetaryWorkflowMixin:
    MARS_FEATURES = {
        "Jezero Crater": (18.38, 77.58, "Perseverance landing region and ancient river-delta deposits."),
        "Gale Crater": (-5.40, 137.80, "Curiosity landing region and the layered mountain Aeolis Mons."),
        "Olympus Mons": (18.65, 226.20, "The largest known volcano in the Solar System."),
        "Valles Marineris": (-14.00, 300.00, "A vast canyon system extending thousands of kilometres."),
        "Gusev Crater": (-14.57, 175.47, "Spirit rover landing region and an ancient crater lake candidate."),
        "Meridiani Planum": (-1.95, 354.47, "Opportunity rover landing region rich in sedimentary deposits."),
        "Viking 1 Landing Site": (22.48, 310.03, "Chryse Planitia landing site of Viking 1."),
        "North Polar Cap": (85.00, 0.00, "Layered water-ice and seasonal carbon-dioxide frost deposits."),
        "South Polar Cap": (-85.00, 0.00, "Permanent and seasonal polar ice deposits."),
    }

    MARS_DATASETS = {
        "MRO HiRISE — projected color/red": {
            "ihid": "MRO", "iid": "HiRISE", "pt": "RDRV11",
            "description": "Very-high-resolution projected images from Mars Reconnaissance Orbiter.",
        },
        "MRO CTX — context camera": {
            "ihid": "MRO", "iid": "CTX", "pt": "EDR",
            "description": "Wide-area context images useful for regional geology and HiRISE context.",
        },
        "Mars Odyssey THEMIS — calibrated visible": {
            "ihid": "ODY", "iid": "THEMIS", "pt": "VISRDR",
            "description": "Calibrated visible-light imaging from Mars Odyssey THEMIS.",
        },
        "Mars Express HRSC — map projected": {
            "ihid": "MEX", "iid": "HRSC", "pt": "REFDR4",
            "description": "Map-projected stereo color imaging from ESA Mars Express.",
        },
        "ExoMars TGO CaSSIS — derived": {
            "ihid": "EM16TGO", "iid": "CASSIS", "pt": "DERSC",
            "description": "Derived color and stereo surface images from ExoMars Trace Gas Orbiter.",
        },
    }

    MOON_FEATURES = {
        "Apollo 11 Landing Site": (0.6741, 23.4730, "Mare Tranquillitatis landing site of Apollo 11."),
        "Apollo 12 Landing Site": (-3.0128, 336.5780, "Oceanus Procellarum landing site of Apollo 12."),
        "Apollo 14 Landing Site": (-3.6453, 342.4690, "Fra Mauro landing site of Apollo 14."),
        "Apollo 15 Landing Site": (26.1322, 3.6339, "Hadley-Apennine landing site of Apollo 15."),
        "Apollo 16 Landing Site": (-8.9734, 15.5011, "Descartes Highlands landing site of Apollo 16."),
        "Apollo 17 Landing Site": (20.1908, 30.7717, "Taurus-Littrow landing site of Apollo 17."),
        "Tycho Crater": (-43.31, 348.80, "Young prominent impact crater with an extensive ray system."),
        "Copernicus Crater": (9.62, 339.92, "Prominent complex crater in eastern Oceanus Procellarum."),
        "Aristarchus Plateau": (23.70, 312.50, "High-albedo volcanic region and frequent imaging target."),
        "Shackleton Crater": (-89.90, 0.00, "South-polar crater with permanently shadowed terrain."),
    }

    MOON_DATASETS = {
        "LRO LROC NAC — calibrated high resolution": {
            "target": "moon", "ihid": "LRO", "iid": "LROC", "pt": "CDRNAC4",
            "description": "Calibrated narrow-angle images from Lunar Reconnaissance Orbiter.",
        },
        "LRO LROC WAC — calibrated color": {
            "target": "moon", "ihid": "LRO", "iid": "LROC", "pt": "CDRWAC4",
            "description": "Calibrated wide-angle color observations from Lunar Reconnaissance Orbiter.",
        },
        "Clementine UV/VIS — experiment images": {
            "target": "moon", "ihid": "CLEM", "iid": "UVVIS", "pt": "EDR",
            "description": "Ultraviolet and visible camera observations from Clementine.",
        },
        "Chandrayaan-1 M3 — reflectance": {
            "target": "moon", "ihid": "CH1-ORB", "iid": "M3", "pt": "REFIMG",
            "description": "Moon Mineralogy Mapper reflectance image products.",
        },
    }

    MERCURY_FEATURES = {
        "Caloris Basin": (
            30.5, 162.7,
            "One of the Solar System's largest impact basins, surrounded by extensive volcanic plains.",
        ),
        "Rembrandt Basin": (
            -32.9, 271.8,
            "A large, well-preserved impact basin with exposed tectonic and volcanic structures.",
        ),
        "Rachmaninoff Basin": (
            27.6, 57.6,
            "A double-ring impact basin containing unusually young-looking smooth plains.",
        ),
        "Raditladi Basin": (
            27.0, 119.0,
            "A comparatively young peak-ring basin containing troughs and smooth interior plains.",
        ),
        "Pantheon Fossae": (
            30.0, 162.0,
            "A radiating system of tectonic troughs near the center of Caloris Basin.",
        ),
        "Discovery Rupes": (
            -56.3, 38.3,
            "A major lobate scarp formed as Mercury's interior cooled and the planet contracted.",
        ),
        "North Polar Deposits": (
            85.0, 30.0,
            "Permanently shadowed craters containing radar-bright deposits consistent with water ice.",
        ),
    }

    MERCURY_DATASETS = {
        "MESSENGER MDIS NAC — calibrated high resolution": {
            "target": "mercury", "ihid": "MESSENGER", "iid": "MDIS-NAC", "pt": "CDRNAC",
            "description": "Calibrated monochrome narrow-angle images from MESSENGER MDIS.",
        },
        "MESSENGER MDIS WAC — calibrated multispectral": {
            "target": "mercury", "ihid": "MESSENGER", "iid": "MDIS-WAC", "pt": "CDRWAC",
            "description": "Calibrated wide-angle multispectral images from MESSENGER MDIS.",
        },
        "MESSENGER MDIS WAC — map-projected color": {
            "target": "mercury", "ihid": "MESSENGER", "iid": "MDIS-WAC", "pt": "MDRWAC",
            "description": "Map-projected three-color multispectral products from MESSENGER MDIS.",
        },
    }

    VENUS_FEATURES = {
        "Maxwell Montes": (65.2, 3.1, "The highest mountain range on Venus, rising above Ishtar Terra."),
        "Maat Mons": (0.5, 194.5, "A large shield volcano whose surface shows evidence of comparatively recent activity."),
        "Aphrodite Terra": (-10.0, 100.0, "An extensive equatorial highland region comparable in size to Africa."),
        "Ishtar Terra": (70.0, 30.0, "A northern highland region containing Lakshmi Planum and Maxwell Montes."),
        "Ovda Regio": (-10.0, 90.0, "Tessera terrain in western Aphrodite Terra, intensely deformed by tectonic activity."),
        "Sapas Mons": (8.5, 188.0, "A broad shield volcano imaged in detail by Magellan radar."),
        "Mead Crater": (12.5, 57.2, "The largest known impact crater on Venus."),
    }

    VENUS_DATASETS = {
        "Magellan SAR — full-resolution radar mosaics": {
            "target": "venus", "ihid": "MGN", "iid": "RDRS", "pt": "FMIDR",
            "description": "Full-resolution Magellan synthetic-aperture radar mosaics.",
        },
        "Magellan SAR — regional context mosaics": {
            "target": "venus", "ihid": "MGN", "iid": "RDRS", "pt": "C1MIDR",
            "description": "Compressed regional Magellan radar mosaics at 225 meters per pixel.",
        },
        "Magellan SAR — broad context mosaics": {
            "target": "venus", "ihid": "MGN", "iid": "RDRS", "pt": "C3MIDR",
            "description": "Broad-coverage Magellan radar mosaics for regional and global context.",
        },
    }

    JUPITER_FEATURES = {
        "Great Red Spot": (-22.0, 0.0, "A long-lived anticyclonic storm; its longitude changes with time."),
        "North Polar Cyclones": (89.0, 0.0, "Juno revealed a central cyclone surrounded by a persistent polygon of cyclones."),
        "South Polar Cyclones": (-89.0, 0.0, "A cluster of powerful cyclones surrounding Jupiter's south pole."),
        "Equatorial Zone": (0.0, 0.0, "Bright ammonia-cloud region shaped by strong east-west jet streams."),
        "North Equatorial Belt": (12.0, 0.0, "A dark atmospheric belt containing turbulent clouds and vortices."),
        "South Equatorial Belt": (-12.0, 0.0, "The prominent belt bordering the Great Red Spot."),
    }

    JUPITER_DATASETS = {
        "JunoCam — raw and community-processed images": {
            "external_url": "https://www.missionjuno.swri.edu/junocam/processing",
            "description": "JunoCam observations, raw products, and processed submissions.",
        },
        "NASA PDS Juno mission archive": {
            "external_url": "https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/JUNO/juno.html",
            "description": "Calibrated Juno atmospheric, particle, and supporting mission data.",
        },
        "NASA PDS OPUS — Jupiter observations": {
            "external_url": "https://opus.pds-rings.seti.org/opus/#/",
            "description": "Cross-mission Jupiter observations from Voyager, Galileo, Cassini, Hubble, and others.",
        },
        "NASA Jupiter image gallery": {
            "external_url": "https://science.nasa.gov/gallery/jupiter/",
            "description": "Curated full-disk and detailed Jupiter imagery from NASA missions.",
        },
    }

    SATURN_FEATURES = {
        "North Polar Hexagon": (78.0, 0.0, "A persistent six-sided jet-stream pattern surrounding the north pole."),
        "North Polar Vortex": (90.0, 0.0, "A compact hurricane-like vortex centered on Saturn's north pole."),
        "South Polar Vortex": (-90.0, 0.0, "A warm, eye-like atmospheric vortex observed by Cassini."),
        "Equatorial Zone": (0.0, 0.0, "A broad cloud zone containing some of Saturn's fastest winds."),
        "Great White Spot Region": (35.0, 0.0, "Latitude band where immense episodic storms have developed."),
        "Main Ring System": (0.0, 0.0, "The A, B, and C rings; use mission archives for viewing rather than fixed surface coordinates."),
    }

    SATURN_DATASETS = {
        "Cassini ISS — OPUS image search": {
            "external_url": "https://opus.pds-rings.seti.org/opus/#/",
            "description": "Search calibrated Cassini Imaging Science Subsystem observations.",
        },
        "Cassini raw image archive": {
            "external_url": "https://science.nasa.gov/mission/cassini/multimedia/images/",
            "description": "NASA's mission imagery from Saturn, its rings, and its moons.",
        },
        "NASA PDS Saturn system archive": {
            "external_url": "https://pds-rings.seti.org/saturn/",
            "description": "PDS holdings for Saturn's rings, moons, and Cassini observations.",
        },
        "NASA Saturn image gallery": {
            "external_url": "https://science.nasa.gov/gallery/saturn/",
            "description": "Curated full-disk and detailed Saturn imagery from multiple missions.",
        },
    }

    PLANETARY_FEATURES = {
        "Mars": MARS_FEATURES,
        "Moon": MOON_FEATURES,
        "Mercury": MERCURY_FEATURES,
        "Venus": VENUS_FEATURES,
        "Jupiter": JUPITER_FEATURES,
        "Saturn": SATURN_FEATURES,
    }

    PLANETARY_DATASETS = {
        "Mars": MARS_DATASETS,
        "Moon": MOON_DATASETS,
        "Mercury": MERCURY_DATASETS,
        "Venus": VENUS_DATASETS,
        "Jupiter": JUPITER_DATASETS,
        "Saturn": SATURN_DATASETS,
    }

    PLANETARY_FULL_VIEW_URLS = {
        "Mars": "https://trek.nasa.gov/mars/",
        "Moon": "https://trek.nasa.gov/moon/",
        "Mercury": "https://trek.nasa.gov/mercury/",
        "Venus": "https://trek.nasa.gov/venus/",
        "Jupiter": "https://eyes.nasa.gov/apps/solar-system/#/jupiter",
        "Saturn": "https://eyes.nasa.gov/apps/solar-system/#/saturn",
    }

    PLANETARY_SOURCES = (
        ("NASA PDS Mars ODE", "https://ode.rsl.wustl.edu/mars/", "Cross-mission orbital product search and downloads."),
        ("NASA Mars Trek", "https://trek.nasa.gov/mars/", "Interactive global mosaics, elevation, landing sites, and WMTS layers."),
        ("NASA PDS Imaging", "https://pds-imaging.jpl.nasa.gov/", "Mission imaging archives and Planetary Image Atlas."),
        ("ESA Planetary Science Archive", "https://psa.esa.int/", "Mars Express and ExoMars mission archives."),
        ("ESO Science Archive", "https://archive.eso.org/", "Ground-based optical and infrared observations."),
        ("NASA PDS Lunar ODE", "https://ode.rsl.wustl.edu/moon/", "Cross-mission lunar product search and downloads."),
        ("LROC QuickMap", "https://quickmap.lroc.asu.edu/", "Interactive LRO imagery, terrain, and Apollo landing sites."),
        ("NASA Apollo Image Atlas", "https://www.lpi.usra.edu/resources/apollo/", "Original Apollo orbital and lunar-surface photography."),
        ("NASA PDS Chandrayaan-1", "https://pds-geosciences.wustl.edu/missions/chandrayaan1/", "M3 mineralogy and Mini-RF radar archives."),
        ("NASA PDS Mercury ODE", "https://ode.rsl.wustl.edu/mercury/", "Search and download MESSENGER MDIS products by location."),
        ("MESSENGER Image Archive", "https://messenger.jhuapl.edu/Explore/Images.html", "Mission images and science highlights from Mercury and the spacecraft."),
        ("ESA BepiColombo Image Archive", "https://www.esa.int/Science_Exploration/Space_Science/BepiColombo/%28archive%29/0/%28type%29/image", "Official images from BepiColombo's cruise and Mercury flybys."),
        ("ESA Planetary Science Archive — BepiColombo", "https://psa.esa.int/", "BepiColombo science products and mission documentation in ESA's archive."),
        ("NASA PDS Venus ODE", "https://ode.rsl.wustl.edu/venus/", "Search and download Magellan radar products by surface location."),
        ("NASA Venus Trek", "https://trek.nasa.gov/venus/", "Interactive global Magellan radar, topography, and geology layers."),
        ("JunoCam Image Processing", "https://www.missionjuno.swri.edu/junocam/processing", "Raw and community-processed JunoCam observations of Jupiter."),
        ("NASA PDS OPUS", "https://opus.pds-rings.seti.org/opus/#/", "Cross-mission search for Jupiter, Saturn, rings, and satellite observations."),
        ("NASA Cassini Images", "https://science.nasa.gov/mission/cassini/multimedia/images/", "Mission imagery of Saturn, its rings, and its moons."),
        ("NASA Eyes on the Solar System", "https://eyes.nasa.gov/apps/solar-system/", "Interactive 3D full-planet and spacecraft views for the outer planets."),
    )

    @staticmethod
    def mars_display_longitude(longitude):
        longitude = float(longitude) % 360.0
        return longitude - 360.0 if longitude > 180.0 else longitude

    @staticmethod
    def mars_search_bounds(latitude, longitude, radius):
        latitude = max(-90.0, min(90.0, float(latitude)))
        longitude = float(longitude) % 360.0
        radius = max(0.01, min(20.0, float(radius)))
        return {
            "minlat": max(-90.0, latitude - radius),
            "maxlat": min(90.0, latitude + radius),
            "westernlon": max(0.0, longitude - radius),
            "easternlon": min(360.0, longitude + radius),
        }

    @classmethod
    def build_mars_ode_url(cls, latitude, longitude, radius, dataset_name, limit=25):
        return cls.build_planetary_ode_url(latitude, longitude, radius, dataset_name, limit)

    @classmethod
    def planetary_dataset_configuration(cls, dataset_name):
        for planet, datasets in cls.PLANETARY_DATASETS.items():
            if dataset_name in datasets:
                return planet, datasets[dataset_name]
        raise KeyError(dataset_name)

    @classmethod
    def build_planetary_ode_url(cls, latitude, longitude, radius, dataset_name, limit=25):
        planet, dataset = cls.planetary_dataset_configuration(dataset_name)
        parameters = {
            "query": "products",
            "target": dataset.get("target", planet.lower()),
            "results": "cm",
            "output": "json",
            "loc": "b",
            "limit": max(1, min(100, int(limit))),
            "ihid": dataset["ihid"],
            "iid": dataset["iid"],
            "pt": dataset["pt"],
            **cls.mars_search_bounds(latitude, longitude, radius),
        }
        return "https://oderest.rsl.wustl.edu/live2?" + urlencode(parameters)

    @staticmethod
    def parse_mars_ode_response(payload):
        root = (payload or {}).get("ODEResults", {})
        if str(root.get("Status", "")).lower() != "success":
            message = root.get("Error") or root.get("ErrorMessage") or "NASA PDS ODE returned an error."
            raise RuntimeError(str(message))
        product_container = root.get("Products", {})
        if not isinstance(product_container, dict):
            return []
        products = product_container.get("Product", [])
        if isinstance(products, dict):
            products = [products]
        return [dict(product) for product in products or []]

    @classmethod
    def query_mars_ode(cls, latitude, longitude, radius, dataset_name, limit=25, timeout=35):
        return cls.query_planetary_ode(latitude, longitude, radius, dataset_name, limit, timeout)

    @classmethod
    def query_planetary_ode(cls, latitude, longitude, radius, dataset_name, limit=25, timeout=35):
        planet, dataset = cls.planetary_dataset_configuration(dataset_name)
        url = cls.build_planetary_ode_url(latitude, longitude, radius, dataset_name, limit)
        request = Request(url, headers={"User-Agent": "Hubble-Workbench/2.0 Planetary-Observatory"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        products = cls.parse_mars_ode_response(payload)
        for product in products:
            product["_Planetary_target"] = dataset.get("target", planet.lower())
        return products, url

    @classmethod
    def build_mars_files_url(cls, product):
        product_id = cls.planetary_archive_product_id(product, "")
        if not product_id:
            raise ValueError("The selected product does not provide an archive product identifier.")
        return "https://oderest.rsl.wustl.edu/live2?" + urlencode({
            "target": str(product.get("_Planetary_target") or "mars").lower(),
            "query": "product",
            "results": "mf",
            "output": "json",
            "pdsid": product_id,
        })

    @staticmethod
    def parse_planetary_product_files(payload):
        products = PlanetaryWorkflowMixin.parse_mars_ode_response(payload)
        if not products:
            return []
        files = products[0].get("Product_files", {}).get("Product_file", [])
        if isinstance(files, dict):
            files = [files]
        return [
            dict(item)
            for item in files or []
            if str(item.get("URL") or "").startswith(("https://", "http://"))
        ]

    @classmethod
    def query_planetary_product_files(cls, product, timeout=35):
        url = cls.build_mars_files_url(product)
        request = Request(url, headers={"User-Agent": "Hubble-Workbench/2.0 Planetary-Observatory"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        return cls.parse_planetary_product_files(payload), url

    @staticmethod
    def planetary_file_size_text(kbytes):
        try:
            size = max(0.0, float(kbytes))
        except (TypeError, ValueError):
            return "Unknown"
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} GB"
        if size >= 1024:
            return f"{size / 1024:.1f} MB"
        return f"{size:.0f} KB"

    @staticmethod
    def unique_planetary_destination(folder, filename):
        folder = Path(folder)
        safe_name = Path(str(filename or "planetary_product.dat")).name
        destination = folder / safe_name
        counter = 2
        while destination.exists():
            destination = folder / f"{Path(safe_name).stem}_{counter}{Path(safe_name).suffix}"
            counter += 1
        return destination

    @staticmethod
    def planetary_map_point(latitude, longitude, width, height, padding=28):
        longitude = PlanetaryWorkflowMixin.mars_display_longitude(longitude)
        plot_width = max(1.0, float(width) - 2 * padding)
        plot_height = max(1.0, float(height) - 2 * padding)
        x = padding + (longitude + 180.0) / 360.0 * plot_width
        y = padding + (90.0 - float(latitude)) / 180.0 * plot_height
        return x, y

    @staticmethod
    def planetary_map_coordinates(x, y, width, height, padding=28):
        plot_width = max(1.0, float(width) - 2 * padding)
        plot_height = max(1.0, float(height) - 2 * padding)
        longitude = ((float(x) - padding) / plot_width) * 360.0 - 180.0
        latitude = 90.0 - ((float(y) - padding) / plot_height) * 180.0
        return max(-90.0, min(90.0, latitude)), longitude % 360.0

    @staticmethod
    def planetary_product_id(product, fallback="Planetary product"):
        direct = product.get("Observation_id") or product.get("Product_id")
        if direct:
            return str(direct)
        for field in ("ProductURL", "FilesURL"):
            query = parse_qs(urlparse(str(product.get(field) or "")).query)
            if query.get("product_id"):
                return str(query["product_id"][0])
        return fallback

    @staticmethod
    def planetary_archive_product_id(product, fallback=""):
        for field in ("ProductURL", "FilesURL"):
            query = parse_qs(urlparse(str(product.get(field) or "")).query)
            if query.get("product_id"):
                return str(query["product_id"][0])
        return PlanetaryWorkflowMixin.planetary_product_id(product, fallback)

    @classmethod
    def build_mars_asset_url(cls, product, kind="thumbnail"):
        if kind not in {"thumbnail", "browse", "lgbrowse"}:
            raise ValueError(f"Unsupported planetary preview type: {kind}")
        product_id = cls.planetary_archive_product_id(product, "")
        if not product_id:
            raise ValueError("The selected product does not provide a PDS product identifier.")
        return "https://oderest.rsl.wustl.edu/live2?" + urlencode({
            "target": str(product.get("_Planetary_target") or "mars").lower(),
            "query": kind,
            "pdsid": product_id,
        })

    @staticmethod
    def fetch_planetary_image(url, timeout=35):
        request = Request(url, headers={"User-Agent": "Hubble-Workbench/2.0 Planetary-Observatory"})
        with urlopen(request, timeout=timeout) as response:
            content_type = str(response.headers.get("Content-Type") or "").lower()
            data = response.read()
        if not data or ("image" not in content_type and not data.startswith(b"\x89PNG")):
            raise RuntimeError("NASA PDS did not return a preview image for this product.")
        return data

    @staticmethod
    def planetary_footprint_points(product):
        footprint = str(product.get("Footprint_C0_geometry") or "")
        if not footprint or "EMPTY" in footprint.upper():
            return []
        match = re.search(r"POLYGON\s*\(\((.*?)\)\)", footprint, re.IGNORECASE)
        if not match:
            return []
        points = []
        for pair in match.group(1).split(","):
            numbers = pair.strip().split()
            if len(numbers) < 2:
                continue
            try:
                longitude, latitude = float(numbers[0]), float(numbers[1])
            except ValueError:
                continue
            points.append((latitude, longitude))
        return points

    @staticmethod
    def planetary_product_details(product, dataset_name=""):
        if not product:
            return "Select a product to see observation details."
        lines = [
            PlanetaryWorkflowMixin.planetary_product_id(product),
            "=" * 54,
            "",
            str(product.get("Comment") or product.get("Description") or "No description supplied."),
            "",
            f"Dataset: {dataset_name}",
            f"Observation time: {product.get('Observation_time') or product.get('UTC_start_time') or 'Unknown'}",
            f"Center: {product.get('Center_latitude', '?')}° latitude, {product.get('Center_longitude', '?')}° longitude",
            f"Map scale: {product.get('Map_scale', 'Unknown')} m/pixel",
            f"Incidence angle: {product.get('Incidence_angle', 'Unknown')}°",
            f"Emission angle: {product.get('Emission_angle', 'Unknown')}°",
            f"Phase angle: {product.get('Phase_angle', 'Unknown')}°",
            f"Solar longitude: {product.get('Solar_longitude', 'Unknown')}°",
            "",
            f"Product page: {product.get('ProductURL', '')}",
            f"Files: {product.get('FilesURL', '')}",
        ]
        return "\n".join(lines)

    def build_planetary_tab(self):
        PLANETARY_DIR.mkdir(parents=True, exist_ok=True)
        controls = ttk.Frame(self.planetary_tab)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="Planet").pack(side="left")
        self.planetary_planet_var = tk.StringVar(value="Mars")
        planet_combo = ttk.Combobox(
            controls,
            textvariable=self.planetary_planet_var,
            values=list(self.PLANETARY_FEATURES),
            state="readonly",
            width=8,
        )
        planet_combo.pack(side="left", padx=(6, 12))
        planet_combo.bind("<<ComboboxSelected>>", self.planetary_select_planet)
        ttk.Label(controls, text="View").pack(side="left")
        self.planetary_view_var = tk.StringVar(value="Surface Detail")
        view_combo = ttk.Combobox(
            controls,
            textvariable=self.planetary_view_var,
            values=("Surface Detail", "Full Planet / Mission View"),
            state="readonly",
            width=22,
        )
        view_combo.pack(side="left", padx=(6, 6))
        view_combo.bind("<<ComboboxSelected>>", self.planetary_view_changed)
        ttk.Button(
            controls,
            text="Open View",
            command=self.open_selected_planetary_view,
        ).pack(side="left", padx=(0, 12))
        ttk.Label(controls, text="Named feature").pack(side="left")
        self.planetary_feature_var = tk.StringVar(value="Jezero Crater")
        self.planetary_feature_combo = ttk.Combobox(
            controls, textvariable=self.planetary_feature_var,
            values=list(self.MARS_FEATURES), state="readonly", width=22,
        )
        self.planetary_feature_combo.pack(side="left", padx=(6, 12))
        self.planetary_feature_combo.bind("<<ComboboxSelected>>", self.planetary_select_feature)
        ttk.Label(controls, text="Dataset").pack(side="left")
        self.planetary_dataset_var = tk.StringVar(value=next(iter(self.MARS_DATASETS)))
        self.planetary_dataset_combo = ttk.Combobox(
            controls, textvariable=self.planetary_dataset_var,
            values=list(self.MARS_DATASETS), state="readonly", width=34,
        )
        self.planetary_dataset_combo.pack(side="left", padx=(6, 12))
        self.planetary_dataset_combo.bind(
            "<<ComboboxSelected>>", self.planetary_dataset_changed
        )
        self.planetary_search_button = ttk.Button(
            controls,
            text="Search NASA PDS",
            command=lambda: self.planetary_search_async(),
        )
        self.planetary_search_button.pack(side="left")
        ttk.Button(
            controls,
            text="Apollo Image Atlas",
            command=lambda: self.open_file("https://www.lpi.usra.edu/resources/apollo/"),
        ).pack(side="left", padx=(6, 0))
        self.enable_responsive_toolbar(controls)

        coordinates = ttk.Frame(self.planetary_tab)
        coordinates.pack(fill="x", pady=(0, 8))
        self.planetary_latitude_var = tk.DoubleVar(value=18.38)
        self.planetary_longitude_var = tk.DoubleVar(value=77.58)
        self.planetary_radius_var = tk.DoubleVar(value=0.25)
        for label, variable, low, high in (
            ("Latitude", self.planetary_latitude_var, -90, 90),
            ("East longitude", self.planetary_longitude_var, 0, 360),
            ("Search radius", self.planetary_radius_var, 0.01, 20),
        ):
            ttk.Label(coordinates, text=label).pack(side="left")
            ttk.Spinbox(coordinates, textvariable=variable, from_=low, to=high, increment=0.1, width=9).pack(side="left", padx=(6, 12))
        ttk.Label(coordinates, text="degrees").pack(side="left")
        ttk.Button(coordinates, text="Redraw Region", command=lambda: self.draw_planetary_map()).pack(side="left", padx=(10, 0))
        ttk.Button(coordinates, text="Open Planetary Folder", command=lambda: self.open_folder(PLANETARY_DIR)).pack(side="left", padx=(6, 0))
        self.planetary_status_var = tk.StringVar(value="Choose a feature or click the Mars map, then search official PDS products.")
        ttk.Label(coordinates, textvariable=self.planetary_status_var).pack(side="left", padx=(12, 0))
        self.enable_responsive_toolbar(coordinates)

        body = tk.PanedWindow(self.planetary_tab, orient="horizontal", bd=0, relief="flat", sashwidth=6, bg="#d1d5db")
        body.pack(fill="both", expand=True)
        map_panel = ttk.Frame(body)
        data_panel = ttk.Frame(body)
        body.add(map_panel, stretch="always", minsize=420)
        body.add(data_panel, stretch="always", minsize=360)
        self.enable_responsive_split_pane(body, self.planetary_tab)

        self.planetary_map_canvas = tk.Canvas(map_panel, bg="#2b1510", highlightthickness=0, height=390)
        self.planetary_map_canvas.pack(fill="both", expand=True)
        self.planetary_map_canvas.bind("<Configure>", lambda _event: self.draw_planetary_map())
        self.planetary_map_canvas.bind("<Button-1>", self.planetary_map_click)
        self.planetary_feature_description_var = tk.StringVar(value="")
        self.responsive_wrap_label(map_panel, textvariable=self.planetary_feature_description_var, minimum=260).pack(fill="x", pady=(6, 0))

        tabs = ttk.Notebook(data_panel)
        tabs.pack(fill="both", expand=True)
        products_panel = ttk.Frame(tabs)
        sources_panel = ttk.Frame(tabs)
        tabs.add(products_panel, text="Products / Preview")
        tabs.add(sources_panel, text="Official Sources")
        sources_content = self.build_scrollable_tab_content(sources_panel)

        result_columns = ("id", "date", "scale", "description")
        self.planetary_results_tree = ttk.Treeview(products_panel, columns=result_columns, show="headings", height=11)
        for column, heading, width in (
            ("id", "Observation", 145), ("date", "Date", 105),
            ("scale", "m/pixel", 70), ("description", "Description", 260),
        ):
            self.planetary_results_tree.heading(column, text=heading)
            self.planetary_results_tree.column(column, width=width, anchor="w")
        self.planetary_results_tree.pack(fill="x", expand=False)
        self.planetary_results_tree.bind("<<TreeviewSelect>>", self.planetary_result_selected)
        product_tools = ttk.Frame(products_panel)
        product_tools.pack(fill="x", pady=6)
        ttk.Button(product_tools, text="Open Product Page", command=lambda: self.open_selected_planetary_url("ProductURL")).pack(side="left")
        ttk.Button(product_tools, text="Open Files", command=lambda: self.open_selected_planetary_url("FilesURL")).pack(side="left", padx=(6, 0))
        ttk.Button(product_tools, text="Browse / Download Files", command=self.load_planetary_file_list_async).pack(side="left", padx=(6, 0))
        ttk.Button(product_tools, text="Open Mission Preview", command=lambda: self.open_selected_planetary_url("External_url")).pack(side="left", padx=(6, 0))
        ttk.Button(product_tools, text="Load Preview", command=lambda: self.load_planetary_preview("browse")).pack(side="left", padx=(6, 0))
        ttk.Button(product_tools, text="Save Browse Image", command=self.save_planetary_browse_async).pack(side="left", padx=(6, 0))
        self.enable_responsive_toolbar(product_tools)
        self.planetary_preview_label = ttk.Label(
            products_panel,
            text="Select a product to load its official PDS browse image.",
            anchor="center",
        )
        self.planetary_preview_label.pack(fill="x", pady=(0, 6))
        self.planetary_details_text = tk.Text(products_panel, wrap="word", bg="#ffffff", fg="#1f1f1f", relief="flat", padx=10, pady=10)
        self.planetary_details_text.pack(fill="both", expand=True)
        self.planetary_details_text.insert("1.0", self.planetary_product_details(None))

        for name, url, description in self.PLANETARY_SOURCES:
            row = ttk.Frame(sources_content, padding=8, relief="ridge")
            row.pack(fill="x", padx=4, pady=4)
            ttk.Label(row, text=name, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(row, text=description, wraplength=480).pack(anchor="w", pady=(2, 5))
            ttk.Button(row, text="Open Official Source", command=lambda address=url: self.open_file(address)).pack(anchor="w")

        self.planetary_products = []
        self.planetary_selected_product = None
        self.planetary_preview_image = None
        self.planetary_preview_token = 0
        self.after(100, self.planetary_select_feature)

    def planetary_current_features(self):
        planet = self.planetary_planet_var.get() if hasattr(self, "planetary_planet_var") else "Mars"
        return self.PLANETARY_FEATURES.get(planet, self.MARS_FEATURES)

    def planetary_current_datasets(self):
        planet = self.planetary_planet_var.get() if hasattr(self, "planetary_planet_var") else "Mars"
        return self.PLANETARY_DATASETS.get(planet, self.MARS_DATASETS)

    def planetary_dataset_changed(self, _event=None):
        dataset = self.planetary_current_datasets().get(
            self.planetary_dataset_var.get(), {}
        )
        external = bool(dataset.get("external_url"))
        self.planetary_search_button.configure(
            text="Open Mission Archive" if external else "Search NASA PDS"
        )
        if external:
            self.planetary_status_var.set(
                dataset.get("description", "Open the official mission archive.")
            )
        return True

    def planetary_view_changed(self, _event=None):
        planet = self.planetary_planet_var.get()
        if self.planetary_view_var.get().startswith("Full Planet"):
            self.planetary_status_var.set(
                f"Full Planet mode selected for {planet}. Choose Open View for NASA's "
                "interactive mission-data globe."
            )
        else:
            self.planetary_status_var.set(
                f"Surface Detail mode selected for {planet}. Choose a feature or click "
                "the map, then search official PDS products."
            )
        return True

    def open_selected_planetary_view(self):
        planet = self.planetary_planet_var.get()
        if self.planetary_view_var.get().startswith("Full Planet"):
            url = self.PLANETARY_FULL_VIEW_URLS.get(planet)
            if not url:
                self.planetary_status_var.set(
                    f"A full-planet globe is not configured for {planet} yet."
                )
                return False
            self.open_file(url)
            self.planetary_status_var.set(
                f"Opened NASA's interactive full-{planet} mission view in your browser."
            )
            return True
        self.draw_planetary_map()
        self.planetary_status_var.set(
            f"Showing the {planet} surface-detail map. Select a feature or search PDS."
        )
        return True

    def planetary_select_planet(self, _event=None):
        planet = self.planetary_planet_var.get()
        features = self.planetary_current_features()
        datasets = self.planetary_current_datasets()
        self.planetary_feature_combo.configure(values=list(features))
        self.planetary_dataset_combo.configure(values=list(datasets))
        self.planetary_feature_var.set(next(iter(features)))
        self.planetary_dataset_var.set(next(iter(datasets)))
        self.planetary_dataset_changed()
        self.planetary_products = []
        self.planetary_selected_product = None
        self.planetary_results_tree.delete(*self.planetary_results_tree.get_children())
        self.clear_planetary_preview(
            f"Select a {planet} product to load its official PDS browse image."
        )
        selected_dataset = datasets[self.planetary_dataset_var.get()]
        if selected_dataset.get("external_url"):
            self.planetary_status_var.set(
                f"Choose a {planet} mission collection, then open its official archive."
            )
        else:
            self.planetary_status_var.set(
                f"Choose a {planet} feature or click the map, then search official PDS products."
            )
        self.planetary_select_feature()
        if self.planetary_view_var.get().startswith("Full Planet"):
            self.planetary_view_changed()

    def planetary_select_feature(self, _event=None):
        feature = self.planetary_current_features().get(self.planetary_feature_var.get())
        if not feature:
            return
        latitude, longitude, description = feature
        self.planetary_latitude_var.set(latitude)
        self.planetary_longitude_var.set(longitude)
        self.planetary_feature_description_var.set(
            f"{self.planetary_feature_var.get()}: {description}"
        )
        self.draw_planetary_map()

    def draw_planetary_map(self):
        if not hasattr(self, "planetary_map_canvas"):
            return
        canvas = self.planetary_map_canvas
        canvas.delete("all")
        width, height = max(420, canvas.winfo_width()), max(260, canvas.winfo_height())
        padding = 28
        planet = self.planetary_planet_var.get()
        palettes = {
            "Moon": ("#171717", "#78716c", "#e7e5e4", "#a8a29e"),
            "Mercury": ("#151515", "#625f5a", "#d6d3d1", "#8f8a83"),
            "Venus": ("#2a1e0f", "#ad7a32", "#f6d58d", "#cf9d55"),
            "Jupiter": ("#241b18", "#b88968", "#f4d4bd", "#8f624d"),
            "Saturn": ("#242117", "#b7a36d", "#f3e5b5", "#8c7a4d"),
            "Mars": ("#2b1510", "#8f3f24", "#f4a261", "#b96542"),
        }
        background, map_fill, map_outline, grid_fill = palettes.get(
            planet, palettes["Mars"]
        )
        canvas.configure(bg=background)
        canvas.create_rectangle(
            padding, padding, width - padding, height - padding,
            fill=map_fill, outline=map_outline, width=2,
        )
        for latitude in range(-60, 61, 30):
            _x, y = self.planetary_map_point(latitude, 0, width, height, padding)
            canvas.create_line(padding, y, width - padding, y, fill=grid_fill)
            canvas.create_text(4, y, text=f"{latitude:+d}°", anchor="w", fill="#f4d6c6")
        for longitude in range(-120, 181, 60):
            x, _y = self.planetary_map_point(0, longitude, width, height, padding)
            canvas.create_line(x, padding, x, height - padding, fill=grid_fill)
            canvas.create_text(x, height - 4, text=f"{longitude:+d}°", anchor="s", fill="#f4d6c6")
        for name, (latitude, longitude, _description) in self.planetary_current_features().items():
            x, y = self.planetary_map_point(latitude, longitude, width, height, padding)
            selected = name == self.planetary_feature_var.get()
            canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#facc15" if selected else "#f8fafc", outline="#111827")
            if selected:
                canvas.create_text(x + 7, y - 7, text=name, anchor="sw", fill="#fff7d6")
        latitude = float(self.planetary_latitude_var.get())
        longitude = float(self.planetary_longitude_var.get())
        radius = float(self.planetary_radius_var.get())
        x, y = self.planetary_map_point(latitude, longitude, width, height, padding)
        dx = radius / 360.0 * (width - 2 * padding) * 2
        dy = radius / 180.0 * (height - 2 * padding) * 2
        canvas.create_rectangle(x - dx, y - dy, x + dx, y + dy, outline="#22d3ee", width=2)
        selected_product = getattr(self, "planetary_selected_product", None)
        for product in getattr(self, "planetary_products", []):
            try:
                footprint = self.planetary_footprint_points(product)
                if footprint:
                    coordinates = []
                    for footprint_latitude, footprint_longitude in footprint:
                        fx, fy = self.planetary_map_point(
                            footprint_latitude, footprint_longitude, width, height, padding,
                        )
                        coordinates.extend((fx, fy))
                    if len(coordinates) >= 6:
                        canvas.create_line(
                            *coordinates,
                            fill="#facc15" if product is selected_product else "#67e8f9",
                            width=3 if product is selected_product else 1,
                        )
                px, py = self.planetary_map_point(
                    float(product.get("Center_latitude")),
                    float(product.get("Center_longitude")),
                    width, height, padding,
                )
                marker_radius = 5 if product is selected_product else 2
                canvas.create_oval(
                    px - marker_radius, py - marker_radius,
                    px + marker_radius, py + marker_radius,
                    fill="#facc15" if product is selected_product else "#22d3ee",
                    outline="#111827" if product is selected_product else "",
                )
            except (TypeError, ValueError):
                continue
        canvas.create_text(
            width / 2, 8,
            text=f"{planet} — equirectangular feature and product map",
            anchor="n", fill="#fff7ed", font=("Segoe UI", 10, "bold"),
        )

    def planetary_map_click(self, event):
        width = max(420, self.planetary_map_canvas.winfo_width())
        height = max(260, self.planetary_map_canvas.winfo_height())
        latitude, longitude = self.planetary_map_coordinates(event.x, event.y, width, height)
        self.planetary_latitude_var.set(round(latitude, 4))
        self.planetary_longitude_var.set(round(longitude, 4))
        self.planetary_feature_var.set("")
        self.planetary_feature_description_var.set(
            f"Custom {self.planetary_planet_var.get()} location: "
            f"{latitude:.4f}° latitude, {longitude:.4f}° east longitude."
        )
        self.draw_planetary_map()

    def planetary_search_async(self):
        dataset_name = self.planetary_dataset_var.get()
        dataset_configuration = self.planetary_current_datasets().get(
            dataset_name, {}
        )
        external_url = dataset_configuration.get("external_url")
        if external_url:
            self.open_file(external_url)
            self.planetary_status_var.set(
                f"Opened the official {dataset_name} source in your browser."
            )
            return True
        try:
            latitude = float(self.planetary_latitude_var.get())
            longitude = float(self.planetary_longitude_var.get())
            radius = float(self.planetary_radius_var.get())
            dataset = dataset_name
            self.build_planetary_ode_url(latitude, longitude, radius, dataset)
        except Exception as exc:
            self.planetary_status_var.set(f"Search settings need attention: {exc}")
            return
        planet = self.planetary_planet_var.get()
        self.planetary_status_var.set(f"Searching NASA PDS {planet} ODE...")

        def worker():
            try:
                products, query_url = self.query_planetary_ode(
                    latitude, longitude, radius, dataset
                )
                error = None
            except Exception as exc:
                products, query_url, error = [], "", exc
            self.after(0, lambda: self.finish_planetary_search(products, query_url, dataset, error))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def finish_planetary_search(self, products, query_url, dataset, error=None):
        if error:
            self.planetary_status_var.set(f"NASA PDS search failed: {error}")
            return
        self.planetary_products = list(products)
        self.planetary_last_query_url = query_url
        self.planetary_results_tree.delete(*self.planetary_results_tree.get_children())
        for index, product in enumerate(self.planetary_products):
            observation_id = self.planetary_product_id(product, f"Product {index + 1}")
            date = str(product.get("Observation_time") or product.get("UTC_start_time") or "")[:10]
            self.planetary_results_tree.insert(
                "", "end", iid=str(index),
                values=(observation_id, date, product.get("Map_scale", ""), product.get("Comment") or product.get("Description") or ""),
            )
        self.planetary_selected_product = None
        self.clear_planetary_preview("Select a product to load its official PDS browse image.")
        self.draw_planetary_map()
        self.planetary_status_var.set(
            f"Found {len(products)} {dataset} product(s) in the selected region."
        )

    def planetary_result_selected(self, _event=None):
        selection = self.planetary_results_tree.selection()
        if not selection:
            return
        index = int(selection[0])
        if not 0 <= index < len(self.planetary_products):
            return
        self.planetary_selected_product = self.planetary_products[index]
        self.planetary_details_text.delete("1.0", "end")
        self.planetary_details_text.insert(
            "1.0",
            self.planetary_product_details(
                self.planetary_selected_product,
                self.planetary_dataset_var.get(),
            ),
        )
        self.draw_planetary_map()
        self.load_planetary_preview("browse")

    def clear_planetary_preview(self, message):
        self.planetary_preview_token += 1
        self.planetary_preview_image = None
        if hasattr(self, "planetary_preview_label"):
            self.planetary_preview_label.configure(image="", text=message)

    def load_planetary_preview(self, kind="thumbnail"):
        product = self.planetary_selected_product
        if not product:
            self.planetary_status_var.set("Select a PDS product first.")
            return False
        try:
            url = self.build_mars_asset_url(product, kind)
        except Exception as exc:
            self.clear_planetary_preview(str(exc))
            return False
        self.planetary_preview_token += 1
        token = self.planetary_preview_token
        product_id = self.planetary_product_id(product)
        self.planetary_preview_label.configure(
            image="", text=f"Loading official PDS {kind} for {product_id}..."
        )

        def worker():
            try:
                data = self.fetch_planetary_image(url)
                error = None
            except Exception as exc:
                data, error = b"", exc
            self.after(0, lambda: self.finish_planetary_preview(data, product_id, kind, token, error))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def finish_planetary_preview(self, data, product_id, kind, token, error=None):
        if token != self.planetary_preview_token:
            return
        if error:
            self.planetary_preview_image = None
            self.planetary_preview_label.configure(
                image="", text=f"No {kind} is available for {product_id}."
            )
            self.planetary_status_var.set(f"Preview unavailable: {error}")
            return
        try:
            with Image.open(BytesIO(data)) as source:
                preview = source.convert("RGB")
                preview.thumbnail((520, 210), Image.Resampling.LANCZOS)
                image = ImageTk.PhotoImage(preview)
            self.planetary_preview_image = image
            self.planetary_preview_label.configure(image=image, text="")
            self.planetary_status_var.set(f"Loaded official PDS {kind} for {product_id}.")
        except (OSError, tk.TclError) as exc:
            self.planetary_preview_label.configure(image="", text="The returned preview could not be displayed.")
            self.planetary_status_var.set(f"Preview display failed: {exc}")

    def save_planetary_browse_async(self):
        product = self.planetary_selected_product
        if not product:
            self.planetary_status_var.set("Select a PDS product first.")
            return False
        try:
            url = self.build_mars_asset_url(product, "lgbrowse")
            product_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.planetary_product_id(product))
        except Exception as exc:
            self.planetary_status_var.set(str(exc))
            return False
        target_folder = str(product.get("_Planetary_target") or "mars").lower()
        browse_folder = PLANETARY_DIR / target_folder
        browse_folder.mkdir(parents=True, exist_ok=True)
        destination = self.unique_planetary_destination(
            browse_folder,
            f"{product_id}_browse.png",
        )
        self.planetary_status_var.set(f"Downloading the best available browse image for {product_id}...")

        def worker():
            try:
                try:
                    data = self.fetch_planetary_image(url)
                except Exception:
                    data = self.fetch_planetary_image(self.build_mars_asset_url(product, "browse"))
                with Image.open(BytesIO(data)) as source:
                    source.convert("RGB").save(destination, format="PNG")
                error = None
            except Exception as exc:
                error = exc
            self.after(0, lambda: self.finish_planetary_browse_save(destination, error))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def finish_planetary_browse_save(self, destination, error=None):
        if error:
            self.planetary_status_var.set(f"Browse image download failed: {error}")
            return
        self.planetary_status_var.set(f"Saved browse image: {destination.name}")
        self.open_folder(destination.parent)

    def open_selected_planetary_url(self, field):
        product = self.planetary_selected_product
        if not product:
            self.planetary_status_var.set("Select a PDS product first.")
            return False
        url = str(product.get(field) or "").strip()
        if not url:
            self.planetary_status_var.set("That link is not available for the selected product.")
            return False
        self.open_file(url)
        return True

    def load_planetary_file_list_async(self):
        product = self.planetary_selected_product
        if not product:
            self.planetary_status_var.set("Select a PDS product first.")
            return False
        product_id = self.planetary_product_id(product)
        self.planetary_status_var.set(f"Loading the official file list for {product_id}...")

        def worker():
            try:
                files, query_url = self.query_planetary_product_files(product)
                error = None
            except Exception as exc:
                files, query_url, error = [], "", exc
            self.after(
                0,
                lambda: self.finish_planetary_file_list(product, files, query_url, error),
            )

        threading.Thread(target=worker, daemon=True).start()
        return True

    def finish_planetary_file_list(self, product, files, query_url, error=None):
        product_id = self.planetary_product_id(product)
        if error:
            self.planetary_status_var.set(f"Could not load the PDS file list: {error}")
            return
        self.planetary_status_var.set(f"Found {len(files)} downloadable file(s) for {product_id}.")
        self.show_planetary_file_dialog(product, files, query_url)

    def show_planetary_file_dialog(self, product, files, query_url=""):
        dialog = tk.Toplevel(self)
        dialog.title(f"PDS Product Files — {self.planetary_product_id(product)}")
        dialog.geometry("900x570")
        dialog.minsize(650, 420)
        dialog.transient(self)

        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Select one official archive file. Large science products can require several gigabytes.",
            wraplength=850,
        ).pack(anchor="w", pady=(0, 8))

        tree_frame = ttk.Frame(body)
        tree_frame.pack(fill="both", expand=True)
        columns = ("type", "name", "size", "description")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        for column, heading, width in (
            ("type", "Type", 90),
            ("name", "File", 280),
            ("size", "Size", 90),
            ("description", "Description", 350),
        ):
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w")
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for index, item in enumerate(files):
            tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    item.get("Type", ""),
                    item.get("FileName", ""),
                    self.planetary_file_size_text(item.get("KBytes")),
                    re.sub(r"<[^>]+>", "", str(item.get("Description") or "")),
                ),
            )

        status_var = tk.StringVar(value=f"{len(files)} file(s) supplied by NASA PDS ODE.")
        ttk.Label(body, textvariable=status_var, wraplength=850).pack(fill="x", pady=(8, 4))
        progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(body, variable=progress_var, maximum=100).pack(fill="x", pady=(0, 8))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        cancel_event = threading.Event()

        def selected_file():
            selection = tree.selection()
            if not selection:
                status_var.set("Select a file first.")
                return None
            index = int(selection[0])
            return files[index] if 0 <= index < len(files) else None

        def open_selected_url():
            item = selected_file()
            if not item:
                return
            self.open_file(str(item.get("URL")))

        ttk.Button(
            buttons,
            text="Open File URL",
            command=open_selected_url,
        ).pack(side="left")
        if query_url:
            ttk.Button(
                buttons,
                text="Open File List Source",
                command=lambda: self.open_file(query_url),
            ).pack(side="left", padx=(6, 0))
        download_button = ttk.Button(buttons, text="Download Selected")
        download_button.pack(side="right")
        cancel_button = ttk.Button(
            buttons,
            text="Cancel Download",
            state="disabled",
            command=cancel_event.set,
        )
        cancel_button.pack(side="right", padx=(0, 6))

        def close_dialog():
            if str(cancel_button.cget("state")) != "disabled":
                cancel_event.set()
                status_var.set("Cancelling the download before closing...")
                return
            dialog.destroy()

        ttk.Button(buttons, text="Close", command=close_dialog).pack(side="right", padx=(0, 6))
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

        download_button.configure(
            command=lambda: self.download_planetary_file_async(
                product,
                selected_file(),
                dialog,
                status_var,
                progress_var,
                download_button,
                cancel_button,
                cancel_event,
            )
        )
        if files:
            tree.selection_set("0")
        dialog.grab_set()

    def download_planetary_file_async(
        self,
        product,
        file_record,
        dialog,
        status_var,
        progress_var,
        download_button,
        cancel_button,
        cancel_event,
    ):
        if not file_record:
            status_var.set("Select a file first.")
            return False
        try:
            kbytes = float(file_record.get("KBytes") or 0)
        except (TypeError, ValueError):
            kbytes = 0
        if kbytes >= 100 * 1024:
            size_text = self.planetary_file_size_text(kbytes)
            if not messagebox.askyesno(
                "Large Planetary Download",
                f"{file_record.get('FileName', 'This file')} is approximately {size_text}.\n\n"
                "Download it now?",
                parent=dialog,
            ):
                return False

        target_folder = str(product.get("_Planetary_target") or "mars").lower()
        product_folder = PLANETARY_DIR / target_folder / re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            self.planetary_archive_product_id(product, "planetary_product"),
        )
        product_folder.mkdir(parents=True, exist_ok=True)
        destination = self.unique_planetary_destination(
            product_folder,
            file_record.get("FileName"),
        )
        part_path = destination.with_name(destination.name + ".part")
        cancel_event.clear()
        download_button.configure(state="disabled")
        cancel_button.configure(state="normal")
        progress_var.set(0)
        status_var.set(f"Downloading {destination.name}...")

        def report(completed, total):
            percent = completed / total * 100 if total else 0
            self.after(
                0,
                lambda: (
                    progress_var.set(percent),
                    status_var.set(
                        f"Downloading {destination.name}: "
                        f"{completed / (1024 * 1024):.1f} MB"
                        + (f" of {total / (1024 * 1024):.1f} MB" if total else "")
                    ),
                ),
            )

        def worker():
            error = None
            cancelled = False
            try:
                request = Request(
                    str(file_record.get("URL")),
                    headers={"User-Agent": "Hubble-Workbench/2.0 Planetary-Observatory"},
                )
                with urlopen(request, timeout=60) as response, part_path.open("wb") as output:
                    total = int(response.headers.get("Content-Length") or 0)
                    completed = 0
                    while True:
                        if cancel_event.is_set():
                            cancelled = True
                            break
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        completed += len(chunk)
                        report(completed, total)
                if cancelled:
                    if part_path.exists():
                        part_path.unlink()
                else:
                    part_path.replace(destination)
            except Exception as exc:
                error = exc
                if part_path.exists():
                    try:
                        part_path.unlink()
                    except OSError:
                        pass
            self.after(
                0,
                lambda: self.finish_planetary_file_download(
                    destination,
                    cancelled,
                    error,
                    status_var,
                    progress_var,
                    download_button,
                    cancel_button,
                ),
            )

        threading.Thread(target=worker, daemon=True).start()
        return True

    def finish_planetary_file_download(
        self,
        destination,
        cancelled,
        error,
        status_var,
        progress_var,
        download_button,
        cancel_button,
    ):
        download_button.configure(state="normal")
        cancel_button.configure(state="disabled")
        if cancelled:
            progress_var.set(0)
            status_var.set("Download cancelled. The incomplete temporary file was removed.")
            self.planetary_status_var.set("Planetary file download cancelled.")
            return
        if error:
            progress_var.set(0)
            status_var.set(f"Download failed: {error}")
            self.planetary_status_var.set(f"Planetary file download failed: {error}")
            return
        progress_var.set(100)
        status_var.set(f"Saved {destination.name}")
        self.planetary_status_var.set(f"Saved planetary file: {destination}")
