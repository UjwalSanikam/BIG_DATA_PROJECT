#!/usr/bin/env bash
set -Eeuo pipefail
STAGE='configuration checks'
trap 'code=$?; printf "\nSETUP_FAILED during %s (line %s, exit %s). Stop here; do not mark Step 5 done.\n" "$STAGE" "$LINENO" "$code" >&2; exit "$code"' ERR
[[ "$EUID" != 0 ]] || { echo 'Run bash setup.sh as your normal VM user, without sudo.'; exit 1; }
[[ "$(uname -m)" == x86_64 ]] || { echo 'This kit requires x86_64 Ubuntu.'; exit 1; }
ROOT="$HOME/searchlab"
cd "$ROOT"
python3 preflight.py "$HOME/searchlab.env"
source "$HOME/searchlab.env"
echo "Installing for Node $NODE as local user $(id -un). Different VM usernames are supported."
STAGE='Ubuntu packages'
sudo apt-get update
sudo apt-get install -y ca-certificates curl python3 openssh-server iputils-ping tar
sudo systemctl enable --now ssh
STAGE='isolated Python 3.11.18'
python3 prepare_python.py
STAGE='Python binary packages'
"$ROOT/venv/bin/python" -m pip install --only-binary=:all: --retries 3 --timeout 60 -r requirements.txt
# Spark sends this identical interpreter path to both worker hosts, even when
# their home directories/usernames differ. Do not replace an unrelated path.
if [[ -e /opt/searchlab-python || -L /opt/searchlab-python ]]; then
  [[ -L /opt/searchlab-python && "$(readlink /opt/searchlab-python)" == "$ROOT/venv" ]] || { echo '/opt/searchlab-python already belongs to another installation. Stop and check its owner before changing it.'; exit 1; }
else
  sudo ln -s "$ROOT/venv" /opt/searchlab-python
fi
mkdir -p data incoming serving runtime
if [[ "$NODE" != 4 ]]; then
  STAGE='Java, Hadoop and Spark downloads'
  "$ROOT/venv/bin/python" download_runtime.py
fi
STAGE='local service configuration'
cat > "$HOME/.searchlab-profile" <<EOF
source "\$HOME/searchlab.env"
export LAB_ROOT="\$HOME/searchlab"
export JAVA_HOME="\$LAB_ROOT/runtime/java"
export HADOOP_HOME="\$LAB_ROOT/runtime/hadoop"
export HADOOP_CONF_DIR="\$HADOOP_HOME/etc/hadoop"
export SPARK_HOME="\$LAB_ROOT/runtime/spark"
export PYSPARK_PYTHON="/opt/searchlab-python/bin/python"
export PYSPARK_DRIVER_PYTHON="\$LAB_ROOT/venv/bin/python"
export PATH="\$JAVA_HOME/bin:\$HADOOP_HOME/bin:\$SPARK_HOME/bin:\$PATH"
export HADOOP_USER_NAME="searchlab"
EOF
if [[ "$NODE" != 4 ]]; then
  source "$HOME/.searchlab-profile"
  mkdir -p "$ROOT/storage/name" "$ROOT/storage/data"
  cat > "$HADOOP_CONF_DIR/core-site.xml" <<EOF
<configuration><property><name>fs.defaultFS</name><value>hdfs://$N2:9000</value></property></configuration>
EOF
  cat > "$HADOOP_CONF_DIR/hdfs-site.xml" <<EOF
<configuration>
<property><name>dfs.replication</name><value>2</value></property>
<property><name>dfs.namenode.name.dir</name><value>file://$ROOT/storage/name</value></property>
<property><name>dfs.datanode.data.dir</name><value>file://$ROOT/storage/data</value></property>
<property><name>dfs.namenode.rpc-address</name><value>$N2:9000</value></property>
<property><name>dfs.namenode.http-address</name><value>$N2:9870</value></property>
<property><name>dfs.namenode.datanode.registration.ip-hostname-check</name><value>false</value></property>
<property><name>dfs.permissions.enabled</name><value>true</value></property>
</configuration>
EOF
  printf '\nexport JAVA_HOME="%s"\n' "$JAVA_HOME" >> "$HADOOP_CONF_DIR/hadoop-env.sh"
  case "$NODE" in 1) MY_IP="$N1";; 2) MY_IP="$N2";; 3) MY_IP="$N3";; esac
  cat > "$SPARK_HOME/conf/spark-env.sh" <<EOF
export JAVA_HOME="$JAVA_HOME"
export HADOOP_CONF_DIR="$HADOOP_CONF_DIR"
export SPARK_LOCAL_IP="$MY_IP"
export SPARK_MASTER_HOST="$N3"
export SPARK_WORKER_HOST="$MY_IP"
export SPARK_WORKER_CORES=2
export SPARK_WORKER_MEMORY=2g
export PYSPARK_PYTHON="/opt/searchlab-python/bin/python"
export PYSPARK_DRIVER_PYTHON="$ROOT/venv/bin/python"
EOF
fi
echo 'SETUP_OK · installer 1.1 · project Python 3.11.18'
