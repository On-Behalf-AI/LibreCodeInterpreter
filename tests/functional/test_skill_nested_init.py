"""Regression test for the orchestrator dedupe-key bug (commit a7c2a57).

When a skill bundle ships multiple `__init__.py` files at different depths
(e.g. `scripts/__init__.py`, `scripts/office/__init__.py`,
`scripts/office/validators/__init__.py`), the orchestrator's mount-dedup
step must keep all of them. Previously `_mount_dedupe_key` used
`sanitize_filename` which strips the directory, collapsing every
`__init__.py` to one key and silently dropping siblings.

The symptom in production was the pptx skill's `pack.py` failing with:

    ImportError: cannot import name 'DOCXSchemaValidator' from 'validators'

because `validators/__init__.py` (the only one with content) was the loser
of the dedup race.

This test reproduces a minimal version: a fake skill with two
`pkg/__init__.py` files at different depths. With the bug, the inner
`__init__.py` never lands in /mnt/data and the import fails. With the
fix, both files mount and the import succeeds.
"""

import pytest


SKILL_FILES = [
    # Outer marker package — content matters: it imports the inner symbol
    ("pkg/__init__.py", b"from .sub import answer\n"),
    # Inner marker package — exposes the symbol the outer __init__.py imports
    ("pkg/sub/__init__.py", b"from .core import answer\n"),
    # The actual function. Putting it three levels deep forces the dedup
    # key to be different from the basename for every __init__.py.
    ("pkg/sub/core.py", b"def answer():\n    return 42\n"),
]


class TestSkillNestedInitFiles:
    """Verify skill bundles with multiple `__init__.py` files mount intact."""

    @pytest.mark.asyncio
    async def test_nested_init_files_all_mount(
        self, async_client, auth_headers, unique_entity_id
    ):
        """All __init__.py files at different depths must reach /mnt/data."""
        # Upload as a skill (kind=skill triggers the agent-file path)
        files_payload = [
            ("files", (path, content, "application/octet-stream"))
            for path, content in SKILL_FILES
        ]
        upload = await async_client.post(
            "/upload",
            headers={"x-api-key": auth_headers["x-api-key"]},
            files=files_payload,
            data={"kind": "skill", "entity_id": unique_entity_id, "read_only": "1"},
        )
        assert upload.status_code == 200, upload.text
        upload_result = upload.json()
        assert upload_result["succeeded"] == len(SKILL_FILES)
        session_id = upload_result["storage_session_id"]

        # Build the explicit file refs the orchestrator will dedupe
        file_refs = [
            {
                "id": entry["fileId"],
                "storage_session_id": session_id,
                "name": entry["filename"],
            }
            for entry in upload_result["files"]
        ]

        # Execute code that exercises the full import chain
        execute = await async_client.post(
            "/exec",
            headers=auth_headers,
            json={
                "lang": "py",
                "code": (
                    "import sys\n"
                    "sys.path.insert(0, '/mnt/data')\n"
                    "import os\n"
                    "for p in ['/mnt/data/pkg/__init__.py',\n"
                    "          '/mnt/data/pkg/sub/__init__.py',\n"
                    "          '/mnt/data/pkg/sub/core.py']:\n"
                    "    print(p, '→', 'OK' if os.path.exists(p) else 'MISSING')\n"
                    "from pkg import answer\n"
                    "print('answer():', answer())\n"
                ),
                "session_id": session_id,
                "files": file_refs,
            },
        )
        assert execute.status_code == 200, execute.text
        result = execute.json()
        stdout = result.get("stdout", "")

        # Both __init__.py files must be physically present
        assert "/mnt/data/pkg/__init__.py → OK" in stdout, (
            f"Outer __init__.py missing — dedup bug present. stdout:\n{stdout}"
        )
        assert "/mnt/data/pkg/sub/__init__.py → OK" in stdout, (
            f"Inner __init__.py missing — dedup bug present. stdout:\n{stdout}"
        )
        # And the import chain must actually resolve
        assert "answer(): 42" in stdout, (
            f"Nested import failed — sibling __init__.py was dropped. stdout:\n{stdout}"
        )

    @pytest.mark.asyncio
    async def test_dedupe_keeps_distinct_relative_paths(
        self, async_client, auth_headers, unique_entity_id
    ):
        """Same basename at different depths must not collide.

        Uploads two siblings both named `config.py` at different levels.
        With the basename-only dedup bug both would map to `config.py` and
        the second would be dropped. With the fix both survive.
        """
        files = [
            ("a/config.py", b"VALUE = 'outer'\n"),
            ("a/b/config.py", b"VALUE = 'inner'\n"),
        ]
        files_payload = [
            ("files", (path, content, "application/octet-stream"))
            for path, content in files
        ]
        upload = await async_client.post(
            "/upload",
            headers={"x-api-key": auth_headers["x-api-key"]},
            files=files_payload,
            data={"kind": "skill", "entity_id": unique_entity_id, "read_only": "1"},
        )
        assert upload.status_code == 200, upload.text
        upload_result = upload.json()
        session_id = upload_result["storage_session_id"]

        file_refs = [
            {
                "id": entry["fileId"],
                "storage_session_id": session_id,
                "name": entry["filename"],
            }
            for entry in upload_result["files"]
        ]

        execute = await async_client.post(
            "/exec",
            headers=auth_headers,
            json={
                "lang": "py",
                "code": (
                    "with open('/mnt/data/a/config.py') as f: print('outer:', f.read().strip())\n"
                    "with open('/mnt/data/a/b/config.py') as f: print('inner:', f.read().strip())\n"
                ),
                "session_id": session_id,
                "files": file_refs,
            },
        )
        assert execute.status_code == 200, execute.text
        stdout = execute.json().get("stdout", "")
        assert "outer: VALUE = 'outer'" in stdout, stdout
        assert "inner: VALUE = 'inner'" in stdout, stdout
