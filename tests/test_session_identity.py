from backend.session_identity import (
    SESSION_MAIN_ID,
    conversation_id_to_session_id,
    normalize_or_bridge_session_id,
    session_id_to_conversation_id,
)


def test_legacy_conversation_bridge_roundtrip() -> None:
    conv_id = "conv_123"
    session_id = conversation_id_to_session_id(conv_id)
    assert session_id == "agent:main:web:legacy:conversation:conv_123"
    assert session_id_to_conversation_id(session_id) == conv_id


def test_normalize_or_bridge_session_id_prefers_canonical() -> None:
    canonical = "agent:main:main"
    assert normalize_or_bridge_session_id(canonical) == canonical
    assert normalize_or_bridge_session_id("") == SESSION_MAIN_ID


def test_legacy_conversation_bridge_preserves_colons() -> None:
    conv_id = "custom:tenant:abc"
    session_id = conversation_id_to_session_id(conv_id)
    assert session_id_to_conversation_id(session_id) == conv_id
