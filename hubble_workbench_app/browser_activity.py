from datetime import datetime


class BrowserActivityMixin:
    def log_background_activity(self, message):
        if hasattr(self, "debug_console_write"):
            self.debug_console_write(message)
    def set_browser_buttons_state(self, state):
        for button in (
            self.search_button,
            self.easy_button,
            self.easy_hq_button,
            self.hla_button,
            self.products_button,
            self.all_products_button,
            self.download_button,
        ):
            button.configure(state=state)
        for name in ("better_sources_button", "completeness_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=state)

    def start_browser_activity(self, message):
        self.browser_operation_id += 1
        if self.browser_busy_job:
            try:
                self.after_cancel(self.browser_busy_job)
            except Exception:
                pass
            self.browser_busy_job = None
        self.browser_busy_message = message
        self.log_background_activity(f"Started: {message}")
        self.browser_busy_started = datetime.now()
        self.browser_progress.start(12)
        self.reset_download_progress()
        self.set_browser_buttons_state("disabled")
        self.stop_browser_button.configure(state="normal")
        if self.browser_timeout_job:
            try:
                self.after_cancel(self.browser_timeout_job)
            except Exception:
                pass
        operation_id = self.browser_operation_id
        self.browser_timeout_job = self.after(
            self.browser_timeout_seconds * 1000,
            lambda: self.browser_activity_timeout(operation_id),
        )
        self.update_browser_activity()
        return operation_id

    def extend_browser_timeout(self, operation_id):
        if operation_id != self.browser_operation_id or not self.browser_busy_started:
            return
        if self.browser_timeout_job:
            try:
                self.after_cancel(self.browser_timeout_job)
            except Exception:
                pass
        self.browser_timeout_job = self.after(
            self.browser_timeout_seconds * 1000,
            lambda: self.browser_activity_timeout(operation_id),
        )

    def update_browser_activity(self):
        if not self.browser_busy_started:
            return
        elapsed = int((datetime.now() - self.browser_busy_started).total_seconds())
        minutes, seconds = divmod(elapsed, 60)
        self.browser_status.set(
            f"{self.browser_busy_message} Active for {minutes}:{seconds:02d}. "
            "Use Stop if this is taking too long."
        )
        self.browser_busy_job = self.after(1000, self.update_browser_activity)

    def browser_activity_timeout(self, operation_id):
        if operation_id != self.browser_operation_id or not self.browser_busy_started:
            return
        minutes = max(1, self.browser_timeout_seconds // 60)
        self.cancel_browser_activity(
            f"This archive operation is taking longer than {minutes} minutes, so I stopped waiting. "
            "Try fewer products, a smaller radius, or try again in a moment."
        )

    def cancel_browser_activity(self, message=None):
        self.browser_operation_id += 1
        self.stop_browser_activity(message or "Stopped waiting for the current MAST request.")

    def reset_download_progress(self):
        if hasattr(self, "download_progress_var"):
            self.download_progress_var.set(0)
            self.download_detail.set("")

    def set_download_progress(self, operation_id, value, detail):
        if operation_id != self.browser_operation_id:
            return
        self.extend_browser_timeout(operation_id)
        self.download_progress_var.set(max(0, min(100, value)))
        self.download_detail.set(detail)
        self.log_background_activity(f"Progress: {detail} ({max(0, min(100, value)):.0f}%)")

    def stop_browser_activity(self, message):
        if self.browser_busy_job:
            try:
                self.after_cancel(self.browser_busy_job)
            except Exception:
                pass
            self.browser_busy_job = None
        if self.browser_timeout_job:
            try:
                self.after_cancel(self.browser_timeout_job)
            except Exception:
                pass
            self.browser_timeout_job = None
        self.browser_busy_started = None
        self.browser_timeout_seconds = self.default_browser_timeout_seconds
        self.browser_progress.stop()
        self.set_browser_buttons_state("normal")
        self.stop_browser_button.configure(state="disabled")
        self.browser_status.set(message)
        self.log_background_activity(f"Finished: {message}")
