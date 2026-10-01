import json
import unittest

from finai_ui import data_service as ds
from finai_ui.financial_engine import build_evidence, prepare_model_evidence, expand_evidence
from finai_ui.ai.verifier import fallback_answer


class FinancialAgentTests(unittest.TestCase):
    def setUp(self):
        ds.refresh_csv_data()
        self.period = ds.resolve_period("2026-09")
        self.evidence = build_evidence("Kenapa laba September meningkat?", self.period, None)

    def test_initial_evidence_ready(self):
        self.assertEqual(self.evidence.get("status"), "READY")
        self.assertIn("net_profit", self.evidence.get("current", {}))
        self.assertIn("mom", self.evidence.get("comparisons", {}))
        self.assertIn("yoy", self.evidence.get("comparisons", {}))

    def test_model_evidence_is_bounded(self):
        full = len(json.dumps(self.evidence, ensure_ascii=False))
        compact = len(json.dumps(prepare_model_evidence(self.evidence), ensure_ascii=False))
        self.assertLess(compact, full)

    def test_dynamic_tools(self):
        for tool in [
            "income_drivers", "balance_drivers", "funding_analysis", "trend",
            "target", "loan_products", "dpk_products", "investment_products", "correlation"
        ]:
            result = expand_evidence(self.evidence, tool, self.period)
            self.assertIsNotNone(result, tool)

    def test_fallback_does_not_answer_unrelated_metric(self):
        answer = fallback_answer(self.evidence, question="Berapa laba September 2026?")
        self.assertIn("778.85", answer)


if __name__ == "__main__":
    unittest.main()
