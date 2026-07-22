# Morning charts — GitHub Actions

Generates `gold_chart.png`, `uranium_stocks.png`, `quantum_stocks.png` on a schedule and
commits them straight into this repo. Runs entirely on GitHub's servers, so it no longer
depends on your Mac being awake at 06:55.

## Why this replaces the local LaunchAgent

The local `~/Documents` LaunchAgent only fires if the Mac is awake at exactly the scheduled
minute — lid closed, sleeping, or powered off means a silent miss with no retry. GitHub
Actions runs on GitHub's own infrastructure on a fixed schedule regardless of your laptop's
state, which removes that single point of failure.

Separately: Cowork's sandbox has no general internet access (confirmed — Yahoo Finance,
stooq, and even generic CDNs all return connection-blocked errors), so charts can only ever
be *generated* on GitHub Actions or your Mac, never inside a Cowork session. But Cowork's
sandbox **can** run `git clone`/`git pull` against `github.com` — that's the one channel
that stays open. So the morning brief now pulls the finished PNGs out of this repo via git,
instead of reading them from your local `~/Documents` folder.

## One-time setup (~5 minutes)

1. Create a new **public** GitHub repository (public keeps `git clone` anonymous — no token
   needed on the Cowork side). Suggested name: `morning-charts`.
2. From this folder, push it:
   ```
   cd ~/Documents/morning-charts-github
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<your-username>/morning-charts.git
   git push -u origin main
   ```
3. On GitHub: **Settings → Actions → General → Workflow permissions** → select
   **"Read and write permissions"**, then Save. (Needed so the workflow's default
   `GITHUB_TOKEN` can push the updated PNGs back to the repo.)
4. Trigger the first run manually to confirm it works: **Actions tab → Update morning
   charts → Run workflow**. Check that `gold_chart.png` etc. appear/update in the repo a
   minute or two later.
5. Tell Laurent's Cowork assistant the repo URL once (e.g. `https://github.com/<your-username>/morning-charts`)
   so the morning brief scheduled task can be pointed at it.

After that, it runs unattended Mon–Fri at 04:30 UTC — no further action needed.

## Local LaunchAgent

You can leave the existing local LaunchAgent running as a backup (harmless — it just
overwrites the same filenames in `~/Documents`), or disable it now that this is authoritative:

```
launchctl unload ~/Library/LaunchAgents/com.laurent.morning-graph-update.plist
```

## Diagnosing a bad run

Check `status.json` in this repo (committed alongside the PNGs after every run) — it has
per-chart `ok` / `failed_no_data` status and any errors. Also check the Actions tab's run
log directly for anything the status file doesn't capture (e.g. the git push itself failing).
