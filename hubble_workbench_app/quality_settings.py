from hubble_workbench_app.settings import SETTINGS, save_settings


class QualitySettingsMixin:
    def on_quality_option_changed(self):
        SETTINGS["high_quality_processing"] = bool(self.high_quality_var.get())
        SETTINGS["prefer_drizzled_products"] = bool(self.prefer_drizzled_var.get())
        if hasattr(self, "presentation_cleanup_var"):
            SETTINGS["presentation_cleanup"] = bool(self.presentation_cleanup_var.get())
        if hasattr(self, "straighten_angle_var"):
            SETTINGS["straighten_angle"] = float(self.straighten_angle_var.get())
        if hasattr(self, "auto_crop_presentation_var"):
            SETTINGS["auto_crop_presentation"] = bool(self.auto_crop_presentation_var.get())
        if hasattr(self, "use_fits_liberator_var"):
            SETTINGS["use_fits_liberator_engine"] = bool(self.use_fits_liberator_var.get())
        save_settings(SETTINGS)
        if hasattr(self, "product_results"):
            self.refresh_product_list()

    def on_stretch_setting_changed(self, _event=None):
        if hasattr(self, "stretch_job") and self.stretch_job:
            try:
                self.after_cancel(self.stretch_job)
            except Exception:
                pass
        self.stretch_job = self.after(120, self.recompose_if_ready)

    def recompose_if_ready(self):
        self.save_quality_settings()
        if self.auto_compose_var.get() and all(
            path.strip() for path in (self.red_path_var.get(), self.green_path_var.get(), self.blue_path_var.get())
        ):
            self.compose_async()

    def reset_advanced_stretch(self):
        for values in self.channel_stretch_vars.values():
            values["low"].set(0.2)
            values["high"].set(99.8)
            values["gamma"].set(1.0)
            values["asinh"].set(12.0)
        self.recompose_if_ready()

    def save_quality_settings(self):
        if hasattr(self, "high_quality_var"):
            SETTINGS["high_quality_processing"] = bool(self.high_quality_var.get())
        if hasattr(self, "prefer_drizzled_var"):
            SETTINGS["prefer_drizzled_products"] = bool(self.prefer_drizzled_var.get())
        if hasattr(self, "presentation_cleanup_var"):
            SETTINGS["presentation_cleanup"] = bool(self.presentation_cleanup_var.get())
        if hasattr(self, "straighten_angle_var"):
            SETTINGS["straighten_angle"] = float(self.straighten_angle_var.get())
        if hasattr(self, "auto_crop_presentation_var"):
            SETTINGS["auto_crop_presentation"] = bool(self.auto_crop_presentation_var.get())
        if hasattr(self, "use_fits_liberator_var"):
            SETTINGS["use_fits_liberator_engine"] = bool(self.use_fits_liberator_var.get())
        if hasattr(self, "channel_stretch_vars"):
            for channel, values in self.channel_stretch_vars.items():
                SETTINGS[f"{channel}_low_percent"] = float(values["low"].get())
                SETTINGS[f"{channel}_high_percent"] = float(values["high"].get())
                SETTINGS[f"{channel}_gamma"] = float(values["gamma"].get())
                SETTINGS[f"{channel}_asinh_strength"] = float(values["asinh"].get())
        save_settings(SETTINGS)
