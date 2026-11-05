import pathlib, sys, tempfile, json, unittest, math, shutil
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'vm-kit'))
import pyarrow as pa
import pyarrow.parquet as pq
import serving
from fastapi.testclient import TestClient
import search
class ServingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parents[1]/'.local')
        self.root=pathlib.Path(self.temp.name)
        serving.SERVING=self.root/'serving';serving.SERVING.mkdir()
        search.SERVING=serving.SERVING;search.loaded=None;search.stamp=None
        self.client=TestClient(search.app)
    def tearDown(self):self.client.close();self.temp.cleanup()
    def bundle(self,version,phase=0):
        folder=self.root/version;folder.mkdir()
        rows={'documents':[dict(doc_id='a',title='Cats',url='https://example.org/a',snippet='cats',length=2),dict(doc_id='b',title='Dogs',url='https://example.org/b',snippet='dogs',length=2)],
              'postings':[dict(term='cat',doc_id='a',tf=2),dict(term='dog',doc_id='b',tf=2)],
              'ranks':[dict(doc_id='a',pagerank=.5),dict(doc_id='b',pagerank=.5)]}
        for name,data in rows.items():
            (folder/name).mkdir();pq.write_table(pa.Table.from_pylist(data),folder/name/'part.parquet');(folder/name/'_SUCCESS').touch()
        manifest=dict(status='complete',version=version,phase=phase,snapshot_id=100+phase,documents=2,postings=2,avgdl=2,iterations=10,damping=.85,k1=1.2,b=.75)
        (folder/'manifest.json').write_text(json.dumps(manifest))
        archive=self.root/(version+'.tar.gz');serving.package(folder,archive)
        return folder,archive
    def test_activate_query_rollback_and_bad_candidate(self):
        self.assertEqual(self.client.get('/health').status_code,503)
        first,a0=self.bundle('phase0-test');serving.activate(a0)
        self.assertEqual(self.client.get('/health').json()['version'],'phase0-test')
        response=self.client.get('/search',params={'q':'cat'}).json()
        self.assertEqual(response['results'][0]['doc_id'],'a')
        self.assertAlmostEqual(response['results'][0]['final_score'],1)
        self.assertEqual(self.client.get('/search',params={'q':'absent'}).json()['results'],[])
        self.assertEqual(self.client.get('/search',params={'q':'cat','limit':100}).status_code,422)
        second,a1=self.bundle('phase1-test',1);serving.activate(a1)
        self.assertEqual(self.client.get('/health').json()['snapshot_id'],101)
        serving.rollback(0);self.assertEqual(self.client.get('/health').json()['version'],'phase0-test')
        serving.rollback(1);serving.reject_test()
        self.assertEqual(self.client.get('/health').json()['version'],'phase1-test')
        before=(serving.SERVING/'active.json').read_bytes()
        with (second/'documents'/'part.parquet').open('ab') as f:f.write(b'bad')
        with self.assertRaises(ValueError):serving.load_export(second)
        self.assertEqual((serving.SERVING/'active.json').read_bytes(),before)
        # A broken externally-written pointer cannot evict the in-memory validated version.
        serving.atomic_json(serving.SERVING/'active.json',{'version':'missing-version'})
        health=self.client.get('/health').json()
        self.assertEqual(health['version'],'phase1-test');self.assertTrue(health['warning'])
    def test_traversal_and_manifest_settings(self):
        for name in ('../escape','a/b','',None):
            with self.assertRaises(ValueError):serving.safe_version(name)
        folder,_=self.bundle('settings-test')
        manifest=json.loads((folder/'manifest.json').read_text());manifest['iterations']=2
        (folder/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):serving.load_export(folder,check_hashes=False)
if __name__=='__main__':unittest.main()
