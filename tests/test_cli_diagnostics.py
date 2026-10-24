from llm_safecall.cli import main


def test_schema_diagnostic_explains_accepted_types_without_echoing_input(capsys):
    assert main(["--prompt", "Hello", "--schema", "value:private-input"]) == 1
    message = capsys.readouterr().err
    assert "Schema types must be str, int, float, or bool" in message
    assert "private-input" not in message


def test_policy_diagnostic_does_not_echo_file_contents(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    path = tmp_path / "private-path.yml"
    path.write_text("block_secrets: private-value")
    assert main(["--prompt", "Hello", "--policy", str(path)]) == 1
    message = capsys.readouterr().err
    assert "Could not load --policy" in message
    assert "private-value" not in message
    assert "private-path" not in message
