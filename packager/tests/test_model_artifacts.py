import pytest

from rah_packager.errors import ModelServiceNotBuiltError, ModelSourcePathNotFoundError
from rah_packager.model_artifacts import resolve_baked_into_image, verify_and_checksum_model_artifacts


def _answers_with_artifacts(artifacts):
    return {"models": {"required": True, "artifacts": artifacts}}


# --- verify_and_checksum_model_artifacts ---


def test_single_file_artifact_is_checksummed(tmp_path):
    model_file = tmp_path / "model.pkl"
    model_file.write_bytes(b"fake model bytes")
    answers = _answers_with_artifacts(
        [{"id": "m1", "version": "1.0.0", "source_path": "model.pkl", "service": "backend"}]
    )

    resolved = verify_and_checksum_model_artifacts(tmp_path, answers)

    assert resolved == [
        {
            "id": "m1",
            "version": "1.0.0",
            "service": "backend",
            "checksum": resolved[0]["checksum"],
        }
    ]
    assert resolved[0]["checksum"].startswith("sha256:")
    assert len(resolved[0]["checksum"]) == len("sha256:") + 64


def test_source_registry_carried_through_when_declared(tmp_path):
    (tmp_path / "model.pkl").write_bytes(b"x")
    answers = _answers_with_artifacts(
        [
            {
                "id": "m1",
                "version": "1.0.0",
                "source_path": "model.pkl",
                "service": "backend",
                "source_registry": "hf://org/model",
            }
        ]
    )

    resolved = verify_and_checksum_model_artifacts(tmp_path, answers)

    assert resolved[0]["source_registry"] == "hf://org/model"


def test_missing_source_path_raises_structured_error(tmp_path):
    answers = _answers_with_artifacts(
        [{"id": "m1", "version": "1.0.0", "source_path": "does/not/exist.pkl", "service": "backend"}]
    )

    with pytest.raises(ModelSourcePathNotFoundError) as exc_info:
        verify_and_checksum_model_artifacts(tmp_path, answers)

    assert exc_info.value.code == "PKG-MANIFEST-MODEL-SOURCE-NOT-FOUND"
    assert exc_info.value.artifact_id == "m1"
    assert exc_info.value.source_path == "does/not/exist.pkl"


def test_no_artifacts_declared_returns_empty_list(tmp_path):
    answers = {"models": {"required": False}}

    assert verify_and_checksum_model_artifacts(tmp_path, answers) == []


def test_directory_artifact_checksum_is_deterministic(tmp_path):
    model_dir = tmp_path / "models_directory"
    (model_dir / "sub").mkdir(parents=True)
    (model_dir / "a.pkl").write_bytes(b"aaa")
    (model_dir / "sub" / "b.pkl").write_bytes(b"bbb")
    answers = _answers_with_artifacts(
        [{"id": "m1", "version": "1.0.0", "source_path": "models_directory", "service": "backend"}]
    )

    first = verify_and_checksum_model_artifacts(tmp_path, answers)[0]["checksum"]
    second = verify_and_checksum_model_artifacts(tmp_path, answers)[0]["checksum"]

    assert first == second
    assert first.startswith("sha256:")


def test_directory_artifact_checksum_changes_with_content(tmp_path):
    model_dir = tmp_path / "models_directory"
    model_dir.mkdir()
    (model_dir / "a.pkl").write_bytes(b"aaa")
    answers = _answers_with_artifacts(
        [{"id": "m1", "version": "1.0.0", "source_path": "models_directory", "service": "backend"}]
    )
    before = verify_and_checksum_model_artifacts(tmp_path, answers)[0]["checksum"]

    (model_dir / "a.pkl").write_bytes(b"changed")
    after = verify_and_checksum_model_artifacts(tmp_path, answers)[0]["checksum"]

    assert before != after


def test_multiple_artifacts_all_resolved(tmp_path):
    (tmp_path / "a.pkl").write_bytes(b"a")
    (tmp_path / "b.pkl").write_bytes(b"b")
    answers = _answers_with_artifacts(
        [
            {"id": "m1", "version": "1.0.0", "source_path": "a.pkl", "service": "backend"},
            {"id": "m2", "version": "1.0.0", "source_path": "b.pkl", "service": "backend"},
        ]
    )

    resolved = verify_and_checksum_model_artifacts(tmp_path, answers)

    assert [entry["id"] for entry in resolved] == ["m1", "m2"]


# --- resolve_baked_into_image ---


def test_service_matching_a_built_image_resolves():
    model_artifacts = [{"id": "m1", "version": "1.0.0", "service": "backend", "checksum": "sha256:" + "a" * 64}]
    docker_images = [{"service": "backend", "repository": "r", "tag": "t", "archive": "a", "required": True}]

    resolved = resolve_baked_into_image(model_artifacts, docker_images)

    assert resolved == [
        {
            "id": "m1",
            "version": "1.0.0",
            "checksum": "sha256:" + "a" * 64,
            "baked_into_image": "backend",
        }
    ]
    assert "service" not in resolved[0]


def test_service_not_built_raises_structured_error():
    model_artifacts = [{"id": "m1", "version": "1.0.0", "service": "missing-service", "checksum": "sha256:" + "a" * 64}]
    docker_images = [{"service": "backend", "repository": "r", "tag": "t", "archive": "a", "required": True}]

    with pytest.raises(ModelServiceNotBuiltError) as exc_info:
        resolve_baked_into_image(model_artifacts, docker_images)

    assert exc_info.value.code == "PKG-MANIFEST-MODEL-SERVICE-NOT-BUILT"
    assert exc_info.value.artifact_id == "m1"
    assert exc_info.value.service == "missing-service"
