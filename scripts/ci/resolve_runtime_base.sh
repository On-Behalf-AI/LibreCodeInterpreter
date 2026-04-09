#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <runtime-image-prefix> <runtime-hash>" >&2
  exit 1
fi

runtime_prefix="$1"
runtime_hash="$2"
runtime_ref="${runtime_prefix}:${runtime_hash}"

if docker buildx imagetools inspect "${runtime_ref}" >/dev/null 2>&1; then
  printf '%s\n' "${runtime_ref}"
else
  printf '%s\n' "runtime-r"
fi
