from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sitewatch.config import load_sites
from sitewatch.dashboard import render_dashboard
from sitewatch.history import append_run, load_history
from sitewatch.report import render
from sitewatch.runner import accept_baseline, run_all


def _cmd_run(args: argparse.Namespace) -> int:
    sites = load_sites(Path(args.config))
    if not sites:
        print(f"No [[site]] entries found in {args.config}", file=sys.stderr)
        return 1

    reports_root = Path(args.reports_dir)
    baseline_dir = Path(args.baseline_dir)
    run_dir, site_reports = run_all(
        sites, reports_root, baseline_dir,
        max_pages=args.max_pages, max_depth=args.max_depth,
    )
    report_path = render(run_dir.name, site_reports, run_dir / "report.html")

    latest = reports_root / "latest.html"
    latest.write_text(report_path.read_text())

    total_broken = sum(len(r.crawl.broken_links) + len(r.crawl.broken_assets) for r in site_reports)
    total_visual = sum(len(r.visual_regressions) for r in site_reports)
    total_failed = sum(len(r.render_failures) for r in site_reports)
    print(f"sitewatch run {run_dir.name}: "
          f"{total_broken} broken link(s)/asset(s), "
          f"{total_visual} visual regression(s), "
          f"{total_failed} render failure(s)")
    print(f"report: {report_path}")

    summary_lines = [f"### sitewatch &mdash; {run_dir.name}", ""]
    for r in site_reports:
        status = "🟢" if not (r.crawl.broken_links or r.crawl.broken_assets
                               or r.crawl.slow_pages or r.visual_regressions
                               or r.render_failures) else "🟡"
        summary_lines.append(
            f"- {status} **{r.site.name}** &mdash; {len(r.crawl.pages)} pages, "
            f"{len(r.crawl.broken_links) + len(r.crawl.broken_assets)} broken, "
            f"{len(r.visual_regressions)} visual change(s)"
        )
    summary_lines += ["", f"Full report in the `report.html` build artifact."]
    (run_dir / "summary.md").write_text("\n".join(summary_lines) + "\n")

    history_path = Path(args.history_file)
    append_run(history_path, run_dir.name, site_reports)
    dashboard_path = render_dashboard(
        run_dir.name, site_reports, load_history(history_path), Path(args.dashboard_out))
    print(f"dashboard: {dashboard_path}")

    if args.fail_on_issues and (total_broken or total_visual or total_failed):
        return 2
    return 0


def _cmd_accept(args: argparse.Namespace) -> int:
    reports_root = Path(args.reports_dir)
    baseline_dir = Path(args.baseline_dir)
    if args.run == "latest":
        candidates = sorted((d for d in reports_root.iterdir() if d.is_dir()), reverse=True) \
            if reports_root.exists() else []
        if not candidates:
            print("No runs found to accept from.", file=sys.stderr)
            return 1
        run_dir = candidates[0]
    else:
        run_dir = reports_root / args.run
        if not run_dir.exists():
            print(f"No such run: {run_dir}", file=sys.stderr)
            return 1

    accepted = accept_baseline(run_dir, baseline_dir, site_slug=args.site)
    print(f"Accepted {len(accepted)} screenshot(s) from {run_dir.name} as new baseline"
          f"{f' for {args.site}' if args.site else ''}.")
    if args.show_fingerprints:
        for a in accepted:
            print(f"  {a.relative_path}: {a.fingerprint}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="sites.toml")
    common.add_argument("--reports-dir", default="reports")
    common.add_argument("--baseline-dir", default="baselines")

    parser = argparse.ArgumentParser(prog="sitewatch", parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", parents=[common],
                            help="Crawl + screenshot every configured site and write a report.")
    run_p.add_argument("--max-pages", type=int, default=60)
    run_p.add_argument("--max-depth", type=int, default=4)
    run_p.add_argument("--fail-on-issues", action="store_true",
                        help="Exit non-zero if anything was flagged (for CI).")
    run_p.add_argument("--history-file", default="history.jsonl",
                        help="Append this run's per-site stats here (for the dashboard trend).")
    run_p.add_argument("--dashboard-out", default="index.html",
                        help="Where to (re)write the standing dashboard page.")
    run_p.set_defaults(func=_cmd_run)

    accept_p = sub.add_parser("accept", parents=[common],
                               help="Promote a run's screenshots to the new baseline.")
    accept_p.add_argument("run", nargs="?", default="latest", help="Run id, or 'latest' (default).")
    accept_p.add_argument("--site", default=None, help="Limit to one site slug.")
    accept_p.add_argument("--show-fingerprints", action="store_true",
                           help="Print a spoken/readable fingerprint per accepted file -- "
                                "useful after downloading a CI run artifact, to confirm "
                                "what you're accepting is actually what CI produced.")
    accept_p.set_defaults(func=_cmd_accept)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
