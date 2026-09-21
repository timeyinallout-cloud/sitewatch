from sitewatch.config import Site
from sitewatch.crawler import CrawlResult, LinkIssue
from sitewatch.runner import SiteReport


def _report(link_ignore_hosts=(), issues=()):
    site = Site(name="X", base_url="https://x.example", link_ignore_hosts=link_ignore_hosts)
    crawl = CrawlResult(site=site, issues=list(issues))
    return SiteReport(site=site, crawl=crawl)


class TestBlockingBrokenCount:
    def test_no_issues_is_zero(self):
        assert _report().blocking_broken_count == 0

    def test_counts_issues_when_no_ignore_list(self):
        issues = [LinkIssue(page_url="https://x.example/", target_url="https://x.example/dead",
                             status=404, kind="link")]
        assert _report(issues=issues).blocking_broken_count == 1

    def test_ignored_host_is_excluded(self):
        issues = [LinkIssue(page_url="https://x.example/", target_url="https://www.gamblingtherapy.org",
                             status=502, kind="link")]
        report = _report(link_ignore_hosts=("www.gamblingtherapy.org",), issues=issues)
        assert report.blocking_broken_count == 0

    def test_non_ignored_issue_still_counts_alongside_ignored_one(self):
        issues = [
            LinkIssue(page_url="https://x.example/", target_url="https://www.gamblingtherapy.org",
                       status=502, kind="link"),
            LinkIssue(page_url="https://x.example/", target_url="https://x.example/dead",
                       status=404, kind="asset"),
        ]
        report = _report(link_ignore_hosts=("www.gamblingtherapy.org",), issues=issues)
        assert report.blocking_broken_count == 1
