"""Deterministic display-RGB suggestions from catalog metadata, without downloads."""
from pathlib import Path
import math


def record_rank(record):
    product = str(record.get('product_type', '')).casefold()
    quality = 2 if any(word in product for word in ('mosaic', 'drizzl', 'combined')) else 1 if 'calibrated' in product else 0
    cached = bool(record.get('local_path')) and Path(record['local_path']).is_file()
    return quality, int(cached)


def record_identity(record):
    return str(record.get('key') or record.get('url') or repr(sorted(record.items())))


def recommend_rgb(records):
    groups = {}
    for record in records:
        group = tuple(str(record.get(field, '')).strip().casefold() for field in ('source', 'instrument', 'target'))
        groups.setdefault(group, []).append(record)
    candidates = []
    for group_key, group in sorted(groups.items()):
        group = sorted(group, key=lambda r: (-record_rank(r)[0], -record_rank(r)[1], record_identity(r)))
        named, bands = {}, {}
        for record in group:
            channel = record.get('channel')
            if channel in ('red', 'green', 'blue'):
                named.setdefault(channel, record)
            try:
                wave = float(record.get('wavelength'))
            except (TypeError, ValueError):
                continue
            if math.isfinite(wave) and wave > 0:
                bands.setdefault(round(wave, 5), record)
        options = []
        if len(named) == 3:
            options.append(named)
        if len(bands) >= 3:
            # Preserve broad wavelength coverage; prefer quality within each band.
            ordered = [bands[key] for key in sorted(bands)]
            options.append(dict(zip(('blue', 'green', 'red'), (ordered[0], ordered[len(ordered)//2], ordered[-1]))))
        for channels in options:
            chosen = list(channels.values())
            if len({record_identity(r) for r in chosen}) != 3:
                continue
            labels = [str(r.get('band', '')).strip().casefold() for r in chosen]
            if all(labels) and len(set(labels)) != 3:
                continue
            quality = sum(record_rank(r)[0] for r in chosen)
            cached = sum(record_rank(r)[1] for r in chosen)
            candidates.append(((quality, cached), group_key, channels))
    if not candidates:
        return {}, 'No three distinct bands for one source, instrument and target. Preview individual bands or assign colors manually.'
    candidates.sort(key=lambda item: (-item[0][0], -item[0][1], item[1]))
    _, _, channels = candidates[0]
    selected = list(channels.values())
    mosaics = sum(record_rank(r)[0] == 2 for r in selected)
    cached = sum(record_rank(r)[1] for r in selected)
    source = selected[0].get('source', 'source')
    explanation = (f'Suggested {source}: {mosaics}/3 mosaic/combined products; {cached}/3 local files available. '
                   'Prefers product quality, then local availability; keeps source, instrument and target together. '
                   'Display colors only. Review footprints; WCS alignment must still verify shared coverage.')
    return channels, explanation
