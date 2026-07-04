import logging
from logging.handlers import RotatingFileHandler
import platform
import sys
import threading
import traceback
from datetime import datetime
from functools import wraps
from pathlib import Path

from hubble_workbench_app.paths import (
    APP_DIR,
    DEBUG_LOG_PATH,
    DEVELOPER_LOG_DIRS,
    DOWNLOAD_DIR,
    MESSIER_LIST_PATH,
    NOTES_DIR,
    OUTPUT_DIR,
    SETTINGS_PATH,
    TIMING_LOG_DIR,
)


# Set to False if you ever want to silence debug_hubble.txt without removing the code.
DEBUG_ENABLED = True


def setup_debug_logging(script_path=None):
    """Initialize debug_hubble.txt as early as possible for command-line and EXE runs."""
    if not DEBUG_ENABLED:
        return
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        # Avoid duplicate file handlers if this module is reloaded.
        for handler in list(root.handlers):
            if getattr(handler, "baseFilename", None) == str(DEBUG_LOG_PATH):
                root.removeHandler(handler)

        for folder in DEVELOPER_LOG_DIRS:
            folder.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            DEBUG_LOG_PATH,
            mode="a",
            maxBytes=5 * 1024 * 1024,
            backupCount=8,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(threadName)s %(funcName)s:%(lineno)d - %(message)s"
        ))
        root.addHandler(file_handler)

        logging.info("=" * 90)
        logging.info("Hubble Workbench debug logging started")
        logging.info("Debug log path: %s", DEBUG_LOG_PATH)
        logging.info("Python executable: %s", sys.executable)
        logging.info("Python version: %s", sys.version.replace("\n", " "))
        logging.info("Platform: %s", platform.platform())
        logging.info("Current working directory: %s", Path.cwd())
        logging.info("Script path: %s", Path(script_path or __file__).resolve())
        logging.info("App directory: %s", APP_DIR)
        logging.info("Command line args: %s", sys.argv)
        logging.info("Frozen executable: %s", getattr(sys, "frozen", False))
        logging.info("PyInstaller _MEIPASS: %s", getattr(sys, "_MEIPASS", None))
        logging.debug("sys.path: %s", sys.path)
    except Exception:
        # Never allow debugging itself to stop the app from opening.
        try:
            print("Failed to initialize debug logging:", traceback.format_exc())
        except Exception:
            pass


def debug_log(message, *args):
    if DEBUG_ENABLED:
        logging.debug(message, *args)


def info_log(message, *args):
    if DEBUG_ENABLED:
        logging.info(message, *args)


def warning_log(message, *args):
    if DEBUG_ENABLED:
        logging.warning(message, *args)


def log_exception(context):
    if DEBUG_ENABLED:
        logging.exception("%s", context)


def check_path(path, label="path"):
    """Log whether a required file/folder exists, then return it as a Path."""
    path = Path(path)
    try:
        if path.exists():
            debug_log("%s exists: %s", label, path)
        else:
            warning_log("%s MISSING: %s", label, path)
    except Exception:
        log_exception(f"Could not check {label}: {path}")
    return path


def append_timing_log(label, elapsed_seconds, detail=""):
    try:
        TIMING_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = TIMING_LOG_DIR / "performance.txt"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} | {label} | {elapsed_seconds:.3f}s | {detail}\n")
    except Exception:
        log_exception("Could not append timing log")


def debug_call(func):
    """Decorator for important startup/action methods: logs entry, exit, and full crashes."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        debug_log("ENTER %s", func.__qualname__)
        started = datetime.now()
        try:
            result = func(*args, **kwargs)
            elapsed = (datetime.now() - started).total_seconds()
            debug_log("EXIT  %s after %.3fs", func.__qualname__, elapsed)
            append_timing_log(func.__qualname__, elapsed)
            return result
        except Exception:
            log_exception(f"Exception in {func.__qualname__}")
            raise
    return wrapper


def install_global_exception_logging():
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    if hasattr(threading, "excepthook"):
        def handle_thread_exception(args):
            logging.critical(
                "Unhandled thread exception in %s",
                getattr(args.thread, "name", "unknown-thread"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        threading.excepthook = handle_thread_exception


def log_shutdown():
    info_log("Hubble Workbench process exiting")
    logging.shutdown()


def log_environment_paths():
    info_log("Checking key project paths")
    for label, path in (
        ("Downloads folder", DOWNLOAD_DIR),
        ("Outputs folder", OUTPUT_DIR),
        ("Notes folder", NOTES_DIR),
        ("Settings file", SETTINGS_PATH),
        ("Messier list", MESSIER_LIST_PATH),
    ):
        check_path(path, label)