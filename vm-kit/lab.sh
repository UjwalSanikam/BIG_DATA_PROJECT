#!/usr/bin/env bash
set -euo pipefail
source "$HOME/.searchlab-profile"
cd "$LAB_ROOT"
ACTION="${1:?Choose an action}"; PHASE="${2:-0}"
role(){ [[ "$NODE" == "$1" ]] || { echo "Run this command on Node $1, not Node $NODE"; exit 1; }; }
phase(){ [[ "$PHASE" =~ ^[01]$ ]] || { echo 'Phase must be 0 or 1'; exit 1; }; }
submit(){
  local IP="$N3"; [[ "$NODE" == 1 ]] && IP="$N1"
  "$SPARK_HOME/bin/spark-submit" --master "spark://$N3:7077" --deploy-mode client \
    --driver-memory 1g --executor-memory 1g --total-executor-cores 4 \
    --conf "spark.driver.host=$IP" --conf "spark.driver.bindAddress=$IP" \
    --conf spark.driver.port=39000 --conf spark.driver.blockManager.port=39001 \
    --conf spark.sql.shuffle.partitions=8 --conf spark.default.parallelism=8 \
    --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
    --conf spark.sql.catalog.lab=org.apache.iceberg.spark.SparkCatalog \
    --conf spark.sql.catalog.lab.type=hadoop \
    --conf "spark.sql.catalog.lab.warehouse=hdfs://$N2:9000/searchlab/warehouse" \
    --py-files "$LAB_ROOT/records.py" \
    --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.2 \
    "$LAB_ROOT/pipeline.py" "$@"
}
case "$ACTION" in
doctor)
  if [[ "$NODE" != 4 ]]; then java -version; hdfs version; "$SPARK_HOME/bin/spark-submit" --version; fi
  "$LAB_ROOT/venv/bin/python" -c 'import fastapi,pyarrow; print("Python environment OK")'
  echo DOCTOR_OK;;
storage-start)
  role 2
  if [[ ! -f "$LAB_ROOT/storage/name/current/VERSION" ]]; then
    [[ -z "$(ls -A "$LAB_ROOT/storage/name")" ]] || { echo 'Nonempty NameNode directory; refusing to format.'; exit 1; }
    hdfs namenode -format -nonInteractive
  fi
  hdfs --daemon start namenode; hdfs --daemon start datanode;;
datanode-start) role 3; hdfs --daemon start datanode;;
storage-check)
  role 2; REPORT="$(hdfs dfsadmin -report)"; printf '%s\n' "$REPORT"
  [[ "$REPORT" == *'Live datanodes (2)'* ]] || { echo 'Wait for exactly two live DataNodes.'; exit 1; }
  hdfs dfsadmin -safemode wait
  [[ "$(hdfs getconf -confKey dfs.replication)" == 2 ]] || exit 1
  hdfs dfs -mkdir -p /searchlab/input /searchlab/warehouse /searchlab/runs /searchlab/exports
  echo 'dfs.replication = 2'; echo STORAGE_OK;;
compute-start) role 3; "$SPARK_HOME/sbin/start-master.sh"; "$SPARK_HOME/sbin/start-worker.sh" "spark://$N3:7077";;
worker-start) role 2; "$SPARK_HOME/sbin/start-worker.sh" "spark://$N3:7077";;
worker-stop) role 2; "$SPARK_HOME/sbin/stop-worker.sh";;
smoke) role 3; submit smoke 0;;
upload)
  role 1; phase; FILE=pages.jsonl; [[ "$PHASE" == 1 ]] && FILE=changes.jsonl
  [[ -s "data/$FILE" ]] || { echo "Place the main dataset at $LAB_ROOT/data/$FILE"; exit 1; }
  DIGEST="$(cat "data/$FILE" schema.json | sha256sum | cut -d' ' -f1)"
  DEST="/searchlab/input/phase$PHASE/$DIGEST"
  hdfs dfs -mkdir -p "$DEST"
  hdfs dfs -put -f "data/$FILE" "$DEST/input.jsonl"
  hdfs dfs -put -f schema.json "$DEST/schema.json"
  hdfs dfs -setrep -w 2 "$DEST"
  printf '%s' "$DIGEST" > "data/phase$PHASE.digest"
  hdfs fsck "$DEST" -files -blocks -locations
  echo "UPLOAD_OK $DEST";;
ingest) role 1; phase; submit ingest "$PHASE" "$(cat "data/phase$PHASE.digest")";;
index|rank|export) role 3; phase; submit "$ACTION" "$PHASE";;
transfer)
  role 3; phase
  REMOTE="$(hdfs dfs -cat "/searchlab/runs/phase$PHASE/export.txt")"
  [[ "$REMOTE" =~ ^/searchlab/exports/[a-zA-Z0-9_-]+$ ]] || exit 1
  TMP="$(mktemp -d "$LAB_ROOT/transfer.XXXXXX")"
  hdfs dfs -get "$REMOTE" "$TMP/export"
  "$LAB_ROOT/venv/bin/python" serving.py package "$TMP/export" "$TMP/phase$PHASE.tar.gz"
  scp "$TMP/phase$PHASE.tar.gz" "$LAB_USER@$N4:searchlab/incoming/phase$PHASE.tar.gz"
  echo "TRANSFER_OK $TMP/phase$PHASE.tar.gz";;
serve) role 4; exec "$LAB_ROOT/venv/bin/uvicorn" search:app --host "$N4" --port 8000;;
activate) role 4; phase; "$LAB_ROOT/venv/bin/python" serving.py activate "incoming/phase$PHASE.tar.gz";;
rollback) role 4; phase; "$LAB_ROOT/venv/bin/python" serving.py rollback "$PHASE";;
reject-test) role 4; "$LAB_ROOT/venv/bin/python" serving.py reject-test;;
time-travel) role 3; submit time-travel 0;;
fault-job) role 3; submit fault-job 1;;
*) echo "Unknown action: $ACTION"; exit 1;;
esac
