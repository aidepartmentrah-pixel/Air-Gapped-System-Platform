import pytest

from conftest import seed_active_deployment, seed_application, seed_release
from rah_platform import application_query
from rah_platform.errors import (
    ApplicationNotFoundError,
    ReleaseBelongsToAnotherApplicationError,
    ReleaseNotFoundError,
)


def _action(actions, name):
    return next(a for a in actions if a["action"] == name)


# --- Fresh Application ---


def test_fresh_application_install_allowed_update_not_allowed(db_engine):
    app_id = seed_application(db_engine)
    release_id = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})

    result = application_query.get_available_actions(db_engine, app_id, target_release_id=release_id)

    assert _action(result["actions"], "INSTALL")["allowed"] is True
    assert _action(result["actions"], "UPDATE")["allowed"] is False
    assert result["active_release"] is None


# --- Installed Application ---


def test_installed_application_fresh_install_blocked(db_engine):
    app_id = seed_application(db_engine)
    release_id = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})
    seed_active_deployment(db_engine, application_id=app_id, release_id=release_id)

    result = application_query.get_available_actions(db_engine, app_id, target_release_id=release_id)

    install = _action(result["actions"], "INSTALL")
    assert install["allowed"] is False
    assert install["blocking_reasons"][0]["code"] == "PLT-APPLICATION-002"


# --- Compatible Target ---


def test_compatible_target_update_allowed(db_engine):
    app_id = seed_application(db_engine)
    v1 = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})
    v2 = seed_release(
        db_engine,
        application_id=app_id,
        version="1.1.0",
        supported_operations={"fresh_install": True, "update": True},
        accepted_installed_versions=["1.0.0"],
    )
    seed_active_deployment(db_engine, application_id=app_id, release_id=v1)

    result = application_query.get_available_actions(db_engine, app_id, target_release_id=v2)

    update = _action(result["actions"], "UPDATE")
    assert update["allowed"] is True
    assert "MANDATORY_VERIFICATION" in update["requirements"]


# --- Unsupported Transition ---


def test_unsupported_transition_update_rejected_with_blocking_reason(db_engine):
    app_id = seed_application(db_engine)
    v1 = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})
    v2 = seed_release(
        db_engine,
        application_id=app_id,
        version="2.0.0",
        supported_operations={"fresh_install": True, "update": True},
        accepted_installed_versions=["1.5.0"],  # 1.0.0 is not an accepted source
    )
    seed_active_deployment(db_engine, application_id=app_id, release_id=v1)

    result = application_query.get_available_actions(db_engine, app_id, target_release_id=v2)

    update = _action(result["actions"], "UPDATE")
    assert update["allowed"] is False
    assert update["blocking_reasons"][0]["code"] == "PLT-TRANSITION-003"


# --- Same Version ---


def test_same_version_no_update(db_engine):
    app_id = seed_application(db_engine)
    v1 = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True, "update": True})
    seed_active_deployment(db_engine, application_id=app_id, release_id=v1)

    result = application_query.get_available_actions(db_engine, app_id, target_release_id=v1)

    update = _action(result["actions"], "UPDATE")
    assert update["allowed"] is False
    assert update["blocking_reasons"][0]["code"] == "PLT-TRANSITION-006"


# --- Release From Different Application ---


def test_release_from_different_application_rejected(db_engine):
    app1 = seed_application(db_engine)
    app2 = seed_application(db_engine)
    other_release = seed_release(db_engine, application_id=app2, version="1.0.0", supported_operations={"fresh_install": True})

    with pytest.raises(ReleaseBelongsToAnotherApplicationError) as exc_info:
        application_query.get_available_actions(db_engine, app1, target_release_id=other_release)
    assert exc_info.value.code == "PLT-RELEASE-003"


# --- Downgrade Unsupported ---


def test_downgrade_unavailable(db_engine):
    app_id = seed_application(db_engine)
    v2 = seed_release(db_engine, application_id=app_id, version="2.0.0", supported_operations={"fresh_install": True})
    v1 = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True, "downgrade": False})
    seed_active_deployment(db_engine, application_id=app_id, release_id=v2)

    result = application_query.get_available_actions(db_engine, app_id, target_release_id=v1)

    downgrade = _action(result["actions"], "DOWNGRADE")
    assert downgrade["allowed"] is False
    assert downgrade["blocking_reasons"][0]["code"] == "PLT-TRANSITION-004"


