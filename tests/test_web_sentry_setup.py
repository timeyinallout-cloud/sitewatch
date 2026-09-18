from sitewatch.web import sentry_setup


def test_no_dsn_is_a_clean_noop(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    sentry_setup.init()  # must not raise, must not import sentry_sdk


def test_dsn_set_calls_sentry_sdk_init(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://example@example.ingest.sentry.io/1")
    calls = []

    class _FakeSentrySDK:
        @staticmethod
        def init(**kwargs):
            calls.append(kwargs)

    import sys
    monkeypatch.setitem(sys.modules, "sentry_sdk", _FakeSentrySDK)
    sentry_setup.init()
    assert calls and calls[0]["dsn"] == "https://example@example.ingest.sentry.io/1"
