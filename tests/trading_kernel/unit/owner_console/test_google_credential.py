import json
from pathlib import Path

import pytest

from scripts.owner_console.prepare_google_credential import CALLBACK, prepare


def test_owner_preparation_keeps_secret_off_stdout_and_writes_private_file(
    tmp_path: Path, capsys
):
    download = tmp_path / "download.json"
    download.write_text(
        json.dumps(
            {
                "web": {
                    "client_id": "test.apps.googleusercontent.com",
                    "client_secret": "FAKE-SECRET",
                    "redirect_uris": [CALLBACK],
                }
            }
        )
    )
    output = tmp_path / "google_oidc"
    prepare(download, output, email="owner@example.com")
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())["owner_subject"] is None
    assert "FAKE-SECRET" not in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        prepare(download, output, email="owner@example.com")


def test_owner_preparation_rejects_wrong_callback_without_disclosing_secret(
    tmp_path: Path,
):
    download = tmp_path / "download.json"
    download.write_text(
        json.dumps(
            {
                "web": {
                    "client_id": "test",
                    "client_secret": "FAKE-SECRET",
                    "redirect_uris": ["https://evil.test"],
                }
            }
        )
    )
    with pytest.raises(ValueError) as error:
        prepare(download, tmp_path / "google_oidc", email="owner@example.com")
    assert "FAKE-SECRET" not in str(error.value)
