from app.preferences import PreferenceStore
from app.schemas import PreferenceUpdate, RewriteMode


def test_preferences_are_versioned_persistent_and_reversible(tmp_path):
    store = PreferenceStore(tmp_path / "preferences.json")
    original = store.get("user-a")
    updated = store.update("user-a", PreferenceUpdate(mode=RewriteMode.style, style_prompt="轻松讲解"))

    assert original.version == 1
    assert updated.version == 2
    assert updated.mode == RewriteMode.style
    assert PreferenceStore(tmp_path / "preferences.json").get("user-a").style_prompt == "轻松讲解"

    restored = store.undo("user-a")
    assert restored.version == 3
    assert restored.mode == RewriteMode.filter
