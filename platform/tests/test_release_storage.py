import pytest

from rah_platform.errors import ReleaseStorageUnavailableError
from rah_platform.release_storage import check_availability


def test_release_storage_reachable(tmp_path):
    result = check_availability(str(tmp_path))
    assert result == {"reachable": True, "path": str(tmp_path)}


def test_release_storage_missing_path_reported_clearly(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(ReleaseStorageUnavailableError) as exc_info:
        check_availability(str(missing))
    assert exc_info.value.code == "PLT-STORAGE-001"
    assert exc_info.value.details["path"] == str(missing)
