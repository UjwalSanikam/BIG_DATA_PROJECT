# SearchLab VM kit

Run the commands in the shared dashboard in order. This kit is for four x86_64 Ubuntu 22.04/24.04 VMs, on a private ZeroTier network, with a separate local Linux username allowed on each VM. Recommended: 4 GB RAM and 20 GB free disk each; 8 GB RAM on Nodes 2 and 3. The classroom cluster has no Kerberos authentication: restrict access to your private team network.

## Roles

| Node | Daemons | Drivers |
| --- | --- | --- |
| 1 | None | Spark ingestion, client mode |
| 2 | HDFS NameNode + DataNode, Spark worker | None |
| 3 | HDFS DataNode, Spark master + worker | Index, PageRank, export, client mode |
| 4 | FastAPI + its search UI | None; reads local Parquet only |

## Get started

1. Download this archive from the dashboard. Transfer to each VM, then extract into `~/searchlab`.
2. Configure your ZeroTier network and authorize all four VMs.
3. Save the four IPs in the dashboard's Team settings.
4. Run the generated configuration block to write `~/searchlab.env` on each VM.
5. Run `bash setup.sh`, then follow that node's dashboard steps.

Do not run pipeline jobs at the same time as another pipeline job. The walkthrough serializes them, and each driver uses ports 39000/39001. Drivers must remain reachable until their jobs finish. Leave the Node 4 service running in its terminal and open another terminal for activation.

## Network

Permit communication between the four assigned ZeroTier IPs on the ZeroTier interface. Keep public cloud security groups closed to cluster ports. Relevant services: SSH 22, NameNode RPC 9000, NameNode UI 9870, DataNode transfer 9866 / IPC 9867 / UI 9864, Spark master 7077 / UI 8080, worker UI 8081, driver 39000/39001, Spark application UI 4040, FastAPI 8000. Spark workers/executors also use dynamically assigned ports; private host-to-host access is simplest for this classroom cluster. Do not disable the firewall globally.

## Exact input supplied for this project

Extract `pages.jsonl` from `phase-0-20261105T030549Z-1-001.zip` and put it at `~/searchlab/data/pages.jsonl` on Node 1. Copy `changes.json` to `~/searchlab/data/changes.jsonl`; it already contains one JSON object per line, so renaming is sufficient. Use the main corpus for the final run.

The inspected base file has 1,040 lines: 1,020 parseable records, 20 malformed JSON lines and 1,000 distinct document IDs. Twenty records are exact duplicates. Twenty distinct documents have no links field (40 records including duplicates). Missing links are normalized to `[]`.

The change file contains 100 records: 50 DELETE operations and 50 UPSERT operations (25 replacements and 25 new documents), leaving 975 active documents. Neither input provides versions. The explicit adapter policy assigns `version = phase + 1` when a record has no version. Provided integer versions, if present in another input, take precedence. This policy makes phase replay deterministic; it is not an inferred source timestamp. Same-ID/same-version different-payload conflicts are quarantined instead of chosen arbitrarily.

Required UPSERT fields: `doc_id`, `title`, `url`, `text`. Optional `links` is a list of document IDs. DELETE requires only `doc_id` and `op: "DELETE"`; it creates a versioned tombstone so old data cannot resurrect deleted documents. A tombstone is not exported or searchable.

## Pipeline contracts

- Input digest covers original bytes plus schema mapping. A committed phase cannot be reused with different input/schema. Replaying an identical phase returns its original snapshot and changed=0, including after a later phase.
- Iceberg `lab.search.pages` retains raw outlinks and tombstones. `lab.search.links` contains only valid source/destination pairs from active documents, with the source snapshot ID. Keeping raw outlinks allows later arrivals without losing historical information. The serving graph contains no missing or deleted target.
- Jobs read a pinned pages snapshot. Index and PageRank metadata must agree with that snapshot before export. This small corpus uses full distributed rebuilds after changes, not incremental index edits.
- Tokenization is lowercase ASCII alphanumeric tokens, consistently applied to title + text and queries. No stop-word removal or stemming. Text includes the original Wiki markup; the indexing policy is explicit.
- PageRank runs 10 iterations with damping 0.85, redistributes dangling mass, and validates rank sum ≈ 1. Checkpoints are stored in HDFS.
- BM25 uses k1=1.2, b=0.75 and IDF=ln(1+(N-df+0.5)/(df+0.5)). Query terms are deduplicated. Matching is OR. Normalize BM25 and PageRank over all matching documents before selecting top-k; ties break by document ID.
- Each export uses a unique directory. Its pointer is written only after validation and all three `_SUCCESS` markers. Transfer adds SHA-256 hashes and validates the downloaded files.
- Node 4 checks hashes, IDs, counts, positive term frequencies, length totals and rank mass before switching `active.json` with an atomic rename. The service loads the candidate into memory before swapping its in-memory reference. Failed reloads retain the last validated version. Old exports are retained.
- `rollback` demonstrates serving rollback. `time-travel` reads the old Iceberg snapshot without mutating the live table. These are deliberately distinct operations.

## Troubleshooting

`ACCESS_DENIED` in ZeroTier: the network owner must authorize the VM. `Connection refused`: check the target daemon, private IP and firewall. `ModuleNotFoundError: records`: use lab.sh, which ships records.py to Spark workers. `Python worker failed`: rerun the updated Step 5 on all nodes and verify `/opt/searchlab-python/bin/python --version` reports 3.11.18 on each. The shared symlink avoids differing home-directory paths; system Python versions may differ. `Incompatible clusterIDs`: do not reformat the NameNode; recover the original metadata and inspect the DataNode directories with your instructor.

Never format a populated NameNode, expire required snapshots, or overwrite the active serving folder. The setup script only initializes an empty local NameNode directory. It does not configure a cloud firewall, create VMs, or join ZeroTier automatically.

## Verification scope

The dashboard/backend and pure normalization/ranking/serving contracts are tested locally. The four-VM HDFS/Spark/Iceberg integration still must be executed and verified on your actual VMs. Runtime downloads, private-network reachability and available memory depend on those machines. Follow each checkpoint and save actual output.

## Installer 1.1 recovery

Refresh the VM kit before retrying Step 5. The installer uses pinned Python 3.11.18 from Astral’s python-build-standalone release and Temurin Java 11.0.33+10 directly from its official GitHub release, verified against SHA-256 digests. It no longer calls the Adoptium discovery API. Hadoop/Spark use pinned Apache SHA-512 digests. Interrupted downloads retry; an incomplete installation never counts as complete.

PyArrow installs from binary wheels only; it will not attempt a C++ build. Incompatible `venv` directories are renamed to `venv.previous-*`, not deleted. Dataset, HDFS storage and serving directories are preserved. `/usr/bin/python3` is never changed.

All Spark nodes use `/opt/searchlab-python/bin/python`, a symlink to that VM’s project virtualenv. Each node exports the shared HDFS application identity `searchlab`; the Linux accounts can differ. Apply this installer to all nodes before starting the cluster. If updating an already-running cluster, stop its daemons and check existing HDFS ownership before changing its application identity. Node 3 asks for Node 4’s actual SSH username during transfer.

Run setup as your normal user, not `sudo bash setup.sh`. Do not edit the script to insert your username or replace NODE with a username. `searchlab.env` accepts numeric NODE and four distinct private IPv4 addresses. Step 5 stops on the first failure and saves setup.log and doctor.log. Mark done only after DOCTOR_OK.
