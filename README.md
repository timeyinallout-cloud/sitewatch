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

Since that's a download to a different machine than the one that produced
it, `sitewatch accept --show-fingerprints` prints a short spoken/readable
[odu-core](https://pypi.org/project/odu-core/) fingerprint per accepted
file -- four Odù figures, quick to compare or paste, that confirm what you
just copied is actually the file CI produced rather than a truncated or
stale download. This catches accidents, not tampering -- it's not a
security check, just a "did the download finish" sanity check.

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

## Interactive chat bot

`sitewatch/web/` is a small FastAPI app (Fly deploy: `sitewatch-bot`) with
a Fleetboard/Foreman-style chat interface: type "run a sweep", "sweep
matchscout", "accept 1234567" or "status", or use the buttons, instead of
running the CLI or waiting for Monday's cron.

**It remote-controls the same two GitHub Actions workflows this README
already describes -- it does not re-implement the crawl.** "Run a sweep"
dispatches `fleet-sweep.yml` and polls it to completion; "accept" dispatches
a new `accept-baseline.yml` (downloads that run's artifact and does exactly
what `sitewatch accept --reports-dir <downloaded dir>` does, committing the
result). This keeps GitHub Actions' pinned Ubuntu/Chromium as the one
environment baselines are ever trusted against — see "Baselines" above for
why that pinning matters at all.

**Local fallback, explicitly unverified.** If GitHub Actions can't be
reached, doesn't produce a run, or doesn't finish within 10 minutes, the
bot runs the crawl itself on its own Chromium (bundled in its Docker image)
instead of just failing. That result is labelled `origin: "local"`
everywhere it shows up (chat, dashboard, job detail) and the bot never
offers "accept" on one — a local run's visual diffs may just be
font-rendering drift from a different Chromium build, not a real
regression, so it's only good for "does the crawl work at all right now,"
not for confirming or denying a visual change.

Deploy:
```sh
fly apps create sitewatch-bot
fly volumes create sitewatch_data --region lhr --size 1
fly secrets set -a sitewatch-bot \
  SITEWATCH_USER=<user> SITEWATCH_PASS=<password> \
  SITEWATCH_GH_REPO=timeyinallout-cloud/sitewatch \
  SITEWATCH_GH_TOKEN=<fine-grained PAT: Actions read+write on this repo>
fly deploy -a sitewatch-bot
```

## Known limitation

A handful of external sites block generic automated clients (Cloudflare
bot-fight mode etc.) regardless of user-agent -- `sitewatch` retries with a
browser user-agent and a longer timeout before flagging an outbound link,
but a small number of real, working links will still show up as broken to
an automated check. Worth a manual click before treating one as a genuine
problem.
