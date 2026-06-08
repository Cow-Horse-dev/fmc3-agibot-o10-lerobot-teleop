#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pickle
import struct
import sys
import traceback
from typing import Any


def _read_message(stream) -> Any | None:
    size_bytes = stream.read(4)
    if not size_bytes:
        return None
    if len(size_bytes) != 4:
        raise EOFError("Incomplete request size header")
    size = struct.unpack(">I", size_bytes)[0]
    payload = stream.read(size)
    if len(payload) != size:
        raise EOFError("Incomplete request payload")
    return pickle.loads(payload)  # nosec


def _write_message(stream, payload: Any) -> None:
    data = pickle.dumps(payload)
    stream.write(struct.pack(">I", len(data)))
    stream.write(data)
    stream.flush()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenPI JAX policy worker")
    parser.add_argument("--checkpoint-dir", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--default-prompt", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    protocol_stdout = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr

    from openpi.policies import policy_config
    from openpi.training import config as openpi_config

    config = openpi_config.get_config(args.config)
    policy = policy_config.create_trained_policy(
        config,
        args.checkpoint_dir,
        default_prompt=args.default_prompt,
    )

    while True:
        request = _read_message(sys.stdin.buffer)
        if request is None:
            return 0
        try:
            if (
                isinstance(request, dict)
                and "observation" in request
                and "sample_kwargs" in request
            ):
                observation = request["observation"]
                sample_kwargs = request["sample_kwargs"]
            else:
                observation = request
                sample_kwargs = {}
            response = policy.infer(observation, **sample_kwargs)
        except Exception:
            response = {"error": traceback.format_exc()}
        _write_message(protocol_stdout, response)


if __name__ == "__main__":
    raise SystemExit(main())
