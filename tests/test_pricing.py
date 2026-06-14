import os
import unittest

from token_dashboard.pricing import load_pricing, cost_for, format_for_user

PRICING = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pricing.json"))


class CostTests(unittest.TestCase):
    def setUp(self):
        self.p = load_pricing(PRICING)

    def _u(self, **kw):
        base = {
            "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
            "cache_create_5m_tokens": 0, "cache_create_1h_tokens": 0,
        }
        base.update(kw)
        return base

    def test_known_frontier_input_cost(self):
        c = cost_for("gpt-5.5", self._u(input_tokens=1_000_000), self.p)
        self.assertAlmostEqual(c["usd"], 5.00, places=4)
        self.assertFalse(c["estimated"])

    def test_known_large_output_cost(self):
        c = cost_for("gpt-5.4", self._u(output_tokens=1_000_000), self.p)
        self.assertAlmostEqual(c["usd"], 15.00, places=4)

    def test_known_claude_sonnet_cost(self):
        c = cost_for("claude-sonnet-4-6", self._u(input_tokens=1_000_000, output_tokens=1_000_000), self.p)
        self.assertAlmostEqual(c["usd"], 18.00, places=4)

    def test_claude_cache_multipliers(self):
        c = cost_for("claude-opus-4-8", self._u(cache_read_tokens=1_000_000, cache_create_5m_tokens=1_000_000), self.p)
        self.assertAlmostEqual(c["usd"], 6.75, places=4)

    def test_unknown_codex_falls_back(self):
        c = cost_for("codex-auto-review", self._u(input_tokens=1_000_000), self.p)
        self.assertAlmostEqual(c["usd"], 2.50, places=4)
        self.assertTrue(c["estimated"])

    def test_unknown_unparseable_returns_none(self):
        c = cost_for("custom-local-model", self._u(input_tokens=9999), self.p)
        self.assertIsNone(c["usd"])

    def test_cache_read_cheaper_than_input(self):
        c_in = cost_for("gpt-5.5", self._u(input_tokens=1_000_000), self.p)
        c_cr = cost_for("gpt-5.5", self._u(cache_read_tokens=1_000_000), self.p)
        self.assertLess(c_cr["usd"], c_in["usd"])


class PlanFormatTests(unittest.TestCase):
    def setUp(self):
        self.p = load_pricing(PRICING)

    def test_api_plan_returns_raw(self):
        out = format_for_user(12.34, "api", self.p)
        self.assertEqual(out["display_usd"], 12.34)
        self.assertIsNone(out["subscription_usd"])

    def test_free_plan_labels_api_equivalent(self):
        out = format_for_user(12.34, "codex-free", self.p)
        self.assertEqual(out["subscription_usd"], 0)
        self.assertIn("API-equivalent", out["subtitle"])

    def test_chatgpt_plus_plan_returns_subscription_subtitle(self):
        out = format_for_user(12.34, "chatgpt-plus", self.p)
        self.assertEqual(out["subscription_usd"], 20)
        self.assertIn("Plus", out["subtitle"])


if __name__ == "__main__":
    unittest.main()
