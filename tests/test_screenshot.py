from sitewatch.screenshot import page_slug


def test_homepage_is_root():
    assert page_slug("https://example.com/") == "root"


def test_path_only_pages_differ():
    assert page_slug("https://example.com/about") != page_slug("https://example.com/directory")


def test_query_string_pages_get_distinct_slugs():
    a = page_slug("https://example.com/?division=E0")
    b = page_slug("https://example.com/?division=SP1")
    root = page_slug("https://example.com/")
    assert len({a, b, root}) == 3


def test_slug_is_filesystem_safe():
    slug = page_slug("https://example.com/search?q=a b&x=1/2")
    assert "/" not in slug
    assert " " not in slug


def test_very_long_path_is_hashed_not_truncated_to_a_collision():
    long_a = "https://example.com/" + "x" * 90 + "?id=1"
    long_b = "https://example.com/" + "x" * 90 + "?id=2"
    assert page_slug(long_a) != page_slug(long_b)
