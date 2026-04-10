#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

mapfile -t runtime_files < <(
  {
    printf '%s\n' "Dockerfile"
    find docker/requirements -maxdepth 1 -type f | sort
  } | sort -u
)

tmpfile="$(mktemp)"
trap 'rm -f "$tmpfile"' EXIT

for file in "${runtime_files[@]}"; do
  sha256sum "$file" >> "$tmpfile"
done

sha256sum "$tmpfile" | cut -c1-16
