# Always-on Cloud Hunter V10 — standalone VM (NOT GitHub Actions)

This is the **always-on scanning mode**. It has a continuously running Python
process on a Linux VM, taking bounded scan batches with a 5-minute cooldown.
It is *not* an exhaustive real-time index of every Meta ad, and it cannot
collect Meta-private ad set IDs, sales or spend.

## Not deployed yet

Source code and a systemd example are provided on a feature branch.
A real VM, Python/Chromium installation and a GitHub token are required.
Do not merge or disable the Actions fallback until this VM passes a real scan
and publishes a JSON result. This branch makes no change to the live schedule.

## Recommended VM

Ubuntu 24.04 on an always-on VM with at least 2 vCPU and 4 GB RAM. Oracle
Cloud Always Free A1 Flex can be eligible, but requires signup and has
capacity and idle-reclamation limitations. Always Free is not a guaranteed
24/7 service-level agreement. Choose **Always Free Eligible** and do not
enable billable resources accidentally.

## Installation outline (operator steps on VM)

1. Create a VM with an SSH key and SSH access. Never share SSH keys or
   GitHub access tokens in chat, source code or screenshots.
2. Install git, python3, python3-venv and python3-pip, clone:
   `git clone --branch feature/always-on-worker-v10 https://github.com/chienlolk49-sketch/Global-Product-Hunter-AI.git /opt/global-product-hunter`
   and clone upstream Sonda Imperial into `/opt/sonda-imperial`.
3. Create `/opt/global-product-hunter/.venv`; install
   `playwright>=1.44 rich>=13.0` and then `python -m playwright install --with-deps chromium`.
   Python package imports require `PYTHONPATH=/opt/sonda-imperial`.
4. Create `/etc/cloud-hunter/worker.env` (0600 permissions, owned by root)
   containing `GH_TOKEN=` plus a GitHub fine-grained token for *only*
   the product hunter repo with **Contents read/write** scope,
   `CLOUD_HUNTER_REPO=chienlolk49-sketch/Global-Product-Hunter-AI`,
   `CLOUD_HUNTER_BRANCH=main`,
   `CLOUD_HUNTER_COOLDOWN_SECONDS=300`, and
   `CLOUD_HUNTER_ROTATION_SECONDS=600`.
   Note: worker.py must exist on the VM even though it may not yet be
   on main. Do NOT merge/activate until test results are verified.
5. Copy `cloud_hunter/cloud-hunter.service` into
   `/etc/systemd/system/cloud-hunter.service`; run
   `sudo systemctl daemon-reload`, `sudo systemctl enable --now cloud-hunter`.
6. Observe `sudo journalctl -u cloud-hunter -n 100 --no-pager`.
   Inspect GitHub `cloud_hunter/data/status.json` for real scan
   timestamps and `cloud_hunter/data/top50.json` for grouped results.
7. Once VM scans and writes are verified, DISABLE the GitHub Actions
   15-minute schedule to avoid duplicate writers. Keep manual
   workflow dispatch only for emergencies.

## Safer test before enabling

`PYTHONPATH=/opt/sonda-imperial .venv/bin/python cloud_hunter/continuous_worker.py --check`

`PYTHONPATH=/opt/sonda-imperial .venv/bin/python cloud_hunter/continuous_worker.py --once --no-publish`

The two commands check local dependencies and do a single real sample scan
without writing to the GitHub repository. They do not require credentials.

## Current limits

- One bounded batch performs four searches and up to 30 results per search.
  The worker rests 300 seconds *after* a batch; actual start-to-start period
  is the scan duration plus 300 seconds. This is **continuous operation**
  with pauses, not endless HTTP requests.
- Running forever can attract rate limits or access restrictions; don't bypass
  authentication challenges, CAPTCHAs, technical access controls or provider
  terms. Use permitted APIs where available.
- The V9 ranking still requires **at least 21 distinct recently observed active
  ad IDs** associated with an approximate product key. Grouping may be
  imprecise and the Top 50 may remain empty.
- A token with write permissions is a sensitive secret. VM compromise exposes
  it; rotate it if compromised.
- A server outage, quota exhaustion, rate limits or hosting policy can interrupt
  cloud collection despite the auto-restart service.
