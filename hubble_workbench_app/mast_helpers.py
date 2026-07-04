from .catalogs import SOLAR_SYSTEM_TARGETS, TARGET_ALIASES
from .fits_io import OBSERVATIONS


class MastSearchHelperMixin:
    @staticmethod
    def parse_degrees_radius(radius_text):
        text = (radius_text or "").strip().lower()
        if text.endswith("deg"):
            text = text[:-3].strip()
        elif text.endswith("d"):
            text = text[:-1].strip()
        return float(text or "0.05")

    @staticmethod
    def is_solar_system_target(target):
        return str(target or "").strip().upper() in SOLAR_SYSTEM_TARGETS

    @staticmethod
    def target_name_variants(target):
        raw = str(target or "").strip()
        variants = [raw, raw.upper(), raw.title()]
        alias = TARGET_ALIASES.get(raw.upper())
        if alias:
            variants.insert(0, alias)
            variants.extend([alias.upper(), alias.title()])
        compact = raw.replace(" ", "")
        if compact and compact != raw:
            variants.extend([compact, compact.upper()])
            compact_alias = TARGET_ALIASES.get(compact.upper())
            if compact_alias:
                variants.insert(0, compact_alias)
                variants.extend([compact_alias.upper(), compact_alias.title()])
        seen = set()
        clean = []
        for item in variants:
            key = item.strip().upper()
            if item.strip() and key not in seen:
                clean.append(item.strip())
                seen.add(key)
        return clean

    @classmethod
    def search_target_variants(cls, target):
        raw = str(target or "").strip()
        variants = cls.target_name_variants(raw)
        alias = TARGET_ALIASES.get(raw.upper())
        if alias:
            return [alias] + [item for item in variants if item.upper() != alias.upper()]
        compact = raw.replace(" ", "")
        compact_alias = TARGET_ALIASES.get(compact.upper()) if compact else None
        if compact_alias:
            return [compact_alias] + [item for item in variants if item.upper() != compact_alias.upper()]
        return variants

    def observation_row_matches_telescope(self, row, telescope_code):
        collection = str(row.get("obs_collection", "")).upper()
        if telescope_code != "BOTH" and collection != telescope_code:
            return False
        if telescope_code == "BOTH" and collection not in ("HST", "JWST"):
            return False
        return str(row.get("dataproduct_type", "")).lower() in ("image", "")

    def mast_row_dicts(self, obs_table, telescope_code):
        rows = []
        for row in obs_table:
            item = {name: self.table_value(row, name) for name in row.colnames}
            if self.observation_row_matches_telescope(item, telescope_code):
                rows.append(item)
        return rows

    def mast_target_name_rows(self, target, telescope_code):
        rows = []
        seen = set()
        collection_values = ["HST", "JWST"] if telescope_code == "BOTH" else [telescope_code]
        for name in self.target_name_variants(target):
            for collection in collection_values:
                try:
                    obs = OBSERVATIONS.query_criteria(
                        target_name=name,
                        obs_collection=collection,
                        dataproduct_type="image",
                    )
                except Exception:
                    continue
                for item in self.mast_row_dicts(obs, telescope_code):
                    key = str(item.get("obsid") or item.get("obs_id") or item)
                    if key not in seen:
                        rows.append(item)
                        seen.add(key)
        return rows

    def mast_image_observation_rows(self, target, radius, telescope_code):
        first_error = None
        rows = []
        for search_target in self.search_target_variants(target):
            try:
                obs = OBSERVATIONS.query_object(search_target, radius=radius)
                rows = self.mast_row_dicts(obs, telescope_code)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                continue
            if rows:
                return rows
        if self.is_solar_system_target(target):
            target_rows = self.mast_target_name_rows(target, telescope_code)
            if target_rows:
                return target_rows
        if first_error:
            raise first_error
        return []
