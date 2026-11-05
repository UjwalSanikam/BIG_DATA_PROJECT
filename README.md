# SearchLab — four-node project workspace

A Vercel-ready website for a four-person distributed search engine project. Each teammate claims a VM, runs one guided command at a time, compares expected output, saves screenshots/notes, and marks the step complete. Cross-node dependencies produce a red waiting state and unlock automatically after the prerequisite is confirmed.

## What is included

- 54 ordered checkpoints across setup, cluster startup, Phase 0, Phase 1 and resilience.
- Four VM workspaces, team overview, pipeline map, activity history, glossary and evidence report export.
- Server-enforced ownership and dependency checks; concurrent updates use database compare-and-swap.
- Shared screenshots (PNG/JPEG/WebP, at most 1 MB each, three per step) and terminal notes.
- Reopen a step and invalidate completed dependents across the team; evidence remains available.
- Private invitation links and per-seat recovery keys; room-owner configuration and seat recovery.
- A downloadable VM kit implementing Spark ingestion, Iceberg merges/snapshots, indexing, PageRank, Parquet export, safe activation, FastAPI and a basic search UI.
- The provided dataset's actual schema, dirty-record counts and missing-version policy are documented.

The dashboard coordinates humans. It does not SSH into VMs, execute shell commands, interpret screenshots, or certify the cluster automatically. The Vercel website is separate from Node 4's private search service.

## Local preview

Use Node.js 22 or newer. No npm dependencies are required.

```bash
node scripts/build.mjs
node scripts/dev.mjs
```

Open http://127.0.0.1:4173. The local server persists room state and screenshots under `.local/`. This is a real server-backed preview, but it binds only to this computer. It is not the production hosting solution.

## Deploy to Vercel with durable shared storage

1. Create a Supabase project in your own account. In its SQL editor, run the repository's `database.sql` once. Both tables have RLS enabled and no browser access policies; all access goes through the Vercel server API.
2. In Vercel, import `UjwalSanikam/BIG_DATA_PROJECT`. Use repository root, Framework Preset **Other**, build command `node scripts/build.mjs`, output directory `dist`, and Node.js 22 or 24. There are no install dependencies. `vercel.json` declares these build settings.
3. Add these **server-only** environment variables in Vercel:

   | Name | Value |
   | --- | --- |
   | `SUPABASE_URL` | Your Supabase project URL, e.g. `https://YOUR_PROJECT.supabase.co` |
   | `SUPABASE_SERVICE_ROLE_KEY` | The server service-role key from your project API settings |
   | `LAB_CREATE_KEY` | A long random private key you choose for creating workspaces |

   Never put the service-role key in frontend code, the Git repository, an invitation, or a screenshot. Do not set `LAB_LOCAL` in Vercel; the production code refuses to use local storage even if it is set.
4. Deploy. `/api/lab?action=health` should report `configured: true`; create a workspace to verify database connectivity. `configured` checks environment presence, not database migration status.
5. The creator enters the creation key, creates the team workspace, saves their private recovery file, and saves the network ID in Team settings. Add the four private IPs after all four VMs join ZeroTier, before completing their address-configuration steps. Share the **invitation link** with three teammates; do not share the owner recovery key.
6. Each person chooses a different node, saves their recovery key, and follows their workspace. Everyone receives updates every three seconds while the tab is visible. An offline connection disables completion until sync returns.

For a small class project, screenshot bytes are stored in a separate Postgres table to keep setup simple. This is bounded evidence storage, not a general file-sharing system. A larger deployment should move images to object storage and add account-based authentication, auditing and rate limits. Polling uses shared server data; localStorage stores only access credentials on each device, never the source of truth for progress.

## Put the dataset on Node 1

The supplied corpus is not committed to the public repository. Extract `phase-0/pages.jsonl` from the supplied ZIP, and copy `changes.json` as `changes.jsonl` to `~/searchlab/data/` on Node 1. Both files use JSON Lines. Use the provided main corpus for the final demonstration. See [vm-kit/README.md](vm-kit/README.md) for the exact normalization and version rules.

## Validation

```bash
node --test tests/*.test.mjs
python tests/vm_contracts.py
# Optional serving tests (requires pyarrow, fastapi and httpx):
python tests/serving_contracts.py
```

These checks cover the dependency graph, cross-node invalidation, seat ownership, concurrent shared updates, screenshot upload/retrieval, credential redaction, record validation, deletion/version handling, BM25 normalization, corrupted exports, activation and HTTP query behavior. The actual distributed pipeline must still be run on the four VMs; it has not been executed on this Windows development machine.

## Sources

- [Hadoop 3.3.6 cluster setup](https://hadoop.apache.org/docs/r3.3.6/hadoop-project-dist/hadoop-common/ClusterSetup.html)
- [Spark 3.5.3 standalone deployment](https://spark.apache.org/docs/3.5.3/spark-standalone.html)
- [Iceberg 1.7.2 Spark integration](https://iceberg.apache.org/docs/1.7.2/spark-getting-started/)
- [ZeroTier network setup](https://docs.zerotier.com/start/)
- [Vercel Node.js functions](https://vercel.com/docs/functions/runtimes/node-js)
- [Supabase API security](https://supabase.com/docs/guides/api/securing-your-api)
