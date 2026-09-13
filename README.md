# sitewatch

Crawl + link-check + visual-regression watch for the live site fleet:
MatchScout, StrategyAudit, SignalMarketplace, and PrivacyScan.

Two questions, answered on a schedule instead of "did anyone notice yet":

1. **Is everything on every page still resolving?** Same-host crawl from
   each homepage, following internal links up to 4 levels deep. Every
   page's HTTP status and load time is recorded; every embedded image,
   script, and stylesheet, plus every outbound link, gets its own status
   check without being crawled into.
2. **Does every page still look like it did last time?** A full-page
   desktop screenshot of every HTML page found, diffed pixel-for-pixel
   against the last accepted baseline. A change over 1% of the page gets
   a red-highlighted diff image in the report.

## Usage

```sh
pip install -e ".[dev]"
python -m playwright install chromium   # + --with-deps on a fresh CI box

sitewatch run                            # crawl, screenshot, diff, report
sitewatch run --fail-on-issues           # same, exit 2 if anything's flagged (CI)
sitewatch accept                         # promote the latest run's screenshots
sitewatch accept --site matchscout       # ...or just one site
```

`sitewatch run` writes `reports/<run-id>/report.html` (and updates
`reports/latest.html`). Open it in a browser -- it links every screenshot
and diff relative to itself.

## Sites

Edit `sites.toml` to add/remove a site. Each entry is just a name and a
homepage URL; the crawler discovers everything else.

## Baselines

`baselines/<site>/<page>.png` is the committed "known good" state, one file
per page (query strings included -- `/?division=E0` and `/?division=SP1`
get distinct baselines, not the same one). A page with no baseline yet is
reported as new, not as a regression -- first run against a fresh site (or
a genuinely new page) always looks clean.

When a visual change is *intentional* (a redesign, new copy, a new
section), review the diff in the report, then run `sitewatch accept` to
make the current state the new baseline. There's no automatic acceptance
-- a screenshot only becomes the new "correct" state when a human looks at
the diff and agrees.

**Baselines are environment-pinned.** Chromium's text layout differs by a
few pixels between OS/font-rendering stacks -- a baseline captured on a
dev machine drifts against CI's Ubuntu Chromium build by the bottom of a
long page, and shows up as a full-page false "regression" on every run.
Always `accept` from a run that happened in the *same* environment future
runs will compare against -- in practice, that means accepting a GitHub
Actions run's own screenshots (download the `sitewatch-report` build
artifact, point `sitewatch accept --reports-dir <downloaded dir>` at it),
not a local `sitewatch run`.

## Dashboard

Every `sitewatch run` regenerates `index.html` at the repo root and appends
one line per site to `history.jsonl` (`--dashboard-out` / `--history-file`
to change where). It's a standing status page, not a one-off report: fleet
summary at the top, one card per site with current status plus a small
trend strip (green/amber/red per run, last 20 runs) so a slow creeping
problem is visible even if no single run trips `--fail-on-issues`.

In CI, this gets committed back to `main` after every scheduled sweep and
served via GitHub Pages from the repo root -- the dashboard is always
whatever the last sweep found, no manual publish step.

## Recurring sweep

`.github/workflows/fleet-sweep.yml` runs the same check every Monday
07:00 UTC (an hour after `tronk-audit`'s weekly security sweep), and on
manual dispatch. It fails the run (red X, plus email if repo notifications
are on) when anything's flagged, and uploads the full report + screenshots
as a 90-day build artifact.

## Known limitation

A handful of external sites block generic automated clients (Cloudflare
bot-fight mode etc.) regardless of user-agent -- `sitewatch` retries with a
browser user-agent and a longer timeout before flagging an outbound link,
but a small number of real, working links will still show up as broken to
an automated check. Worth a manual click before treating one as a genuine
problem.
