# Cloud Hunter pilot (separate from Sonda Imperial V7.1)

This directory is a **small cloud proof-of-concept**, not a ready production deployment.
The existing React/ProdIntel app on `main` is left unchanged.

## What it does

- GitHub Actions attempts a bounded scan at **00:17, 06:17, 12:17 and 18:17 UTC**
  (07:17, 13:17, 19:17 and 01:17 Vietnam time, next calendar day for 01:17).
- On every run, it rotates through a limited set of **keywords** and **10 countries**
  (US, GB, DE, FR, BR, VN, JP, AU, CA, KR).
- **Cambodia (KH), Malaysia (MY), Philippines (PH), Thailand (TH)** are excluded
  from source search. Pet products are filtered out.
- Deduplicates by Meta ad ID. Produces top 50 **per category** based on observed
  unique ads; groups are *approximate*, normalized ad-title matching, not SKU matching.
- Preserves previous observations (up to 1,000 ads / last 35 days), stores diagnostic
  status and outputs JSON in `cloud_hunter/data`.

## IMPORTANT limitations

- The upstream scraper relies on Meta's changing public ad library pages.
  Running on GitHub-hosted IPs may be blocked or may return **zero ads**.
  The first real run is essential to verify this.
- The scheduled workflow runs **only when present on the default branch**.
  This pilot branch is NOT scheduled to run every 6 hours until merged.
  Its branch `push` event is only a smoke test.
- GitHub may delay or drop scheduled jobs. Free public repo actions are
  subject to GitHub policies and fair-use restrictions.
- Not a complete worldwide scan. Terms and regions are deliberately limited.
- Link to a landing page is *not* proof of a valid purchasable product.
  Advertisement count is *not* sales, ad budget, video views or popularity.
- Video links provided by Meta can expire and may be unavailable.
- Public repositories expose the collected data and ad metadata to everyone.
- A cloud JSON dataset is **not yet connected to the Windows Sonda Imperial UI**.
  That requires a further Windows-side read-only sync adapter.
- Don't store Meta session cookies, account credentials, tokens, or personal data
  in this repository.

## Files

- `scan.py` bounded scanner with conservative ad-ID dedup and ranked categories.
- `data/ads.json` observed ad records after a successful run.
- `data/top50.json` ranked product name groups by category.
- `data/status.json` success/error counts and timestamps.
- `../.github/workflows/cloud-hunter.yml` automation definition.

## Verification / rollout

1. Open GitHub > Actions > Cloud Hunter pilot. Check the pilot push test.
2. Inspect `data/status.json` and `data/top50.json` **on the pilot branch**.
3. Only after genuine data collection and valid grouping are verified, merge the
   PR into `main` to enable the actual schedule.
4. Build the Windows sync/read adapter so Sonda Imperial Top 50 reads cloud data.

If runs fail, do NOT merge blindly. Fix test failures first.
