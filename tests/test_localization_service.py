import json
import tempfile
import unittest
from pathlib import Path

from app.services.localization_service import LocalizationService


class StubRepository:
    pass


class LocalizationServiceTest(unittest.TestCase):
    def test_template_response_is_marked_as_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            localization_dir = Path(directory)
            template_dir = localization_dir / "pt-br" / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "writing_template.json").write_text(
                json.dumps([{"slot": "synthetic"}]),
                encoding="utf-8",
            )
            service = LocalizationService(
                repository=StubRepository(),
                localization_dir=localization_dir,
            )

            template = service.get_template(locale="pt-BR", category="Writing")

        self.assertEqual(template["artifact_type"], "template_scaffold")
        self.assertFalse(template["rubrics_are_final"])
        self.assertEqual(template["rubrics"], [{"slot": "synthetic"}])
        self.assertIn("scaffold", template["message"].lower())


if __name__ == "__main__":
    unittest.main()
