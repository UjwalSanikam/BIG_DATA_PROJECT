# Put SearchLab online for your four teammates

**One person does steps 1–3. Everyone does step 4.** The dashboard does not require all four people to have a Vercel or Supabase account.

1. **Create the database.** Open [Supabase](https://supabase.com/dashboard), create a project, and save its database password privately. Once it is ready, open **SQL Editor → New query**. Copy all of [database.sql](https://github.com/UjwalSanikam/BIG_DATA_PROJECT/blob/main/database.sql), paste it there, and click **Run**. You should see success and two tables, `lab_rooms` and `lab_evidence`.
2. **Import the website.** Open [Vercel’s import page for this repository](https://vercel.com/new/import?s=https%3A%2F%2Fgithub.com%2FUjwalSanikam%2FBIG_DATA_PROJECT). Sign in to your own account. If asked, connect GitHub and choose `UjwalSanikam/BIG_DATA_PROJECT`. Leave the root directory at the repository root. The included configuration uses preset **Other**, build command `node scripts/build.mjs` and output directory `dist`.
3. **Enable shared progress.** In Vercel’s Environment Variables section, enter these server-side settings, then deploy. If the project has already deployed, add them under **Project settings → Environment Variables**, then **Redeploy** the production deployment.

   | Setting | Where to get its value |
   | --- | --- |
   | `SUPABASE_URL` | Supabase project → Connect / API settings → Project URL |
   | `SUPABASE_SERVICE_ROLE_KEY` | Supabase project → Settings → API keys → server secret key, or Legacy API keys → `service_role` |
   | `LAB_CREATE_KEY` | Generate a long random passphrase in your password manager. Only the room creator needs it. |

   Do not share the Supabase server key or database password with teammates or put them in screenshots. The website never asks teammates for those secrets.

4. **Create one shared workspace.** Open the production URL Vercel gives you. Enter the creation passphrase, create the workspace, and download the owner recovery file. Click **Invite team** and share that link with your three teammates. Each person claims a different node and saves their own recovery key. Each browser will see team changes within about three seconds.

## First session together

- Open **Team settings** and save the ZeroTier network ID. The four IP fields can stay empty until the devices join.
- Confirm your Ubuntu setup in each node's workspace. Nodes 1–3 need the same Python minor version, so choose the same Ubuntu release there. Use the same Linux username on all four VMs.
- Join and authorize all four ZeroTier devices. Add their four private IPs in Team settings. Confirm connectivity before installing and starting cluster services.
- Use **Download VM kit** and follow just your own active command. Compare actual output with **What success looks like**. Save a screenshot or terminal output for evidence checkpoints.
- A red screen identifies a dependency. Wait for that specific teammate to finish, then your screen unlocks automatically. The site records human confirmations; it does not run commands on your behalf.

## Dataset handoff to the Node 1 operator

Use the supplied `Node1-dataset.zip` from the delivery if available. It contains `data/pages.jsonl` and `data/changes.jsonl`. Download the VM kit first. In a terminal on your **laptop**, replace USER and NODE1_IP with the configured Linux username and actual ZeroTier IP:

```bash
scp Node1-dataset.zip USER@NODE1_IP:searchlab/Node1-dataset.zip
```

On **Node 1**, extract the files without changing their contents:

```bash
cd ~/searchlab
python3 -m zipfile -e Node1-dataset.zip .
python3 inspect_data.py data/pages.jsonl
python3 inspect_data.py data/changes.jsonl
```

If you use the instructor’s originals instead, extract `phase-0/pages.jsonl` from the base ZIP and put it in `~/searchlab/data/pages.jsonl`. Copy `changes.json` to `~/searchlab/data/changes.jsonl`; its contents already use JSON Lines.

The base has 1,000 active documents after validation and deduplication. The change set leaves 975. See [dataset-reference.json](public/dataset-reference.json) for independent local reference results, **not evidence of a four-VM run**. Your team should capture its own Spark UI, HDFS replication report, snapshots, search results, failed export test and recovery demonstration.

## If something goes wrong

- **Creation is disabled:** confirm all three environment variables are set in Production, then redeploy.
- **Storage request failed:** verify you ran `database.sql` in the correct Supabase project and used the server-only key, not the anon/publishable key.
- **A teammate sees a different room:** use the full **Invite team** link from the original room; do not create four separate workspaces.
- **Lost your seat:** restore your recovery file. If unavailable, the owner can release that seat without deleting its progress.
- **A step was marked done too soon:** open it and choose **Reopen step**. Dependent completions are cleared across the team. Screenshots stay; real VM commands are not undone.
- **Need the instructions before setup?** Open `/guide.html` on the deployed site for the read-only runbook, and `/setup.html` for the owner guide.
