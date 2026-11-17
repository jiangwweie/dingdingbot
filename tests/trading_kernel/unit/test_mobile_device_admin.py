import pytest

from scripts.owner_console.manage_mobile_device import require_private_destination


def test_binding_output_requires_new_private_path(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    require_private_destination(private / "binding")
    (private / "binding").write_text("old")
    with pytest.raises(ValueError):
        require_private_destination(private / "binding")


def test_public_or_symlink_destination_rejected(tmp_path):
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(ValueError):
        require_private_destination(public / "token")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    (private / "link").symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError):
        require_private_destination(private / "link")
