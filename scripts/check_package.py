"""Install the built wheel in a clean environment and exercise its public interface."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def run(command, cwd, env, *, expected=0):
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    if result.returncode != expected:
        raise AssertionError(
            f"{command[0]} exited with {result.returncode}, expected {expected}:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PYTHON", "LLM_"))
        and key not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
    }
    env["LLM_PROVIDER"] = "mock"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="safecall-consumer-") as temporary:
        root = Path(temporary)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(environment)
        binary = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "--python",
                str(binary),
                "install",
                str(wheel),
            ],
            root,
            env,
        )
        source = r'''
import importlib.util
from pathlib import Path
from pydantic import BaseModel
import llm_safecall
from llm_safecall import MockProvider, SafeCall
assert Path(llm_safecall.__file__).resolve().is_relative_to(Path.cwd())
assert importlib.util.find_spec("openai") is None
assert importlib.util.find_spec("anthropic") is None
assert SafeCall(MockProvider()).generate("Hello") == "Mock response: Hello"
class FlightPlan(BaseModel):
    origin: str
    destination: str
    depart_date: str
result = SafeCall(MockProvider(), output=FlightPlan).generate("Plan a flight as JSON")
assert result.origin == "Berlin"
assert result._report.input_tokens is not None
'''
        run([str(binary), "-c", source], root, env)
        cli = environment / ("Scripts/llm-safecall.exe" if os.name == "nt" else "bin/llm-safecall")
        assert run([str(cli), "--help"], root, env).stdout.startswith("usage:")
        assert run([str(cli), "--prompt", "Hello"], root, env).stdout == "Mock response: Hello\n"
        structured = run(
            [
                str(cli),
                "--prompt",
                "Plan a flight as JSON",
                "--schema",
                "origin:str,destination:str",
            ],
            root,
            env,
        )
        assert json.loads(structured.stdout) == {"origin": "Berlin", "destination": "Tokyo"}
        run([str(cli)], root, env, expected=2)
        run([str(cli), "--prompt", "Hello", "--schema", "invalid"], root, env, expected=1)
        run([str(binary), "-m", "llm_safecall", "--prompt", "Hello"], root, env)
        run(
            [str(binary), "-m", "llm_safecall", "--prompt", "Hello", "--policy", "missing.yml"],
            root,
            env,
            expected=1,
        )
    print("Installed wheel and CLI checks passed without provider SDKs.")


if __name__ == "__main__":
    main()
