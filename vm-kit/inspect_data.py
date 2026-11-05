import json, sys, collections
path = sys.argv[1]
fields, ops, ids = collections.Counter(), collections.Counter(), collections.Counter()
bad = missing_links = missing_version = total = 0
sample = None
with open(path, encoding='utf-8') as f:
    for line in f:
        total += 1
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('not an object')
            fields.update({k + ':' + type(v).__name__: 1 for k, v in row.items()})
            ops[row.get('op', 'UPSERT')] += 1
            ids[str(row.get('doc_id'))] += 1
            missing_links += 'links' not in row
            missing_version += 'version' not in row
            if sample is None:
                sample = {k: v[:160] if isinstance(v, str) else v for k, v in row.items()}
        except (ValueError, TypeError):
            bad += 1
print(json.dumps(dict(lines=total, malformed=bad, distinct_ids=len(ids), duplicate_records=sum(v-1 for v in ids.values()), missing_links=missing_links, missing_version=missing_version, operations=dict(ops), fields=dict(fields), sample=sample), indent=2))
print('SCHEMA_REVIEW: verify the field mapping. Missing versions use phase+1; missing links use [].')
