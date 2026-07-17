from __future__ import annotations


pytest_plugins = ("pytester",)


def test_required_gate_plugin_keeps_passing_session_green(pytester):
    pytester.makepyfile("def test_ok(): assert True")

    result = pytester.runpytest("-p", "tests.fail_on_skip_plugin", "-q")

    assert result.ret == 0


def test_required_gate_plugin_rejects_skip_and_xfail(pytester):
    pytester.makepyfile(
        """
        import pytest

        @pytest.fixture
        def skipped_fixture():
            pytest.skip('required gate setup proof')

        def test_skip():
            pytest.skip('required gate call proof')

        def test_setup_skip(skipped_fixture):
            assert skipped_fixture

        @pytest.mark.xfail(reason='required gate proof')
        def test_xfail():
            assert False
        """
    )

    result = pytester.runpytest("-p", "tests.fail_on_skip_plugin", "-q")

    assert result.ret != 0
