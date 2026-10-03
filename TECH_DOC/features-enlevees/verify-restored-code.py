"""Verify exact upstream source text for restored units, without network or ORM."""

import argparse
import ast
import hashlib
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UNITS = [
    ("C", "webview/validators.py", "deploy/Laboutik/validators.py",
     "DataAchatDepuisClientValidator", "validate_articles"),
    ("D", "webview/views.py", "deploy/Laboutik/views.py", None, "index"),
    ("D", "webview/views.py", "deploy/Laboutik/views.py", None, "preparation"),
    ("D", "webview/views.py", "deploy/Laboutik/views.py", None, "paiement"),
    ("F", "fedow_connect/fedow_api.py", "deploy/Laboutik/fedow_api.py",
     "FedowAPI", "send_assets_from_cashless"),
]


def unit_text(source, class_name, function_name):
    tree = ast.parse(source)
    parent = tree if class_name is None else next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    node = next(node for node in parent.body
                if isinstance(node, ast.FunctionDef) and node.name == function_name)
    first_line = min([node.lineno] + [decorator.lineno for decorator in node.decorator_list])
    # AST only locates the original lines. Never regenerate or normalize source.
    return "".join(source.splitlines(keepends=True)[first_line - 1:node.end_lineno])


def verify(archive_path):
    catalog = json.loads((ROOT / "deploy/source/image-sources.json").read_bytes())
    reference = catalog["laboutik"]
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if digest != reference["archive_sha256"]:
        raise ValueError("Upstream archive SHA-256 mismatch")
    results = []
    with tarfile.open(archive_path, "r:gz") as archive:
        members = {"/".join(Path(member.name).parts[1:]): member
                   for member in archive.getmembers() if member.isfile()}
        for feature, upstream_path, local_path, class_name, function_name in UNITS:
            original = archive.extractfile(members[upstream_path]).read().decode("utf-8")
            current = (ROOT / local_path).read_bytes().decode("utf-8")
            original_unit = unit_text(original, class_name, function_name).encode("utf-8")
            current_unit = unit_text(current, class_name, function_name).encode("utf-8")
            if original_unit != current_unit:
                raise ValueError("Restored unit differs from TiBillet: " + local_path + ":" + function_name)
            results.append({
                "feature": feature, "upstream_path": upstream_path, "local_path": local_path,
                "class_name": class_name, "function_name": function_name,
                "byte_length": len(current_unit),
                "upstream_sha256": hashlib.sha256(original_unit).hexdigest(),
                "restored_sha256": hashlib.sha256(current_unit).hexdigest(),
                "exact_text_match": True,
            })
    return {
        "scope": "Only the listed units; shared files retain other customizations.",
        "reference_repository": reference["repository"], "reference_commit": reference["commit"],
        "reference_image": reference["image"], "archive_sha256": digest, "units": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--receipt", type=Path, help="Explicit output path for a verification receipt")
    args = parser.parse_args()
    reference = json.loads((ROOT / "deploy/source/image-sources.json").read_bytes())["laboutik"]
    archive_path = args.archive or ROOT / ".context/source-cache" / (
        reference["repository"].replace("/", "-") + "-" + reference["commit"] + ".tar.gz"
    )
    result = verify(archive_path)
    serialized = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.receipt:
        args.receipt.write_text(serialized, encoding="utf-8")
    print("TiBillet archive verified; " + str(len(result["units"])) + " restored units match exactly.")
