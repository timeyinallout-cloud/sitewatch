from sitewatch.web import intent


class TestSweep:
    def test_bare_sweep(self):
        assert intent.parse("sweep") == {"action": "sweep", "site": None}

    def test_run_a_sweep(self):
        assert intent.parse("run a sweep") == {"action": "sweep", "site": None}

    def test_sweep_for_site(self):
        assert intent.parse("sweep for matchscout") == {"action": "sweep", "site": "matchscout"}

    def test_sweep_bare_site_name(self):
        assert intent.parse("sweep matchscout") == {"action": "sweep", "site": "matchscout"}

    def test_sweep_on_site(self):
        assert intent.parse("run sweep on privacyscan") == {"action": "sweep", "site": "privacyscan"}

    def test_case_insensitive(self):
        assert intent.parse("SWEEP") == {"action": "sweep", "site": None}


class TestCheck:
    def test_check_everything(self):
        assert intent.parse("check everything") == {"action": "sweep", "site": None}

    def test_check_one_site(self):
        assert intent.parse("check matchscout") == {"action": "sweep", "site": "matchscout"}


class TestAccept:
    def test_accept_with_run_id(self):
        assert intent.parse("accept 12345") == {"action": "accept", "run_id": "12345", "site": None}

    def test_accept_run_prefixed(self):
        assert intent.parse("accept run 12345") == {"action": "accept", "run_id": "12345", "site": None}

    def test_accept_with_site(self):
        assert intent.parse("accept 12345 for matchscout") == {
            "action": "accept", "run_id": "12345", "site": "matchscout"}

    def test_bare_accept_is_not_a_command(self):
        """No run id given -- must not be treated as a valid accept command,
        so a mistyped "accept" gets the unknown-command hint instead of
        silently doing nothing with a missing run id."""
        assert intent.parse("accept") is None


class TestStatus:
    def test_status(self):
        assert intent.parse("status") == {"action": "status"}

    def test_status_with_question_mark(self):
        assert intent.parse("status?") == {"action": "status"}


class TestUnknown:
    def test_unrelated_text(self):
        assert intent.parse("hello there") is None

    def test_empty_string(self):
        assert intent.parse("") is None
