from tempfile import SpooledTemporaryFile
import unittest
from typing import BinaryIO, cast

import pandas as pd
from starlette.datastructures import UploadFile

from app.schemas.ai_schemas import AiAnomalyProfile, AiAuditCandidate
from app.services.ai_service import _postprocess_profile
from app.services.import_service import (
	LAND_COLUMN_ALIASES,
	_canonicalize_columns,
	_compose_owner_name_columns,
	_resolve_owner_name,
	_read_table,
)


class AuditWorkflowRulesTest(unittest.IsolatedAsyncioTestCase):
	def test_compose_owner_name_from_split_columns(self) -> None:
		raw_df = pd.DataFrame(
			{
				"Прізвище": ["Петренко"],
				"Ім'я": ["Іван"],
				"По батькові": ["Олексійович"],
			}
		)

		canonical_df = _canonicalize_columns(raw_df, LAND_COLUMN_ALIASES)
		composed_df = _compose_owner_name_columns(canonical_df)

		self.assertIn("owner_name", composed_df.columns)
		self.assertEqual(composed_df.iloc[0]["owner_name"], "Петренко Іван Олексійович")

	def test_compose_owner_name_fills_blank_owner_column(self) -> None:
		raw_df = pd.DataFrame(
			{
				"owner_name": ["", "UNKNOWN_OWNER"],
				"Прізвище": ["Шевченко", "Коваль"],
				"Ім'я": ["Марія", "Олег"],
			}
		)

		canonical_df = _canonicalize_columns(raw_df, LAND_COLUMN_ALIASES)
		composed_df = _compose_owner_name_columns(canonical_df)

		self.assertEqual(composed_df.iloc[0]["owner_name"], "Шевченко Марія")
		self.assertEqual(composed_df.iloc[1]["owner_name"], "Коваль Олег")

	def test_resolve_owner_name_from_owner_like_column(self) -> None:
		row = {
			"prizvyshche_im_ya_po_batkovi_fizichnoyi_osobi": "Гнатюк Ігор Степанович",
			"owner_name": "UNKNOWN_OWNER",
		}
		self.assertEqual(_resolve_owner_name(row), "Гнатюк Ігор Степанович")

	async def test_read_csv_supports_semicolon_delimiter(self) -> None:
		payload = (
			"tax_id;owner_name;ownership_share;reg_date;record_number;reg_authority;doc_type\n"
			"12345678;Петренко Іван;1/1;2026-01-10;REC-001;Реєстр;Витяг\n"
		).encode("utf-8-sig")

		buffer = SpooledTemporaryFile()
		buffer.write(payload)
		buffer.seek(0)
		upload = UploadFile(filename="land.csv", file=cast(BinaryIO, cast(object, buffer)))
		df = await _read_table(upload)

		self.assertEqual(
			list(df.columns),
			[
				"tax_id",
				"owner_name",
				"ownership_share",
				"reg_date",
				"record_number",
				"reg_authority",
				"doc_type",
			],
		)
		self.assertEqual(df.iloc[0]["owner_name"], "Петренко Іван")

	def test_postprocess_profile_caps_missing_identity_risk(self) -> None:
		candidate = AiAuditCandidate(
			zone="RED",
			tax_id=None,
			purpose=None,
			ownership_type=None,
			owner_name_known=False,
			location=None,
			potential_loss_uah=0,
		)
		profile = AiAnomalyProfile(risk_score=95, ai_summary="risk", decision_confidence=80)

		result = _postprocess_profile(candidate, profile)

		self.assertLessEqual(result.risk_score, 92)

	def test_postprocess_profile_zero_loss_red_stays_below_max_bucket(self) -> None:
		candidate = AiAuditCandidate(
			zone="RED",
			tax_id="12345678",
			purpose="Сільськогосподарське",
			ownership_type="Приватна",
			owner_name_known=True,
			location="Львівська область",
			potential_loss_uah=0,
		)
		profile = AiAnomalyProfile(risk_score=92, ai_summary="risk", decision_confidence=80)

		result = _postprocess_profile(candidate, profile)

		self.assertLessEqual(result.risk_score, 98)









