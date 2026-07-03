import numpy as np
from PIL import Image, ImageFilter

from .paths import RGB_WORKING_PREVIEW_MAX_PIXELS, CHANNEL_THUMBNAIL_MAX_PIXELS


def normalize_image(data, low_percent=0.5, high_percent=99.5, stretch="asinh"):
    arr = np.asarray(data, dtype=np.float64)
    arr = np.where(np.isfinite(arr), arr, np.nan)
    if np.all(np.isnan(arr)):
        raise RuntimeError("Image data contains no finite pixels.")
    lo, hi = np.nanpercentile(arr, [low_percent, high_percent])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo, hi = np.nanmin(arr), np.nanmax(arr)
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    scaled = np.clip((arr - lo) / (hi - lo), 0, 1)
    if stretch == "sqrt":
        scaled = np.sqrt(scaled)
    elif stretch == "pow":
        scaled = np.power(scaled, 0.5)
    elif stretch == "log":
        scaled = np.log1p(30 * scaled) / np.log1p(30)
    else:
        scaled = np.arcsinh(10 * scaled) / np.arcsinh(10)
    return np.clip(scaled * 255, 0, 255).astype(np.uint8)


def normalize_float_channel(data, low_percent=0.2, high_percent=99.8, stretch="asinh", gamma=1.0, asinh_strength=12.0):
    arr = np.asarray(data, dtype=np.float64)
    arr = np.where(np.isfinite(arr), arr, np.nan)
    if np.all(np.isnan(arr)):
        raise RuntimeError("Image data contains no finite pixels.")
    lo, hi = np.nanpercentile(arr, [low_percent, high_percent])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo, hi = np.nanmin(arr), np.nanmax(arr)
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.float32)
    scaled = np.clip((arr - lo) / (hi - lo), 0, 1)
    if stretch == "sqrt":
        scaled = np.sqrt(scaled)
    elif stretch == "pow":
        exponent = max(0.05, float(gamma))
        scaled = np.power(np.clip(scaled, 0, 1), exponent)
    elif stretch == "log":
        scaled = np.log1p(30 * scaled) / np.log1p(30)
    elif stretch == "asinh":
        strength = max(0.1, float(asinh_strength))
        scaled = np.arcsinh(strength * scaled) / np.arcsinh(strength)
    gamma = max(0.05, float(gamma))
    if stretch != "pow" and abs(gamma - 1.0) > 0.001:
        scaled = np.power(np.clip(scaled, 0, 1), 1.0 / gamma)
    return np.clip(scaled, 0, 1).astype(np.float32)




def resize_to_match(channels, mode="smallest"):
    heights = [item.shape[0] for item in channels]
    widths = [item.shape[1] for item in channels]
    if mode == "largest":
        target = (max(widths), max(heights))
    else:
        target = (min(widths), min(heights))
    resized = []
    for channel in channels:
        img = Image.fromarray(channel, mode="L")
        if img.size != target:
            img = img.resize(target, Image.Resampling.LANCZOS)
        resized.append(np.asarray(img))
    return resized


def resize_float_to_match(channels, mode="smallest"):
    heights = [item.shape[0] for item in channels]
    widths = [item.shape[1] for item in channels]
    if mode == "largest":
        target = (max(widths), max(heights))
    else:
        target = (min(widths), min(heights))
    resized = []
    for channel in channels:
        if (channel.shape[1], channel.shape[0]) == target:
            resized.append(channel.astype(np.float32, copy=False))
            continue
        img = Image.fromarray(np.clip(channel * 65535, 0, 65535).astype(np.uint16), mode="I;16")
        img = img.resize(target, Image.Resampling.LANCZOS)
        resized.append((np.asarray(img, dtype=np.float32) / 65535.0).clip(0, 1))
    return resized


def downsample_float_rgb_for_preview(arr, max_pixels=RGB_WORKING_PREVIEW_MAX_PIXELS):
    height, width = arr.shape[:2]
    longest = max(width, height)
    if longest <= max_pixels:
        return arr.astype(np.float32, copy=False)
    scale = max_pixels / float(longest)
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    image = Image.fromarray(float_rgb_to_uint8(arr), mode="RGB")
    image = image.resize(size, Image.Resampling.LANCZOS)
    return (np.asarray(image, dtype=np.float32) / 255.0).clip(0, 1)


def downsample_image_for_preview(image, max_pixels=RGB_WORKING_PREVIEW_MAX_PIXELS):
    longest = max(image.width, image.height)
    if longest <= max_pixels:
        return image
    preview = image.copy()
    preview.thumbnail((max_pixels, max_pixels), Image.Resampling.LANCZOS)
    return preview


