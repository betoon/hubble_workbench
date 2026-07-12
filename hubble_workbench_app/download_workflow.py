import html
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

from .fits_io import OBSERVATIONS
from .paths import DOWNLOAD_DIR, DOWNLOAD_LOG_DIR


class DownloadWorkflowMixin:
    def download_selected_async(self):
        selections = self.product_list.curselection()
        if not selections:
            messagebox.showinfo("Download", "Select one or more products.")
            return
        rows = [self.visible_product_results[index] for index in selections]
        self.download_product_rows_async(rows)

    def download_product_rows_async(self, rows, folder_label=None, rgb_set=None):
        if not (rows and rows[0].get("_source") == "HLA") and not self.require_astroquery():
            return
        target = self.target_var.get().strip().replace(" ", "_") or "target"
        if folder_label:
            target = f"{target}_{folder_label}"
        download_path = DOWNLOAD_DIR / target / datetime.now().strftime("%Y%m%d_%H%M%S")
        download_path.mkdir(parents=True, exist_ok=True)
        self.browser_timeout_seconds = 3600
        operation_id = self.start_browser_activity(f"Downloading {len(rows)} product(s)...")
        self.reset_download_progress()
        heartbeat_active = {"running": True}

        def download_heartbeat(started):
            if operation_id != self.browser_operation_id or not heartbeat_active["running"]:
                return
            elapsed = int((datetime.now() - started).total_seconds())
            minutes, seconds = divmod(elapsed, 60)
            self.set_download_progress(
                operation_id,
                10,
                f"MAST download is still running ({minutes}:{seconds:02d}). Large FITS files can take a while.",
            )
            self.after(15000, lambda: download_heartbeat(started))

        self.after(15000, lambda: download_heartbeat(datetime.now()))

        def worker():
            try:
                if rows and rows[0].get("_source") == "HLA":
                    manifest = self.download_hla_products(rows, download_path, operation_id)
                else:
                    self.after(
                        0,
                        lambda: self.set_download_progress(
                            operation_id,
                            5,
                            "MAST download is running. The archive reports progress only after the selected files finish.",
                        ),
                    )
                    try:
                        manifest = OBSERVATIONS.download_products(rows, download_dir=str(download_path), cache=True)
                    except Exception as exc:
                        self.after(
                            0,
                            lambda: self.set_download_progress(
                                operation_id,
                                5,
                                "Bulk MAST download did not start cleanly. Trying the selected files one at a time...",
                            ),
                        )
                        manifest = self.download_mast_products_individually(rows, download_path, operation_id, exc)
                result = (manifest, download_path, None, rgb_set)
            except Exception as exc:
                result = (None, download_path, exc, rgb_set)
            heartbeat_active["running"] = False
            self.after(0, lambda: self.finish_download(operation_id, result))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def format_error_message(error):
        text = str(error).strip()
        if text and text.lower() != "true":
            return text
        return repr(error)

    @staticmethod
    def safe_filename(name):
        cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(name))
        return cleaned.strip("._") or "hla_product.fits"

    def download_hla_products(self, rows, download_path, operation_id):
        downloaded = []
        total_files = max(1, len(rows))
        for index, row in enumerate(rows, start=1):
            url = html.unescape(str(row.get("URL", "")))
            filename = self.safe_filename(row.get("productFilename", "hla_product.fits"))
            output_path = download_path / filename
            self.after(
                0,
                lambda i=index, total=total_files, name=filename: self.set_download_progress(
                    operation_id,
                    ((i - 1) / total) * 100,
                    f"Downloading file {i} of {total}: {name}",
                ),
            )

            def reporthook(block_count, block_size, total_size, i=index, total=total_files, name=filename):
                if total_size and total_size > 0:
                    file_fraction = min(1.0, (block_count * block_size) / total_size)
                    percent = (((i - 1) + file_fraction) / total) * 100
                    detail = f"Downloading file {i} of {total}: {name} ({int(file_fraction * 100)}%)"
                else:
                    percent = ((i - 1) / total) * 100
                    detail = f"Downloading file {i} of {total}: {name}"
                self.after(0, lambda p=percent, d=detail: self.set_download_progress(operation_id, p, d))

            urllib.request.urlretrieve(url, output_path, reporthook=reporthook)
            downloaded.append(str(output_path))
            self.after(
                0,
                lambda i=index, total=total_files, name=filename: self.set_download_progress(
                    operation_id,
                    (i / total) * 100,
                    f"Finished file {i} of {total}: {name}",
                ),
            )
        return downloaded

    def finish_download(self, operation_id, result):
        if operation_id != self.browser_operation_id:
            return
        manifest, download_path, error, rgb_set = result
        if error:
            if hasattr(self, "set_easy_all_sensors_status") and getattr(self, "easy_all_sensors_pending_stage", None) == "download":
                self.set_easy_all_sensors_status("stopped", "Download failed before the RGB set could be loaded.")
                self.save_easy_all_sensors_status_snapshot()
                self.easy_all_sensors_pending_stage = None
            self.stop_browser_activity(f"Download failed: {self.format_error_message(error)}")
            return
        self.download_progress_var.set(100)
        self.download_detail.set("Download complete.")
        if self.save_download_logs_var.get():
            self.save_diagnostic_json(DOWNLOAD_LOG_DIR, f"{self.current_target_for_log()}_download", {
                "target": self.current_target_for_log(),
                "download_path": str(download_path),
                "manifest": manifest,
                "rgb_set": rgb_set,
            })
        if rgb_set:
            self.load_downloaded_rgb_set(manifest, download_path, rgb_set)
            return
        self.stop_browser_activity(f"Downloaded products to {download_path}")

    def load_downloaded_rgb_set(self, manifest, download_path, rgb_set):
        downloaded = self.extract_downloaded_paths(manifest, download_path)
        channel_paths = self.match_downloaded_rgb_paths(downloaded, rgb_set)
        missing = [channel for channel in ("blue", "green", "red") if channel not in channel_paths]
        if missing:
            if hasattr(self, "set_easy_all_sensors_status") and getattr(self, "easy_all_sensors_pending_stage", None) == "download":
                self.set_easy_all_sensors_status("stopped", "Downloaded the RGB files, but could not match one or more channels.")
                self.save_easy_all_sensors_status_snapshot()
                self.easy_all_sensors_pending_stage = None
            self.stop_browser_activity(
                f"Downloaded RGB products to {download_path}, but could not identify: {', '.join(missing)}. "
                "Use Load Latest RGB Set or choose the files manually."
            )
            return
        self.red_path_var.set(str(channel_paths["red"]))
        self.green_path_var.set(str(channel_paths["green"]))
        self.blue_path_var.set(str(channel_paths["blue"]))
        self.compose_status.set(f"Loading downloaded RGB channels from {download_path.name}...")
        self.notebook.select(self.compose_tab)
        self.compose_progress.start(12)
        if hasattr(self, "set_easy_all_sensors_status") and getattr(self, "easy_all_sensors_pending_stage", None) == "download":
            auto_compose_var = getattr(self, "auto_compose_var", None)
            compose_enabled = bool(auto_compose_var.get()) if auto_compose_var is not None else False
            next_stage = "compose" if compose_enabled else "loaded"
            self.easy_all_sensors_pending_stage = next_stage
            detail = "RGB channels are loaded; composing automatically." if next_stage == "compose" else "RGB channels are loaded in the Compose tab."
            self.set_easy_all_sensors_status(next_stage, detail)
        self.preview_channel_thumbnails_async(channel_paths, download_path)
        self.stop_browser_activity(f"Downloaded and loaded RGB set from {download_path}")

    def download_mast_products_individually(self, rows, download_path, operation_id, first_error=None):
        downloaded = []
        total_files = max(1, len(rows))
        for index, row in enumerate(rows, start=1):
            data_uri = str(row.get("dataURI", "") or row.get("dataURL", "")).strip()
            if not data_uri:
                raise RuntimeError(
                    f"Bulk download failed ({self.format_error_message(first_error)}), "
                    f"and {row.get('productFilename', 'one selected product')} has no MAST download URI."
                )
            filename = self.safe_filename(row.get("productFilename", Path(data_uri).name or f"mast_product_{index}.fits"))
            output_path = download_path / filename
            self.after(
                0,
                lambda i=index, total=total_files, name=filename: self.set_download_progress(
                    operation_id,
                    ((i - 1) / total) * 100,
                    f"Downloading file {i} of {total}: {name}",
                ),
            )
            OBSERVATIONS.download_file(data_uri, local_path=str(output_path), cache=True)
            downloaded.append(str(output_path))
            self.after(
                0,
                lambda i=index, total=total_files, name=filename: self.set_download_progress(
                    operation_id,
                    (i / total) * 100,
                    f"Finished file {i} of {total}: {name}",
                ),
            )
        return downloaded

    @staticmethod
    def extract_downloaded_paths(manifest, download_path):
        paths = []
        try:
            if hasattr(manifest, "colnames") and "Local Path" in manifest.colnames:
                paths.extend(Path(str(item)) for item in manifest["Local Path"])
            elif isinstance(manifest, (list, tuple)):
                paths.extend(Path(str(item)) for item in manifest)
        except Exception:
            pass
        paths = [path for path in paths if path.exists()]
        if not paths:
            paths = [
                path for path in Path(download_path).rglob("*")
                if path.is_file() and path.name.lower().endswith((".fits", ".fits.gz", ".fit"))
            ]
        return paths

    def match_downloaded_rgb_paths(self, downloaded_paths, rgb_set):
        matched = {}
        for channel, row in rgb_set.items():
            expected = str(row.get("productFilename", "")).lower()
            for path in downloaded_paths:
                if path.name.lower() == expected or path.name.lower().endswith(expected):
                    matched[channel] = path
                    break
        if len(matched) < 3:
            fallback = self.pick_rgb_files_from_paths(downloaded_paths)
            matched.update({channel: path for channel, path in fallback.items() if channel not in matched})
        return matched

    def pick_rgb_files_from_paths(self, files):
        channels = self.rgb_filename_tokens()
        picks = {}
        for channel, tokens in channels.items():
            scored = []
            for path in files:
                score = self.channel_score(path, tokens)
                if score is not None:
                    scored.append((score, path.name.upper(), path))
            if scored:
                picks[channel] = sorted(scored)[0][2]
        return picks
