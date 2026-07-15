from pathlib import Path


def test_writer_fence_condition_is_release_independent():
    path = Path(__file__).resolve().parents[2] / "deploy/systemd/production-writer-fence.conf"
    assert path.read_text(encoding="utf-8") == (
        "[Unit]\n"
        "ConditionPathExists=!/home/ubuntu/brc-deploy/control-plane/production-writers.blocked\n"
    )
