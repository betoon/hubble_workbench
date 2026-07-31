import json
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


OPUS_ROOT = "https://opus.pds-rings.seti.org/opus"
OPUS_API_ROOT = f"{OPUS_ROOT}/api"
OPUS_COLUMNS = (
    "opusid",
    "instrument",
    "planet",
    "target",
    "time1",
    "observationduration",
)


def opus_product_page_url(opus_id):
    return f"{OPUS_ROOT}/#/view=detail&detail={quote(str(opus_id), safe='-')}"


def build_opus_search_url(
    query, endpoint="data.json", limit=25, start_obs=1,
    order="time1,opusid",
):
    parameters = {
        **dict(query or {}),
        "order": str(order or "time1,opusid"),
        "startobs": max(1, int(start_obs)),
        "limit": max(1, min(100, int(limit))),
    }
    if endpoint == "data.json":
        parameters["cols"] = ",".join(OPUS_COLUMNS)
    return f"{OPUS_API_ROOT}/{endpoint}?{urlencode(parameters)}"


def _read_json(url, timeout=35):
    request = Request(
        url,
        headers={"User-Agent": "Hubble-Workbench/2.0 Planetary-Observatory"},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def parse_opus_search_results(metadata_payload, image_payload):
    rows = list((metadata_payload or {}).get("page") or [])
    images = {
        str(item.get("opusid") or item.get("opus_id")): item
        for item in (image_payload or {}).get("data") or []
        if item.get("opusid") or item.get("opus_id")
    }
    products = []
    for row in rows:
        values = dict(zip(OPUS_COLUMNS, row))
        opus_id = str(values.get("opusid") or "").strip()
        if not opus_id:
            continue
        image = images.get(opus_id, {})
        instrument = str(values.get("instrument") or "Unknown instrument")
        target = str(values.get("target") or values.get("planet") or "Unknown target")
        products.append({
            "Observation_id": opus_id,
            "Observation_time": values.get("time1") or "",
            "Comment": f"{instrument} observation of {target}",
            "Instrument": instrument,
            "Target": target,
            "Duration": values.get("observationduration") or "",
            "ProductURL": opus_product_page_url(opus_id),
            "FilesURL": f"{OPUS_API_ROOT}/files/{quote(opus_id, safe='-')}.json",
            "External_url": image.get("url") or "",
            "_OPUS_id": opus_id,
            "_OPUS_preview_url": image.get("url") or "",
        })
    return products


def query_opus_products_page(
    query, limit=25, start_obs=1, order="time1,opusid", timeout=35
):
    metadata_url = build_opus_search_url(
        query, "data.json", limit, start_obs=start_obs, order=order
    )
    image_url = build_opus_search_url(
        query, "images/med.json", limit, start_obs=start_obs, order=order
    )
    metadata_payload = _read_json(metadata_url, timeout)
    products = parse_opus_search_results(
        metadata_payload,
        _read_json(image_url, timeout),
    )
    page_info = {
        "start_obs": max(1, int(metadata_payload.get("start_obs") or start_obs)),
        "limit": max(1, int(metadata_payload.get("limit") or limit)),
        "count": max(0, int(metadata_payload.get("count") or len(products))),
        "available": max(0, int(metadata_payload.get("available") or len(products))),
    }
    return products, metadata_url, page_info


def query_opus_products(query, limit=25, timeout=35):
    products, metadata_url, _page_info = query_opus_products_page(
        query, limit=limit, start_obs=1, timeout=timeout
    )
    return products, metadata_url


def parse_opus_product_files(payload, opus_id):
    product_types = ((payload or {}).get("data") or {}).get(str(opus_id), {})
    files = []
    seen = set()
    for product_type, urls in product_types.items():
        for url in urls or []:
            url = str(url or "")
            if not url.startswith(("https://", "http://")) or url in seen:
                continue
            seen.add(url)
            files.append({
                "FileName": Path(url).name,
                "URL": url,
                "KBytes": None,
                "Description": str(product_type).replace("_", " "),
            })
    return files


def query_opus_product_files(opus_id, timeout=35):
    url = f"{OPUS_API_ROOT}/files/{quote(str(opus_id), safe='-')}.json"
    return parse_opus_product_files(_read_json(url, timeout), opus_id), url
