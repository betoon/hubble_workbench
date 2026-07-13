import html
import io
import threading
import urllib.parse
import urllib.request
from tkinter import messagebox

from hubble_workbench_app.catalogs import TELESCOPE_CHOICES
from hubble_workbench_app.fits_io import OBSERVATIONS
from hubble_workbench_app.settings import SETTINGS, save_settings


class HlaWorkflowMixin:
    def hla_search_async(self, fallback_message=None):
        if not self.require_astropy():
            return
        if not fallback_message and TELESCOPE_CHOICES.get(self.telescope_var.get()) == "JWST":
            messagebox.showinfo("HLA Fallback", "The Hubble Legacy Archive fallback is Hubble-only. Use Search MAST for JWST data.")
            return
        target = self.target_var.get().strip()
        radius = self.radius_var.get().strip() or "0.05 deg"
        if not target:
            messagebox.showinfo("Search HLA", "Enter a target name.")
            return
        SETTINGS["last_target"] = target
        SETTINGS["radius"] = radius
        save_settings(SETTINGS)
        operation_id = self.start_browser_activity(fallback_message or "Searching Hubble Legacy Archive products...")
        self.obs_list.delete(0, "end")
        self.product_list.delete(0, "end")
        self.product_results = []
        self.visible_product_results = []

        def worker():
            try:
                rows = self.fetch_hla_product_rows(target, radius)
                result = (rows, None)
            except Exception as exc:
                result = ([], exc)
            self.after(0, lambda: self.finish_hla_search(operation_id, result))

        threading.Thread(target=worker, daemon=True).start()

    def fetch_hla_product_rows(self, target, radius):
        from astropy.coordinates import SkyCoord
        from astropy.io.votable import parse_single_table

        if self.is_solar_system_target(target):
            return self.fetch_hla_product_rows_for_solar_system_target(target)

        last_error = None
        coord = None
        for search_target in self.search_target_variants(target):
            try:
                coord = SkyCoord.from_name(search_target)
                break
            except Exception as exc:
                last_error = exc
        if coord is None:
            raise last_error or RuntimeError(f"Could not resolve target: {target}")
        size = self.parse_degrees_radius(radius)
        query = urllib.parse.urlencode({
            "POS": f"{coord.ra.deg},{coord.dec.deg}",
            "SIZE": str(size),
            "FORMAT": "ALL",
        })
        url = f"https://hla.stsci.edu/cgi-bin/hlaSIAP.cgi?{query}"
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = response.read()
        table = parse_single_table(io.BytesIO(payload)).to_table()
        rows = []
        for row in table:
            item = {name: self.table_value(row, name) for name in table.colnames}
            product_url = html.unescape(str(item.get("URL", "")))
            dataset = str(item.get("Dataset", "")).strip()
            if not product_url or not dataset:
                continue
            item["_source"] = "HLA"
            item["URL"] = product_url
            item["productFilename"] = self.hla_filename(item)
            item["productSubGroupDescription"] = (
                f"HLA {item.get('Detector', '')} {item.get('Spectral_Elt', '')}".strip()
            )
            rows.append(item)
        rows.sort(key=self.hla_sort_key)
        return rows

    def fetch_hla_product_rows_for_solar_system_target(self, target):
        rows = []
        seen = set()
        for obs_row in self.mast_target_name_rows(target, "HST"):
            obsid = obs_row.get("obsid")
            if not obsid:
                continue
            try:
                products = OBSERVATIONS.get_product_list(obsid)
            except Exception:
                continue
            for row in products:
                item = self.normalize_product_row({name: self.table_value(row, name) for name in row.colnames}, obs_row)
                filename = str(item.get("productFilename", "")).lower()
                if not filename.endswith((".fits", ".fits.gz")):
                    continue
                key = (
                    item.get("obsid"),
                    item.get("productFilename"),
                    item.get("dataURI"),
                    item.get("obs_id"),
                )
                if key in seen:
                    continue
                item["_source"] = "MAST target-name fallback"
                rows.append(item)
                seen.add(key)
        rows.sort(key=self.product_sort_key)
        return rows

    @staticmethod
    def hla_filename(item):
        dataset = str(item.get("Dataset", "hla_product")).strip() or "hla_product"
        fmt = str(item.get("Format", "")).lower()
        if "jpeg" in fmt or "jpg" in fmt:
            suffix = ".jpg"
        elif "png" in fmt:
            suffix = ".png"
        elif "tar" in fmt:
            suffix = ".tar"
        elif dataset.lower().endswith((".fits", ".fit", ".fits.gz", ".jpg", ".jpeg", ".png", ".tar")):
            suffix = ""
        else:
            suffix = ".fits"
        return f"{dataset}{suffix}"

    @staticmethod
    def hla_sort_key(item):
        level = str(item.get("Level", "9"))
        name = str(item.get("productFilename", "")).lower()
        fmt = str(item.get("Format", "")).lower()
        fits_priority = 0 if "fits" in fmt or name.endswith((".fits", ".fits.gz")) else 1
        return fits_priority, level, name

    def finish_hla_search(self, operation_id, result):
        if operation_id != self.browser_operation_id:
            return
        rows, error = result
        if error:
            self.stop_browser_activity(f"HLA search failed: {error}")
            return
        self.search_results = []
        self.search_results_target = ""
        self.product_results = rows
        self.product_results_target = self.target_var.get().strip() if hasattr(self, "target_var") else ""
        self.obs_list.insert("end", "HLA search returned direct downloadable products.")
        self.obs_list.insert("end", "Select one or more products on the right, then choose Download Selected Products.")
        self.refresh_product_list()
        self.stop_browser_activity(
            f"Found {len(rows)} HLA products. Showing {len(self.visible_product_results)} with the current filters."
        )
