from tkinter import messagebox

from hubble_workbench_app.catalogs import JWST_TARGET_GALLERY, TARGET_GALLERY, TARGET_RECIPES, TELESCOPE_CHOICES


class TargetGalleryMixin:
    def target_recipe(self, target):
        text = f" {target.upper()} "
        for key, recipe in TARGET_RECIPES.items():
            if f" {key} " in text or key == target.upper().strip():
                return recipe
        return None

    def apply_recipe_stretch(self, recipe):
        stretch = recipe.get("stretch", {})
        for values in self.channel_stretch_vars.values():
            values["low"].set(float(stretch.get("low", values["low"].get())))
            values["high"].set(float(stretch.get("high", values["high"].get())))
            values["gamma"].set(float(stretch.get("gamma", values["gamma"].get())))
            values["asinh"].set(float(stretch.get("asinh", values["asinh"].get())))
        preset = recipe.get("preset")
        if preset:
            self.apply_processing_preset(preset, update_status=False)

    def output_prefix(self):
        code = TELESCOPE_CHOICES.get(self.telescope_var.get(), "HST")
        if code == "JWST":
            return "jwst"
        if code == "BOTH":
            return "space_telescope"
        return "hubble"

    def current_gallery(self):
        return JWST_TARGET_GALLERY if TELESCOPE_CHOICES.get(self.telescope_var.get()) == "JWST" else TARGET_GALLERY

    def use_target_gallery(self):
        selected = self.target_gallery_var.get()
        for label, target, radius in self.current_gallery():
            if label == selected:
                self.target_var.set(target)
                self.radius_var.set(radius)
                self.browser_status.set(f"Loaded {label}.")
                return

    def search_target_gallery_hla(self):
        self.use_target_gallery()
        if TELESCOPE_CHOICES.get(self.telescope_var.get()) == "JWST":
            messagebox.showinfo("HLA Fallback", "HLA fallback is Hubble-only. Use Search MAST for JWST data.")
            return
        self.hla_search_async()
