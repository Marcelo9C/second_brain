import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes import localization as localization_routes
from app.schemas.localization import RubricCaseCreate, RubricCaseUpdate


class BlockingService:
    def update_case(self, case_id: str, payload: dict) -> dict:
        raise ValueError("Status approved blocked: approval readiness is not pass.")


class LocalizationSchemaTest(unittest.TestCase):
    def test_draft_allows_incomplete_rubrics(self) -> None:
        case = RubricCaseCreate(
            category="Writing",
            template_name="synthetic_template.json",
            status="draft",
            rubrics=[{"partial": True}],
        )

        self.assertEqual(case.status, "draft")
        self.assertEqual(case.rubrics, [{"partial": True}])

    def test_approved_requires_structured_rubrics(self) -> None:
        with self.assertRaises(ValidationError):
            RubricCaseCreate(
                category="Writing",
                template_name="synthetic_template.json",
                status="approved",
                rubrics=[],
            )

    def test_partial_draft_update_allows_incomplete_rubrics_without_status(self) -> None:
        update = RubricCaseUpdate(rubrics=[{"partial": True}])

        self.assertIsNone(update.status)
        self.assertEqual(update.rubrics, [{"partial": True}])

    def test_approved_update_block_returns_controlled_http_error(self) -> None:
        payload = RubricCaseUpdate(status="approved", rubrics=[{"partial": True}])

        with patch.object(localization_routes, "get_localization_service", return_value=BlockingService()):
            with self.assertRaises(HTTPException) as error:
                localization_routes.update_rubric_case("synthetic-id", payload)

        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("approval readiness", error.exception.detail)


if __name__ == "__main__":
    unittest.main()
