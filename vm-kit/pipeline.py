"""Distributed HDFS + Iceberg pipeline. Run through lab.sh on the assigned VM."""
import json, math, sys, time, uuid
from pyspark.sql import SparkSession, functions as F, types as T, Window
from records import normalize, tokens

action, phase = sys.argv[1], int(sys.argv[2])
assert phase in (0, 1)
spark = SparkSession.builder.appName(f'SearchLab-{action}-phase{phase}').getOrCreate()
spark.sparkContext.setLogLevel('WARN')
sc = spark.sparkContext
sc.setCheckpointDir('/searchlab/checkpoints')
fs = sc._jvm.org.apache.hadoop.fs.FileSystem.get(sc._jsc.hadoopConfiguration())
Path = sc._jvm.org.apache.hadoop.fs.Path
base = f'/searchlab/runs/phase{phase}'
TABLE = 'lab.search.pages'

def exists(path):
    return fs.exists(Path(path))

def read_text(path):
    stream = fs.open(Path(path))
    try:
        return sc._jvm.org.apache.commons.io.IOUtils.toString(stream, 'UTF-8')
    finally:
        stream.close()

def write_text(path, text):
    # Only publish the small pointer after all prior writes/validation completed.
    fs.mkdirs(Path(path.rsplit('/', 1)[0]))
    temp = path + '.tmp-' + uuid.uuid4().hex
    stream = fs.create(Path(temp), False)
    try:
        stream.write(bytearray(text.encode('utf-8')))
    finally:
        stream.close()
    context = sc._jvm.org.apache.hadoop.fs.FileContext.getFileContext(sc._jsc.hadoopConfiguration())
    options = sc._gateway.new_array(sc._jvm.org.apache.hadoop.fs.Options.Rename, 1)
    options[0] = sc._jvm.org.apache.hadoop.fs.Options.Rename.OVERWRITE
    context.rename(Path(temp), Path(path), options)

def write_json(path, obj):
    write_text(path, json.dumps(obj, sort_keys=True))

def current_snapshot():
    row = spark.table(TABLE + '.snapshots').orderBy(F.desc('committed_at')).first()
    assert row is not None, 'No committed Iceberg snapshot'
    return int(row.snapshot_id)

def source():
    return json.loads(read_text(base + '/source.json'))

def documents():
    pin = source()
    return spark.read.option('snapshot-id', str(pin['snapshot_id'])).table(TABLE).where(~F.col('deleted'))

def graph(docs):
    ids = docs.select(F.col('doc_id').alias('dst'))
    return (docs.select(F.col('doc_id').alias('src'), F.explode('links').alias('dst'))
            .join(ids, 'dst', 'inner').where(F.col('src') != F.col('dst'))
            .select('src', 'dst').distinct())

record_schema = T.StructType([
    T.StructField('doc_id', T.StringType(), False), T.StructField('version', T.LongType(), False),
    T.StructField('title', T.StringType(), False), T.StructField('url', T.StringType(), False),
    T.StructField('text', T.StringType(), False), T.StructField('links', T.ArrayType(T.StringType()), False),
    T.StructField('deleted', T.BooleanType(), False), T.StructField('record_hash', T.StringType(), False)])

