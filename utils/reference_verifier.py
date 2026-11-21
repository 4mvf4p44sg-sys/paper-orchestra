# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Verifies that every citation in a LaTeX paper resolves to a real reference.

Two checks are performed:
  1. Every \\cite-style key used in the .tex exists in the .bib file.
  2. Every cited .bib entry's title is found on Semantic Scholar (fuzzy match).
"""

import json
import re
from typing import Callable, Dict, List, Optional

from thefuzz import fuzz  # type: ignore

CITE_RE = re.compile(r"\\(?:cite[a-zA-Z]*|nocite)\*?(?:\[[^\]]*\])*\{([^}]*)\}")
BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
MATCH_THRESHOLD = 85


def extract_cited_keys(tex: str) -> List[str]:
    """Returns the cited keys in order of first appearance, ignoring comments."""
    tex = re.sub(r"(?<!\\)%.*", "", tex)
    keys: List[str] = []
    for group in CITE_RE.findall(tex):
        for key in group.split(","):
            key = key.strip()
            if key and key not in keys:
                keys.append(key)
    return keys


def _field(body: str, name: str) -> Optional[str]:
    m = re.search(rf"\b{name}\s*=\s*", body, re.IGNORECASE)
    if not m or m.end() >= len(body):
        return None
    i = m.end()
    if body[i] == "{":
        depth, j = 0, i
        while j < len(body):
            if body[j] == "{":
                depth += 1
            elif body[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        value = body[i + 1 : j]
    elif body[i] == '"':
        j = body.find('"', i + 1)
        value = body[i + 1 : j if j != -1 else len(body)]
    else:
        value = re.split(r"[,\n}]", body[i], maxsplit=1)[0]
    return re.sub(r"[{}]", "", value).strip()


def parse_bib(bib: str) -> Dict[str, Dict[str, Optional[str]]]:
    """Parses a .bib string into {key: {"type", "title", "year"}}."""
    entries: Dict[str, Dict[str, Optional[str]]] = {}
    matches = list(BIB_ENTRY_RE.finditer(bib))
    for idx, m in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(bib)
        body = bib[m.end() : end]
        entries[m.group(2)] = {
            "type": m.group(1).lower(),
            "title": _field(body, "title"),
            "year": _field(body, "year"),
        }
    return entries


def _default_search(title: str, year: Optional[int]) -> Optional[Dict]:
    from utils.scholar_utils import s2_title_search

    return s2_title_search(title, year)


def verify_references(
    tex: str,
    bib: str,
    search_fn: Optional[Callable[[str, Optional[int]], Optional[Dict]]] = None,
) -> Dict:
    """Checks citation keys and cited bib entries; returns a JSON-serialisable report.

    Per-entry status: "verified", "unverified" (no matching paper found, possibly
    hallucinated), or "no_title".
    """
    search_fn = search_fn or _default_search
    entries = parse_bib(bib)
    cited = extract_cited_keys(tex)
    missing_keys = [k for k in cited if k not in entries]

    results = {}
    for key in cited:
        if key not in entries:
            continue
        title, year = entries[key]["title"], entries[key]["year"]
        if not title:
            results[key] = {"status": "no_title"}
            continue
        year_hint = int(year) if year and year.isdigit() else None
        match = search_fn(title, year_hint)
        if match and fuzz.ratio(title.lower(), match["title"].lower()) >= MATCH_THRESHOLD:
            results[key] = {
                "status": "verified",
                "matched_title": match["title"],
                "year": match.get("year"),
            }
        else:
            results[key] = {"status": "unverified", "title": title}

    unverified = [k for k, v in results.items() if v["status"] != "verified"]
    return {
        "n_cited": len(cited),
        "missing_keys": missing_keys,
        "unverified_keys": unverified,
        "unused_keys": [k for k in entries if k not in cited],
        "entries": results,
        "ok": not missing_keys and not unverified,
    }


def verify_files(
    tex_path: str, bib_path: str, output_path: Optional[str] = None
) -> Dict:
    with open(tex_path, encoding="utf-8") as f:
        tex = f.read()
    with open(bib_path, encoding="utf-8") as f:
        bib = f.read()
    report = verify_references(tex, bib)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    return report


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Verify citations of a LaTeX paper.")
    ap.add_argument("tex")
    ap.add_argument("bib")
    ap.add_argument("--output", default=None)
    a = ap.parse_args()
    r = verify_files(a.tex, a.bib, a.output)
    print(json.dumps({k: v for k, v in r.items() if k != "entries"}, indent=2))
