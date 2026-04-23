#!/usr/bin/env python3
"""Fill the Note Interne (internal memo) template with sender/recipient data and body.

Usage:
    python3 fill_note_template.py <template-note-interne.docx> <output.docx> <config.json>

Config JSON format (simple body):
{
    "from": "Jane Doe",
    "to": "Technical Team",
    "cc": "Management",
    "date": "21 avril 2026",
    "subject": "Process update",
    "body": [
        "First paragraph.",
        "Second paragraph with **bold** if needed."
    ],
    "sender": {
        "name": "Jane Doe",
        "title": "Director"
    }
}

Config JSON format (structured sections):
{
    "from": "Jane Doe",
    "to": "Technical Team",
    "cc": "Management",
    "date": "21 avril 2026",
    "subject": "Process update",
    "sections": [
        {
            "title": "Section Title",
            "level": 1,
            "content": [
                {"type": "text", "text": "Paragraph text."},
                {"type": "bullets", "items": ["Item A", "Item B"]},
                {"type": "numbered", "items": ["Step 1", "Step 2"]}
            ]
        }
    ],
    "sender": {
        "name": "Jane Doe",
        "title": "Director"
    }
}

Notes:
- "body" and "sections" are mutually exclusive. If both are present, "sections" takes priority.
- The agent may also nest metadata under a "memo" key — this is handled transparently.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).parent))
from fill_template import (
    _w, W_NS, XML_NS,
    _make_run, _make_runs_from_text, _make_empty_para,
    _make_heading, _make_paragraph, _make_bullet, _make_numbered,
    _make_code_line, _make_table,
    replace_placeholders, detect_num_ids, _expand_list_items,
)

SCRIPTS_DIR = Path(__file__).parent
OFFICE_DIR = SCRIPTS_DIR / "office"


def _normalize_config(config: dict) -> dict:
    """Normalize config to handle various JSON shapes the agent might produce.

    Handles:
    - Nested "memo" key: {"memo": {"to": "..."}} → {"to": "..."}
    - "intro" key merged into sections
    """
    # If agent nested metadata under "memo", flatten it
    if "memo" in config and isinstance(config["memo"], dict):
        memo = config["memo"]
        for key in ("from", "to", "cc", "date", "subject", "attachments"):
            if key in memo and key not in config:
                config[key] = memo[key]

    # If agent used "intro" as separate content, prepend to sections or body
    if "intro" in config and isinstance(config["intro"], list):
        if "sections" in config:
            # Prepend intro content as an untitled section
            intro_section = {"title": "", "level": 0, "content": config["intro"]}
            config["sections"].insert(0, intro_section)
        elif "body" not in config:
            # Convert intro to body paragraphs
            config["body"] = [
                block.get("text", "") for block in config["intro"]
                if isinstance(block, dict) and block.get("type") == "text"
            ]

    return config


def fill_note(template_path: str, output_path: str, config: dict) -> str:
    """Fill an internal memo template."""
    config = _normalize_config(config)

    with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
        unpack_dir = os.path.join(tmpdir, "unpacked")

        with zipfile.ZipFile(template_path) as z:
            z.extractall(unpack_dir)

        doc_path = os.path.join(unpack_dir, "word", "document.xml")
        tree = etree.parse(doc_path)
        root = tree.getroot()
        body = root.find(_w("body"))

        if body is None:
            return "Error: No <w:body> found"

        # Step 1: Replace metadata placeholders
        placeholders = {
            "[Expéditeur]": config.get("from", ""),
            "[Destinataires]": config.get("to", ""),
            "[Copies]": config.get("cc", ""),
            "[Date]": config.get("date", ""),
            "[Objet de la note]": config.get("subject", ""),
            "[Prénom Nom]": config.get("sender", {}).get("name", config.get("from", "")),
            "[Fonction]": config.get("sender", {}).get("title", ""),
        }
        n_replaced = replace_placeholders(body, placeholders)
        print(f"Replaced {n_replaced} placeholder(s)")

        # Step 2: Find and remove body placeholder paragraphs
        body_para_idx = None
        to_remove = []
        for i, child in enumerate(list(body)):
            if child.tag != _w("p"):
                continue
            texts = [t.text for t in child.iter(_w("t")) if t.text]
            full_text = " ".join(texts)
            if "Corps de la note" in full_text or "information" in full_text or "Développer" in full_text or "paragraphes additionnels" in full_text:
                to_remove.append(child)
                if body_para_idx is None:
                    body_para_idx = i

        for elem in to_remove:
            body.remove(elem)

        if body_para_idx is None:
            # Fallback: insert before signature (look for [Prénom Nom] or sender name)
            sect_pr = body.find(_w("sectPr"))
            body_para_idx = list(body).index(sect_pr) - 3 if sect_pr is not None else len(list(body)) - 1

        # Step 3: Insert content — either "sections" (structured) or "body" (flat)
        sections = config.get("sections", [])
        body_paragraphs = config.get("body", [])

        if sections:
            # Structured sections (like fill_cr_template)
            numbering_path = os.path.join(unpack_dir, "word", "numbering.xml")
            bullet_id, numbered_id = detect_num_ids(numbering_path)

            elements = []
            for section in sections:
                title = section.get("title", "")
                level = section.get("level", 1)
                content_blocks = section.get("content", [])

                if title:
                    elements.append(_make_heading(title, level))

                for block in content_blocks:
                    block_type = block.get("type", "text")

                    if block_type == "text":
                        elements.append(_make_paragraph(
                            block.get("text", ""), bold=block.get("bold", False)))
                    elif block_type == "bullets":
                        elements.extend(_expand_list_items(
                            block.get("items", []), _make_bullet, level=0,
                            bullet_id=bullet_id, numbered_id=numbered_id))
                    elif block_type == "numbered":
                        elements.extend(_expand_list_items(
                            block.get("items", []), _make_numbered, level=0,
                            bullet_id=bullet_id, numbered_id=numbered_id))
                    elif block_type == "code":
                        for line in block.get("text", "").split("\n"):
                            elements.append(_make_code_line(line))
                    elif block_type == "table":
                        headers = block.get("headers", [])
                        rows = block.get("rows", [])
                        if headers:
                            elements.append(_make_table(headers, rows))
                    elif block_type == "empty":
                        elements.append(_make_empty_para())

                elements.append(_make_empty_para())

            for j, elem in enumerate(elements):
                body.insert(body_para_idx + j, elem)

            print(f"Inserted {len(elements)} element(s) from {len(sections)} section(s)")

        elif body_paragraphs:
            # Simple flat body paragraphs
            for j, para_text in enumerate(body_paragraphs):
                p = etree.Element(_w("p"))
                for run in _make_runs_from_text(para_text):
                    p.append(run)
                body.insert(body_para_idx + j, p)

            print(f"Inserted {len(body_paragraphs)} body paragraph(s)")

        else:
            print("WARNING: No body or sections content provided")

        tree.write(doc_path, xml_declaration=True, encoding="UTF-8", standalone=True)

        pack_result = subprocess.run(
            [sys.executable, str(OFFICE_DIR / "pack.py"), unpack_dir, output_path, "--validate", "false"],
            capture_output=True, text=True
        )
        if pack_result.returncode != 0:
            print(pack_result.stdout)
            print(pack_result.stderr, file=sys.stderr)
            return f"Error: pack.py failed"
        print(pack_result.stdout.strip())

        val_result = subprocess.run(
            [sys.executable, str(OFFICE_DIR / "validate.py"), output_path],
            capture_output=True, text=True
        )
        print(val_result.stdout.strip())

    return f"Success: {output_path}"


def main():
    parser = argparse.ArgumentParser(description="Fill an internal memo DOCX template")
    parser.add_argument("template", help="Path to note interne template DOCX")
    parser.add_argument("output", help="Output DOCX file path")
    parser.add_argument("config", help="Path to JSON config file")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    result = fill_note(args.template, args.output, config)
    print(result)

    if result.startswith("Error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
