#!/usr/bin/env python3
"""Deploy one immutable Test candidate to the single Smoke EC2 via SSM."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def aws(*args: str) -> dict[str, object]:
    result = subprocess.run(
        ["aws", *args, "--region", "eu-west-3", "--output", "json"],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def wait_for_ssm(command_id: str, instance_id: str) -> None:
    for _ in range(180):
        try:
            result = aws("ssm", "get-command-invocation", "--command-id", command_id, "--instance-id", instance_id)
        except subprocess.CalledProcessError as error:
            if "InvocationDoesNotExist" in error.stderr:
                time.sleep(5)
                continue
            raise
        status = result.get("Status")
        if status == "Success":
            return
        if status not in {"Pending", "InProgress", "Delayed"}:
            raise RuntimeError(f"Smoke SSM command {command_id} failed: {status}")
        time.sleep(5)
    raise RuntimeError(f"Smoke SSM command {command_id} timed out")


def send(instance_id: str, document: str, parameters: dict[str, object]) -> None:
    response = aws(
        "ssm", "send-command", "--document-name", document,
        "--instance-ids", instance_id, "--parameters", json.dumps(parameters),
    )
    command_id = response["Command"]["CommandId"]
    print(f"Smoke SSM command submitted: {command_id}", flush=True)
    wait_for_ssm(command_id, instance_id)


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"{name} is required")
    return value


def put_immutable(bucket: str, key: str, path: Path) -> None:
    try:
        aws("s3api", "put-object", "--bucket", bucket, "--key", key,
            "--body", str(path), "--if-none-match", "*")
    except subprocess.CalledProcessError as error:
        if "PreconditionFailed" not in error.stderr and "412" not in error.stderr:
            raise
        with tempfile.TemporaryDirectory() as directory:
            prior = Path(directory) / "manifest.json"
            subprocess.run(["aws", "s3", "cp", "--only-show-errors", f"s3://{bucket}/{key}", str(prior), "--region", "eu-west-3"], check=True)
            if prior.read_bytes() != path.read_bytes():
                raise ValueError(f"immutable S3 object {key} already holds different bytes") from error


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: deploy-smoke-candidate.py MANIFEST.json")
    path = Path(sys.argv[1])
    manifest = json.loads(path.read_text(encoding="utf-8"))
    commit = manifest["fork_commit"]
    if manifest["gala_slug"] != "gala-smoke" or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("manifest is not a fixed Smoke commit")
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if source_commit != commit:
        raise ValueError("Smoke candidate differs from CodePipeline source revision")
    identity = aws("sts", "get-caller-identity")
    if identity.get("Account") != "318629836660":
        raise ValueError("wrong AWS account")
    instance_id = required("SMOKE_INSTANCE_ID")
    if not re.fullmatch(r"i-[0-9a-f]{8,17}", instance_id):
        raise ValueError("invalid Smoke instance ID")
    bucket = required("RELEASE_BUCKET")
    document = required("SMOKE_DEPLOY_DOCUMENT")

    key = f"releases/gala-smoke/smoke-{commit}.json"
    put_immutable(bucket, key, path)
    uri = f"s3://{bucket}/{key}"
    print(f"Immutable Smoke manifest: {uri}", flush=True)
    send(instance_id, document, {"ReleaseManifestUri": [uri]})
    # This marker is created only after the complete SSM deployment and local
    # healthcheck have succeeded. Production validation trusts the marker,
    # never a build-only candidate or an uploaded-but-failed Smoke manifest.
    put_immutable(bucket, f"test-validated/smoke-{commit}.json", path)
    print(f"Smoke deployment succeeded: commit={commit} instance={instance_id}")


if __name__ == "__main__":
    main()
