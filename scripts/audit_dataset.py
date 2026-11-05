"""Independent, single-machine reference for the two supplied JSONL files.

Not a substitute for executing the distributed Spark/HDFS pipeline or collecting VM evidence.
"""
import collections, hashlib, json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vm-kit'))
from records import normalize,tokens
from ranking import score
def audit(files):
    state={};report={'kind':'Local reference computation; not distributed execution evidence','phases':[]}
    mapping=json.loads((ROOT/'vm-kit'/'schema.json').read_text())
    for phase,path in enumerate(files):
        path=pathlib.Path(path);rows=0;rejected=0;valid={};duplicates=0
        with path.open(encoding='utf-8') as f:
            for line in f:
                rows+=1
                result=normalize(line,phase,mapping)
                if not result['ok']:rejected+=1;continue
                item=result['record'];key=item['doc_id']
                if key in valid:
                    duplicates+=1
                    if item['version']==valid[key]['version'] and item['record_hash']!=valid[key]['record_hash']:raise ValueError('Ambiguous source version in reference input')
                    if item['version']<=valid[key]['version']:continue
                valid[key]=item
        changed=0
        for id,item in valid.items():
            if id not in state or item['version']>state[id]['version']:state[id]=item;changed+=1
        docs={id:r for id,r in state.items() if not r['deleted']};N=len(docs)
        graph={id:sorted({dst for dst in r['links'] if dst in docs and dst!=id}) for id,r in docs.items()}
        ranks={id:1/N for id in docs}
        for _ in range(10):
            dangling=sum(ranks[id] for id in docs if not graph[id]);updated={id:(1-.85)/N+.85*dangling/N for id in docs}
            for id,edges in graph.items():
                for dst in edges:updated[dst]+=.85*ranks[id]/len(edges)
            ranks=updated
        postings=collections.defaultdict(dict);meta={}
        for id,r in docs.items():
            terms=tokens(r['title']+' '+r['text']);meta[id]={'doc_id':id,'title':r['title'],'url':r['url'],'length':len(terms)}
            for term,tf in collections.Counter(terms).items():postings[term][id]=tf
        avgdl=sum(x['length'] for x in meta.values())/N
        result={'phase':phase,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'lines':rows,'rejected':rejected,'accepted_unique':len(valid),'duplicates':duplicates,'changed_first_run':changed,'active_documents':N,'valid_edges':sum(map(len,graph.values())),'postings':sum(map(len,postings.values())),'unique_terms':len(postings),'avgdl':avgdl,'rank_mass_after_10_iterations':sum(ranks.values()),'queries':{}}
        for q in ('beard','april'):
            result['queries'][q]=score(q,meta,postings,ranks,avgdl,5)
        report['phases'].append(result)
    return report
if __name__=='__main__':
    if len(sys.argv)!=4:raise SystemExit('Usage: python scripts/audit_dataset.py pages.jsonl changes.json output.json')
    report=audit(sys.argv[1:3]);pathlib.Path(sys.argv[3]).write_text(json.dumps(report,indent=2),encoding='utf-8')
    for p in report['phases']:print('REFERENCE',json.dumps({k:p[k] for k in ('phase','lines','rejected','active_documents','valid_edges','postings','avgdl','rank_mass_after_10_iterations')}))
