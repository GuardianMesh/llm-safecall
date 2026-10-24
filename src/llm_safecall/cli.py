from __future__ import annotations

import argparse
import json
import sys

from pydantic import create_model

from .env import from_env
from .policy_yaml import load_policy


class _UsageError(ValueError):
    """A fixed CLI message that contains no provider or file contents."""


def _schema(value: str):
    types = {"str": str, "int": int, "float": float, "bool": bool}
    fields = {}
    for part in value.split(","):
        pieces = [piece.strip() for piece in part.split(":")]
        if len(pieces) != 2:
            raise _UsageError("Schema fields must use name:type")
        name, kind = pieces
        if not name.isidentifier() or name.startswith("_") or name in fields:
            raise _UsageError("Schema field names must be unique public identifiers")
        if kind not in types:
            raise _UsageError("Schema types must be str, int, float, or bool")
        fields[name] = (types[kind], ...)
    return create_model("CliSchema", **fields)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="llm-safecall", description="Model calls with policy checks"
    )
    parser.add_argument("--prompt", "-p", required=True, help="Prompt text")
    parser.add_argument("--policy", help="Path to policy.yml")
    parser.add_argument("--schema", help="Comma-separated fields, e.g. title:str,count:int")
    parser.add_argument(
        "--fail-safe", action="store_true", help="Return a fallback on generation errors"
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        output = _schema(args.schema) if args.schema is not None else None
        safe = from_env(output=output)
        if args.policy:
            try:
                safe.policy = load_policy(args.policy)
            except Exception as error:
                raise _UsageError(
                    "Could not load --policy; check the file path, YAML keys, and value types"
                ) from error
        safe.fail_safe = args.fail_safe
        result = safe.generate(args.prompt)
        if hasattr(result, "model_dump"):
            print(json.dumps(result.model_dump(mode="json"), indent=2))
        else:
            print(str(result))
    except Exception as error:
        # Only locally defined usage errors have messages suitable for stderr.
        message = str(error) if isinstance(error, _UsageError) else type(error).__name__
        print(f"llm-safecall: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