# --- Release Package Missing ---


def test_release_package_missing_historical_release_visible_action_blocked(db_engine):
    app_id = seed_application(db_engine)
    release_id = seed_release(
        db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True}, storage_state="REMOVED_FROM_STORAGE"
    )

    # still visible
    release = application_query.get_release(db_engine, release_id)
    assert release["id"] == release_id
    assert release["storage_state"] == "REMOVED_FROM_STORAGE"

    # but action blocked
    result = application_query.get_available_actions(db_engine, app_id, target_release_id=release_id)
    install = _action(result["actions"], "INSTALL")
    assert install["allowed"] is False
    assert install["blocking_reasons"][0]["code"] == "PLT-RELEASE-002"


# --- Not found errors ---


def test_get_application_not_found(db_engine):
    with pytest.raises(ApplicationNotFoundError):
        application_query.get_application(db_engine, "00000000-0000-0000-0000-000000000000")


def test_get_release_not_found(db_engine):
    with pytest.raises(ReleaseNotFoundError):
        application_query.get_release(db_engine, "00000000-0000-0000-0000-000000000000")


# --- Query surfaces (list, application detail, active deployment) ---


def test_list_applications_and_get_application(db_engine):
    app_id = seed_application(db_engine, slug="my-app", name="My App")
    seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})

    listed = application_query.list_applications(db_engine)
    assert any(a["id"] == app_id for a in listed["items"])

    application = application_query.get_application(db_engine, app_id)
    assert application["slug"] == "my-app"
    assert application["available_release_count"] == 1
    assert application["active_deployment"] is None
    assert application["operational_health"] == "NOT_INSTALLED"


def test_get_application_with_active_deployment_reports_unknown_health(db_engine):
    app_id = seed_application(db_engine)
    release_id = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})
    seed_active_deployment(db_engine, application_id=app_id, release_id=release_id)

    application = application_query.get_application(db_engine, app_id)
    assert application["active_deployment"]["release_id"] == release_id
    assert application["operational_health"] == "UNKNOWN"


def test_list_application_releases(db_engine):
    app_id = seed_application(db_engine)
    v1 = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})
    v2 = seed_release(db_engine, application_id=app_id, version="1.1.0", supported_operations={"fresh_install": True})
    seed_active_deployment(db_engine, application_id=app_id, release_id=v1)

    result = application_query.list_application_releases(db_engine, app_id)
    by_version = {r["version"]: r for r in result["items"]}
    assert by_version["1.0.0"]["deployment_state"] == "ACTIVE"
    assert by_version["1.1.0"]["deployment_state"] == "NEVER_DEPLOYED"


def test_get_active_deployment_none_when_not_installed(db_engine):
    app_id = seed_application(db_engine)
    assert application_query.get_active_deployment(db_engine, app_id) is None


def test_get_active_deployment_returns_deployment(db_engine):
    app_id = seed_application(db_engine)
    release_id = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})
    seed_active_deployment(db_engine, application_id=app_id, release_id=release_id, verification_status="PASS")

    active = application_query.get_active_deployment(db_engine, app_id)
    assert active["release_id"] == release_id
    assert active["verification_status"] == "PASS"


# --- VERIFY / BACKUP / RECOVER real logic ---


def test_verify_and_backup_require_installed_application(db_engine):
    app_id = seed_application(db_engine)
    release_id = seed_release(db_engine, application_id=app_id, version="1.0.0", supported_operations={"fresh_install": True})

    not_installed = application_query.get_available_actions(db_engine, app_id, target_release_id=release_id)
    assert _action(not_installed["actions"], "VERIFY")["allowed"] is False
    assert _action(not_installed["actions"], "BACKUP")["allowed"] is False

    seed_active_deployment(db_engine, application_id=app_id, release_id=release_id)
    installed = application_query.get_available_actions(db_engine, app_id)
    assert _action(installed["actions"], "VERIFY")["allowed"] is True
    assert _action(installed["actions"], "BACKUP")["allowed"] is True


def test_recover_always_unsupported_with_correct_reasoning(db_engine):
    app_id = seed_application(db_engine)
    result = application_query.get_available_actions(db_engine, app_id)
    recover = _action(result["actions"], "RECOVER")
    assert recover["allowed"] is False
    assert recover["blocking_reasons"][0]["code"] == "PLT-RECOVERY-001"
