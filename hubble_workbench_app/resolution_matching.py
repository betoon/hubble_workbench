"""Optional, user-estimated circular Gaussian resolution matching."""
import numpy as np


def validate_resolution(values, count):
    if values is None:
        return None
    values = np.asarray(values, dtype=float)
    if values.shape != (count,) or not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('Enter a positive FWHM in arcseconds for each assigned RGB/L channel.')
    return values


def match_resolution(arrays, headers, values, cancel=None):
    from astropy.convolution import Gaussian2DKernel, convolve_fft
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_scales
    from .archive_catalog import check_cancel
    values = validate_resolution(values, len(arrays))
    if values is None:
        return arrays, {}
    target = float(values.max())
    output = []
    for data, header, current in zip(arrays, headers, values):
        check_cancel(cancel)
        scales = np.abs(proj_plane_pixel_scales(WCS(header).celestial)) * 3600
        if len(scales) != 2 or not np.isfinite(scales).all() or (scales <= 0).any():
            raise ValueError('Resolution matching requires valid celestial pixel scales.')
        sigma = np.sqrt(max(0., target**2-current**2)) / np.sqrt(8*np.log(2)) / scales
        if sigma.max() > 64:
            raise ValueError('Requested smoothing exceeds 64 pixels sigma. Use a smaller output or closer resolutions.')
        valid = np.isfinite(data)
        if sigma.max() < 0.01:
            result = np.array(data, copy=True)
        else:
            kernel = Gaussian2DKernel(max(float(sigma[0]), .01), max(float(sigma[1]), .01))
            kwargs = dict(boundary='fill', fill_value=0, nan_treatment='fill', normalize_kernel=True)
            numerator = convolve_fft(np.where(valid, data, 0.), kernel, **kwargs)
            weight = convolve_fft(valid.astype(float), kernel, **kwargs)
            result = np.full(data.shape, np.nan, dtype=np.float32)
            np.divide(numerator, weight, out=result, where=valid & (weight > 1e-8))
        header['PSFFWHM'] = (target, 'Assumed Gaussian FWHM arcsec; user estimate')
        output.append(result)
    return output, {'method': 'circular Gaussian approximation from user estimates',
                    'input_fwhm_arcsec': values.tolist(), 'target_fwhm_arcsec': target}


def show_resolution_controls(app):
    import tkinter as tk
    from tkinter import ttk, messagebox
    window = tk.Toplevel(app)
    window.title('Match image resolution')
    window.transient(app)
    enabled = tk.BooleanVar(value=getattr(app, 'wizard_resolution', {}).get('enabled', False))
    ttk.Checkbutton(window, text='Match resolution when building RGB/LRGB', variable=enabled).pack(anchor='w', padx=15, pady=10)
    ttk.Label(window, text='Enter estimated FWHM in arcseconds. Sharper channels are smoothed\nto the broadest assigned channel. This is a Gaussian approximation,\nnot a measured telescope PSF or a sharpening tool.').pack(padx=15)
    entries = {}
    for channel in ('red', 'green', 'blue', 'luminance'):
        row = ttk.Frame(window); row.pack(fill='x', padx=15, pady=4)
        ttk.Label(row, text=channel.title(), width=12).pack(side='left')
        entries[channel] = tk.StringVar(value=getattr(app, 'wizard_resolution', {}).get(channel, ''))
        ttk.Entry(row, textvariable=entries[channel], width=12).pack(side='left')
    def save():
        settings = {'enabled': enabled.get(), **{k:v.get().strip() for k,v in entries.items()}}
        if enabled.get():
            channels = ['red', 'green', 'blue'] + (['luminance'] if 'luminance' in app.wizard_channels else [])
            try:
                validate_resolution([settings[k] for k in channels], len(channels))
            except ValueError:
                messagebox.showerror('Resolution', 'Enter positive FWHM values for RGB and assigned L.', parent=window)
                return
        app.wizard_resolution = settings
        app.wizard_status.set('Resolution settings saved. Rebuild the composite to apply them.')
        window.destroy()
    ttk.Button(window, text='Save settings', command=save).pack(pady=12)
