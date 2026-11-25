from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("cafete", Path(__file__).resolve().parents[1] / "tools/check-cafete-retirement.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class CafeteRetirementTests(unittest.TestCase):
    def responses(self, fault=None):
        metadata = f"gala={module.OLD_SLUG}\nbackup_id={module.BACKUP_ID}\nfedow_sqlite=1\nbackup_format=2\n"
        sums = "".join(f"{hashlib.sha256(metadata.encode()).hexdigest() if name == 'metadata.txt' else 'a' * 64}  {name}\n"
                       for name in sorted(module.FILES))

        def respond(*args):
            operation = args[:2]
            if operation == ("sts", "get-caller-identity"):
                return {"Account": module.ACCOUNT}
            if operation == ("ssm", "get-parameter"):
                return {"Parameter": {"Value": module.OLD_SLUG if fault == "old_active" else module.NEW_SLUG}}
            if operation == ("ec2", "describe-instances"):
                hosts = []
                for identity, slug, state in ((module.OLD_INSTANCE, module.OLD_SLUG, "stopped"),
                                               (module.NEW_INSTANCE, module.NEW_SLUG, "running")):
                    hosts.append({"InstanceId": identity, "State": {"Name": "running" if fault == "old_running" and slug == module.OLD_SLUG else state},
                                  "Tags": [{"Key": k, "Value": v} for k, v in {
                                      "Gala": slug, "Project": "tibillet-gala-paris", "ManagedBy": "terraform"}.items()]})
                return {"Reservations": [{"Instances": hosts}]}
            if operation == ("ec2", "describe-addresses"):
                return {"Addresses": [] if "--filters" in args else [{"InstanceId": module.OLD_INSTANCE if fault == "wrong_eip" else module.NEW_INSTANCE}]}
            if operation == ("ec2", "describe-volumes"):
                return {"Volumes": [{"Encrypted": True, "Size": 40, "Attachments": [{"InstanceId": module.OLD_INSTANCE}]}]}
            if operation == ("ssm", "get-command-invocation"):
                restore = module.RESTORE_COMMAND in args
                content = ("\n".join(f"gala={module.OLD_SLUG} backup_id={module.BACKUP_ID} source={s}" for s in ("lespass_postgres", "laboutik_postgres", "fedow_sqlite"))
                           if restore else f"gala={module.OLD_SLUG} backup_id={module.BACKUP_ID} postgres=2 sqlite=1")
                return {"Status": "Failed" if restore and fault == "failed_restore" else "Success", "ResponseCode": 0,
                        "StandardOutputContent": content, "ExecutionEndDateTime": "2026-11-25T12:10:00Z"}
            if operation == ("s3api", "head-object"):
                return {"ServerSideEncryption": "AES256", "VersionId": "version", "ContentLength": 100,
                        "LastModified": "2026-11-25T12:11:00Z" if fault == "archive_changed" else "2026-11-25T12:07:00Z"}
            if operation == ("s3api", "get-object"):
                filename = args[args.index("--key") + 1].split("/")[-1]
                Path(args[-1]).write_text((metadata + "tampered" if fault == "bad_metadata" else metadata) if filename == "metadata.txt" else sums)
                return {}
            raise AssertionError("unexpected AWS operation")
        return respond

    def test_verified_archive_and_active_replacement_allow_read_only_preflight(self):
        with patch.object(module, "aws", side_effect=self.responses()) as calls:
            module.verify()
        self.assertTrue(all(call.args[1].startswith(("get-", "describe-", "head-")) for call in calls.call_args_list))

    def test_live_old_event_missing_restore_or_modified_archive_block_retirement(self):
        for fault in ("old_active", "old_running", "wrong_eip", "failed_restore", "archive_changed", "bad_metadata"):
            with self.subTest(fault=fault), patch.object(module, "aws", side_effect=self.responses(fault)), self.assertRaises(ValueError):
                module.verify()
