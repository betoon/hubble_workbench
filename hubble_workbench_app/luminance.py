"""Display-only luminance blending for WCS-aligned Wizard projects."""
from pathlib import Path
import numpy as np


def luminance_settings(provenance, paths):
    setting = provenance.get('luminance') or {}
    aligned = provenance.get('aligned_paths') or []
    if not setting or len(aligned) < 4 or [str(Path(p).resolve()) for p in paths] != [str(Path(p).resolve()) for p in aligned[:3]]:
        return None
    strength = float(setting.get('strength', .5))
    if not np.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError('Luminance strength must be between 0 and 1.')
    return {'path': aligned[3], 'strength': strength}


def blend_luminance(rgb, luminance, strength, valid=None):
    """Scale RGB equally per pixel, retaining hue and avoiding missing-data fill."""
    rgb = np.asarray(rgb, dtype=np.float32)
    luminance = np.asarray(luminance, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.shape[:2] != luminance.shape:
        raise ValueError('RGB and luminance must share the same aligned pixel grid.')
    if not np.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError('Luminance strength must be between 0 and 1.')
    result = rgb.copy()
    if strength == 0:
        return result
    brightness = np.sum(rgb * np.array([.2126, .7152, .0722]), axis=2)
    mask = np.isfinite(rgb).all(axis=2) & np.isfinite(luminance) & (brightness > 1e-6)
    if valid is not None:
        mask &= valid
    target = (1-strength)*brightness + strength*np.clip(luminance, 0, 1)
    gain = np.ones_like(brightness)
    gain[mask] = target[mask]/brightness[mask]
    # Limit the shared gain rather than clipping individual color channels.
    gain[mask] = np.minimum(gain[mask], 1/np.maximum(rgb.max(axis=2)[mask], 1e-6))
    result[mask] *= gain[mask,None]
    return result
