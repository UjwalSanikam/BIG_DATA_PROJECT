#!/usr/bin/env bash
set -euo pipefail
source "$HOME/searchlab.env"
[[ "$(uname -m)" == x86_64 ]] || { echo 'This kit requires x86_64 Ubuntu.'; exit 1; }
[[ "$NODE" =~ ^[1-4]$ ]] || exit 1
[[ "$(id -un)" == "$LAB_USER" ]] || { echo 'Use the same configured Linux username on all four VMs.'; exit 1; }
ROOT="$HOME/searchlab"
cd "$ROOT"
sudo apt-get update
sudo apt-get install -y curl python3 python3-venv openssh-server iputils-ping
sudo systemctl enable --now ssh
python3 -m venv "$ROOT/venv"
"$ROOT/venv/bin/pip" install 'fastapi==0.115.6' 'uvicorn==0.34.0' 'pyarrow==18.1.0'
mkdir -p data incoming serving runtime
cat > "$HOME/.searchlab-profile" <<EOF
source "\$HOME/searchlab.env"
export LAB_ROOT="\$HOME/searchlab"
export JAVA_HOME="\$LAB_ROOT/runtime/java"
export HADOOP_HOME="\$LAB_ROOT/runtime/hadoop"
export HADOOP_CONF_DIR="\$HADOOP_HOME/etc/hadoop"
export SPARK_HOME="\$LAB_ROOT/runtime/spark"
export PYSPARK_PYTHON="\$LAB_ROOT/venv/bin/python"
export PYSPARK_DRIVER_PYTHON="\$LAB_ROOT/venv/bin/python"
export PATH="\$JAVA_HOME/bin:\$HADOOP_HOME/bin:\$SPARK_HOME/bin:\$PATH"
export HADOOP_USER_NAME="$LAB_USER"
EOF
if [[ "$NODE" != 4 ]]; then
  python3 download_runtime.py
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
export PYSPARK_PYTHON="$ROOT/venv/bin/python"
export PYSPARK_DRIVER_PYTHON="$ROOT/venv/bin/python"
EOF
fi
echo SETUP_OK
