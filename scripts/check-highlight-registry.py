#!/usr/bin/env python3
"""Drift checker between backend/src/agent/registry.py's declared voice
actions and the frontend's data-hl wiring (see frontend/src/lib/highlightBridge.ts).

Before the highlight system was unified onto data-hl attributes, catching a
gap here meant a manual audit like the one that found Continue/Next/Back
buttons had never been wired at all, and MagicAvatar's launchpad actions had
zero visual cue -- discovered only by live-testing, not by any check. This
script is the replacement: it re-derives the exact same "every registry
action needs a real, findable target" rule and runs it automatically,
instead of trusting convention.

Most page/component ids are matched by a literal `data-hl="component:method"`
string somewhere in frontend/src. Content Studio's 30 format cards are the
one deliberately dynamic exception (data-hl={`${formatSlug(f.tool)}:open`}) --
those are cross-checked separately below by re-deriving the exact same slugs
registry.py itself declares, rather than trying to statically resolve a
template literal via regex.

Exit code 0 = no drift found. Exit code 1 = report printed, drift found.
Run from anywhere; paths are resolved relative to this file."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND_SRC = ROOT / "frontend" / "src"

sys.path.insert(0, str(BACKEND))

from src.agent.registry import UI_REGISTRY, CONTENT_STUDIO_FORMATS  # noqa: E402


def content_studio_format_slug(tool: str) -> str:
    """Mirrors frontend/src/registry/contentStudio.ts's formatSlug() exactly
    -- lowercase, non-alphanumerics stripped. Kept in sync by hand since
    there's no shared code between the two packages (same tradeoff already
    accepted for CONTENT_STUDIO_FORMATS itself, see registry.py's own
    comment) -- if this ever drifts from the real implementation, the
    content-studio section below will start reporting false positives,
    which is itself a signal to go re-check formatSlug()."""
    return re.sub(r"[^a-z0-9]+", "", tool.lower())


# "scroll" is a real, non-simulated action (scrollBy on the page's own
# container, see useProductPages.tsx) that every page registers identically
# -- there's no specific element to visually point at for "scroll the whole
# page", so it deliberately has no data-hl target at all. Not a gap.
EXCLUDED_COMPONENTS = {"scroll"}


def expected_keys() -> dict[str, set[str]]:
    """page_id -> set of "component:method" keys registry.py declares."""
    expected: dict[str, set[str]] = {}
    for page in UI_REGISTRY:
        keys = set()
        for component in page.components:
            if component.id in EXCLUDED_COMPONENTS:
                continue
            for action in component.actions:
                keys.add(f"{component.id}:{action.id}")
        expected[page.id] = keys
    return expected


def scan_string_literals() -> set[str]:
    """Every "component:method"-shaped double-quoted string literal
    anywhere in frontend/src -- deliberately broader than just the literal
    `data-hl="..."` JSX attribute form, since a couple of real call sites
    (e.g. StepBar's `dataHl` callback prop) return the same literal string
    from inside a function rather than writing it directly as an attribute
    value. Not page-scoped, for the same reason as before."""
    pattern = re.compile(r'"([a-zA-Z][a-zA-Z0-9_-]*:[a-zA-Z][a-zA-Z0-9_-]*)"')
    found: set[str] = set()
    result = subprocess.run(
        ["grep", "-rhoE", r'"[a-zA-Z][a-zA-Z0-9_-]*:[a-zA-Z][a-zA-Z0-9_-]*"', str(FRONTEND_SRC)],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        m = pattern.search(line)
        if m:
            found.add(m.group(1))
    return found


def known_dynamic_keys() -> dict[str, set[str]]:
    """Keys built from a JSX template literal (data-hl={`...${var}...`}),
    which a plain string-literal scan can never resolve -- enumerated by
    hand here, matching exactly how each is actually constructed in
    source, rather than trying to teach the regex scanner real template
    interpolation."""
    content_studio = {f"{content_studio_format_slug(f.tool)}:open" for f in CONTENT_STUDIO_FORMATS}
    # ContentStudio.tsx: data-hl={`${t.toLowerCase()}-tab:click`} for each
    # MAGIC_ENGINES tabId.
    content_studio |= {f"{tab.lower()}-tab:click" for tab in ("Video", "Aid", "Mail", "Canvas", "Doc")}
    # MagicReelStudio.tsx: data-hl={`wizard:select-source-${l}`} for each lane.
    magicreel = {f"wizard:select-source-{lane}" for lane in ("dossier", "news", "custom")}
    return {"content-studio": content_studio, "magicreel-studio": magicreel}


def main() -> int:
    expected = expected_keys()
    literal_hits = scan_string_literals()
    dynamic = known_dynamic_keys()

    problems = []
    for page_id, keys in expected.items():
        covered = literal_hits | dynamic.get(page_id, set())
        missing = sorted(keys - covered)
        if missing:
            problems.append((page_id, missing))

    if not problems:
        print("OK -- every registry.py action has a matching data-hl target (or the known Content Studio dynamic exception).")
        return 0

    print("Highlight registry drift found:\n")
    for page_id, missing in problems:
        print(f"  [{page_id}]")
        for key in missing:
            print(f"    MISSING data-hl for: {key}")
    print(
        "\nEach of the above is a registry.py action with no matching "
        '`data-hl="component:method"` anywhere in frontend/src -- either a '
        "new backend action was added without wiring its frontend target, "
        "or a frontend element's data-hl was renamed/removed without "
        "updating registry.py. See frontend/src/lib/highlightBridge.ts."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
