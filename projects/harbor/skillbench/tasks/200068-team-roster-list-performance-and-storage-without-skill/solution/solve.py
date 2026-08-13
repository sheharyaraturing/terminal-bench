"""Oracle solver for the team roster panel fix task.

This is a genuine transformer, not a pre-baked artifact: it reads the actual
starter component from INPUT_PATH and rewrites only the parts the fix touches.
Everything else (the Member type, props annotation, JSX markup, class names,
heading text and aria-labels) is carried through verbatim from the input, so any
incidental change to the starter flows straight into the output.

The skill-grounded fixes applied are:
  1. content-visibility on the roster rows (rendering-content-visibility) so a
     large list defers off-screen layout/paint while every row stays rendered.
  2. flicker-free hydration (rendering-hydration-no-flicker): a synchronous
     pre-hydration <script dangerouslySetInnerHTML> reads the persisted ids before
     React hydrates, stashes them on window, AND toggles the `is-expanded` class on
     the already server-rendered rows so the correct rows are open before first
     paint. The component reads that same window value in its initializer, so its
     first client render matches the patched DOM (no hydration mismatch), and it
     never reads client storage during render (no SSR break) or in a post-mount
     effect (no flash). Department content is always rendered and shown/hidden via
     the `is-expanded` class, so restoring expansion is a class toggle the script
     can apply without needing per-row data.
  3. a versioned, guarded localStorage key (client-localstorage-schema): the
     unversioned `teamRosterExpanded` key becomes `teamRosterExpanded:v1`, the
     bootstrap read and the persistence write are wrapped in try/catch, and only
     the minimal id array is stored (no in-payload version field).
"""

import re
from pathlib import Path

INPUT_PATH = Path("/root/inputs/team_roster_panel.tsx")
OUTPUT_PATH = Path("/root/team_roster_panel.fixed.tsx")

STORAGE_KEY = "teamRosterExpanded:v1"


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(
            f"cannot apply fix: expected exactly one occurrence of {label} "
            f"in the starter, found {count}"
        )
    return text.replace(old, new, 1)


