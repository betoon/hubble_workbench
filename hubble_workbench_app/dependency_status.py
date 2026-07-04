from tkinter import messagebox

from hubble_workbench_app.fits_io import FITS, OBSERVATIONS, MISSING_DEPS


class DependencyStatusMixin:
    def refresh_dependency_status(self):
        self.dep_text.delete("1.0", "end")
        if MISSING_DEPS:
            self.dep_text.insert("end", "Some astronomy dependencies are missing.\n\n")
            self.dep_text.insert("end", "Run install_dependencies.bat in this folder, then restart Space Telescope Workbench.\n\n")
            self.dep_text.insert("end", "Missing:\n")
            for item in MISSING_DEPS:
                self.dep_text.insert("end", f"- {item}\n")
            self.dep_text.insert("end", "\nAlready available:\n- numpy\n- Pillow\n")
        else:
            self.dep_text.insert("end", "All core dependencies are available.\n\n")
            self.dep_text.insert("end", "You can search MAST, download Hubble or JWST products, preview FITS files, and compose RGB images.\n")
        self.dep_text.insert("end", "\nSuggested workflow:\n")
        self.dep_text.insert("end", "1. Choose Hubble/HST or James Webb/JWST, then search a target.\n")
        self.dep_text.insert("end", "2. Select an observation and get science products.\n")
        self.dep_text.insert("end", "3. Download calibrated or drizzled FITS products.\n")
        self.dep_text.insert("end", "4. Preview individual FITS files.\n")
        self.dep_text.insert("end", "5. Assign three filters to red, green, and blue channels.\n")
        self.dep_text.insert("end", "6. Export preview PNG, high-quality TIFF, and notes.\n")

    def require_astroquery(self):
        if OBSERVATIONS is None:
            messagebox.showinfo("Dependencies", "astroquery is not installed. Run install_dependencies.bat, then restart.")
            return False
        return True

    def require_astropy(self):
        if FITS is None:
            messagebox.showinfo("Dependencies", "astropy is not installed. Run install_dependencies.bat, then restart.")
            return False
        return True
