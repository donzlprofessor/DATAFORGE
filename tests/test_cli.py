from typer.testing import CliRunner

from dataforge.cli import app

runner = CliRunner()


def test_default_paths_and_repeat(raw_order, write_csv, tmp_path, monkeypatch):
    source = write_csv([raw_order])
    monkeypatch.chdir(tmp_path)
    first = runner.invoke(app, ["run", str(source)])
    assert first.exit_code == 0, first.output
    assert "1 inserted, 0 skipped, 0 rejected" in first.output
    for name in ("orders.db", "quality_report.json", "rejected_orders.csv"):
        assert (tmp_path / "artifacts" / name).exists()
    second = runner.invoke(app, ["run", str(source)])
    assert second.exit_code == 0
    assert "0 inserted, 1 skipped" in second.output


def test_custom_paths(raw_order, write_csv, outputs):
    arguments = ["run", str(write_csv([raw_order]))]
    for option, path in outputs.items():
        arguments.extend([f"--{option}", str(path)])
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    assert all(path.exists() for path in outputs.values())


def test_missing_input(tmp_path):
    result = runner.invoke(app, ["run", str(tmp_path / "missing.csv")])
    assert result.exit_code == 1
    assert "Import failed:" in result.output


def test_invalid_schema(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("wrong\nvalue\n")
    result = runner.invoke(app, ["run", str(source)])
    assert result.exit_code == 1
    assert "Missing required columns" in result.output


def test_database_failure(raw_order, write_csv, tmp_path):
    database = tmp_path / "bad.db"
    database.write_text("not a database")
    result = runner.invoke(app, ["run", str(write_csv([raw_order])), "--database", str(database)])
    assert result.exit_code == 1
    assert "Import failed:" in result.output


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
