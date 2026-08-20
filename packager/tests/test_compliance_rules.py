from rah_packager.compliance_rules import RuleContext, _looks_like_placeholder, rc_cfg_002, rc_off_004


def test_recognizes_generate_me_style_placeholder():
    # Real pattern found in HCopilot's actual .env.offline.template —
    # __GENERATE_ME__ wasn't recognized by the original marker list,
    # a real false positive (RC-CFG-001/RC-SEC-003 flagging a genuine,
    # unambiguous placeholder as a real secret).
    assert _looks_like_placeholder("__GENERATE_ME__")
    assert _looks_like_placeholder("GENERATE_ME")


def test_recognizes_set_me_style_placeholder():
    # Real pattern found in HCAT's actual .env.offline.template —
    # __SET_ME__ is just as unambiguous a placeholder as __GENERATE_ME__,
    # only the verb differs; wasn't recognized either.
    assert _looks_like_placeholder("__SET_ME__")
    assert _looks_like_placeholder("SET_ME")


def test_still_recognizes_original_marker_styles():
    assert _looks_like_placeholder("CHANGE_ME")
    assert _looks_like_placeholder("your-password-here")
    assert _looks_like_placeholder("<password>")
    assert _looks_like_placeholder("${DB_PASSWORD}")


def test_does_not_flag_a_real_looking_secret():
    assert not _looks_like_placeholder("Tr0ub4dor&3xamplePass!")


# --- RC-CFG-002 ---


def test_rc_cfg_002_ignores_shell_examples_in_comments(tmp_path):
    """Real pattern found in STT-SCHEDULE's actual .env.offline.template: a
    comment line with an illustrative `for p in ...` shell one-liner
    (operator guidance for checking free ports before install) got matched
    as an undeclared `$p` placeholder by a whole-file regex scan, even
    though a comment isn't a substitutable value at all. Real declared
    placeholders (`${BACKEND_PORT}`) must still be caught.
    """
    release_dir = tmp_path
    (release_dir / "compose").mkdir()
    template = release_dir / "compose" / ".env.offline.template"
    template.write_text(
        "# verify with: for p in 8002 8081; do echo $p; done\n"
        "BACKEND_PORT=${BACKEND_PORT}\n"
    )
    manifest = {
        "configuration": {
            "template": "compose/.env.offline.template",
            "inputs": [{"key": "BACKEND_PORT"}],
        }
    }
    ctx = RuleContext(release_dir, manifest)

    result = rc_cfg_002(ctx)

    assert result["result"] == "PASS"


def test_rc_cfg_002_still_catches_a_real_undeclared_placeholder(tmp_path):
    release_dir = tmp_path
    (release_dir / "compose").mkdir()
    template = release_dir / "compose" / ".env.offline.template"
    template.write_text("SOME_KEY=${UNDECLARED_VAR}\n")
    manifest = {"configuration": {"template": "compose/.env.offline.template", "inputs": []}}
    ctx = RuleContext(release_dir, manifest)

    result = rc_cfg_002(ctx)

    assert result["result"] == "FAIL"
    assert "UNDECLARED_VAR" in result["message"]


# --- RC-OFF-004 ---


def test_rc_off_004_ignores_docker_compose_service_names(tmp_path):
    """Real pattern found in Voice Project's actual configuration template:
    WHISPER_SERVICE_URL=http://whisper:5001/transcribe — a completely
    normal Docker Compose service-to-service reference (`whisper` is a
    service name from docker-compose.yml, resolved by Docker's internal
    DNS), not a real offline-readiness gap. A bare single-label host can
    never resolve on the public internet at all — DNS requires a real
    domain structure — so it must not be flagged as one.
    """
    release_dir = tmp_path
    (release_dir / "configuration").mkdir()
    (release_dir / "configuration" / ".env.offline.template").write_text(
        "WHISPER_SERVICE_URL=http://whisper:5001/transcribe\n"
    )
    ctx = RuleContext(release_dir, {})

    result = rc_off_004(ctx)

    assert result["result"] == "PASS"


def test_rc_off_004_still_catches_a_real_public_url(tmp_path):
    release_dir = tmp_path
    (release_dir / "configuration").mkdir()
    (release_dir / "configuration" / ".env.offline.template").write_text(
        "MODEL_REGISTRY=https://huggingface.co/some/model\n"
    )
    ctx = RuleContext(release_dir, {})

    result = rc_off_004(ctx)

    assert result["result"] == "FAIL"
    assert "huggingface.co" in result["message"]