def solve(source: str) -> str:
    """Return the corrected component derived from the starter `source`."""
    text = source

    # 1) Drop the stale banner comment that sits above the react import; it is
    #    not part of the fix and the corrected file does not carry it.
    text = re.sub(r"\n//[^\n]*\n(?=import )", "\n", text, count=1)

    # 2) Introduce the versioned storage key and the roster-row CSS constants
    #    just before the type declarations.
    constants = (
        f"const EXPANDED_STORAGE_KEY = '{STORAGE_KEY}'\n"
        "\n"
        "const ROSTER_ITEM_CSS = `.team-roster-item {\n"
        "  content-visibility: auto;\n"
        "  contain-intrinsic-size: 0 56px;\n"
        "}\n"
        ".roster-member-department {\n"
        "  display: none;\n"
        "}\n"
        ".team-roster-item.is-expanded .roster-member-department {\n"
        "  display: inline;\n"
        "}`\n"
        "\n"
    )
    text = _replace_once(
        text,
        "\n\ntype Member = {",
        "\n\n" + constants + "type Member = {",
        "the Member type declaration",
    )

    # 3) Replace the render-time storage loader with a window bootstrap reader (the
    #    pre-hydration script populates window before hydration) and a guarded saver.
    old_loader = (
        "function loadExpandedIds(): string[] {\n"
        "  const raw = localStorage.getItem('teamRosterExpanded')\n"
        "  if (!raw) return []\n"
        "  return JSON.parse(raw)\n"
        "}"
    )
    new_loader = (
        "function readBootstrapExpandedIds(): string[] {\n"
        "  if (typeof window === 'undefined') return []\n"
        "  const ids = (window as { __ROSTER_EXPANDED__?: string[] }).__ROSTER_EXPANDED__\n"
        "  return Array.isArray(ids) ? ids : []\n"
        "}\n"
        "\n"
        "function saveExpandedIds(ids: string[]) {\n"
        "  try {\n"
        "    localStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify(ids))\n"
        "  } catch {\n"
        "    // Storage may be unavailable in private browsing or when quota is exceeded.\n"
        "  }\n"
        "}"
    )
    text = _replace_once(text, old_loader, new_loader, "the loadExpandedIds function")

    # 4) Initialize state from the value the pre-hydration script stashed on window,
    #    not from a render-time storage read.
    old_state = (
        "  const [expandedIds, setExpandedIds] = useState<string[]>(loadExpandedIds)"
    )
    new_state = (
        "  // The pre-hydration script below stashes the persisted ids on window and\n"
        "  // patches the server-rendered rows before React hydrates. Reading the same\n"
        "  // value here makes the first client render match the already-patched DOM, so\n"
        "  // there is no hydration mismatch and no first-paint flash.\n"
        "  const [expandedIds, setExpandedIds] = useState<string[]>(readBootstrapExpandedIds)"
    )
    text = _replace_once(text, old_state, new_state, "the expandedIds useState initializer")

    # 5) Persist through the guarded saver instead of a raw, unversioned write.
    text = _replace_once(
        text,
        "    localStorage.setItem('teamRosterExpanded', JSON.stringify(expandedIds))\n",
        "    saveExpandedIds(expandedIds)\n",
        "the expandedIds persistence effect",
    )

    # 6) Add the scoped content-visibility (plus department visibility) style at the
    #    top of the panel.
    text = _replace_once(
        text,
        '    <section className="team-roster-panel">\n',
        '    <section className="team-roster-panel">\n'
        "      <style>{ROSTER_ITEM_CSS}</style>\n",
        "the roster panel <section> open tag",
    )

    # 7) Render every row's department unconditionally and drive expansion through an
    #    `is-expanded` class plus a data-member-id hook the pre-hydration script uses.
    old_li = '          <li key={member.id} className="team-roster-item">'
    new_li = (
        "          <li\n"
        "            key={member.id}\n"
        "            className={\n"
        "              'team-roster-item' +\n"
        "              (expandedIds.includes(member.id) ? ' is-expanded' : '')\n"
        "            }\n"
        "            data-member-id={member.id}\n"
        "          >"
    )
    text = _replace_once(text, old_li, new_li, "the roster item <li> open tag")

    old_span = (
        "            {expandedIds.includes(member.id) ? (\n"
        '              <span className="roster-member-department">{member.department}</span>\n'
        "            ) : null}"
    )
    new_span = (
        '            <span className="roster-member-department">{member.department}</span>'
    )
    text = _replace_once(text, old_span, new_span, "the conditional department span")

    # 8) Emit the synchronous pre-hydration bootstrap script AFTER the list so the
    #    rows already exist in the DOM when it runs: it stashes the persisted ids on
    #    window (consumed by the initializer above) and patches the rendered rows'
    #    `is-expanded` class before first paint, so the DOM matches React's first
    #    render (no hydration mismatch) and the correct rows are open (no flash).
    script = (
        "      <script\n"
        "        dangerouslySetInnerHTML={{\n"
        "          __html: `(function () {\n"
        "  try {\n"
        "    var raw = localStorage.getItem('teamRosterExpanded:v1');\n"
        "    var ids = raw ? JSON.parse(raw) : [];\n"
        "    window.__ROSTER_EXPANDED__ = ids;\n"
        "    var lookup = {};\n"
        "    for (var i = 0; i < ids.length; i += 1) lookup[ids[i]] = true;\n"
        "    var items = document.querySelectorAll('.team-roster-item[data-member-id]');\n"
        "    for (var j = 0; j < items.length; j += 1) {\n"
        "      if (lookup[items[j].getAttribute('data-member-id')]) {\n"
        "        items[j].classList.add('is-expanded');\n"
        "      }\n"
        "    }\n"
        "  } catch (e) {\n"
        "    window.__ROSTER_EXPANDED__ = [];\n"
        "  }\n"
        "})();`,\n"
        "        }}\n"
        "      />\n"
    )
    text = _replace_once(
        text,
        "      </ul>\n    </section>",
        "      </ul>\n" + script + "    </section>",
        "the roster list </ul> close tag",
    )

    return text


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing starter file: {INPUT_PATH}")
    fixed = solve(INPUT_PATH.read_text(encoding="utf-8"))
    OUTPUT_PATH.write_text(fixed, encoding="utf-8")


if __name__ == "__main__":
    main()
