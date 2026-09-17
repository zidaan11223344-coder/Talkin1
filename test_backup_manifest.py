import json
import hashlib
import bot


def test_full_backup_queues_all_state_files_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DATA_DIR", tmp_path)
    monkeypatch.setattr(bot, "GITHUB_SYNC_ENABLED", True)
    saved = {}
    monkeypatch.setattr(bot, "_github_sync_after_local_save", lambda path, data: saved.__setitem__(str(path), data))
    (tmp_path / "points.json").write_text(json.dumps({"alice": {"points": 10}}), encoding="utf-8")
    (tmp_path / "verified_users.json").write_text(json.dumps({"alice": {"username": "alice"}}), encoding="utf-8")
    (tmp_path / "game_stats.json").write_text(json.dumps({"alice": {"games": {"x": {"plays": 2}}}}), encoding="utf-8")

    queued = bot._queue_github_full_backup()
    manifest_path = str(tmp_path / "backup_manifest.json")
    assert queued == 4
    assert str(tmp_path / "points.json") in saved
    assert str(tmp_path / "verified_users.json") in saved
    assert str(tmp_path / "game_stats.json") in saved
    manifest = saved[manifest_path]
    assert manifest["version"] == 1
    assert manifest["files"]["points.json"]["sha256"] == hashlib.sha256((tmp_path / "points.json").read_bytes()).hexdigest()
    assert "game_stats.json" in manifest["files"]

print("backup manifest: PASS")
