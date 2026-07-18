import numpy as np
from PIL import Image, ImageFilter


HYDROGEN_PRESETS = {
    "Vibrant Magenta/Pink": (1.0, 50 / 255, 180 / 255),
    "Natural H-Alpha Red": (1.0, 0.0, 0.0),
    "Hubble Palette Green": (0.0, 1.0, 0.0),
    "OIII Cyan/Blue": (0.0, 1.0, 1.0),
    "Electric Purple": (180 / 255, 0.0, 1.0),
}


def _float_rgb(image):
    arr = np.asarray(image)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError("Hydrogen enhancement requires an RGB image.")
    arr = arr.astype(np.float32)
    if arr.size and np.nanmax(arr) > 1.0:
        scale = 65535.0 if np.nanmax(arr) > 255 else 255.0
        arr /= scale
    return np.nan_to_num(np.clip(arr, 0, 1), nan=0.0, posinf=1.0, neginf=0.0)


def _opening_tophat(channel, kernel_size):
    size = max(3, int(kernel_size))
    if size % 2 == 0:
        size -= 1
    image = Image.fromarray(np.clip(channel * 255, 0, 255).astype(np.uint8), mode="L")
    opened = image.filter(ImageFilter.MinFilter(size)).filter(ImageFilter.MaxFilter(size))
    return np.clip(channel - np.asarray(opened, dtype=np.float32) / 255.0, 0, 1)


def process_hydrogen_rgb(
    image,
    *,
    background_color=None,
    mask_background=True,
    tolerance=10,
    channel_scales=(1.0, 1.0, 1.0),
    stretch_factor=15.0,
    black_point=0.0,
    sky_percentile=2.0,
    preset="Vibrant Magenta/Pink",
    glow_strength=1.5,
    kernel_size=15,
    smooth=True,
):
    """Return a float RGB enhancement and a float H-II visual proxy mask."""
    rgb = _float_rgb(image)
    if background_color is None:
        background_color = rgb[0, 0]
    background_color = _float_rgb(np.asarray(background_color).reshape(1, 1, 3))[0, 0]
    tolerance = max(0.0, float(tolerance)) / 255.0
    background_mask = np.zeros(rgb.shape[:2], dtype=bool)
    if mask_background:
        background_mask = np.all(np.abs(rgb - background_color) <= tolerance, axis=2)

    scales = np.asarray(channel_scales, dtype=np.float32).reshape(1, 1, 3)
    balanced = np.clip(rgb * scales, 0, 1)
    balanced[background_mask] = 0
    for channel in range(3):
        values = balanced[:, :, channel][~background_mask]
        if values.size:
            balanced[:, :, channel] = np.clip(
                balanced[:, :, channel] - np.percentile(values, float(sky_percentile)), 0, 1
            )

    shifted = np.clip(balanced - float(black_point), 0, 1)
    strength = max(0.01, float(stretch_factor))
    stretched = np.arcsinh(strength * shifted) / np.arcsinh(strength)
    stretched[background_mask] = 0

    red_tophat = _opening_tophat(stretched[:, :, 0], kernel_size)
    blue_tophat = _opening_tophat(stretched[:, :, 2], kernel_size)
    proxy = np.minimum(red_tophat, blue_tophat)
    proxy = np.clip(0.7 * proxy + 0.3 * blue_tophat, 0, 1)
    proxy[background_mask] = 0
    glow_image = Image.fromarray(np.clip(proxy * 255, 0, 255).astype(np.uint8), mode="L")
    glow = np.asarray(glow_image.filter(ImageFilter.GaussianBlur(radius=1.2)), dtype=np.float32) / 255.0

    color = np.asarray(HYDROGEN_PRESETS.get(preset, HYDROGEN_PRESETS["Vibrant Magenta/Pink"]), dtype=np.float32)
    factor = max(0.0, float(glow_strength)) * 2.55
    enhanced = stretched.copy()
    enhanced[:, :, 0] += factor * glow * color[0]
    enhanced[:, :, 1] -= factor * glow * (1.0 - color[1]) * 0.1
    enhanced[:, :, 1] += factor * glow * color[1] * 0.5
    enhanced[:, :, 2] += factor * glow * color[2]
    enhanced = np.clip(enhanced, 0, 1)
    if smooth:
        base = Image.fromarray(np.clip(enhanced * 255, 0, 255).astype(np.uint8), mode="RGB")
        softened = np.asarray(base.filter(ImageFilter.GaussianBlur(radius=0.55)), dtype=np.float32) / 255.0
        enhanced = 0.8 * enhanced + 0.2 * softened
    enhanced[background_mask] = 0
    return enhanced.astype(np.float32), proxy.astype(np.float32)
