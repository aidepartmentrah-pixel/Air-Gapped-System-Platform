from rah_packager.checksums import (
    compute_file_checksums,
    compute_release_fingerprint,
    render_sha256sums,
    verify_checksums,
    write_checksums,
)


def _make_release(tmp_path):
    (tmp_path / "release.yaml").write_text("application: {}\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "install.sh").write_text("#!/bin/sh\necho install\n")
    return tmp_path


def test_compute_file_checksums_covers_every_real_file(tmp_path):
    release_dir = _make_release(tmp_path)

    checksums = compute_file_checksums(release_dir)

    assert set(checksums) == {"release.yaml", "scripts/install.sh"}
    assert all(len(digest) == 64 for digest in checksums.values())


def test_checksum_file_never_lists_itself(tmp_path):
    release_dir = _make_release(tmp_path)
    write_checksums(release_dir)

    checksums = compute_file_checksums(release_dir)

    assert "checksums/SHA256SUMS" not in checksums


def test_render_sha256sums_is_sorted_and_sha256sum_compatible(tmp_path):
    release_dir = _make_release(tmp_path)
    checksums = compute_file_checksums(release_dir)

    rendered = render_sha256sums(checksums)
    lines = rendered.splitlines()

    assert lines == sorted(lines)
    for line in lines:
        digest, _, path = line.partition("  ")
        assert len(digest) == 64
        assert path in checksums


def test_write_checksums_creates_real_file(tmp_path):
    release_dir = _make_release(tmp_path)

    checksum_path = write_checksums(release_dir)

    assert checksum_path == release_dir / "checksums" / "SHA256SUMS"
    assert checksum_path.is_file()


def test_verify_checksums_passes_for_untouched_release(tmp_path):
    release_dir = _make_release(tmp_path)
    write_checksums(release_dir)

    assert verify_checksums(release_dir) == []


def test_verify_checksums_detects_tampering(tmp_path):
    release_dir = _make_release(tmp_path)
    write_checksums(release_dir)

    (release_dir / "scripts" / "install.sh").write_text("#!/bin/sh\necho tampered\n")

    mismatches = verify_checksums(release_dir)
    assert any("scripts/install.sh" in m and "mismatch" in m for m in mismatches)


def test_verify_checksums_detects_missing_file(tmp_path):
    release_dir = _make_release(tmp_path)
    write_checksums(release_dir)

    (release_dir / "scripts" / "install.sh").unlink()

    mismatches = verify_checksums(release_dir)
    assert any("scripts/install.sh" in m and "missing" in m for m in mismatches)


def test_verify_checksums_detects_unrecorded_new_file(tmp_path):
    release_dir = _make_release(tmp_path)
    write_checksums(release_dir)

    (release_dir / "scripts" / "extra.sh").write_text("#!/bin/sh\necho new\n")

    mismatches = verify_checksums(release_dir)
    assert any("scripts/extra.sh" in m and "not recorded" in m for m in mismatches)


def test_compute_release_fingerprint_is_deterministic_and_sensitive_to_content():
    content = b"application:\n  name: Test\n"
    fp1 = compute_release_fingerprint(content)
    fp2 = compute_release_fingerprint(content)
    fp3 = compute_release_fingerprint(content + b"extra: true\n")

    assert fp1 == fp2
    assert fp1.startswith("sha256:")
    assert len(fp1) == len("sha256:") + 64
    assert fp1 != fp3