def ingest():
    digest = sys.argv[3]
    assert len(digest) == 64 and all(c in '0123456789abcdef' for c in digest)
    if exists(base + '/source.json'):
        old = source()
        assert old['input_digest'] == digest, 'Phase already committed with different input/schema. Use a new run, never overwrite a phase.'
        print('INGEST_OK', json.dumps({**old, 'changed': 0, 'replay': True}), flush=True)
        return
    if phase == 1:
        assert exists('/searchlab/runs/phase0/source.json'), 'Phase 0 must be committed first'
    input_dir = f'/searchlab/input/phase{phase}/{digest}'
    mapping = json.loads(read_text(input_dir + '/schema.json'))
    parsed = sc.textFile(input_dir + '/input.jsonl', minPartitions=8).map(lambda line: normalize(line, phase, mapping)).cache()
    invalid = parsed.filter(lambda r: not r['ok']).map(lambda r: (r['reason'], r['raw']))
    rejects = spark.createDataFrame(invalid, 'reason string, raw string')
    valid = spark.createDataFrame(parsed.filter(lambda r: r['ok']).map(lambda r: r['record']), record_schema).cache()
    conflicts = valid.groupBy('doc_id','version').agg(F.countDistinct('record_hash').alias('hashes')).where('hashes > 1').select('doc_id','version')
    ambiguous = valid.join(conflicts, ['doc_id','version']).select(F.lit('conflicting payloads at the same version').alias('reason'), F.to_json(F.struct(*valid.columns)).alias('raw'))
    rejects = rejects.unionByName(ambiguous)
    clean = valid.join(conflicts, ['doc_id','version'], 'left_anti')
    window = Window.partitionBy('doc_id').orderBy(F.desc('version'), 'record_hash')
    incoming = clean.withColumn('_n', F.row_number().over(window)).where('_n = 1').drop('_n').cache()
    accepted = incoming.count()
    assert accepted > 0, 'Zero accepted records: check field mapping and rejection reasons'
    spark.sql('CREATE NAMESPACE IF NOT EXISTS lab.search')
    if not spark.catalog.tableExists(TABLE):
        spark.createDataFrame([], record_schema).writeTo(TABLE).tableProperty('format-version','2').create()
    old = spark.table(TABLE).select('doc_id', F.col('version').alias('old_version'), F.col('record_hash').alias('old_hash'))
    joined = incoming.join(old, 'doc_id', 'left')
    collisions = joined.where((F.col('version') == F.col('old_version')) & (F.col('record_hash') != F.col('old_hash')))
    collision_rejects = collisions.select(F.lit('existing version has a different payload').alias('reason'), F.to_json(F.struct(*incoming.columns)).alias('raw'))
    rejects = rejects.unionByName(collision_rejects)
    rejected = rejects.count()
    rejects.write.mode('overwrite').json(base + '/rejects')
    updates = joined.where(F.col('old_version').isNull() | (F.col('version') > F.col('old_version'))).select(*incoming.columns).cache()
    changed = updates.count()
    if changed:
        updates.createOrReplaceTempView('incoming_changes')
        spark.sql(f'''MERGE INTO {TABLE} t USING incoming_changes s ON t.doc_id = s.doc_id
          WHEN MATCHED AND s.version > t.version THEN UPDATE SET *
          WHEN NOT MATCHED THEN INSERT *''')
    snapshot = current_snapshot()
    active = spark.read.option('snapshot-id', str(snapshot)).table(TABLE).where(~F.col('deleted')).cache()
    assert active.count() > 0, 'No active documents remain'
    edges = graph(active).withColumn('source_snapshot', F.lit(snapshot))
    # Raw outlinks stay on pages to support later arrivals; this Iceberg table is the validated graph.
    edges.writeTo('lab.search.links').createOrReplace()
    result = dict(phase=phase, snapshot_id=snapshot, input_digest=digest, accepted=accepted,
                  rejected=rejected, changed=changed, active_documents=active.count(), valid_edges=edges.count())
    write_json(base + '/source.json', result)
    print('INGEST_OK', json.dumps(result), flush=True)

def index():
    docs = documents().cache()
    tokenize = F.udf(tokens, T.ArrayType(T.StringType()))
    indexed = docs.withColumn('tokens', tokenize(F.concat_ws(' ', 'title','text')))
    meta = indexed.select('doc_id','title','url',F.substring('text',1,320).alias('snippet'),F.size('tokens').alias('length'))
    postings = indexed.select('doc_id',F.explode('tokens').alias('term')).groupBy('term','doc_id').agg(F.count('*').alias('tf'))
    assert meta.count() > 0 and postings.count() > 0
    dest = base + '/index-' + uuid.uuid4().hex
    meta.write.parquet(dest + '/documents')
    postings.write.parquet(dest + '/postings')
    write_json(base + '/index.json', {'path':dest,'snapshot_id':source()['snapshot_id']})
    print('INDEX_OK', json.dumps(dict(documents=meta.count(),postings=postings.count(),snapshot_id=source()['snapshot_id'])), flush=True)

def rank():
    docs = documents().select('doc_id','links').cache()
    count = docs.count(); assert count > 0
    ids = docs.select('doc_id').cache()
    edges = graph(docs).cache()
    degree = edges.groupBy('src').count().withColumnRenamed('count','degree').cache()
    ranks = ids.withColumn('pagerank',F.lit(1.0/count)).cache()
    for iteration in range(10):
        dangling = ranks.join(degree, ranks.doc_id == degree.src, 'left_anti').agg(F.sum('pagerank')).first()[0] or 0.0
        sent = edges.join(degree,'src').join(ranks, edges.src == ranks.doc_id).select(F.col('dst').alias('doc_id'), (F.col('pagerank')/F.col('degree')).alias('contribution')).groupBy('doc_id').agg(F.sum('contribution').alias('contribution'))
        updated = ids.join(sent,'doc_id','left').fillna({'contribution':0.0}).select('doc_id', (F.lit((1-.85)/count+.85*dangling/count)+.85*F.col('contribution')).alias('pagerank')).checkpoint(eager=True)
        ranks.unpersist(); ranks=updated
        mass = ranks.agg(F.sum('pagerank')).first()[0]
        assert math.isfinite(mass) and abs(mass-1)<1e-6
        print(f'Iteration {iteration+1}/10 rank_mass={mass:.10f}',flush=True)
    dest = base + '/rank-' + uuid.uuid4().hex
    ranks.write.parquet(dest)
    write_json(base + '/rank.json',{'path':dest,'snapshot_id':source()['snapshot_id'],'iterations':10,'damping':.85})
    print('PAGERANK_OK', flush=True)

