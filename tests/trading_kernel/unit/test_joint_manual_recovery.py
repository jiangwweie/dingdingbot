from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.trading_kernel import manual_joint_recovery as joint


def test_joint_maintenance_never_runs_before_target_certification(monkeypatch,tmp_path):
    monkeypatch.setattr(joint.subprocess,'check_output',Mock(return_value='a'*40))
    gate=Mock(side_effect=ValueError('candidate_not_certified'))
    monkeypatch.setattr(joint,'load_release_certification_manifest',gate)
    run=Mock();monkeypatch.setattr(joint.subprocess,'run',run)
    with pytest.raises(ValueError,match='not_certified'):
        joint.require_commits(tmp_path,'b'*40,'c'*40)
    run.assert_not_called()


def test_joint_maintenance_requires_exact_clean_prelude(monkeypatch,tmp_path):
    values=iter(['a'*40,'b'*40,' M file.py'])
    monkeypatch.setattr(joint.subprocess,'check_output',lambda *a,**k:next(values))
    for name in ['load_release_certification_manifest','validate_owner_api_release_certification','validate_owner_static_release_certification']:
        monkeypatch.setattr(joint,name,Mock())
    run=Mock();monkeypatch.setattr(joint.subprocess,'run',run)
    with pytest.raises(ValueError,match='exact_clean'):
        joint.require_commits(tmp_path,'b'*40,'c'*40)
    run.assert_not_called()


def test_joint_source_is_staged_under_maintenance_and_never_repoints_runtime():
    source=Path(joint.__file__).read_text()
    assert '/opt/brc/maintenance/' in source
    assert 'systemctl' not in source and 'os.replace' not in source
    assert 'stage-upgrade' not in source and 'activate-upgrade' not in source
