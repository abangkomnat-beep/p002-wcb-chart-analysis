from pathlib import Path

from tools import migrate_thai_output_layout as migration
from tools import country_first_output


def _article(images):
    return "---\nasset: xauusd\n---\n" + "\n".join(f"![chart]({name})" for name in images) + "\n"


def _seed(root: Path):
    day = root / "output/07-09-2026"
    for _, _, folder, template in migration.LAYOUT:
        article = day / folder / template.format(date="2026-09-07")
        article.parent.mkdir(parents=True, exist_ok=True)
        asset = article.stem.split("-")[0]
        image = f"{asset}-chart.webp"
        article.write_text(_article([image]), encoding="utf-8")
        (article.parent / image).write_bytes(b"webp fixture " + image.encode())
    (day / "TH-Thailand").mkdir()
    (day / "TH-Thailand/STATUS.md").write_text("placeholder\n", encoding="utf-8")


def test_prepare_and_apply_moves_every_legacy_file_into_country_layout(tmp_path):
    _seed(tmp_path)
    tx = migration.prepare(tmp_path, "2026-09-07", "layout-r1")
    assert (tx / "prepared/TH-Thailand/D/XAUUSD/P002-20260907-TH-D-XAUUSD-article.md").is_file()
    result = migration.apply(tmp_path, "2026-09-07", "layout-r1")
    day = tmp_path / "output/07-09-2026"
    assert result["status"] == "COMMITTED"
    assert result["articles"] == 6 and result["images"] == 6
    assert not (day / "D-โครงสร้างกราฟ").exists()
    target = day / "TH-Thailand/L/EURUSD/P002-20260907-TH-L-EURUSD-article.md"
    assert target.is_file()
    assert "P002-20260907-TH-L-EURUSD-img01-chart.webp" in target.read_text(encoding="utf-8")
    assert (tx / "backup/D-โครงสร้างกราฟ/xauusd.md").is_file()


def test_prepare_refuses_an_unmapped_legacy_file(tmp_path):
    _seed(tmp_path)
    extra = tmp_path / "output/07-09-2026/L-Forex-Daily/keep-me.txt"
    extra.write_text("unmapped", encoding="utf-8")
    try:
        migration.prepare(tmp_path, "2026-09-07", "layout-r1")
    except migration.MigrationError as exc:
        assert "unmapped legacy files" in str(exc)
    else:
        raise AssertionError("unmapped file was accepted")


def test_tuesday_layout_moves_the_four_approved_articles(tmp_path):
    day = tmp_path / "output/08-09-2026"
    for _, _, folder, template in migration.layout_for_date("2026-09-08"):
        article = day / folder / template.format(date="2026-09-08")
        article.parent.mkdir(parents=True, exist_ok=True)
        image = f"{article.stem}-chart.webp"
        article.write_text(_article([image]), encoding="utf-8")
        (article.parent / image).write_bytes(b"webp fixture " + image.encode())

    migration.prepare(tmp_path, "2026-09-08", "tuesday-layout-r1")
    result = migration.apply(tmp_path, "2026-09-08", "tuesday-layout-r1")

    assert result["status"] == "COMMITTED"
    assert result["articles"] == 4
    root = tmp_path / "output/08-09-2026/TH-Thailand"
    assert (root / "E/XAUUSD/P002-20260908-TH-E-XAUUSD-article.md").is_file()
    assert (root / "M/BTCUSD/P002-20260908-TH-M-BTCUSD-article.md").is_file()
    assert (root / "L/GBPUSD/P002-20260908-TH-L-GBPUSD-article.md").is_file()
    assert (root / "L/AUDUSD/P002-20260908-TH-L-AUDUSD-article.md").is_file()


def test_canonical_hash_is_the_rewritten_article_while_original_hash_is_preserved(tmp_path):
    _seed(tmp_path)
    tx = migration.prepare(tmp_path, "2026-09-07", "canonical-r1")
    journal = __import__("json").loads((tx / "journal.json").read_text(encoding="utf-8"))
    entry = journal["articles"][0]
    prepared = tx / "prepared/TH-Thailand/D/XAUUSD/P002-20260907-TH-D-XAUUSD-article.md"
    assert entry["source_original_sha256"] != entry["source_canonical_sha256"]
    assert entry["source_canonical_sha256"] == migration._sha(prepared.read_bytes())


