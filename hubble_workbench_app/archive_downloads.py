"""Streaming, cancellable FITS downloads with verified reusable cache entries."""
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from .archive_catalog import Cancelled, check_cancel, network_session


def validate_archive_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    roots = ("stsci.edu", "nasa.gov", "ipac.caltech.edu", "harvard.edu")
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password or not any(host == root or host.endswith("."+root) for root in roots):
        raise ValueError("This is not a supported public archive download URL.")
    return url


def digest_file(path, cancel=None):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            check_cancel(cancel)
            digest.update(block)
    return digest.hexdigest()


def validate_fits(path):
    from astropy.io import fits
    with fits.open(path, memmap=False) as hdul:
        # Older public Chandra products use lowercase FITS exponents. Repair
        # fixable header formatting in memory; retain the original file bytes.
        hdul.verify("silentfix+exception")
        if not any(hdu.header.get("NAXIS", 0) >= 2 and hdu.header.get("NAXIS1", 0) > 0 for hdu in hdul):
            raise ValueError("The archive returned no image data in this FITS file.")
        for hdu in hdul:
            if hdu.header.get("NAXIS", 0) >= 2:
                _ = hdu.data  # Detect truncated image payloads, not just headers.


class DownloadCache:
    def __init__(self, root, session=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.session = session or network_session()

    def paths(self, record):
        key = hashlib.sha256(str(record.get("key") or record["url"]).encode()).hexdigest()
        suffix = ".fits.gz" if urlparse(record["url"]).path.lower().endswith(".gz") else ".fits"
        path = self.root / (key + suffix)
        return path, path.with_suffix(path.suffix+".json")

    def cached(self, record, cancel=None):
        path, meta = self.paths(record)
        try:
            saved = json.loads(meta.read_text(encoding="utf-8"))
            if saved["bytes"] == path.stat().st_size and digest_file(path, cancel) == saved["sha256"]:
                return path
        except (OSError, ValueError, KeyError):
            pass
        return None

    def fetch(self, record, cancel=None, progress=lambda done,total,message: None):
        check_cancel(cancel)
        url = validate_archive_url(record["url"])
        cached = self.cached(record, cancel)
        if cached:
            progress(cached.stat().st_size, cached.stat().st_size, "Reusing verified download")
            return cached
        path, meta = self.paths(record)
        partial = path.with_suffix(path.suffix+".part")
        partial_meta = path.with_suffix(path.suffix+".part.json")
        offset, headers = 0, {"Accept-Encoding":"identity"}
        try:
            prior = json.loads(partial_meta.read_text(encoding="utf-8"))
            validator = prior.get("etag") or prior.get("modified")
            if prior.get("url") == url and validator and partial.exists():
                offset = partial.stat().st_size
                headers.update({"Range":f"bytes={offset}-", "If-Range":validator})
        except (OSError, ValueError):
            pass
        response = self.session.get(url, headers=headers, stream=True, timeout=(15,45))
        if response.status_code == 416 and offset:
            # A complete partial file or changed remote size cannot be resumed.
            response.close()
            offset = 0
            response = self.session.get(url, headers={"Accept-Encoding":"identity"}, stream=True, timeout=(15,45))
        with response:
            response.raise_for_status()
            validate_archive_url(response.url)
            if response.status_code == 206:
                if not offset or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise ValueError("Archive returned an invalid resume range; partial file preserved.")
            else:
                offset = 0
            length = int(response.headers.get("Content-Length", 0) or 0)
            total = offset + length if length else None
            partial_meta.write_text(json.dumps({"url":url, "etag":response.headers.get("ETag"),
                                                "modified":response.headers.get("Last-Modified")}), encoding="utf-8")
            done = offset
            with partial.open("ab" if offset else "wb") as output:
                for block in response.iter_content(chunk_size=256*1024):
                    check_cancel(cancel)
                    if not block:
                        continue
                    output.write(block)
                    done += len(block)
                    progress(done, total, "Downloading")
            check_cancel(cancel)
            if total and done != total:
                raise ValueError("Download incomplete; retry to resume the partial file.")
        # FITS reader detects gzip from magic bytes, including .part filenames.
        validate_fits(partial)
        digest = digest_file(partial, cancel)
        os.replace(partial, path)
        saved = {"bytes":path.stat().st_size, "sha256":digest, "record":record}
        temp_meta = meta.with_suffix(meta.suffix+".tmp")
        temp_meta.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        os.replace(temp_meta, meta)
        partial_meta.unlink(missing_ok=True)
        progress(saved["bytes"], saved["bytes"], "Verified")
        return path
