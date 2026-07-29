import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from PIL import Image

from hubble_workbench_app.ai_image_editor import (
    AI_EDIT_WARNING,
    AI_IMAGE_MODEL,
    AI_IMAGE_MODELS,
    ai_edit_output_paths,
    ai_edit_provenance,
    build_ai_edit_prompt,
    encode_multipart,
    image_edit_cost_notice,
    prepare_ai_image,
)


class AIImageEditorTests(unittest.TestCase):
    def test_prompt_includes_guardrails_and_user_instructions(self):
        prompt = build_ai_edit_prompt("Careful astronomy polish", "Reduce the green cast.")
        self.assertIn("Do not add stars", prompt)
        self.assertIn("Reduce the green cast.", prompt)
        self.assertIn("without captions", prompt)

    def test_prepare_image_normalizes_to_bounded_png(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.jpg"
            Image.new("RGB", (3000, 1200), "navy").save(source)
            data, filename = prepare_ai_image(source, maximum_dimension=512)
            self.assertTrue(data.startswith(b"\x89PNG"))
            self.assertEqual(filename, "source.png")
            normalized = Path(folder) / "normalized.png"
            normalized.write_bytes(data)
            with Image.open(normalized) as image:
                self.assertLessEqual(max(image.size), 512)

    def test_multipart_contains_model_prompt_and_image(self):
        body, content_type = encode_multipart(
            {"model": AI_IMAGE_MODEL, "prompt": "preserve the stars"},
            "image[]",
            "input.png",
            b"\x89PNG\r\n",
        )
        self.assertIn("multipart/form-data; boundary=", content_type)
        self.assertIn(b"gpt-image-1", body)
        self.assertIn(b'name="image[]"', body)
        self.assertIn(b"\x89PNG\r\n", body)

    def test_model_picker_supports_both_requested_models(self):
        self.assertEqual(AI_IMAGE_MODELS, ("gpt-image-1", "gpt-image-2"))

    def test_cost_notice_uses_published_gpt_image_1_output_estimate(self):
        notice = image_edit_cost_notice("gpt-image-1", "low", "1024x1024")
        self.assertIn("$0.011", notice)
        self.assertIn("additional", notice)
        self.assertIn("Paid API request", image_edit_cost_notice("gpt-image-2", "low", "auto"))

    def test_output_is_separate_and_clearly_named(self):
        output, notes = ai_edit_output_paths(
            "M42.png",
            "outputs",
            "notes",
            now=datetime(2026, 7, 28, 12, 34, 56),
        )
        self.assertEqual(output.name, "M42_ai_creative_20260728_123456.png")
        self.assertEqual(output.parent.name, "ai_creative_edits")
        self.assertEqual(notes.name, "M42_ai_creative_20260728_123456_notes.txt")

    def test_provenance_marks_output_non_scientific(self):
        text = ai_edit_provenance(
            "source.png",
            "edited.png",
            "Polish it.",
            "medium",
            model="gpt-image-2",
            size="1024x1536",
        )
        self.assertIn("NOT SCIENTIFIC DATA", text)
        self.assertIn(AI_EDIT_WARNING, text)
        self.assertIn("gpt-image-2", text)
        self.assertIn("1024x1536", text)
        self.assertIn("source.png", text)


if __name__ == "__main__":
    unittest.main()
