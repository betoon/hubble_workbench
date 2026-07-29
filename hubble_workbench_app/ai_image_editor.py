import base64
import json
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image, ImageOps


AI_IMAGE_MODEL = "gpt-image-2"
AI_IMAGE_EDIT_URL = "https://api.openai.com/v1/images/edits"
AI_EDIT_WARNING = (
    "AI output is a creative interpretation. It may alter, remove, or invent astronomical "
    "features and must not be used as scientific evidence or measurement data."
)

AI_EDIT_PRESETS = {
    "Careful astronomy polish": (
        "Improve color balance, local contrast, noise appearance, and clarity while preserving "
        "the original composition and visible structures as closely as possible. Do not add stars, "
        "nebulae, planets, surface features, text, or objects that are not visible in the input."
    ),
    "Natural photographic finish": (
        "Create a polished natural-looking astronomy photograph with balanced color, controlled "
        "highlights, clean shadows, subtle noise reduction, and restrained sharpening. Preserve "
        "the original composition and do not add new celestial objects."
    ),
    "Dramatic creative interpretation": (
        "Create a dramatic, gallery-ready artistic interpretation with rich color, depth, contrast, "
        "and fine detail while keeping the main subject and composition recognizable."
    ),
}


def build_ai_edit_prompt(preset, instructions=""):
    base = AI_EDIT_PRESETS.get(preset, AI_EDIT_PRESETS["Careful astronomy polish"])
    instructions = str(instructions or "").strip()
    prompt = (
        f"{base}\n\n"
        "This is an astronomy-image creative edit. Preserve orientation and framing. "
        "Return a single finished image without captions, borders, labels, or watermarks."
    )
    if instructions:
        prompt += f"\n\nAdditional user instructions: {instructions}"
    return prompt


def prepare_ai_image(path, maximum_dimension=2048):
    path = Path(path)
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail(
            (int(maximum_dimension), int(maximum_dimension)),
            Image.Resampling.LANCZOS,
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), f"{path.stem}.png"


def encode_multipart(fields, file_field, filename, file_data, content_type="image/png"):
    boundary = f"HubbleWorkbench{uuid.uuid4().hex}"
    body = BytesIO()
    for name, value in fields.items():
        body.write(f"--{boundary}\r\n".encode("ascii"))
        body.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.write(str(value).encode("utf-8"))
        body.write(b"\r\n")
    body.write(f"--{boundary}\r\n".encode("ascii"))
    body.write(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{Path(filename).name}"\r\n'
        ).encode("utf-8")
    )
    body.write(f"Content-Type: {content_type}\r\n\r\n".encode("ascii"))
    body.write(file_data)
    body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode("ascii"))
    return body.getvalue(), f"multipart/form-data; boundary={boundary}"


def request_ai_image_edit(api_key, image_path, prompt, quality="medium", timeout=180):
    api_key = str(api_key or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    image_data, filename = prepare_ai_image(image_path)
    body, content_type = encode_multipart(
        {
            "model": AI_IMAGE_MODEL,
            "prompt": prompt,
            "quality": quality,
            "size": "auto",
            "output_format": "png",
        },
        "image[]",
        filename,
        image_data,
    )
    request = Request(
        AI_IMAGE_EDIT_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
            "User-Agent": "Hubble-Workbench/2.0 AI-Creative-Edit",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(detail).get("error", {}).get("message") or detail
        except json.JSONDecodeError:
            message = detail
        raise RuntimeError(f"OpenAI image edit failed: {message}") from exc
    try:
        return base64.b64decode(payload["data"][0]["b64_json"], validate=True)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("OpenAI returned no usable edited image.") from exc


def ai_edit_output_paths(source_path, output_dir, notes_dir, now=None):
    source_path = Path(source_path)
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    stem = f"{source_path.stem}_ai_creative_{stamp}"
    return Path(output_dir) / "ai_creative_edits" / f"{stem}.png", Path(notes_dir) / f"{stem}_notes.txt"


def ai_edit_provenance(source_path, output_path, prompt, quality):
    return "\n".join((
        "AI CREATIVE EDIT — NOT SCIENTIFIC DATA",
        "=" * 48,
        AI_EDIT_WARNING,
        "",
        f"Source file: {Path(source_path)}",
        f"Output file: {Path(output_path)}",
        f"Model: {AI_IMAGE_MODEL}",
        f"Quality: {quality}",
        f"Created: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "Prompt:",
        prompt,
        "",
        "The original source image was preserved unchanged.",
    ))
