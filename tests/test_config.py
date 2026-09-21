from pathlib import Path

from sitewatch.config import Site, load_sites


class TestExcludesVisual:
    def test_no_patterns_excludes_nothing(self):
        site = Site(name="X", base_url="https://x.example")
        assert site.excludes_visual("https://x.example/") is False
        assert site.excludes_visual("https://x.example/anything") is False

    def test_bare_path_pattern_matches_regardless_of_query(self):
        site = Site(name="X", base_url="https://x.example", visual_exclude=("/",))
        assert site.excludes_visual("https://x.example/") is True

    def test_bare_path_pattern_does_not_match_other_paths(self):
        site = Site(name="X", base_url="https://x.example", visual_exclude=("/",))
        assert site.excludes_visual("https://x.example/about") is False

    def test_query_glob_matches_any_value(self):
        site = Site(name="X", base_url="https://x.example", visual_exclude=("/?division=*",))
        assert site.excludes_visual("https://x.example/?division=E0") is True
        assert site.excludes_visual("https://x.example/?division=SP1") is True

    def test_query_glob_does_not_match_bare_path(self):
        site = Site(name="X", base_url="https://x.example", visual_exclude=("/?division=*",))
        assert site.excludes_visual("https://x.example/") is False

    def test_multiple_patterns_are_all_checked(self):
        site = Site(name="X", base_url="https://x.example",
                    visual_exclude=("/all", "/european"))
        assert site.excludes_visual("https://x.example/all") is True
        assert site.excludes_visual("https://x.example/european") is True
        assert site.excludes_visual("https://x.example/about") is False

    def test_static_pages_remain_diffable_alongside_exclusions(self):
        site = Site(name="X", base_url="https://x.example", visual_exclude=("/", "/all"))
        assert site.excludes_visual("https://x.example/privacy") is False


class TestLoadSites:
    def test_loads_visual_exclude_when_present(self, tmp_path):
        path = tmp_path / "sites.toml"
        path.write_text(
            '[[site]]\nname = "X"\nbase_url = "https://x.example"\n'
            'visual_exclude = ["/", "/all"]\n'
        )
        sites = load_sites(path)
        assert sites[0].visual_exclude == ("/", "/all")

    def test_defaults_to_empty_when_absent(self, tmp_path):
        path = tmp_path / "sites.toml"
        path.write_text('[[site]]\nname = "X"\nbase_url = "https://x.example"\n')
        sites = load_sites(path)
        assert sites[0].visual_exclude == ()

    def test_loads_link_ignore_hosts_when_present(self, tmp_path):
        path = tmp_path / "sites.toml"
        path.write_text(
            '[[site]]\nname = "X"\nbase_url = "https://x.example"\n'
            'link_ignore_hosts = ["www.gamblingtherapy.org"]\n'
        )
        sites = load_sites(path)
        assert sites[0].link_ignore_hosts == ("www.gamblingtherapy.org",)


class TestIgnoresLinkHost:
    def test_no_hosts_ignores_nothing(self):
        site = Site(name="X", base_url="https://x.example")
        assert site.ignores_link_host("https://www.gamblingtherapy.org/") is False

    def test_matching_host_is_ignored(self):
        site = Site(name="X", base_url="https://x.example",
                    link_ignore_hosts=("www.gamblingtherapy.org",))
        assert site.ignores_link_host("https://www.gamblingtherapy.org/page") is True

    def test_non_matching_host_is_not_ignored(self):
        site = Site(name="X", base_url="https://x.example",
                    link_ignore_hosts=("www.gamblingtherapy.org",))
        assert site.ignores_link_host("https://other.example/") is False
