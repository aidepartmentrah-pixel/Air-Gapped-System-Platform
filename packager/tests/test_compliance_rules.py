from rah_packager.compliance_rules import _looks_like_placeholder


def test_recognizes_generate_me_style_placeholder():
    # Real pattern found in HCopilot's actual .env.offline.template —
    # __GENERATE_ME__ wasn't recognized by the original marker list,
    # a real false positive (RC-CFG-001/RC-SEC-003 flagging a genuine,
    # unambiguous placeholder as a real secret).
    assert _looks_like_placeholder("__GENERATE_ME__")
    assert _looks_like_placeholder("GENERATE_ME")


def test_still_recognizes_original_marker_styles():
    assert _looks_like_placeholder("CHANGE_ME")
    assert _looks_like_placeholder("your-password-here")
    assert _looks_like_placeholder("<password>")
    assert _looks_like_placeholder("${DB_PASSWORD}")


def test_does_not_flag_a_real_looking_secret():
    assert not _looks_like_placeholder("Tr0ub4dor&3xamplePass!")
