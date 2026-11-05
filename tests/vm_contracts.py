"""Run with Python's standard library; no Spark service needed."""
import pathlib,sys,unittest,json,math
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'vm-kit'))
from records import normalize,tokens
from ranking import score
class Contracts(unittest.TestCase):
    def test_phase_versions_and_tombstones(self):
        delete=json.dumps({'doc_id':'1','op':'DELETE'})
        one=normalize(delete,1,{})
        self.assertTrue(one['ok']);self.assertEqual(one['record']['version'],2);self.assertTrue(one['record']['deleted'])
        self.assertEqual(one,normalize(delete,1,{}))
    def test_dirty_inputs(self):
        self.assertFalse(normalize('{broken',0,{})['ok'])
        self.assertFalse(normalize('{"doc_id":"1"}',0,{})['ok'])
        row={'doc_id':'1','title':'Title','url':'https://example.org','text':'hello'}
        parsed=normalize(json.dumps(row),0,{})
        self.assertEqual(parsed['record']['links'],[])
        row['version']=True;self.assertFalse(normalize(json.dumps(row),0,{})['ok'])
        row['version']=5;self.assertEqual(normalize(json.dumps(row),0,{})['record']['version'],5)
    def test_ranking_normalization_and_empty_query(self):
        docs={'a':{'doc_id':'a','length':3},'b':{'doc_id':'b','length':8},'c':{'doc_id':'c','length':1}}
        posts={'cat':{'a':2,'b':1}}
        ranks={'a':.1,'b':.2,'c':.7}
        result=score('cat',docs,posts,ranks,4,10)
        self.assertEqual(len(result),2)
        expected=math.log(1+(3-2+.5)/(2+.5))*4.4/(2+1.2*(.25+.75*3/4))
        a=next(x for x in result if x['doc_id']=='a')
        self.assertAlmostEqual(a['bm25'],expected)
        self.assertAlmostEqual(a['final_score'],.7+.3*.5)
        self.assertEqual(score('missing',docs,posts,ranks,4),[])
        self.assertEqual(score('!!!',docs,posts,ranks,4),[])
        self.assertEqual(score('cat cat',docs,posts,ranks,4),result)
        self.assertEqual(score('cat',docs,posts,ranks,4,1),result[:1])
if __name__=='__main__':unittest.main()
