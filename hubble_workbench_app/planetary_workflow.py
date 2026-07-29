import json
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

import tkinter as tk
from tkinter import ttk

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

    PLANETARY_SOURCES = (
        ("NASA PDS Mars ODE", "https://ode.rsl.wustl.edu/mars/", "Cross-mission orbital product search and downloads."),
        ("NASA Mars Trek", "https://trek.nasa.gov/mars/", "Interactive global mosaics, elevation, landing sites, and WMTS layers."),
        ("NASA PDS Imaging", "https://pds-imaging.jpl.nasa.gov/", "Mission imaging archives and Planetary Image Atlas."),
        ("ESA Planetary Science Archive", "https://psa.esa.int/", "Mars Express and ExoMars mission archives."),
        ("ESO Science Archive", "https://archive.eso.org/", "Ground-based optical and infrared observations."),
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
        dataset = cls.MARS_DATASETS[dataset_name]
        parameters = {
            "query": "products",
            "target": "mars",
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
        products = root.get("Products", {}).get("Product", [])
        if isinstance(products, dict):
            products = [products]
        return [dict(product) for product in products or []]

    @classmethod
    def query_mars_ode(cls, latitude, longitude, radius, dataset_name, limit=25, timeout=35):
        url = cls.build_mars_ode_url(latitude, longitude, radius, dataset_name, limit)
        request = Request(url, headers={"User-Agent": "Hubble-Workbench/2.0 Planetary-Observatory"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        return cls.parse_mars_ode_response(payload), url

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
    def planetary_product_id(product, fallback="Mars product"):
        direct = product.get("Observation_id") or product.get("Product_id")
        if direct:
            return str(direct)
        for field in ("ProductURL", "FilesURL"):
            query = parse_qs(urlparse(str(product.get(field) or "")).query)
            if query.get("product_id"):
                return str(query["product_id"][0])
        return fallback

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
        ttk.Combobox(controls, textvariable=self.planetary_planet_var, values=["Mars"], state="readonly", width=8).pack(side="left", padx=(6, 12))
        ttk.Label(controls, text="Named feature").pack(side="left")
        self.planetary_feature_var = tk.StringVar(value="Jezero Crater")
        feature_combo = ttk.Combobox(
            controls, textvariable=self.planetary_feature_var,
            values=list(self.MARS_FEATURES), state="readonly", width=22,
        )
        feature_combo.pack(side="left", padx=(6, 12))
        feature_combo.bind("<<ComboboxSelected>>", self.planetary_select_feature)
        ttk.Label(controls, text="Dataset").pack(side="left")
        self.planetary_dataset_var = tk.StringVar(value=next(iter(self.MARS_DATASETS)))
        ttk.Combobox(
            controls, textvariable=self.planetary_dataset_var,
            values=list(self.MARS_DATASETS), state="readonly", width=34,
        ).pack(side="left", padx=(6, 12))
        ttk.Button(controls, text="Search NASA PDS", command=lambda: self.planetary_search_async()).pack(side="left")
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
        tabs.add(products_panel, text="PDS Products")
        tabs.add(sources_panel, text="Official Sources")

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
        ttk.Button(product_tools, text="Open Mission Preview", command=lambda: self.open_selected_planetary_url("External_url")).pack(side="left", padx=(6, 0))
        self.planetary_details_text = tk.Text(products_panel, wrap="word", bg="#ffffff", fg="#1f1f1f", relief="flat", padx=10, pady=10)
        self.planetary_details_text.pack(fill="both", expand=True)
        self.planetary_details_text.insert("1.0", self.planetary_product_details(None))

        for name, url, description in self.PLANETARY_SOURCES:
            row = ttk.Frame(sources_panel, padding=8, relief="ridge")
            row.pack(fill="x", padx=4, pady=4)
            ttk.Label(row, text=name, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(row, text=description, wraplength=480).pack(anchor="w", pady=(2, 5))
            ttk.Button(row, text="Open Official Source", command=lambda address=url: self.open_file(address)).pack(anchor="w")

        self.planetary_products = []
        self.planetary_selected_product = None
        self.after(100, self.planetary_select_feature)

    def planetary_select_feature(self, _event=None):
        feature = self.MARS_FEATURES.get(self.planetary_feature_var.get())
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
        canvas.create_rectangle(padding, padding, width - padding, height - padding, fill="#8f3f24", outline="#f4a261", width=2)
        for latitude in range(-60, 61, 30):
            _x, y = self.planetary_map_point(latitude, 0, width, height, padding)
            canvas.create_line(padding, y, width - padding, y, fill="#b96542")
            canvas.create_text(4, y, text=f"{latitude:+d}°", anchor="w", fill="#f4d6c6")
        for longitude in range(-120, 181, 60):
            x, _y = self.planetary_map_point(0, longitude, width, height, padding)
            canvas.create_line(x, padding, x, height - padding, fill="#b96542")
            canvas.create_text(x, height - 4, text=f"{longitude:+d}°", anchor="s", fill="#f4d6c6")
        for name, (latitude, longitude, _description) in self.MARS_FEATURES.items():
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
        for product in getattr(self, "planetary_products", []):
            try:
                px, py = self.planetary_map_point(
                    float(product.get("Center_latitude")),
                    float(product.get("Center_longitude")),
                    width, height, padding,
                )
                canvas.create_oval(px - 2, py - 2, px + 2, py + 2, fill="#22d3ee", outline="")
            except (TypeError, ValueError):
                continue
        canvas.create_text(width / 2, 8, text="Mars — equirectangular feature and product map", anchor="n", fill="#fff7ed", font=("Segoe UI", 10, "bold"))

    def planetary_map_click(self, event):
        width = max(420, self.planetary_map_canvas.winfo_width())
        height = max(260, self.planetary_map_canvas.winfo_height())
        latitude, longitude = self.planetary_map_coordinates(event.x, event.y, width, height)
        self.planetary_latitude_var.set(round(latitude, 4))
        self.planetary_longitude_var.set(round(longitude, 4))
        self.planetary_feature_var.set("")
        self.planetary_feature_description_var.set(
            f"Custom Mars location: {latitude:.4f}° latitude, {longitude:.4f}° east longitude."
        )
        self.draw_planetary_map()

    def planetary_search_async(self):
        try:
            latitude = float(self.planetary_latitude_var.get())
            longitude = float(self.planetary_longitude_var.get())
            radius = float(self.planetary_radius_var.get())
            dataset = self.planetary_dataset_var.get()
            self.build_mars_ode_url(latitude, longitude, radius, dataset)
        except Exception as exc:
            self.planetary_status_var.set(f"Search settings need attention: {exc}")
            return
        self.planetary_status_var.set("Searching NASA PDS Mars ODE...")

        def worker():
            try:
                products, query_url = self.query_mars_ode(latitude, longitude, radius, dataset)
                error = None
            except Exception as exc:
                products, query_url, error = [], "", exc
            self.after(0, lambda: self.finish_planetary_search(products, query_url, dataset, error))

        threading.Thread(target=worker, daemon=True).start()

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
