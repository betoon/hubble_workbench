import math

from .catalogs import (
    JWST_NIRCAM_FILTERS,
    JWST_MIRI_FILTERS,
    HST_BLUE_FILTERS,
    HST_GREEN_FILTERS,
    HST_RED_FILTERS,
    SOLAR_SYSTEM_TARGETS,
)
from .paths import ENHANCED_PRODUCT_TOKENS


class ProductScoringMixin:
    @staticmethod
    def product_footprint_bounds(row):
        text = str(row.get("s_region", "") or row.get("S_REGION", "") or "").strip()
        if "POLYGON" not in text.upper():
            return None
        values = []
        for token in text.replace("(", " ").replace(")", " ").replace(",", " ").split():
            try:
                values.append(float(token))
            except Exception:
                continue
        if len(values) < 6:
            return None
        ras = values[0::2]
        decs = values[1::2]
        return min(ras), max(ras), min(decs), max(decs)

    @classmethod
    def product_overlap_status(cls, left, right):
        """Return 2 for confirmed overlap, 1 for unknown, and 0 for confirmed separation."""
        left_bounds = cls.product_footprint_bounds(left)
        right_bounds = cls.product_footprint_bounds(right)
        if left_bounds and right_bounds:
            separated = (
                left_bounds[1] < right_bounds[0] or right_bounds[1] < left_bounds[0]
                or left_bounds[3] < right_bounds[2] or right_bounds[3] < left_bounds[2]
            )
            return 0 if separated else 2
        try:
            left_ra = float(left.get("s_ra"))
            left_dec = float(left.get("s_dec"))
            right_ra = float(right.get("s_ra"))
            right_dec = float(right.get("s_dec"))
            left_fov = float(left.get("s_fov"))
            right_fov = float(right.get("s_fov"))
        except (TypeError, ValueError):
            return 1
        dec_scale = max(0.01, abs(math.cos(math.radians((left_dec + right_dec) / 2))))
        distance = math.hypot((left_ra - right_ra) * dec_scale, left_dec - right_dec)
        return 2 if distance <= (left_fov + right_fov) / 2 else 0

    @staticmethod
    def row_identity(row):
        return (
            str(row.get("productFilename", "")),
            str(row.get("obsID", "") or row.get("obsid", "")),
            str(row.get("dataURI", "") or row.get("dataURL", "")),
        )

    def unique_product_rows(self, rows):
        seen = set()
        unique = []
        for row in rows:
            key = self.row_identity(row)
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

    def extra_rgb_download_rows(self, rows, rgb_set, limit=18):
        selected = {self.row_identity(rgb_set[channel]) for channel in ("blue", "green", "red")}
        candidates = []
        target_group = self.rgb_group_key(rgb_set["blue"])
        for row in rows:
            if self.row_identity(row) in selected:
                continue
            if not self.product_is_direct_fits(row) or self.product_is_spectrum(row):
                continue
            if not self.product_rgb_channel(row):
                continue
            same_group = self.rgb_group_key(row) == target_group
            score = self.product_quality_score(row) + (30 if same_group else 0)
            candidates.append((-score, self.product_sort_key(row), row))
        return [row for _score, _sort, row in sorted(candidates)[:limit]]

    def rgb_stack_download_rows(self, rows, rgb_set, per_channel=3):
        """Choose independent, same-filter exposures for each selected RGB channel."""
        result = {}
        for channel in ("blue", "green", "red"):
            selected = rgb_set[channel]
            selected_filter = str(selected.get("filters", "") or selected.get("Spectral_Elt", "")).strip().upper()
            chosen = [selected]
            seen_observations = {
                str(selected.get("obsid", "") or selected.get("obs_id", "") or self.row_identity(selected))
            }
            candidates = []
            for row in rows:
                if self.row_identity(row) == self.row_identity(selected):
                    continue
                if not self.product_is_direct_fits(row) or self.product_is_spectrum(row):
                    continue
                if self.product_rgb_channel(row) != channel:
                    continue
                row_filter = str(row.get("filters", "") or row.get("Spectral_Elt", "")).strip().upper()
                if not selected_filter or row_filter != selected_filter:
                    continue
                overlap_status = self.product_overlap_status(selected, row)
                if overlap_status == 0:
                    continue
                candidates.append((-overlap_status, -self.product_quality_score(row), self.product_sort_key(row), row))
            for _overlap, _score, _sort, row in sorted(candidates):
                observation = str(row.get("obsid", "") or row.get("obs_id", "") or self.row_identity(row))
                if observation in seen_observations:
                    continue
                chosen.append(row)
                seen_observations.add(observation)
                if len(chosen) >= max(1, int(per_channel)):
                    break
            result[channel] = chosen
        return result

    def quality_badges(self, row):
        name = str(row.get("productFilename", "")).lower()
        badges = []
        if any(token in name for token in ENHANCED_PRODUCT_TOKENS):
            badges.append("Drizzled")
        try:
            size = int(float(row.get("size", 0) or 0))
        except Exception:
            size = 0
        if size >= 50_000_000:
            badges.append("Large")
        if self.product_rgb_channel(row):
            badges.append("RGB Match")
        if not self.product_is_direct_fits(row):
            badges.append("Preview Only")
        if any(token in name for token in ("raw", "uncal")):
            badges.append("Raw/Not Ideal")
        if not badges:
            badges.append("Usable")
        return badges

    def current_target_is_solar_system(self):
        try:
            target = self.target_var.get()
        except Exception:
            target = ""
        return str(target or "").strip().upper() in SOLAR_SYSTEM_TARGETS

    def current_solar_system_target_key(self):
        try:
            target = self.target_var.get()
        except Exception:
            target = ""
        target_key = str(target or "").strip().upper()
        return target_key if target_key in SOLAR_SYSTEM_TARGETS else ""

    @staticmethod
    def product_numeric_value(row, *keys):
        for key in keys:
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except Exception:
                continue
        return None

    def solar_system_frame_score(self, row):
        target_key = self.current_solar_system_target_key()
        if not target_key:
            return 0
        name = str(row.get("productFilename", "") or "").upper()
        target_name = str(row.get("Target", "") or row.get("target_name", "") or "").upper()
        obs_id = str(row.get("obs_id", "") or row.get("obsid", "") or "").upper()
        instrument = str(row.get("Detector", "") or row.get("instrument_name", "") or "").upper()
        text = " ".join((name, target_name, obs_id, instrument, self.product_filter_text(row)))
        score = 0
        if target_name == target_key:
            score += 85
        elif target_key in target_name:
            score += 55
        elif target_key in text:
            score += 25
        for token in ("FULL", "FULLDISK", "FULL_DISK", "GLOBAL", "PLANET", "OPAL", "MAP", "MOSAIC", "COMBINED", "COADD"):
            if token in text:
                score += 22
        for token in ("SUBARRAY", "SUBARR", "CORNER", "PARTIAL", "LIMB", "AURORA", "SPOT", "GRS", "RING", "MOON"):
            if token in text:
                score -= 25
        if target_key in {"JUPITER", "SATURN", "URANUS", "NEPTUNE"}:
            for moon in ("IO", "EUROPA", "GANYMEDE", "CALLISTO", "TITAN", "ENCELADUS", "TRITON"):
                if moon in target_name and target_name != target_key:
                    score -= 45
        for token, value in (("NIRCAM", 32), ("MIRI", 26), ("WFC3/UVIS", 28), ("ACS/WFC", 24), ("WFPC2", 14)):
            if token in instrument:
                score += value
        fov = self.product_numeric_value(row, "s_fov", "s_region_fov", "fov")
        if fov is not None:
            if fov >= 0.01:
                score += 28
            elif fov >= 0.004:
                score += 12
        return score

    def product_quality_score(self, row):
        name = str(row.get("productFilename", "")).lower()
        score = 0
        # Strongly prefer already-resampled or combined products. These are much more likely
        # to look complete than a single narrow calibrated exposure.
        for value, token in ((110, "_i2d"), (100, "_drc"), (92, "_drz"), (85, "mosaic"), (78, "combined"), (72, "coadd"), (28, "_cal"), (16, "_flc"), (12, "_flt"), (8, "rate")):
            if token in name:
                score += value
        if "raw" in name or "uncal" in name:
            score -= 70
        score += self.solar_system_frame_score(row)
        if self.product_rgb_channel(row):
            score += 20
        if row.get("_source") == "HLA":
            score += 35
        try:
            score += min(35, int(float(row.get("size", 0) or 0)) // 15_000_000)
        except Exception:
            pass
        return score

    def easy_choice_explanation(self, rgb_set, obs_row, recipe, high_quality, downloaded_count):
        pieces = []
        if high_quality:
            pieces.append("Easy High Quality used patient downloads, high-quality 16-bit processing, and the largest composite size.")
        if recipe:
            pieces.append(f"Target recipe: {recipe.get('name', 'known target')} with {recipe.get('preset', 'Natural')} starting look.")
        names = " ".join(str(rgb_set[channel].get("productFilename", "")).lower() for channel in ("blue", "green", "red"))
        if any(token in names for token in ("_drc", "_drz", "_i2d", "mosaic", "combined", "coadd")):
            pieces.append("Picked drizzled/mosaic-style science products because they are usually cleaner and sharper.")
        filters = []
        for channel in ("blue", "green", "red"):
            row = rgb_set[channel]
            filt = row.get("Spectral_Elt", "") or row.get("filters", "") or row.get("filter", "") or "unknown filter"
            filters.append(f"{channel} {filt}")
        pieces.append("Used " + ", ".join(filters) + ".")
        detector = obs_row.get("instrument_name", "") or rgb_set["blue"].get("Detector", "")
        if detector:
            pieces.append(f"Instrument/source: {detector}.")
        if downloaded_count > 3:
            pieces.append(f"Downloaded {downloaded_count} useful products so you can improve or reprocess this project later.")
        return "\n".join(pieces)


    def product_label(self, row):
        badges = " ".join(f"[{badge}]" for badge in self.quality_badges(row))
        if row.get("_source") == "HLA":
            return (
                f"{badges} "
                f"{row.get('productFilename', '')} | {row.get('Target', '')} | "
                f"{row.get('Detector', '')} | {row.get('Spectral_Elt', '')} | {row.get('Format', '')}"
            )
        return (
            f"{badges} "
            f"{row.get('obs_collection', '') or row.get('mission', '')} | {row.get('productFilename', '')} | "
            f"{row.get('productSubGroupDescription', '')} | {row.get('filters', '') or row.get('filter', '')} | {row.get('size', '')}"
        )

    @staticmethod
    def product_filter_text(row):
        return " ".join(str(row.get(key, "")) for key in (
            "productFilename",
            "productSubGroupDescription",
            "productType",
            "Spectral_Elt",
            "filters",
            "filter",
            "Format",
            "Detector",
            "instrument_name",
        )).upper()

    @staticmethod
    def product_filter_name(row):
        return str(row.get("Spectral_Elt", "") or row.get("filters", "") or row.get("filter", "")).upper()

    def jwst_filter_wavelengths(self, row):
        text = self.product_filter_text(row)
        wavelengths = []
        for token, wavelength in {**JWST_NIRCAM_FILTERS, **JWST_MIRI_FILTERS}.items():
            if token in text:
                wavelengths.append((token, wavelength))
        return wavelengths

    def product_rgb_channel(self, row):
        text = self.product_filter_text(row)
        jwst_filters = self.jwst_filter_wavelengths(row)
        if jwst_filters:
            detector_text = str(row.get("Detector", "") or row.get("instrument_name", "")).upper()
            wavelength = min(value for _token, value in jwst_filters)
            if "MIRI" in detector_text or any(token in JWST_MIRI_FILTERS for token, _value in jwst_filters):
                if wavelength <= 8.0:
                    return "blue"
                if wavelength <= 15.0:
                    return "green"
                return "red"
            if wavelength < 1.8:
                return "blue"
            if wavelength < 3.2:
                return "green"
            return "red"
        if any(token in text for token in HST_BLUE_FILTERS):
            return "blue"
        if any(token in text for token in HST_GREEN_FILTERS):
            return "green"
        if any(token in text for token in HST_RED_FILTERS):
            return "red"
        return None

    def product_is_direct_fits(self, row):
        fmt = str(row.get("Format", "")).lower()
        name = str(row.get("productFilename", "")).lower()
        if "text/html" in fmt:
            return False
        return "image/fits" in fmt or name.endswith((".fits", ".fits.gz"))

    def product_is_spectrum(self, row):
        text = self.product_filter_text(row)
        return any(token in text for token in ("G102", "G141", "G230", "G430", "G750", "GRISM", "PRISM", "SPECTR", "NRS", "MRS", "IFU"))

    def rgb_candidate_label(self, row):
        return (
            f"{row.get('Spectral_Elt', '') or row.get('filters', '')} | "
            f"{row.get('Target', '') or row.get('target_name', '') or row.get('obs_id', '')} | "
            f"{row.get('Detector', '') or row.get('instrument_name', '')} | "
            f"{row.get('productFilename', '')}"
        )

    @staticmethod
    def rgb_group_key(row):
        target = str(row.get("Target", "") or row.get("target_name", "") or row.get("obs_id", "")).strip()
        detector = str(row.get("Detector", "") or row.get("instrument_name", "")).strip()
        name = str(row.get("productFilename", "") or row.get("obs_id", "")).strip()
        parts = name.split("_")
        prefix = "_".join(parts[:3]) if len(parts) >= 3 else name[:12]
        return target, detector, prefix

    @staticmethod
    def suggested_rgb_label(rgb_set):
        blue = rgb_set["blue"]
        green = rgb_set["green"]
        red = rgb_set["red"]
        target = blue.get("Target", "") or blue.get("obs_id", "")
        detector = blue.get("Detector", "") or blue.get("instrument_name", "")
        return (
            f"{target} | {detector} | "
            f"B {blue.get('Spectral_Elt', '')}  G {green.get('Spectral_Elt', '')}  R {red.get('Spectral_Elt', '')}"
        )

    def rgb_set_score(self, rgb_set, recipe=None):
        score = 0
        detector_text = " ".join(str(rgb_set[channel].get("Detector", "") or rgb_set[channel].get("instrument_name", "")) for channel in ("blue", "green", "red")).upper()
        filter_text = " ".join(str(rgb_set[channel].get("Spectral_Elt", "") or rgb_set[channel].get("filters", "")) for channel in ("blue", "green", "red")).upper()
        target_text = " ".join(str(rgb_set[channel].get("Target", "") or rgb_set[channel].get("obs_id", "")) for channel in ("blue", "green", "red")).upper()
        filename_text = " ".join(str(rgb_set[channel].get("productFilename", "")) for channel in ("blue", "green", "red")).lower()
        if "ACS/WFC" in detector_text:
            score += 40
        if "WFC3/UVIS" in detector_text:
            score += 35
        if "WFPC2" in detector_text:
            score += 20
        if "NIRCAM" in detector_text:
            score += 45
        if "MIRI" in detector_text:
            score += 38
        jwst_wavelengths = []
        for channel in ("blue", "green", "red"):
            values = self.jwst_filter_wavelengths(rgb_set[channel])
            if values:
                jwst_wavelengths.append(min(value for _token, value in values))
        if len(jwst_wavelengths) == 3:
            spread = max(jwst_wavelengths) - min(jwst_wavelengths)
            score += min(35, int(spread * 8))
            if max(jwst_wavelengths) <= 5.0:
                score += 18
            elif min(jwst_wavelengths) >= 5.0:
                score += 15
            else:
                score += 10
            if jwst_wavelengths == sorted(jwst_wavelengths):
                score += 12
        if "_drc" in filename_text:
            score += 45
        if "_drz" in filename_text:
            score += 40
        if "_i2d" in filename_text:
            score += 35
        if "_cal" in filename_text:
            score += 20
        if any(token in filename_text for token in ("mosaic", "combined", "coadd")):
            score += 30
        for token in ("DARK", "CALIB", "ANY"):
            if token in target_text:
                score -= 40
        for token in ("F435W", "F438W", "F439W", "F475W", "F090W", "F115W", "F150W"):
            if token in filter_text:
                score += 12
        for token in ("F555W", "F606W", "F200W", "F277W", "F335M", "F1000W", "F1130W", "F1280W"):
            if token in filter_text:
                score += 12
        for token in ("F814W", "F850LP", "F356W", "F444W", "F1500W", "F1800W", "F2100W"):
            if token in filter_text:
                score += 12
        if all(self.product_is_direct_fits(rgb_set[channel]) for channel in ("blue", "green", "red")):
            score += 25
        if recipe:
            filters = recipe.get("filters", {})
            for channel in ("blue", "green", "red"):
                wanted = filters.get(channel, ())
                text = self.product_filter_text(rgb_set[channel])
                if any(token in text for token in wanted):
                    score += 22
        if self.current_target_is_solar_system():
            frame_scores = [self.solar_system_frame_score(rgb_set[channel]) for channel in ("blue", "green", "red")]
            score += min(frame_scores) + int(sum(frame_scores) / 6)
            targets = {str(rgb_set[channel].get("Target", "") or rgb_set[channel].get("target_name", "")).upper() for channel in ("blue", "green", "red")}
            if len(targets) == 1:
                score += 25
        return score
