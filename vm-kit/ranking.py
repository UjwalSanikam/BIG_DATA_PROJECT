"""Dependency-free BM25 scoring; all matching documents define the normalization maxima."""
import math
from collections import defaultdict
from records import tokens
def score(query, documents, postings, ranks, avgdl, limit=10):
    terms=set(tokens(query))
    if not terms or not documents or avgdl<=0:
        return []
    bm25=defaultdict(float)
    count=len(documents)
    for term in terms:
        hits=postings.get(term,{})
        df=len(hits)
        if not df:
            continue
        idf=math.log(1+(count-df+.5)/(df+.5))
        for doc_id,tf in hits.items():
            length=documents[doc_id]['length']
            bm25[doc_id]+=idf*(tf*2.2)/(tf+1.2*(.25+.75*length/avgdl))
    if not bm25:
        return []
    max_text=max(bm25.values())
    max_rank=max(ranks[doc_id] for doc_id in bm25)
    results=[]
    for doc_id,value in bm25.items():
        row=documents[doc_id]
        final=.7*(value/max_text if max_text else 0)+.3*(ranks[doc_id]/max_rank if max_rank else 0)
        results.append({**row,'bm25':value,'pagerank':ranks[doc_id],'final_score':final})
    return sorted(results,key=lambda x:(-x['final_score'],x['doc_id']))[:limit]
