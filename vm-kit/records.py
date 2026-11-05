"""Pure record normalization shared by Spark and local contract checks."""
import json, hashlib, re
from urllib.parse import urlsplit
def normalize(line, phase, mapping):
    try:
        x = json.loads(line)
        if not isinstance(x, dict):
            raise ValueError('record is not an object')
        def field(name, default=None):
            return x.get(mapping.get(name, name), default)
        doc = field('doc_id')
        if not isinstance(doc, (str, int)) or isinstance(doc, bool) or not str(doc).strip():
            raise ValueError('missing or invalid doc_id')
        op = field('op', 'UPSERT')
        if op not in ('UPSERT', 'DELETE'):
            raise ValueError('invalid op')
        version = field('version', int(phase) + 1)
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError('invalid version')
        if op == 'DELETE':
            title = url = text = ''; links = []
        else:
            title, url, text = (field(k) for k in ('title','url','text'))
            if any(not isinstance(v, str) or not v.strip() for v in (title,url,text)):
                raise ValueError('missing required title, url or text')
            parsed = urlsplit(url)
            if parsed.scheme not in ('http','https') or not parsed.netloc:
                raise ValueError('invalid URL')
            links = field('links', [])
            if not isinstance(links, list) or any(not isinstance(v, (str,int)) or isinstance(v,bool) for v in links):
                raise ValueError('links must be a list of document IDs')
            links = sorted(set(str(v) for v in links if str(v).strip()))
        record = dict(doc_id=str(doc),version=version,title=title,url=url,text=text,links=links,deleted=op=='DELETE')
        record['record_hash'] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        return dict(ok=True, record=record, reason='', raw=line)
    except (ValueError, TypeError, KeyError) as e:
        return dict(ok=False, record=None, reason=str(e), raw=line)
def tokens(text):
    return re.findall(r'[a-z0-9]+', text.lower())
