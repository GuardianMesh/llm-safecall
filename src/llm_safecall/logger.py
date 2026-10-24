import json
import sys
import time
from typing import Any


def log_json(event: str, **fields: Any):
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event}
    record.update(fields)
    try:
        sys.stderr.write(json.dumps(record) + "\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        # A closed logging destination must not interrupt generation.
        return
