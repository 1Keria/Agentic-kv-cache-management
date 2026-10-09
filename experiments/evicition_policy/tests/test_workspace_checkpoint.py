"""Working-space reserve must depend only on arrived requests and real budgets."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workspace_checkpoint import WorkspaceInputReplay


class WorkspaceTests(unittest.TestCase):
    def test_observed_high_water_scales_budget_without_cache_reset(self):
        engine = WorkspaceInputReplay(64, 32, page_size=2, window=2, chunk=4,
            policy='frontier', max_prompt=64, frontier_settings={
                'enabled': True, 'max_units': 8, 'full_budget_tokens': 32,
                'swa_budget_tokens': 8, 'admission_policy': 'retain_existing',
                'partial_checkpoints': True, 'resident_downgrade': True})
        root = engine.cache.root_node
        first = engine.request({'input_ids': list(range(25))}, 0)
        self.assertEqual(first['workspace_high_water_full'], 26)
        self.assertEqual(first['workspace_protection_full_cap'], 32)
        receipt = engine.update_budget(32, 16, 0)
        self.assertTrue(receipt['complete'])
        self.assertEqual(engine.controller.protection_cap.full, 6)
        small = engine.request({'input_ids': list(range(7))}, 1)
        self.assertEqual(small['workspace_high_water_full'], 26)
        self.assertLessEqual(small['after']['frontier']['full_dependency_tokens'], 6)
        engine.update_budget(64, 32, 1)
        self.assertEqual(engine.controller.protection_cap.full, 32)
        self.assertIs(engine.cache.root_node, root)
        engine.assert_integrity()

    def test_zero_headroom_revokes_qualification_but_preserves_legal_admission(self):
        engine = WorkspaceInputReplay(32, 16, page_size=2, window=2, chunk=4,
            policy='frontier', max_prompt=64, frontier_settings={
                'enabled': True, 'max_units': 8, 'full_budget_tokens': 16,
                'swa_budget_tokens': 8, 'admission_policy': 'retain_existing',
                'partial_checkpoints': True, 'resident_downgrade': True})
        result = engine.request({'input_ids': list(range(31))}, 0)
        self.assertEqual(result['workspace_protection_full_cap'], 0)
        self.assertFalse(engine.frontier.units)
        self.assertTrue(result['budget_checks_complete'])
        engine.assert_integrity()


if __name__ == '__main__':
    unittest.main()