def export():
    pin = source(); idx = json.loads(read_text(base+'/index.json')); pr = json.loads(read_text(base+'/rank.json'))
    assert idx['snapshot_id']==pr['snapshot_id']==pin['snapshot_id'], 'Mixed source snapshots'
    docs=spark.read.parquet(idx['path']+'/documents'); postings=spark.read.parquet(idx['path']+'/postings'); ranks=spark.read.parquet(pr['path'])
    count=docs.count(); assert count>0 and docs.select('doc_id').distinct().count()==count
    assert ranks.count()==count and ranks.select('doc_id').distinct().count()==count
    assert not ranks.join(docs,'doc_id','left_anti').take(1)
    assert not postings.join(docs,'doc_id','left_anti').take(1)
    assert not ranks.where(F.isnan('pagerank') | (F.col('pagerank')<0) | F.col('pagerank').isNull()).take(1)
    mass = ranks.agg(F.sum('pagerank')).first()[0]; assert math.isfinite(mass) and abs(mass-1)<1e-6
    assert not postings.where('tf <= 0').take(1)
    assert postings.select('term','doc_id').distinct().count()==postings.count()
    version=f'phase{phase}-s{pin["snapshot_id"]}-{uuid.uuid4().hex[:8]}'
    path='/searchlab/exports/'+version
    docs.write.parquet(path+'/documents');postings.write.parquet(path+'/postings');ranks.write.parquet(path+'/ranks')
    for dataset in ('documents','postings','ranks'):
        assert exists(path+'/'+dataset+'/_SUCCESS')
    manifest=dict(status='complete',version=version,phase=phase,snapshot_id=pin['snapshot_id'],documents=count,
                  postings=postings.count(),avgdl=docs.agg(F.avg('length')).first()[0],iterations=pr['iterations'],damping=.85,k1=1.2,b=.75)
    write_json(path+'/manifest.json',manifest)
    write_text(base+'/export.txt',path)
    print('EXPORT_OK',path,json.dumps(manifest),flush=True)

if action=='ingest': ingest()
elif action=='index': index()
elif action=='rank': rank()
elif action=='export': export()
elif action=='smoke':
    import random
    inside=sc.parallelize(range(200000),8).map(lambda _: int(random.random()**2+random.random()**2<1)).sum()
    print('Pi is roughly',4*inside/200000,flush=True)
elif action=='time-travel':
    old=json.loads(read_text('/searchlab/runs/phase0/source.json'))['snapshot_id']
    old_count=spark.read.option('snapshot-id',str(old)).table(TABLE).where(~F.col('deleted')).count()
    new=current_snapshot(); current=spark.table(TABLE).where(~F.col('deleted')).count()
    print('TIME_TRAVEL_OK',json.dumps(dict(phase0_snapshot=old,phase0_documents=old_count,current_snapshot=new,current_documents=current)),flush=True)
    # Demonstrate table recovery on an isolated one-row copy, never on the live corpus.
    demo='recovery_'+uuid.uuid4().hex[:12]
    target='lab.search.'+demo
    spark.table(TABLE).where(~F.col('deleted')).limit(1).writeTo(target).tableProperty('format-version','2').create()
    good=spark.table(target+'.snapshots').orderBy(F.desc('committed_at')).first().snapshot_id
    original=spark.table(target).first().title
    spark.sql(f"UPDATE {target} SET title = '__INTENTIONALLY_BAD_TITLE__'")
    assert spark.table(target).first().title=='__INTENTIONALLY_BAD_TITLE__'
    spark.sql(f"CALL lab.system.rollback_to_snapshot('search.{demo}', {good}L)")
    assert spark.table(target).first().title==original
    assert current_snapshot()==new, 'Live pages snapshot should not change during this isolated drill'
    print('ICEBERG_RECOVERY_OK',target,'restored_snapshot',good,flush=True)
elif action=='fault-job':
    from concurrent.futures import ThreadPoolExecutor
    def slow_partition(rows):
        import time
        time.sleep(35)
        yield sum(rows)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(lambda: sc.parallelize(range(3200),32).mapPartitions(slow_partition).sum())
        while not future.done():
            tracker=sc.statusTracker()
            running=[tracker.getStageInfo(stage) for stage in tracker.getActiveStageIds()]
            if any(info and info.numActiveTasks>0 for info in running):
                print('READY_TO_STOP: tasks are running. Ask Node 2 to stop its Spark worker now.',flush=True)
                break
            time.sleep(1)
        result=future.result()
    assert result==sum(range(3200))
    print('FAULT_JOB_OK',result,flush=True)
else: raise ValueError('Unknown action '+action)
spark.stop()