def downsample_array_for_preview(data, max_pixels=CHANNEL_THUMBNAIL_MAX_PIXELS):
    arr = np.asarray(data)
    if arr.ndim != 2:
        return arr
    longest = max(arr.shape)
    if longest <= max_pixels:
        return arr
    step = max(1, int(math.ceil(longest / float(max_pixels))))
    return arr[::step, ::step]


def float_rgb_to_uint8(arr):
    return np.clip(arr * 255.0, 0, 255).astype(np.uint8)


def float_rgb_to_uint16(arr):
    return np.clip(arr * 65535.0, 0, 65535).astype(np.uint16)


def patch_sample_color(arr, dark, y1, y2, x1, x2):
    patch = arr[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
    patch_dark = dark[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
    if patch.size == 0:
        return None
    valid = patch[~patch_dark]
    if valid.size == 0:
        return None
    return np.median(valid.reshape(-1, 3), axis=0)


def blended_gap_image(arr, mask):
    if not mask.any():
        return Image.fromarray(arr, mode="RGB")
    base = Image.fromarray(arr, mode="RGB")
    soft = base.filter(ImageFilter.GaussianBlur(radius=2.2))
    mask_image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    mask_image = mask_image.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(radius=1.4))
    base.paste(soft, mask=mask_image)
    return base


def crop_black_border(image, threshold=6, padding=8):
    arr = np.asarray(image.convert("RGB"), dtype=np.uint8)
    mask = arr.max(axis=2) > int(threshold)
    if not mask.any():
        return image
    y_indices, x_indices = np.where(mask)
    left = max(0, int(x_indices.min()) - padding)
    right = min(image.width, int(x_indices.max()) + padding + 1)
    top = max(0, int(y_indices.min()) - padding)
    bottom = min(image.height, int(y_indices.max()) + padding + 1)
    if right <= left or bottom <= top:
        return image
    return image.crop((left, top, right, bottom))


def presentation_transform(image, angle=0.0, auto_crop=True):
    transformed = image.convert("RGB")
    if abs(float(angle)) > 0.01:
        transformed = transformed.rotate(
            float(angle),
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor=(0, 0, 0),
        )
    if auto_crop:
        transformed = crop_black_border(transformed)
    return transformed


def fill_internal_black_gaps(image, threshold=6, max_gap_width=120):
    arr = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
    dark = arr.max(axis=2) <= int(threshold)
    height, width = dark.shape
    repair_mask = np.zeros((height, width), dtype=bool)
    fills = 0

    for y in range(height):
        row = dark[y]
        x = 0
        while x < width:
            if not row[x]:
                x += 1
                continue
            start = x
            while x < width and row[x]:
                x += 1
            end = x
            gap_width = end - start
            if start == 0 or end >= width or gap_width > max_gap_width:
                continue
            left = start - 1
            right = end
            if dark[y, left] or dark[y, right]:
                continue
            left_color = patch_sample_color(arr, dark, y - 8, y + 9, max(0, start - 18), start)
            right_color = patch_sample_color(arr, dark, y - 8, y + 9, end, min(width, end + 18))
            if left_color is None:
                left_color = arr[y, left].astype(np.float32)
            if right_color is None:
                right_color = arr[y, right].astype(np.float32)
            steps = gap_width + 1
            for offset, col in enumerate(range(start, end), start=1):
                t = offset / steps
                arr[y, col] = np.clip((1.0 - t) * left_color + t * right_color, 0, 255)
                repair_mask[y, col] = True
            fills += 1

    dark = arr.max(axis=2) <= int(threshold)
    for x in range(width):
        column = dark[:, x]
        y = 0
        while y < height:
            if not column[y]:
                y += 1
                continue
            start = y
            while y < height and column[y]:
                y += 1
            end = y
            gap_height = end - start
            if start == 0 or end >= height or gap_height > max_gap_width:
                continue
            top = start - 1
            bottom = end
            if dark[top, x] or dark[bottom, x]:
                continue
            top_color = patch_sample_color(arr, dark, max(0, start - 18), start, x - 8, x + 9)
            bottom_color = patch_sample_color(arr, dark, end, min(height, end + 18), x - 8, x + 9)
            if top_color is None:
                top_color = arr[top, x].astype(np.float32)
            if bottom_color is None:
                bottom_color = arr[bottom, x].astype(np.float32)
            steps = gap_height + 1
            for offset, row in enumerate(range(start, end), start=1):
                t = offset / steps
                arr[row, x] = np.clip((1.0 - t) * top_color + t * bottom_color, 0, 255)
                repair_mask[row, x] = True
            fills += 1

    cleaned = blended_gap_image(arr, repair_mask)
    return cleaned, fills

