from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
DOWNLOAD_DIR = APP_DIR / "downloads"
OUTPUT_DIR = APP_DIR / "outputs"
NOTES_DIR = APP_DIR / "notes"
SETTINGS_PATH = APP_DIR / "hubble_settings.json"
MESSIER_LIST_PATH = APP_DIR / "The Complete Messier List.txt"

RGB_WORKING_PREVIEW_MAX_PIXELS = 1200
RGB_PRESET_PREVIEW_MAX_PIXELS = 360
CHANNEL_THUMBNAIL_MAX_PIXELS = 900
ENHANCED_PRODUCT_TOKENS = ("_i2d", "_drc", "_drz", "mosaic", "combined", "coadd")

DEBUG_LOG_PATH = APP_DIR / "debug_hubble.txt"
LOG_DIR = APP_DIR / "logs"
SEARCH_LOG_DIR = LOG_DIR / "searches"
PRODUCT_LOG_DIR = LOG_DIR / "products"
DOWNLOAD_LOG_DIR = LOG_DIR / "downloads"
COMPOSE_LOG_DIR = LOG_DIR / "compose"
TIMING_LOG_DIR = LOG_DIR / "timing"
DEVELOPER_LOG_DIRS = (
    LOG_DIR,
    SEARCH_LOG_DIR,
    PRODUCT_LOG_DIR,
    DOWNLOAD_LOG_DIR,
    COMPOSE_LOG_DIR,
    TIMING_LOG_DIR,
)