def test_refresh_displaces_existing_thailand_and_rerun_is_idempotent(tmp_path):
    _seed(tmp_path)
    migration.prepare(tmp_path, "2026-09-07", "refresh-r1")
    migration.apply(tmp_path, "2026-09-07", "refresh-r1")
    day = tmp_path / "output/07-09-2026"
    for _, _, folder, template in migration.LAYOUT:
        article = day / folder / template.format(date="2026-09-07")
        article.parent.mkdir(parents=True, exist_ok=True)
        image = f"{article.stem}-next.webp"
        article.write_text(_article([image]), encoding="utf-8")
        (article.parent / image).write_bytes(b"next")
    migration.prepare(tmp_path, "2026-09-07", "refresh-r2")
    assert migration.apply(tmp_path, "2026-09-07", "refresh-r2")["status"] == "COMMITTED"
    assert (tmp_path / "work/localization/07-09-2026/migrations/refresh-r2/displaced/TH-Thailand").is_dir()
    assert migration.apply(tmp_path, "2026-09-07", "refresh-r2")["status"] == "COMMITTED"


def test_final_journal_failure_restores_target_and_legacy_sources(tmp_path, monkeypatch):
    _seed(tmp_path)
    tx = migration.prepare(tmp_path, "2026-09-07", "recover-r1")
    original = migration._write_journal

    def fail_commit(path, journal):
        if journal.get("state") == "COMMITTED":
            raise OSError("simulated journal failure")
        return original(path, journal)

    monkeypatch.setattr(migration, "_write_journal", fail_commit)
    try:
        migration.apply(tmp_path, "2026-09-07", "recover-r1")
    except OSError:
        pass
    else:
        raise AssertionError("commit failure was accepted")
    assert (tmp_path / "output/07-09-2026/D-โครงสร้างกราฟ/xauusd.md").is_file()
    assert not (tmp_path / "output/07-09-2026/TH-Thailand/D/XAUUSD").exists()
    monkeypatch.setattr(migration, "_write_journal", original)
    assert migration.recover(tmp_path, "2026-09-07", "recover-r1")["status"] == "ROLLED_BACK"


def test_country_first_repair_is_idempotent_for_canonical_image_names(tmp_path):
    lane = tmp_path / "output/09-09-2026/TH-Thailand/E/XAUUSD"
    lane.mkdir(parents=True)
    article = lane / "P002-20260909-TH-E-XAUUSD-article.md"
    image = lane / "P002-20260909-TH-E-XAUUSD-img01-chart.webp"
    article.write_text(f"---\nasset: xauusd\n---\n![chart]({image.name})\n", encoding="utf-8")
    image.write_bytes(b"webp")
    first = country_first_output.repair_canonical_day(
        output_root=tmp_path / "output", work_root=tmp_path / "work", business_date="2026-09-09")
    names_after_first = sorted(p.name for p in lane.glob("*.webp"))
    second = country_first_output.repair_canonical_day(
        output_root=tmp_path / "output", work_root=tmp_path / "work", business_date="2026-09-09")
    assert first["repaired"] == 0
    assert second["repaired"] == 0
    assert names_after_first == [image.name]


def test_recovery_refuses_to_delete_foreign_file_from_replacement_target(tmp_path):
    day = tmp_path / "output/07-09-2026"
    target = day / "TH-Thailand"
    (target / "L/EURUSD").mkdir(parents=True)
    (target / "L/EURUSD/article.md").write_text("installed", encoding="utf-8")
    (target / "foreign.txt").write_text("do not delete", encoding="utf-8")
    tx = tmp_path / "work/localization/07-09-2026/migrations/foreign-r1"
    displaced = tx / "displaced/TH-Thailand"
    displaced.mkdir(parents=True)
    (displaced / "old.md").write_text("old", encoding="utf-8")
    journal_path = tx / "journal.json"
    journal = {"state": "APPLYING", "installed_files": ["L/EURUSD/article.md"], "legacy_moves": []}
    journal_path.write_text("{}", encoding="utf-8")
    try:
        migration._rollback(day, tx, journal_path, journal)
    except migration.MigrationError as exc:
        assert "foreign files" in str(exc)
    else:
        raise AssertionError("foreign file was treated as migration-owned")
    assert (target / "foreign.txt").read_text(encoding="utf-8") == "do not delete"
