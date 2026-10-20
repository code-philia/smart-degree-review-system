import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from paper_compiler.budget import BudgetExceeded, BudgetLedger
from paper_compiler.llm import ModelError

spec = importlib.util.spec_from_file_location('repair_model_proposal', Path(__file__).resolve().parents[1] / 'scripts/repair_model_proposal.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class RepairMeteringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / 'model.env'
        self.config.write_text('MAAS_API_KEY=fake-never-sent\nMAAS_BASE_URL=https://api.modelarts-maas.com/openai/v1\nMAAS_MODEL=deepseek-v4.1-flash\nMAAS_MODEL_VERSION=test-v1\n')
        self.ledger = BudgetLedger(self.root / 'test.sqlite3', '500')
        self.messages = [{'role': 'system', 'content': 'Return repair actions'}, {'role': 'user', 'content': '{}'}]
        self.transport = Mock(return_value={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'status': 'suggested', 'actions': []})}}], 'usage': {'prompt_tokens': 20, 'completion_tokens': 10}})
    def tearDown(self):
        self.temp.cleanup()
    def execute(self):
        return bridge.execute(self.messages, config_path=self.config, ledger=self.ledger, cache=self.root / 'cache', transport=self.transport)
    def test_records_actual_cost_and_force_generations_do_not_replay_transport_cache(self):
        first = self.execute();self.execute()
        self.assertEqual(first['usage'], {'input_tokens':20,'output_tokens':10,'attempts':1})
        self.assertEqual(self.transport.call_count, 2)
        self.assertEqual(self.ledger.summary()['requests'], 2)
        self.assertEqual(self.ledger.summary()['spent_cny'], '0.000240')
    def test_exhausted_cumulative_budget_never_sends_request(self):
        self.ledger.reserve('preexisting', '500', 'prior', '500')
        with self.assertRaises(BudgetExceeded):self.execute()
        self.transport.assert_not_called()
    def test_network_failure_keeps_reservation_without_retry(self):
        self.transport.side_effect=TimeoutError()
        with self.assertRaises(ModelError):self.execute()
        self.assertEqual(self.transport.call_count, 1)
        self.assertEqual(self.ledger.summary()['uncertain_requests'], 1)
        self.assertGreater(float(self.ledger.summary()['committed_cny']), 0)
    def test_uses_authorized_shared_website_phase_limit(self):
        with patch.dict('os.environ', {'PAPER_COMPILER_PHASE_BUDGET_CNY': '20'}):
            self.execute()
        import sqlite3
        with sqlite3.connect(self.root / 'test.sqlite3') as conn:
            self.assertEqual(conn.execute("SELECT limit_micro FROM phases WHERE name='website'").fetchone()[0], 20000000)
    def test_invalid_model_json_is_still_charged(self):
        self.transport.return_value['choices'][0]['message']['content']='bad json'
        with self.assertRaises(ModelError):self.execute()
        self.assertEqual(self.ledger.summary()['spent_cny'], '0.000120')

if __name__ == '__main__':unittest.main()
