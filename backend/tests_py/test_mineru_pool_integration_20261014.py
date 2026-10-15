"""Exercise actual cache/HTTP boundaries for fixed PDF account ownership."""
import json
import os
from hashlib import sha256
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import pymupdf
from pdf_rules import mineru_api, engine
from pdf_rules.mineru_account_pool import MinerUAccountPool
from pdf_rules.mineru_cache import RawLayoutCache, TaskState
from test_mineru_api import FakeHttp, fake_zip

class PoolIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'paper.pdf';self.cache=RawLayoutCache(Path(temp.name)/'cache')
        with pymupdf.open() as pdf:
            pdf.new_page(width=600,height=800);pdf.save(self.path)
        self.pool=MinerUAccountPool.from_tokens(['fixture-legacy','fixture-second'],legacy_token='fixture-legacy')
        self.identity=next(str(i) for i in range(100) if self.pool.select_for_pdf(str(i)).token=='fixture-second')
        self.env=patch.dict(os.environ,{'MINERU_CACHE_DIR':str(self.cache.folder)})
        self.env.start();self.addCleanup(self.env.stop)
    def parse(self,http,**kw):
        return mineru_api.parse_layout(self.path,None,http,account_pool=self.pool,pdf_identity=self.identity,**kw)
    def resumed(self):
        http=FakeHttp();http.chunk_pages=1;return http
    def auth(self,http):
        return [c[2]['Authorization'] for c in http.calls if 'Authorization' in c[2]]
    def pending(self,owner='fixture-legacy',unmarked=False):
        state=TaskState(self.cache,self.cache.key(self.path.read_bytes()),owner);state.write('retained-batch')
        if unmarked:
            record=json.loads(state.path.read_text());record.pop('account_sha');state.path.write_text(json.dumps(record))
        return state
    def test_new_pdf_uses_selected_account_for_post_and_poll_only(self):
        http=FakeHttp();self.parse(http)
        self.assertEqual(self.auth(http),['Bearer fixture-second']*2)
        self.assertEqual([c[2] for c in http.calls if c[0]=='PUT'],[{}])
    def test_marked_pending_overrides_assignment_without_reupload(self):
        self.pending();http=self.resumed();self.parse(http)
        self.assertEqual(self.auth(http),['Bearer fixture-legacy'])
        self.assertFalse(any(c[0] in {'POST','PUT'} for c in http.calls))
    def test_unmarked_legacy_pending_requires_explicit_read_and_legacy_owner(self):
        state=self.pending(unmarked=True)
        self.assertIsNone(state.read())
        self.assertEqual(state.read(legacy_owned=True),'retained-batch')
        self.pool=MinerUAccountPool.from_tokens(['fixture-second','fixture-legacy'],legacy_token='fixture-legacy')
        http=self.resumed();self.parse(http)
        self.assertEqual(self.auth(http),['Bearer fixture-legacy'])
        self.assertFalse(any(c[0] in {'POST','PUT'} for c in http.calls))
    def test_marked_other_account_still_rejected_by_legacy_read(self):
        state=self.pending('fixture-second')
        wrong=TaskState(self.cache,self.cache.key(self.path.read_bytes()),'fixture-legacy')
        self.assertIsNone(wrong.read(legacy_owned=True))
    def test_missing_pending_owner_fails_before_any_http_with_safe_reason(self):
        self.pending('removed-secret');http=self.resumed()
        with self.assertRaises(mineru_api.MinerUError) as raised:self.parse(http)
        self.assertEqual(raised.exception.diagnostics,{'account_failure':'owner_missing'})
        self.assertEqual(http.calls,[])
        self.assertNotIn(sha256(b'removed-secret').hexdigest(),str(raised.exception))
        self.assertIsNone(raised.exception.__context__)
    def test_present_null_owner_is_invalid_and_never_assumed_legacy(self):
        state=self.pending();record=json.loads(state.path.read_text());record['account_sha']=None
        state.path.write_text(json.dumps(record));http=self.resumed()
        with self.assertRaises(mineru_api.MinerUError) as raised:self.parse(http)
        self.assertEqual(raised.exception.diagnostics,{'account_failure':'owner_invalid'})
        self.assertEqual(http.calls,[])
    def test_completed_raw_cache_is_account_independent_and_skips_bad_pending_owner(self):
        self.pending('removed-secret')
        self.cache.write(self.cache.key(self.path.read_bytes()),json.loads(__import__('zipfile').ZipFile(__import__('io').BytesIO(fake_zip())).read('layout.json'))['pdf_info'])
        http=self.resumed();objects=self.parse(http)
        self.assertTrue(objects);self.assertEqual(http.calls,[])
    def test_binding_remains_fixed_across_distinct_parse_subsets_and_ocr(self):
        binding=mineru_api.MinerUTaskBinding(self.pool,self.identity)
        first=FakeHttp();mineru_api.parse_layout(self.path,None,first,account_binding=binding)
        with pymupdf.open(self.path) as pdf:pdf[0].insert_text((50,50),'different subset');pdf.saveIncr()
        second=FakeHttp();mineru_api.parse_layout(self.path,None,second,force_ocr=True,account_binding=binding)
        self.assertEqual(self.auth(first)+self.auth(second),['Bearer fixture-second']*4)
    def test_later_conflicting_pending_owner_fails_without_cross_account_poll(self):
        binding=mineru_api.MinerUTaskBinding(self.pool,self.identity)
        mineru_api.parse_layout(self.path,None,FakeHttp(),account_binding=binding)
        with pymupdf.open(self.path) as pdf:pdf[0].insert_text((50,50),'different subset');pdf.saveIncr()
        self.pending('fixture-legacy');http=self.resumed()
        with self.assertRaises(mineru_api.MinerUError) as raised:
            mineru_api.parse_layout(self.path,None,http,account_binding=binding)
        self.assertEqual(raised.exception.diagnostics,{'account_failure':'owner_conflict'})
        self.assertEqual(http.calls,[])
    def test_later_chunk_pending_owner_is_preflighted_before_first_new_upload(self):
        with pymupdf.open(self.path) as pdf:
            pdf.new_page(width=600,height=800);pdf[1].insert_text((50,50),'distinct pending chunk');pdf.saveIncr()
        with pymupdf.open(self.path) as pdf,pymupdf.open() as chunk:
            chunk.insert_pdf(pdf,from_page=1,to_page=1);payload=chunk.tobytes(garbage=4,deflate=True,no_new_id=True)
        TaskState(self.cache,self.cache.key(payload),'fixture-legacy').write('retained-batch')
        http=FakeHttp(lambda count:fake_zip(page_count=count));http.chunk_pages=1;self.parse(http,page_limit=1)
        self.assertEqual(self.auth(http),['Bearer fixture-legacy']*3)
        self.assertEqual(sum(c[0]=='POST' for c in http.calls),1)
    def test_engine_shared_binding_reaches_initial_and_ocr_recovery(self):
        with pymupdf.open(self.path) as pdf:
            image=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,600,800),False)
            image.clear_with(220);pdf[0].insert_image(pdf[0].rect,pixmap=image);pdf.saveIncr()
        contexts=[]
        def parse(path,token,client,**kw):
            contexts.append(kw.get('account_binding'))
            raise mineru_api.MinerUError('MinerU task timed out')
        def missing(path,doc,token,client,**kw):
            contexts.append(kw.get('account_binding'));return []
        with patch.object(engine,'parse_layout',side_effect=parse),patch.object(engine,'_ocr_missing_pages',side_effect=missing):
            engine.detect(self.path,{11,13},account_pool=self.pool)
        self.assertGreaterEqual(len(contexts),2)
        self.assertIsNotNone(contexts[0]);self.assertTrue(all(x is contexts[0] for x in contexts))
    def test_owner_failure_persists_across_new_subsets_without_new_http(self):
        binding=mineru_api.MinerUTaskBinding(self.pool,self.identity)
        self.pending('removed-secret')
        with self.assertRaises(mineru_api.MinerUError):
            mineru_api.parse_layout(self.path,None,self.resumed(),account_binding=binding)
        with pymupdf.open(self.path) as pdf:pdf[0].insert_text((50,50),'new OCR subset');pdf.saveIncr()
        http=FakeHttp()
        with self.assertRaises(mineru_api.MinerUError) as raised:
            mineru_api.parse_layout(self.path,None,http,force_ocr=True,account_binding=binding)
        self.assertEqual(http.calls,[])
        self.assertEqual(raised.exception.diagnostics,{'account_failure':'owner_missing'})
    def test_engine_missing_owner_never_falls_back_to_another_ocr_account(self):
        with pymupdf.open(self.path) as pdf:
            image=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,600,800),False)
            image.clear_with(220);pdf[0].insert_image(pdf[0].rect,pixmap=image);pdf.saveIncr()
        with patch.object(engine,'parse_layout',side_effect=mineru_api.MinerUError(
                'MinerU PDF account ownership is unavailable',diagnostics={'account_failure':'owner_missing'})), \
                patch.object(engine,'_ocr_missing_pages') as missing:
            result=engine.detect(self.path,{11,13},account_pool=self.pool)
        missing.assert_not_called()
        self.assertEqual(result['rules']['13']['status'],'unsupported')
        self.assertEqual(result['rules']['13']['diagnostics'],{'account_failure':'owner_missing'})
    def env_pool(self,valid=True):
        poolpath=self.cache.folder.parent/'keys.json'
        poolpath.write_text(json.dumps({'format':'mineru-private-key-pool-v1','keys':['fixture-second','fixture-legacy']}) if valid else '{fixture-private-config')
        poolpath.chmod(0o600)
        for index in range(30):
            if self.pool.select_for_pdf(sha256(self.path.read_bytes()).hexdigest()).token=='fixture-second':break
            with pymupdf.open(self.path) as pdf:pdf[0].insert_text((50,50+index),'distinct routing identity '+str(index));pdf.saveIncr()
        self.assertEqual(self.pool.select_for_pdf(sha256(self.path.read_bytes()).hexdigest()).token,'fixture-second')
        return poolpath
    def test_cli_style_engine_call_honors_explicit_pool_environment(self):
        path=self.env_pool();http=FakeHttp()
        with patch.dict(os.environ,{'MINERU_ACCOUNT_POOL_FILE':str(path),'MINERU_LEGACY_TOKEN_FILE':''}):
            engine.detect(self.path,{13},token='fixture-legacy',http_client=http)
        self.assertEqual(self.auth(http),['Bearer fixture-second']*2)
    def test_cli_style_invalid_pool_fails_safe_before_http(self):
        path=self.env_pool(valid=False);http=FakeHttp()
        with patch.dict(os.environ,{'MINERU_ACCOUNT_POOL_FILE':str(path),'MINERU_LEGACY_TOKEN_FILE':''}):
            result=engine.detect(self.path,{13},token='fixture-legacy',http_client=http)
        self.assertEqual(http.calls,[])
        self.assertEqual(result['rules']['13']['status'],'unsupported')
        self.assertEqual(result['rules']['13']['diagnostics'],{'account_failure':'pool_invalid'})
        self.assertNotIn('fixture-private-config',json.dumps(result))
    def test_explicit_pool_argument_wins_over_environment_config(self):
        path=self.env_pool(valid=False);http=FakeHttp()
        with patch.dict(os.environ,{'MINERU_ACCOUNT_POOL_FILE':str(path)}):
            engine.detect(self.path,{13},token='fixture-legacy',http_client=http,account_pool=self.pool)
        self.assertEqual(self.auth(http),['Bearer fixture-second']*2)
    def test_account_failure_export_is_strict_and_safe(self):
        exc=mineru_api.MinerUError('MinerU pending account is unavailable',diagnostics={'account_failure':'owner_missing','account_id':'secret'})
        self.assertEqual(engine._mineru_error_record(exc)['diagnostics'],{'account_failure':'owner_missing'})
        exc.diagnostics['account_failure']='secret'
        self.assertNotIn('diagnostics',engine._mineru_error_record(exc))
if __name__=='__main__':unittest.main()
