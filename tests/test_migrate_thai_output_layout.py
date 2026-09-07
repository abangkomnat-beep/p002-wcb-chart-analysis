from pathlib import Path

from tools import migrate_thai_output_layout as migration


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
    assert (tx / "prepared/TH-Thailand/D/XAUUSD/article.md").is_file()
    result = migration.apply(tmp_path, "2026-09-07", "layout-r1")
    day = tmp_path / "output/07-09-2026"
    assert result["status"] == "COMMITTED"
    assert result["articles"] == 6 and result["images"] == 6
    assert not (day / "D-โครงสร้างกราฟ").exists()
    assert (day / "TH-Thailand/L/EURUSD/article.md").is_file()
    assert "images/eurusd-chart.webp" in (day / "TH-Thailand/L/EURUSD/article.md").read_text(encoding="utf-8")
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
