"""Verify exact upstream source text for restored units, without network or ORM."""

import argparse
import ast
import hashlib
import json
import re
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UNITS = [
    ("C", "webview/validators.py", "deploy/Laboutik/validators.py",
     "DataAchatDepuisClientValidator", "validate_articles"),
    ("D", "webview/views.py", "deploy/Laboutik/views.py", None, "index"),
    ("D", "webview/views.py", "deploy/Laboutik/views.py", None, "preparation"),
    ("D", "webview/views.py", "deploy/Laboutik/views.py", None, "paiement"),
    ("F", "fedow_connect/fedow_api.py", None,
     "FedowAPI", "send_assets_from_cashless"),
    ("E", "fedow_connect/fedow_api.py", None, None, "_get"),
    ("E", "fedow_connect/fedow_api.py", None, None, "_post"),
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


def verify(archive_path, fedow_archive_path=None):
    catalog = json.loads((ROOT / "deploy/source/image-sources.json").read_bytes())
    reference = catalog["laboutik"]
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if digest != reference["archive_sha256"]:
        raise ValueError("Upstream archive SHA-256 mismatch")
    laboutik_compose = (ROOT / "deploy/Laboutik/docker-compose.yml").read_text()
    laboutik_targets = re.findall(r"^\s*-\s+[^:\s]+:([^:\s]+)", laboutik_compose, re.MULTILINE)
    api_target = "/DjangoFiles/fedow_connect/fedow_api.py"
    if any(target.rstrip("/") == api_target
           or api_target.startswith(target.rstrip("/") + "/")
           for target in laboutik_targets):
        raise ValueError("LaBoutik Fedow API is still replaced by a mount")
    if (ROOT / "deploy/Laboutik/fedow_api.py").exists():
        raise ValueError("Legacy LaBoutik Fedow API still exists in the active deployment")
    results = []
    retained_files = []
    with tarfile.open(archive_path, "r:gz") as archive:
        members = {"/".join(Path(member.name).parts[1:]): member
                   for member in archive.getmembers() if member.isfile()}
        for feature, upstream_path, local_path, class_name, function_name in UNITS:
            original = archive.extractfile(members[upstream_path]).read().decode("utf-8")
            current = (ROOT / local_path).read_bytes().decode("utf-8") if local_path else original
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
                "source_provider": "local_overlay" if local_path else "native_image",
            })
        recipe = json.loads((ROOT / "TECH_DOC/features-enlevees/LaBoutik-ecarts-herites/retained-E-source.json").read_bytes())
        if recipe["reference"] != reference:
            raise ValueError("Retained E patch uses another LaBoutik reference")
        for file in recipe["files"]:
            native = archive.extractfile(members[file["upstream_path"]]).read().decode("utf-8")
            expected = native
            for replacement in file["replacements"]:
                if expected.count(replacement["old"]) != 1:
                    raise ValueError("Ambiguous retained E source span")
                expected = expected.replace(replacement["old"], replacement["new"], 1)
            expected = (file["notice"] + expected).encode("utf-8")
            current = (ROOT / file["local_path"]).read_bytes()
            if current != expected:
                raise ValueError("Unexpected difference outside retained E: " + file["local_path"])
            retained_files.append({
                "upstream_path": file["upstream_path"], "local_path": file["local_path"],
                "upstream_sha256": hashlib.sha256(native.encode("utf-8")).hexdigest(),
                "restored_sha256": hashlib.sha256(current).hexdigest(),
                "exact_except_declared_E_and_notice": True,
            })
        native_api = archive.extractfile(members["fedow_connect/fedow_api.py"]).read()
    fedow = catalog["fedow"]
    fedow_archive_path = fedow_archive_path or cached_archive(fedow)
    fedow_digest = hashlib.sha256(fedow_archive_path.read_bytes()).hexdigest()
    if fedow_digest != fedow["archive_sha256"]:
        raise ValueError("Fedow archive SHA-256 mismatch")
    compose = (ROOT / "deploy/Fedow/docker-compose.yml").read_text()
    targets = re.findall(r"^\s*-\s+[^:\s]+:([^:\s]+)", compose, re.MULTILINE)
    native_path = "fedow_core/serializers.py"
    if "/home/fedow/Fedow/" + native_path in targets:
        raise ValueError("Fedow serializer is still replaced by a mount")
    if (ROOT / "deploy/Fedow/custom_patches/fedow_core/serializers.py").exists():
        raise ValueError("Legacy G serializer still exists in the active deployment")
    dashboard_target = "/home/fedow/Fedow/fedow_dashboard"
    if any(target.rstrip("/") == dashboard_target
           or target.startswith(dashboard_target + "/")
           or dashboard_target.startswith(target.rstrip("/") + "/")
           for target in targets):
        raise ValueError("Fedow dashboard is still replaced by a mount")
    if any(path.is_file() for path in
           (ROOT / "deploy/Fedow/custom_patches/fedow_dashboard").rglob("*")):
        raise ValueError("Legacy H dashboard still exists in the active deployment")
    native_dashboard_files = []
    with tarfile.open(fedow_archive_path, "r:gz") as archive:
        member = next(member for member in archive.getmembers()
                      if member.isfile() and "/".join(Path(member.name).parts[1:]) == native_path)
        native = archive.extractfile(member).read()
        settings_member = next(member for member in archive.getmembers()
                               if member.isfile() and "/".join(Path(member.name).parts[1:]) == "fedowallet_django/settings.py")
        native_settings = archive.extractfile(settings_member).read().decode("utf-8")
        for member in archive.getmembers():
            path = "/".join(Path(member.name).parts[1:])
            if not member.isfile() or not path.startswith("fedow_dashboard/"):
                continue
            data = archive.extractfile(member).read()
            if path.startswith("fedow_dashboard/templates/"):
                template_path = path[len("fedow_dashboard/templates/"):]
                if (ROOT / "deploy/source/admin-templates" / template_path).exists():
                    raise ValueError("Shared template directory overrides dashboard: " + template_path)
            native_dashboard_files.append({
                "upstream_path": path, "upstream_sha256": hashlib.sha256(data).hexdigest(),
                "byte_length": len(data),
            })
    def database_text(source):
        node = next(node for node in ast.parse(source).body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "DATABASES" for target in node.targets))
        return "".join(source.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    restored_database = database_text((ROOT / "deploy/Fedow/settings.py").read_text())
    if restored_database != database_text(native_settings):
        raise ValueError("Fedow DATABASES differs from the exact native SQLite source")
    return {
        "scope": "LaBoutik native files except declared E spans/notices, native Fedow API selected by Compose, previous C/D/F/G/H/I restorations; no live runtime verification.",
        "reference_repository": reference["repository"], "reference_commit": reference["commit"],
        "reference_image": reference["image"], "archive_sha256": digest, "units": results,
        "retained_laboutik_files": retained_files,
        "native_laboutik_api": {
            "upstream_path": "fedow_connect/fedow_api.py",
            "upstream_sha256": hashlib.sha256(native_api).hexdigest(),
            "source_override_removed": True,
        },
        "native_image_files": [{
            "feature": "G", "upstream_path": native_path,
            "reference_repository": fedow["repository"], "reference_commit": fedow["commit"],
            "reference_image": fedow["image"], "archive_sha256": fedow_digest,
            "upstream_sha256": hashlib.sha256(native).hexdigest(),
            "byte_length": len(native), "source_override_removed": True,
        }],
        "native_database_settings": {
            "feature": "I", "upstream_path": "fedowallet_django/settings.py",
            "native_commit": fedow["commit"], "exact_text_match": True,
            "sha256": hashlib.sha256(restored_database.encode("utf-8")).hexdigest(),
        },
        "native_dashboard": {
            "feature": "H", "reference_repository": fedow["repository"],
            "reference_commit": fedow["commit"], "reference_image": fedow["image"],
            "archive_sha256": fedow_digest, "source_override_removed": True,
            "shared_template_override_absent": True, "files": native_dashboard_files,
        },
    }


def cached_archive(reference):
    return ROOT / ".context/source-cache" / (
        reference["repository"].replace("/", "-") + "-" + reference["commit"] + ".tar.gz"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--fedow-archive", type=Path)
    parser.add_argument("--receipt", type=Path, help="Explicit output path for a verification receipt")
    args = parser.parse_args()
    reference = json.loads((ROOT / "deploy/source/image-sources.json").read_bytes())["laboutik"]
    archive_path = args.archive or cached_archive(reference)
    result = verify(archive_path, args.fedow_archive)
    serialized = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.receipt:
        args.receipt.write_text(serialized, encoding="utf-8")
    print("TiBillet archives verified; " + str(len(result["units"])) +
          " restored units match exactly; LaBoutik differs only by declared E spans/notices; native APIs and Fedow dashboard have no override.")
