"""CLI JSON must survive ill-formed embedded-font characters."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

class CliEncodingTests(unittest.TestCase):
    def test_font_surrogate_is_losslessly_serialized_on_strict_utf8_stdout(self):
        path=Path(__file__).resolve().parents[1]/'scripts/six_rule_detector.py'
        spec=importlib.util.spec_from_file_location('six_rule_cli',path)
        cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        stream=io.BytesIO();stdout=io.TextIOWrapper(stream,encoding='utf-8',errors='strict')
        result={'pages':1,'rules':{'15':{'status':'completed','findings':[{'text_excerpt':'bad font \ud800'}]}}}
        with patch.object(cli,'detect',return_value=result),patch('sys.argv',['six_rule_detector','--pdf','fixture.pdf','--rule','15']),patch('sys.stdout',stdout):
            self.assertEqual(cli.main(),0)
        stdout.flush()
        self.assertEqual(json.loads(stream.getvalue().decode('utf-8')),result)

if __name__=='__main__':unittest.main()
