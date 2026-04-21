#!/usr/bin/env python3
"""Fill the Note Interne (internal memo) template with sender/recipient data and body.

Usage:
    python3 fill_note_template.py <template-note-interne.docx> <output.docx> <config.json>

Config JSON format:
{
    "from": "Damien Juillard",
    "to": "Équipe Technique",
    "cc": "Direction Générale",
    "date": "21 avril 2026",
    "subject": "Mise à jour process de déploiement",
    "body": [
        "Premier paragraphe de la note.",
        "Deuxième paragraphe avec **mots en gras** si besoin.",
        "Troisième paragraphe."
    ],
    "sender": {
        "name": "Damien Juillard",
        "title": "Directeur Général"
    }
}
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
    replace_placeholders,
)

SCRIPTS_DIR = Path(__file__).parent
OFFICE_DIR = SCRIPTS_DIR / "office"


def fill_note(template_path: str, output_path: str, config: dict) -> str:
    """Fill an internal memo template."""
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

        # Step 2: Replace body placeholder with actual paragraphs
        body_paragraphs = config.get("body", [])
        body_para = None
        body_para_idx = None
        for i, child in enumerate(list(body)):
            if child.tag != _w("p"):
                continue
            texts = [t.text for t in child.iter(_w("t")) if t.text]
            full_text = " ".join(texts)
            if "Corps de la note" in full_text or "information" in full_text:
                body_para = child
                body_para_idx = i
                break

        if body_para is not None and body_paragraphs:
            # Find and remove placeholder paragraphs (body + "Développer si nécessaire")
            to_remove = [body_para]
            # Check next paragraphs for the second placeholder
            children = list(body)
            for j in range(body_para_idx + 1, min(body_para_idx + 4, len(children))):
                child = children[j]
                if child.tag == _w("p"):
                    texts = [t.text for t in child.iter(_w("t")) if t.text]
                    full = " ".join(texts)
                    if "Développer" in full or "paragraphes additionnels" in full:
                        to_remove.append(child)

            for elem in to_remove:
                body.remove(elem)

            # Insert actual body paragraphs
            for j, para_text in enumerate(body_paragraphs):
                p = etree.Element(_w("p"))
                for run in _make_runs_from_text(para_text):
                    p.append(run)
                body.insert(body_para_idx + j, p)

        print(f"Inserted {len(body_paragraphs)} body paragraph(s)")

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
