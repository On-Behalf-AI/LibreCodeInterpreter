#!/usr/bin/env python3
"""Fill a contract/legal template with party data and optional sections.

Usage:
    python3 fill_contrat_template.py <template.docx> <output.docx> <config.json>

Works with all legal document templates:
- template-contrat-services.docx (master service contract)
- template-contrat-apport.docx (business referral agreement)
- template-nda.docx (confidentiality agreement)
- template-reponse-ao.docx (RFQ/tender response)

Config JSON format:
{
    "placeholders": {
        "[Nom du Client]": "Société XYZ",
        "[Forme juridique]": "SAS",
        "[Adresse complète]": "123 rue de la Paix, 75001 Paris",
        "[Numéro de SIRET]": "123 456 789 00001",
        "[Nom du représentant]": "M. Jean Dupont",
        "[Montant en euros]": "15 000"
    },
    "sections": [
        {
            "title": "Section additionnelle",
            "level": 1,
            "content": [
                {"type": "text", "text": "Paragraphe additionnel."},
                {"type": "bullets", "items": ["Point A", "Point B"]}
            ]
        }
    ]
}

The "placeholders" dict does simple text replacement across the entire document.
The optional "sections" list appends structured content before the signature block
(uses the same format as fill_template.py sections).
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
    HEADING_STYLES,
)

SCRIPTS_DIR = Path(__file__).parent
OFFICE_DIR = SCRIPTS_DIR / "office"


def insert_sections_before_signatures(body, sections, bullet_id=None, numbered_id=None):
    """Insert content sections before the last table (signature block) or before sectPr."""
    sect_pr = body.find(_w("sectPr"))
    children = list(body)

    # Find the last table (usually the signature block)
    tables = body.findall(_w("tbl"))
    if tables:
        last_tbl = tables[-1]
        insert_point = children.index(last_tbl)
    elif sect_pr is not None:
        insert_point = children.index(sect_pr)
    else:
        insert_point = len(children)

    elements = [_make_empty_para()]

    for section in sections:
        title = section.get("title", "")
        level = section.get("level", 1)
        content_blocks = section.get("content", [])

        if title:
            elements.append(_make_heading(title, level))

        for block in content_blocks:
            block_type = block.get("type", "text")

            if block_type == "text":
                elements.append(_make_paragraph(block.get("text", ""), bold=block.get("bold", False)))
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

    for i, elem in enumerate(elements):
        body.insert(insert_point + i, elem)

    return len(elements)


def fill_contrat(template_path: str, output_path: str, config: dict) -> str:
    """Fill a contract template with party data and optional sections."""
    placeholders = config.get("placeholders", {})
    sections = config.get("sections", [])

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

        # Step 1: Replace all placeholders
        n_replaced = replace_placeholders(body, placeholders)
        print(f"Replaced {n_replaced} placeholder(s)")

        # Step 2: Insert optional additional sections
        if sections:
            numbering_path = os.path.join(unpack_dir, "word", "numbering.xml")
            bullet_id, numbered_id = detect_num_ids(numbering_path)
            n_inserted = insert_sections_before_signatures(
                body, sections, bullet_id=bullet_id, numbered_id=numbered_id)
            print(f"Inserted {n_inserted} element(s)")

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
    parser = argparse.ArgumentParser(description="Fill a contract/legal DOCX template")
    parser.add_argument("template", help="Path to contract template DOCX")
    parser.add_argument("output", help="Output DOCX file path")
    parser.add_argument("config", help="Path to JSON config file")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    result = fill_contrat(args.template, args.output, config)
    print(result)

    if result.startswith("Error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
