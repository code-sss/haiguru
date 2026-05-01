from pathlib import Path

import llm_factory


class _DummyEmbedding:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_resolve_local_hf_model_path_prefers_refs_main_snapshot(tmp_path):
    cache_root = tmp_path / "models"
    repo_dir = cache_root / "models--BAAI--bge-m3"
    good_snapshot = repo_dir / "snapshots" / "good-revision"
    stale_snapshot = repo_dir / "snapshots" / "stale-revision"

    good_snapshot.mkdir(parents=True)
    stale_snapshot.mkdir(parents=True)
    (good_snapshot / "config.json").write_text("{}", encoding="utf-8")
    (stale_snapshot / "README.md").write_text("stale", encoding="utf-8")
    (repo_dir / "refs").mkdir(parents=True)
    (repo_dir / "refs" / "main").write_text("good-revision\n", encoding="utf-8")

    resolved = llm_factory._resolve_local_hf_model_path("BAAI/bge-m3", str(cache_root))

    assert resolved == str(good_snapshot)


def test_make_embed_model_uses_cached_snapshot_locally(tmp_path, monkeypatch):
    cache_root = tmp_path / "models"
    snapshot_dir = cache_root / "models--BAAI--bge-m3" / "snapshots" / "revision"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "config.json").write_text("{}", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_huggingface_embedding(**kwargs):
        captured.update(kwargs)
        return _DummyEmbedding(**kwargs)

    monkeypatch.setattr(
        "llama_index.embeddings.huggingface.HuggingFaceEmbedding",
        fake_huggingface_embedding,
    )

    model = llm_factory.make_embed_model(
        "BAAI/bge-m3",
        device="cpu",
        model_path=str(cache_root),
    )

    assert isinstance(model, _DummyEmbedding)
    assert Path(captured["model_name"]) == snapshot_dir
    assert captured["local_files_only"] is True
    assert captured["cache_folder"] == str(cache_root)
    assert captured["device"] == "cpu"