import json
import unittest
from unittest.mock import patch

from finai_ui import data_service as ds
from finai_ui.financial_engine import build_evidence, prepare_model_evidence, expand_evidence
from finai_ui.ai.verifier import fallback_answer
from finai_ui.ai import orchestrator


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

    def test_model_evidence_is_reasonably_small(self):
        payload = json.dumps(prepare_model_evidence(self.evidence), ensure_ascii=False)
        self.assertLess(len(payload), 30000)

    def test_monthly_profit_flow_is_distinguished_from_cumulative(self):
        tool = self.evidence["analysis_tools"]["income_drivers"]
        self.assertAlmostEqual(tool["monthly_flow"]["net_profit"]["current_flow"], 81.26, places=2)
        self.assertAlmostEqual(tool["monthly_flow"]["net_profit"]["change"]["percent"], 4.38, places=2)

    def test_factual_python_fallback_is_still_available(self):
        answer = fallback_answer(self.evidence, question="Berapa laba September 2026?")
        self.assertIn("778.85", answer)

    @patch("finai_ui.ai.orchestrator.inspect")
    def test_analytical_question_does_not_use_python_analytical_fallback(self, mock_inspect):
        mock_inspect.return_value = {"ok": False, "error": "provider unavailable"}
        result = orchestrator.run_financial_analysis("Kenapa laba September meningkat?", "2026-09")
        self.assertEqual(result["stage"], "llm_director_unavailable")
        self.assertNotEqual(result["stage"], "python_analytical_fallback")
        self.assertIn("belum dapat menyelesaikan analisis", result["answer"].lower())

    @patch("finai_ui.ai.orchestrator.synthesize")
    @patch("finai_ui.ai.orchestrator.inspect")
    def test_agent_requests_more_evidence_before_synthesis(self, mock_inspect, mock_synthesize):
        mock_inspect.side_effect = [
            {"ok": True, "analysis": {"scope": "FINANCIAL", "response_mode": "ANALYSIS", "need_more_evidence": True, "requests": ["trend"], "findings": [{"type": "fact", "statement": "x"}]}},
            {"ok": True, "analysis": {"scope": "FINANCIAL", "response_mode": "ANALYSIS", "need_more_evidence": False, "requests": [], "findings": [{"type": "relationship", "statement": "y"}]}},
        ]
        mock_synthesize.return_value = {"ok": True, "content": "Kesimpulan berdasarkan evidence yang tersedia.", "model": "test"}
        result = orchestrator.run_financial_analysis("Kenapa laba September meningkat?", "2026-09")
        self.assertEqual(result["stage"], "analyst_agent")
        self.assertEqual(mock_inspect.call_count, 2)
        self.assertEqual(mock_synthesize.call_count, 1)
        self.assertIn("trend", result["evidence"]["analysis_tools"])


if __name__ == "__main__":
    unittest.main()
