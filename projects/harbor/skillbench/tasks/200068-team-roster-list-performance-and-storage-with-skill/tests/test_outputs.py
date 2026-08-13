import re
import shutil
import subprocess
import tempfile
from pathlib import Path


OUTPUT_PATH = Path("/root/team_roster_panel.fixed.tsx")

TSX_PARSE_DECLARATIONS = """
declare module 'react' {
  export function useEffect(...args: any[]): any
  export function useState<T>(initial: T | (() => T)): [T, (next: any) => void]
  export function useMemo<T>(factory: () => T, deps?: any[]): T
  export function useCallback<T extends (...args: any[]) => any>(callback: T, deps?: any[]): T
  export function memo<T>(component: T, propsAreEqual?: (a: any, b: any) => boolean): T
  const React: any
  export default React
}

declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any
  }
}
"""

TS_SYNTAX_ERROR_CODES = {
    "1002",
    "1003",
    "1005",
    "1109",
    "1110",
    "1128",
    "1131",
    "1134",
    "1135",
    "1136",
    "1137",
    "1138",
    "1144",
    "1160",
    "1161",
    "1180",
    "1381",
    "1382",
    "17002",
    "17008",
    "17014",
}


def read_output() -> str:
    """Return the generated TSX artifact text."""
    return OUTPUT_PATH.read_text(encoding="utf-8")


def strip_js_comments(source: str) -> str:
    """Remove JavaScript comments while preserving strings."""
    result = []
    i = 0
    state = "code"
    quote = ""
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""

        if state == "line_comment":
            if ch == "\n":
                result.append(ch)
                state = "code"
            i += 1
            continue

        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                i += 2
            else:
                result.append("\n" if ch == "\n" else " ")
                i += 1
            continue

        if state == "string":
            result.append(ch)
            if ch == "\\" and i + 1 < len(source):
                result.append(source[i + 1])
                i += 2
                continue
            if ch == quote:
                state = "code"
            i += 1
            continue

        if ch in {"'", '"', "`"}:
            state = "string"
            quote = ch
            result.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            state = "line_comment"
            i += 2
            continue

        if ch == "/" and nxt == "*":
            state = "block_comment"
            i += 2
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def code_text() -> str:
    """Return artifact text without comments for code checks."""
    return strip_js_comments(read_output())


def has_class(attrs: str, class_name: str) -> bool:
    """Return whether TSX attributes include a class name."""
    class_patterns = [
        r'className\s*=\s*["\']([^"\']*)["\']',
        r'className\s*=\s*\{\s*["\']([^"\']*)["\']\s*\}',
        r'className\s*=\s*\{\s*`([^`]*)`\s*\}',
    ]
    for pattern in class_patterns:
        for match in re.finditer(pattern, attrs):
            if class_name in match.group(1).split():
                return True
    return False


def find_opening_tag_attrs(source: str, tag: str) -> list[str]:
    """Collect opening attributes for a TSX tag."""
    return [match.group("attrs") for match in re.finditer(rf"<{tag}\b(?P<attrs>[\s\S]*?)>", source)]


def find_item_li_attrs(source: str) -> list[str]:
    """Collect opening attributes for roster item li elements."""
    return [attrs for attrs in find_opening_tag_attrs(source, "li") if has_class(attrs, "team-roster-item")]


def has_balanced_delimiters(source: str) -> bool:
    """Check that core TSX delimiters are balanced."""
    stripped = strip_js_comments(source)
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    state = "code"
    quote = ""
    for i, ch in enumerate(stripped):
        prev = stripped[i - 1] if i else ""
        if state == "string":
            if ch == quote and prev != "\\":
                state = "code"
            continue
        if ch in {"'", '"', "`"}:
            state = "string"
            quote = ch
            continue
        if ch in "([{" :
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack and state == "code"


def typescript_syntax_errors(source: str) -> list[str]:
    """Return TypeScript parser syntax diagnostics for TSX text."""
    tsc = shutil.which("tsc")
    if not tsc:
        return ["tsc compiler is not available"]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifact_path = tmp_path / "artifact.tsx"
        declarations_path = tmp_path / "globals.d.ts"
        artifact_path.write_text(source, encoding="utf-8")
        declarations_path.write_text(TSX_PARSE_DECLARATIONS, encoding="utf-8")

        result = subprocess.run(
            [
                tsc,
                "--noEmit",
                "--jsx",
                "preserve",
                "--target",
                "ES2020",
                "--module",
                "ESNext",
                "--moduleResolution",
                "node",
                "--lib",
                "ES2020,DOM",
                "--skipLibCheck",
                "--pretty",
                "false",
                str(declarations_path),
                str(artifact_path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    diagnostics = result.stdout.splitlines() + result.stderr.splitlines()
    syntax_errors = []
    for line in diagnostics:
        match = re.search(r"error TS(\d+):", line)
        if match and match.group(1) in TS_SYNTAX_ERROR_CODES:
            syntax_errors.append(line)
    return syntax_errors


def ul_block(source: str) -> str:
    """Return the roster list ul block when it is present."""
    for match in re.finditer(r"<ul\b(?P<attrs>[\s\S]*?)>(?P<body>[\s\S]*?)</ul>", source):
        if has_class(match.group("attrs"), "team-roster-list"):
            return match.group(0)
    return ""


def find_call_arguments(source: str, callee: str) -> list[str]:
    """Collect argument text for calls to a callee."""
    args = []
    for match in re.finditer(re.escape(callee) + r"\s*\(", source):
        start = match.end()
        depth = 1
        i = start
        state = "code"
        quote = ""
        while i < len(source):
            ch = source[i]
            if state == "string":
                if ch == "\\" and i + 1 < len(source):
                    i += 2
                    continue
                if ch == quote:
                    state = "code"
                i += 1
                continue
            if ch in {"'", '"', "`"}:
                state = "string"
                quote = ch
                i += 1
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    args.append(source[start:i])
                    break
            i += 1
    return args


def strip_wrapping_parens(expr: str) -> str:
    """Remove balanced wrapping parentheses from an expression."""
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")") and has_balanced_delimiters(expr[1:-1]):
        expr = expr[1:-1].strip()
    return expr


def first_argument(args: str) -> str:
    """Return the first top-level argument from a call."""
    depth = 0
    state = "code"
    quote = ""
    for i, ch in enumerate(args):
        if state == "string":
            if ch == "\\" and i + 1 < len(args):
                continue
            if ch == quote:
                state = "code"
            continue
        if ch in {"'", '"', "`"}:
            state = "string"
            quote = ch
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            return args[:i].strip()
    return args.strip()


def split_top_level_arguments(args: str) -> list[str]:
    """Split call arguments at top-level commas."""
    parts = []
    depth = 0
    state = "code"
    quote = ""
    start = 0
    for i, ch in enumerate(args):
        if state == "string":
            if ch == "\\":
                continue
            if ch == quote:
                state = "code"
            continue
        if ch in {"'", '"', "`"}:
            state = "string"
            quote = ch
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(args[start:i].strip())
            start = i + 1
    tail = args[start:].strip()
    if tail or args.strip():
        parts.append(tail)
    return parts


def split_top_level_plus(expr: str) -> list[str]:
    """Split an expression on top-level string concatenation operators."""
    parts = []
    start = 0
    depth = 0
    state = "code"
    quote = ""
    i = 0
    while i < len(expr):
        ch = expr[i]
        if state == "string":
            if ch == "\\" and i + 1 < len(expr):
                i += 2
                continue
            if ch == quote:
                state = "code"
            i += 1
            continue
        if ch in {"'", '"', "`"}:
            state = "string"
            quote = ch
            i += 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "+" and depth == 0:
            parts.append(expr[start:i].strip())
            start = i + 1
        i += 1
    parts.append(expr[start:].strip())
    return parts


def string_constant_expressions(source: str) -> dict[str, str]:
    """Map const names to simple string expression text."""
    constants: dict[str, str] = {}
    pattern = r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*([^;\n]+)"
    for match in re.finditer(pattern, source):
        constants[match.group(1)] = match.group(2).strip()
    return constants


def resolve_string_expression(
    expr: str, constants: dict[str, str], seen: set[str] | None = None
) -> str | None:
    """Resolve simple string literals, templates, consts, and concatenation."""
    expr = strip_wrapping_parens(expr)
    seen = seen or set()
    if expr in constants and expr not in seen:
        return resolve_string_expression(constants[expr], constants, seen | {expr})
    if len(expr) >= 2 and expr[0] in {"'", '"'} and expr[-1] == expr[0]:
        return expr[1:-1]
    if len(expr) >= 2 and expr[0] == "`" and expr[-1] == "`":
        body = expr[1:-1]

        def replace_const(match: re.Match[str]) -> str:
            """Replace simple template placeholders from constants."""
            value = resolve_string_expression(match.group(1), constants, seen)
            return value if value is not None else match.group(0)

        return re.sub(r"\$\{\s*([A-Za-z_$][\w$]*)\s*\}", replace_const, body)
    parts = split_top_level_plus(expr)
    if len(parts) > 1:
        values = [resolve_string_expression(part, constants, seen) for part in parts]
        if all(value is not None for value in values):
            return "".join(value or "" for value in values)
    return None


def local_storage_setitem_key_values(source: str) -> list[str]:
    """Return resolved keys passed to localStorage.setItem (write path only)."""
    constants = string_constant_expressions(source)
    values: list[str] = []
    for args in find_call_arguments(source, "localStorage.setItem"):
        value = resolve_string_expression(first_argument(args), constants)
        if value is not None:
            values.append(value)
    return values


UNVERSIONED_EXPANDED_STORAGE_KEY = "teamRosterExpanded"


def persists_under_unversioned_key(source: str) -> bool:
    """Return whether any setItem writes under the legacy unversioned key."""
    return UNVERSIONED_EXPANDED_STORAGE_KEY in local_storage_setitem_key_values(source)


def payload_has_version_property(expr: str, source: str, seen: set[str] | None = None) -> bool:
    """Return whether an expression serializes a JSON object containing version."""
    expr = strip_wrapping_parens(expr)
    seen = seen or set()
    if expr in seen:
        return False
    seen.add(expr)
    stringify = re.search(r"JSON\.stringify\s*\(\s*(?P<inner>[\s\S]+)\)", expr)
    if stringify:
        return payload_has_version_property(stringify.group("inner"), source, seen)
    if expr.lstrip().startswith("{"):
        return bool(re.search(r"\bversion\s*:", expr))
    if re.fullmatch(r"[A-Za-z_$][\w$]*", expr):
        ident = expr
        obj_pat = (
            rf"\b(?:const|let|var)\s+{re.escape(ident)}(?:\s*:[^=]+)?\s*=\s*"
            rf"\{{(?P<body>[\s\S]*?)\}}"
        )
        obj_match = re.search(obj_pat, source)
        if obj_match and re.search(r"\bversion\s*:", obj_match.group("body")):
            return True
        for assign in re.finditer(
            rf"\b{re.escape(ident)}\s*=\s*\{{(?P<body>[\s\S]*?)\}}", source
        ):
            if re.search(r"\bversion\s*:", assign.group("body")):
                return True
    return False


def setitem_serializes_object_with_version(source: str) -> bool:
    """Return whether any setItem persists a JSON object with a version field."""
    for args in find_call_arguments(source, "localStorage.setItem"):
        parts = split_top_level_arguments(args)
        if len(parts) < 2:
            continue
        if payload_has_version_property(parts[1].strip(), source):
            return True
    return False


def style_expression(attrs: str) -> str:
    """Return the expression used by a style prop."""
    match = re.search(r"\bstyle\s*=\s*\{(?P<expr>[\s\S]*?)\}", attrs)
    return match.group("expr").strip() if match else ""


def inline_style_has_property(attrs: str, property_name: str, value: str | None = None) -> bool:
    """Return whether inline style attributes contain a property."""
    pattern = rf"\b{re.escape(property_name)}\s*:"
    if value is not None:
        pattern += rf"\s*['\"]{re.escape(value)}['\"]"
    return bool(re.search(pattern, attrs))


def referenced_style_text(source: str, expr: str) -> str:
    """Return a local style object or function body referenced by style."""
    expr = strip_wrapping_parens(expr)
    dotted = re.fullmatch(r"([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)", expr)
    if dotted:
        base, prop = dotted.groups()
        object_match = re.search(
            rf"\b(?:const|let|var)\s+{re.escape(base)}(?:\s*:[^=]+)?\s*=\s*\{{[\s\S]*?\b{re.escape(prop)}\s*:\s*\{{(?P<body>[\s\S]*?)\}}",
            source,
        )
        return object_match.group("body") if object_match else ""
    if not re.match(r"^[A-Za-z_$][\w$]*(?:\([^)]*\))?$", expr):
        return ""
    name = expr.split("(", 1)[0]
    object_match = re.search(
        rf"\b(?:const|let|var)\s+{re.escape(name)}(?:\s*:[^=]+)?\s*=\s*\{{(?P<body>[\s\S]*?)\}}",
        source,
    )
    if object_match:
        return object_match.group("body")
    function_match = re.search(
        rf"\b(?:function\s+{re.escape(name)}\b|(?:const|let|var)\s+{re.escape(name)}(?:\s*:[^=]+)?\s*=\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>)(?P<body>[\s\S]{{0,800}})",
        source,
    )
    return function_match.group("body") if function_match else ""


def style_prop_has_property(source: str, attrs: str, property_name: str, value: str | None = None) -> bool:
    """Return whether a style prop sets a property inline or by reference."""
    if not re.search(r"\bstyle\s*=", attrs):
        return False
    if inline_style_has_property(attrs, property_name, value):
        return True
    style_text = referenced_style_text(source, style_expression(attrs))
    pattern = rf"\b{re.escape(property_name)}\s*:"
    if value is not None:
        pattern += rf"\s*['\"]{re.escape(value)}['\"]"
    if style_text and re.search(pattern, style_text):
        return True
    for spread_name in re.findall(r"\.\.\.\s*([A-Za-z_$][\w$]*)", attrs):
        if re.search(pattern, referenced_style_text(source, spread_name)):
            return True
    return False


def resolve_multiline_const(name: str, source: str) -> str | None:
    """Resolve a const assigned a (possibly multi-line) template literal or quoted
    string to its raw string body, e.g. `const ROSTER_ITEM_CSS = \\`...\\``."""
    template = re.search(
        rf"\bconst\s+{re.escape(name)}\s*(?::[^=]+)?=\s*`(?P<body>[\s\S]*?)`",
        source,
    )
    if template:
        return template.group("body")
    quoted = re.search(
        rf"\bconst\s+{re.escape(name)}\s*(?::[^=]+)?=\s*(['\"])(?P<body>[\s\S]*?)\1",
        source,
    )
    if quoted:
        return quoted.group("body")
    return None


def const_rhs_text(name: str, source: str) -> str | None:
    """Return the raw right-hand-side source text of `const NAME = <rhs>`, up to the
    next top-level declaration/boundary. Unlike resolve_multiline_const this keeps the
    expression verbatim, so string concatenation (`'a' + 'b' + fn(x)`) and template
    literals are preserved for substring checks."""
    m = re.search(rf"\bconst\s+{re.escape(name)}\s*(?::[^=]+?)?=\s*", source)
    if not m:
        return None
    rest = source[m.end():]
    boundary = re.search(r"\n(?:const |let |var |function |export |type |}\s*\n)", rest)
    end = boundary.start() if boundary else min(len(rest), 4000)
    return rest[:end]


def expr_raw_text(expr: str, source: str) -> str:
    """Resolve an expression to raw source text usable for substring checks. A bare
    identifier resolves to its const right-hand side (supporting string concatenation);
    anything else (inline literal, concatenation, or template) is returned as-is."""
    expr = expr.strip()
    if re.fullmatch(r"[A-Za-z_$][\w$]*", expr):
        rhs = const_rhs_text(expr, source)
        return rhs if rhs is not None else expr
    return expr


def danger_html_expr(attrs: str) -> str | None:
    """Extract EXPR from `dangerouslySetInnerHTML={{ __html: EXPR }}` in a tag's attrs."""
    m = re.search(
        r"dangerouslySetInnerHTML\s*=\s*\{\{\s*__html\s*:\s*(?P<expr>[\s\S]*?)\}\s*\}",
        attrs,
    )
    return m.group("expr").strip() if m else None


def style_elements(source: str) -> list[tuple[str, str]]:
    """Return (attrs, body) for every <style> element, whether self-closing
    (`<style ... />`) or paired (`<style ...>...</style>`)."""
    elements: list[tuple[str, str]] = []
    for match in re.finditer(r"<style\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>", source):
        attrs = match.group("attrs")
        if match.group("selfclose") == "/":
            elements.append((attrs, ""))
        else:
            close = source.find("</style>", match.end())
            body = source[match.end():close] if close != -1 else ""
            elements.append((attrs, body))
    return elements


def css_snippets_for_team_roster_item(source: str) -> list[str]:
    """Return CSS text that is actually APPLIED to the page via a rendered <style>
    element. Handles the common rendering shapes:
      - <style>...css...</style> or <style>{`...css...`}</style> (children body),
      - <style>{ROSTER_ITEM_CSS}</style> (a const referenced as children), and
      - <style dangerouslySetInnerHTML={{ __html: EXPR }} /> where EXPR is an inline
        string/template/concatenation or a referenced const.

    CSS that only lives in a constant which is never rendered inside a <style>
    element is intentionally NOT returned: a declared-but-unapplied CSS string does
    not make the browser defer off-screen paint, so it must not satisfy V2/V3."""
    snippets: list[str] = []
    for attrs, body in style_elements(source):
        # CSS text written directly inside the rendered <style>.
        if "team-roster-item" in body:
            snippets.append(body)
        # Or a constant referenced as children (e.g. <style>{ROSTER_ITEM_CSS}</style>).
        for ident in re.findall(r"[A-Za-z_$][\w$]*", body):
            resolved = resolve_multiline_const(ident, source)
            if resolved and "team-roster-item" in resolved:
                snippets.append(resolved)
        # Or injected via dangerouslySetInnerHTML={{ __html: EXPR }} on the <style>.
        html_expr = danger_html_expr(attrs)
        if html_expr is not None:
            text = expr_raw_text(html_expr, source)
            if "team-roster-item" in text:
                snippets.append(text)
    return snippets


def css_rule_bodies_for_team_roster_item(source: str) -> list[str]:
    """Return CSS declaration blocks for rules targeting team-roster-item."""
    bodies: list[str] = []
    for snippet in css_snippets_for_team_roster_item(source):
        for match in re.finditer(
            r"\.team-roster-item[^{]*\{(?P<body>[\s\S]*?)\}",
            snippet,
        ):
            bodies.append(match.group("body"))
    return bodies


def css_applies_content_visibility_auto(source: str) -> bool:
    """Return whether a CSS rule on .team-roster-item sets content-visibility: auto."""
    return any(
        re.search(r"content-visibility\s*:\s*auto\b", body)
        for body in css_rule_bodies_for_team_roster_item(source)
    )


def css_applies_contain_intrinsic_size(source: str) -> bool:
    """Return whether a CSS rule on .team-roster-item sets contain-intrinsic-size."""
    return any(
        re.search(r"contain-intrinsic-size\s*:", body)
        for body in css_rule_bodies_for_team_roster_item(source)
    )


def item_li_inline_style_content_visibility_auto(source: str) -> bool:
    """Return whether a team-roster-item li applies content-visibility:auto via an
    inline React style prop (camelCase `contentVisibility`) or a referenced style
    object — the idiomatic React expression of the same optimization the CSS-rule
    form checks."""
    for attrs in find_item_li_attrs(source):
        if style_prop_has_property(source, attrs, "contentVisibility", "auto"):
            return True
        if style_prop_has_property(source, attrs, "content-visibility", "auto"):
            return True
    return False


def item_li_inline_style_intrinsic_size(source: str) -> bool:
    """Return whether a team-roster-item li sets contain-intrinsic-size via an
    inline React style prop (camelCase `containIntrinsicSize`) or a referenced
    style object."""
    for attrs in find_item_li_attrs(source):
        if style_prop_has_property(source, attrs, "containIntrinsicSize"):
            return True
        if style_prop_has_property(source, attrs, "contain-intrinsic-size"):
            return True
    return False


def storage_key_is_versioned(source: str) -> bool:
    """Return whether any setItem uses a storage key that carries an explicit version
    token (vN) attached to the key with a common delimiter — colon, underscore,
    hyphen, or dot (e.g. `key:v1`, `key_v1`, `key-v1`, `key.v1`).

    The skill teaches that the version belongs IN the localStorage key; it shows a
    `:vN` example but does not mandate the colon delimiter. So any explicit
    key-version delimiter counts. (Versioning only inside the JSON payload does not
    version the key and is handled separately by the payload-version check.)"""
    constants = string_constant_expressions(source)
    version_re = re.compile(r"[:_.\-]v\d+")
    delim_join_re = re.compile(r"\.join\s*\(\s*['\"][:_.\-]['\"]\s*\)")
    for args in find_call_arguments(source, "localStorage.setItem"):
        expr = first_argument(args)
        value = resolve_string_expression(expr, constants)
        if value is not None and version_re.search(value):
            return True
        candidates = [expr, constants.get(expr.strip(), "")]
        multiline = resolve_multiline_const(expr.strip(), source)
        if multiline:
            candidates.append(multiline)
        for candidate in candidates:
            if version_re.search(candidate):
                return True
            joins_with_delim = delim_join_re.search(candidate)
            includes_version = re.search(r"['\"]v\d+['\"]", candidate)
            if joins_with_delim and includes_version:
                return True
    return False


def subset_member_variable_names(source: str) -> set[str]:
    """Find local variables that clearly hold sliced or windowed members."""
    names = set(re.findall(r"\b(?:visible|windowed|virtualized|scrollDerived)Members\b", source))
    for match in re.finditer(
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:useMemo\s*\(\s*\(\s*\)\s*=>\s*)?members\s*\.\s*slice\s*\((?P<args>[^)]*)\)",
        source,
    ):
        if slice_args_are_subset(match.group("args")):
            names.add(match.group(1))
    return names


def slice_args_are_subset(args: str) -> bool:
    """Return whether slice arguments clearly drop member rows."""
    parts = split_top_level_arguments(args)
    if not parts:
        return False
    start = parts[0].strip()
    if len(parts) == 1:
        return start not in {"0", "+0"}
    end = parts[1].strip()
    starts_at_zero = start in {"0", "+0"}
    ends_at_length = bool(re.fullmatch(r"members\s*\.\s*length", end))
    return not (starts_at_zero and ends_at_length)


def roster_block_maps_subset(source: str) -> bool:
    """Return whether roster list rows map from a subset of members."""
    block = ul_block(source)
    if not block:
        return False
    for match in re.finditer(r"\bmembers\s*\.\s*slice\s*\((?P<args>[^)]*)\)", block):
        if slice_args_are_subset(match.group("args")):
            return True
    for name in subset_member_variable_names(source):
        if re.search(rf"\b{re.escape(name)}\s*\.\s*map\s*\(", block):
            return True
    return False


def preserves_visible_behavior(source: str) -> bool:
    """Return whether the roster still exhibits its user-visible behavior: it renders
    the full members list via map (not a sliced subset), exposes a per-row toggle
    control (onClick), and conditionally shows a member's department when expanded.
    Intentionally lenient so legitimate refactors are not rejected."""
    if roster_block_maps_subset(source):
        return False
    if not re.search(r"\bmembers\s*\.\s*map\s*\(", source):
        return False
    if not re.search(r"\bonClick\s*=", source):
        return False
    if not re.search(r"\.department\b", source):
        return False
    if not re.search(r"expand|collaps|toggl|open", source, re.IGNORECASE):
        return False
    return True


def braced_body(source: str, open_index: int) -> str:
    """Return the text inside the braces starting at open_index, string-aware."""
    depth = 0
    i = open_index
    n = len(source)
    start = open_index + 1
    state = "code"
    quote = ""
    while i < n:
        ch = source[i]
        if state == "string":
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == quote:
                state = "code"
            i += 1
            continue
        if ch in {"'", '"', "`"}:
            state = "string"
            quote = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start:i]
        i += 1
    return source[start:]


def storage_reader_function_names(source: str) -> set[str]:
    """Return names of helper functions whose body reads localStorage (getItem)."""
    names: set[str] = set()
    for match in re.finditer(
        r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*(?::[^{]*?)?\{",
        source,
    ):
        body = braced_body(source, match.end() - 1)
        if re.search(r"localStorage\s*\.\s*getItem", body):
            names.add(match.group(1))
    for match in re.finditer(
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+?)?=\s*(?:async\s*)?\([^)]*\)\s*=>\s*",
        source,
    ):
        j = match.end()
        if j < len(source) and source[j] == "{":
            body = braced_body(source, j)
        else:
            body = source[j : j + 200]
        if re.search(r"localStorage\s*\.\s*getItem", body):
            names.add(match.group(1))
    return names


def usestate_initializers(source: str) -> list[str]:
    """Return the initializer expression text passed to each useState(...) call,
    skipping any generic <...> type argument."""
    inits: list[str] = []
    n = len(source)
    for match in re.finditer(r"\buseState\b", source):
        i = match.end()
        while i < n and source[i].isspace():
            i += 1
        if i < n and source[i] == "<":
            depth = 0
            while i < n:
                ch = source[i]
                if ch == "<":
                    depth += 1
                elif ch == ">":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            while i < n and source[i].isspace():
                i += 1
        if i < n and source[i] == "(":
            depth = 0
            start = i + 1
            j = i
            state = "code"
            quote = ""
            while j < n:
                ch = source[j]
                if state == "string":
                    if ch == "\\" and j + 1 < n:
                        j += 2
                        continue
                    if ch == quote:
                        state = "code"
                    j += 1
                    continue
                if ch in {"'", '"', "`"}:
                    state = "string"
                    quote = ch
                    j += 1
                    continue
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        inits.append(source[start:j])
                        break
                j += 1
    return inits


def useeffect_callback_bodies(source: str) -> list[str]:
    """Return the first-argument callback text of every useEffect(...) call."""
    return [first_argument(args) for args in find_call_arguments(source, "useEffect")]


def prehydration_script_bodies(source: str) -> list[str]:
    """Return the JS body of every pre-hydration inline script, whether written
    inline in `dangerouslySetInnerHTML={{ __html: `...` }}` or factored into a
    referenced string constant (`__html: BOOTSTRAP_SCRIPT`)."""
    bodies: list[str] = []
    for match in re.finditer(r"dangerouslySetInnerHTML", source):
        window = source[match.start() : match.start() + 4000]
        # A single inline string/template literal: capture it whole (it may itself
        # contain `}}`, so a full-literal match is safer than scanning to `}}`).
        inline = re.match(r"[\s\S]*?__html\s*:\s*(`[\s\S]*?`|'[^']*'|\"[^\"]*\")", window)
        # A referenced identifier (possibly a string-concatenation const).
        ident = re.match(r"[\s\S]*?__html\s*:\s*([A-Za-z_$][\w$]*)\s*\}", window)
        if inline:
            bodies.append(inline.group(1))
        elif ident:
            bodies.append(expr_raw_text(ident.group(1), source))
        else:
            # Fallback: an inline concatenation/expression up to the closing `}}`.
            generic = re.match(r"[\s\S]*?__html\s*:\s*(?P<expr>[\s\S]*?)\}\s*\}", window)
            if generic:
                bodies.append(generic.group("expr"))
    return bodies


def _storage_reading_script_bodies(source: str) -> list[str]:
    """Pre-hydration script bodies that read persisted client storage (getItem)."""
    return [
        body
        for body in prehydration_script_bodies(source)
        if re.search(r"localStorage\s*\.\s*getItem", body)
    ]


def _prehydration_storage_script_present(source: str) -> bool:
    """Return whether a synchronous pre-hydration inline script reads persisted
    client storage before React hydrates."""
    return bool(_storage_reading_script_bodies(source))


def script_window_targets(source: str) -> set[str]:
    """Global identifiers a storage-reading pre-hydration script writes its restored
    value onto, e.g. `window.__ROSTER_EXPANDED__ = ...` -> {'__ROSTER_EXPANDED__'}.
    These are the handoff points a first render can consume so it matches the DOM."""
    targets: set[str] = set()
    for body in _storage_reading_script_bodies(source):
        for m in re.finditer(r"window\s*\.\s*([A-Za-z_$][\w$]*)\s*=(?!=)", body):
            targets.add(m.group(1))
        for m in re.finditer(r"window\s*\[\s*['\"]([^'\"]+)['\"]\s*\]\s*=(?!=)", body):
            targets.add(m.group(1))
    return targets


def script_mutates_dom(source: str) -> bool:
    """Return whether a storage-reading pre-hydration script actively restores page
    state by mutating the DOM (class/attribute/style/text) after locating elements —
    the skill's imperative pre-hydration DOM-patch pattern."""
    for body in _storage_reading_script_bodies(source):
        locates = re.search(
            r"document\s*\.\s*(?:getElementById|querySelector|querySelectorAll|getElementsBy\w+)",
            body,
        )
        mutates = re.search(
            r"\.\s*(?:classList\b|className\b|setAttribute\b|style\b|textContent\b|innerHTML\b|dataset\b)",
            body,
        )
        if locates and mutates:
            return True
    return False


def initializer_consumes_targets(source: str, targets: set[str]) -> bool:
    """Return whether any useState initializer reads one of the window `targets` the
    pre-hydration script populated — directly, or via a reader helper it calls — so
    the first React render reflects the restored value (and therefore matches the DOM
    the script already produced)."""
    if not targets:
        return False
    target_re = re.compile("|".join(rf"\b{re.escape(t)}\b" for t in targets))
    reader_names: set[str] = set()
    for match in re.finditer(
        r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*(?::[^{]*?)?\{", source
    ):
        body = braced_body(source, match.end() - 1)
        if target_re.search(body):
            reader_names.add(match.group(1))
    for match in re.finditer(
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+?)?=\s*(?:async\s*)?\([^)]*\)\s*=>\s*",
        source,
    ):
        j = match.end()
        body = braced_body(source, j) if j < len(source) and source[j] == "{" else source[j : j + 300]
        if target_re.search(body):
            reader_names.add(match.group(1))
    for init in usestate_initializers(source):
        if target_re.search(init):
            return True
        if any(re.search(rf"\b{re.escape(name)}\b", init) for name in reader_names):
            return True
    return False


def storage_read_is_hydration_safe(source: str) -> bool:
    """Return whether the persisted expanded-row state is restored with the
    flicker-free, mismatch-free pattern the skill rendering-hydration-no-flicker
    sanctions.

    The panel is a server-rendered ('use client') Next.js component. The skill labels
    reading localStorage in a useState initializer as "Incorrect (breaks SSR)" (it runs
    during render; the server has no localStorage and the first client render would
    disagree with the server HTML). It also labels loading storage AFTER the page
    appears as an "Incorrect (visual flickering)" pattern. The sanctioned pattern is a
    synchronous pre-hydration inline script that resolves and APPLIES the persisted
    value before React hydrates. The instruction forbids the symptom of the wrong
    patterns ("must not cause a hydration mismatch or a flash of incorrect content on
    first paint").

    Graded against the semantic invariant rather than one exact code shape:
      (A) no useState initializer reads client storage (that would break SSR), AND
      (C) a pre-hydration inline script reads the persisted value before hydration
          (inline body or referenced const), AND
      (D) that script ACTIVELY restores page state before first paint — proven by
          EITHER
            (i)  it writes the restored value to a window global that a useState
                 initializer consumes, so the first React render matches the DOM, OR
            (ii) it imperatively mutates the DOM (class/attribute/style/text) after
                 locating the target rows (the skill's DOM-patch pattern).
    A merely decorative script whose result is never consumed, and a default-empty
    initializer that only restores later in a post-mount useEffect, both fail (D)
    because they leave the first paint showing the wrong (default) content.

    Checked structurally because the tsc-only container cannot execute a real SSR
    render."""
    readers = storage_reader_function_names(source)

    def reads_storage(expr: str) -> bool:
        if re.search(r"localStorage\s*\.\s*getItem", expr):
            return True
        return any(re.search(rf"\b{re.escape(name)}\b", expr) for name in readers)

    # (C) a synchronous pre-hydration inline script that reads storage before hydration.
    if not _prehydration_storage_script_present(source):
        return False

    # (A) reject a storage read in any useState initializer — it runs during the server
    #     render and breaks SSR regardless of the bootstrap script.
    for init in usestate_initializers(source):
        if reads_storage(init):
            return False

    # (D) the script must actively restore state before first paint, not be decorative.
    if initializer_consumes_targets(source, script_window_targets(source)):
        return True
    if script_mutates_dom(source):
        return True
    return False


def try_catch_spans(source: str) -> list[tuple[int, int]]:
    """Return (open_brace_index, close_brace_index) spans for try blocks that are
    immediately followed by a catch clause, using string-aware brace matching."""
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"\btry\b\s*\{", source):
        brace_open = match.end() - 1
        depth = 0
        i = brace_open
        state = "code"
        quote = ""
        while i < len(source):
            ch = source[i]
            if state == "string":
                if ch == "\\" and i + 1 < len(source):
                    i += 2
                    continue
                if ch == quote:
                    state = "code"
                i += 1
                continue
            if ch in {"'", '"', "`"}:
                state = "string"
                quote = ch
                i += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    if re.match(r"\s*catch\b", source[i + 1:]):
                        spans.append((brace_open, i))
                    break
            i += 1
    return spans


def storage_access_is_resilient(source: str) -> bool:
    """Return whether every localStorage read (getItem) and write (setItem) call is
    enclosed in a try/catch, so storage failures (private browsing, quota, disabled)
    are recovered from gracefully instead of crashing the component."""
    spans = try_catch_spans(source)

    def inside_try(idx: int) -> bool:
        return any(open_idx < idx < close_idx for open_idx, close_idx in spans)

    getters = [m.start() for m in re.finditer(r"\blocalStorage\s*\.\s*getItem\s*\(", source)]
    setters = [m.start() for m in re.finditer(r"\blocalStorage\s*\.\s*setItem\s*\(", source)]
    if not getters or not setters:
        return False
    return all(inside_try(idx) for idx in getters + setters)


def test_v1_output_artifact_exists_and_is_tsx_like() -> None:
    """Validate that the artifact exists and parses as TSX."""
    assert OUTPUT_PATH.exists(), f"{OUTPUT_PATH} does not exist"
    text = read_output()
    assert text.strip(), "output artifact is empty"
    syntax_errors = typescript_syntax_errors(text)
    assert not syntax_errors, "output has TSX syntax errors:\n" + "\n".join(syntax_errors)


def test_v2_roster_item_li_uses_content_visibility_auto() -> None:
    """Verify roster items defer off-screen paint via content-visibility:auto on
    team-roster-item, applied either as a CSS rule inside a rendered <style> element
    or as an inline React style prop. Declared-but-unrendered CSS does not count."""
    code = code_text()
    assert css_applies_content_visibility_auto(code) or item_li_inline_style_content_visibility_auto(code)


def test_v3_roster_item_li_sets_intrinsic_size() -> None:
    """Verify roster items set contain-intrinsic-size on team-roster-item, applied
    either as a CSS rule inside a rendered <style> element or as an inline React style
    prop. Declared-but-unrendered CSS does not count."""
    code = code_text()
    assert css_applies_contain_intrinsic_size(code) or item_li_inline_style_intrinsic_size(code)


def test_v4_storage_key_is_versioned() -> None:
    """Confirm the expanded-row storage key carries an explicit version token attached
    with a common delimiter (:v1, _v1, -v1, or .v1). The skill teaches versioning the
    key and does not mandate a specific delimiter."""
    assert storage_key_is_versioned(code_text())


def test_v5_unversioned_storage_key_is_not_used_for_persistence() -> None:
    """Reject persisting prefs under the old key (a one-time migration getItem read is allowed)."""
    assert not persists_under_unversioned_key(code_text())


def test_v6_storage_payload_does_not_embed_version_object() -> None:
    """Reject persisted JSON objects that contain a version field: versioning belongs
    in the storage key, and the payload should stay the minimal expanded-id array."""
    assert not setitem_serializes_object_with_version(code_text())


def test_v7_roster_preserves_visible_behavior() -> None:
    """Confirm user-visible behavior is preserved: the full members list is rendered
    (no sliced/windowed subset), each row has a toggle control, and the department is
    shown only when a row is expanded (instruction: user-visible behavior stays the
    same)."""
    assert preserves_visible_behavior(code_text())


def test_v8_storage_access_recovers_from_failure() -> None:
    """Confirm expanded-row persistence reads and writes are wrapped in try/catch so
    storage failures are recovered from gracefully (skill client-localstorage-schema;
    instruction Issue 2 resilient restore)."""
    assert storage_access_is_resilient(code_text())


def test_v9_storage_read_is_hydration_safe() -> None:
    """Hydration safety (instruction Issue 2, server-rendered dashboard): restoring the
    persisted expanded rows must not cause a hydration mismatch or a flash of incorrect
    content on first paint. Per skill rendering-hydration-no-flicker, the sanctioned
    pattern for client-only storage is a synchronous pre-hydration inline script that
    resolves AND applies the persisted value before hydration; a useState-initializer
    storage read ("Incorrect (breaks SSR)") is disqualifying, and a decorative script
    whose result is never used to restore first paint does not qualify. The tsc-only
    container cannot run an SSR render, so this is checked structurally against the
    semantic invariant: no storage read in a useState initializer, and a
    `<script dangerouslySetInnerHTML>` (inline body or referenced const) that reads
    storage before hydration AND actively restores it — either by writing a window
    value the initializer consumes, or by imperatively patching the rendered rows'
    DOM (class/attribute/style/text)."""
    assert storage_read_is_hydration_safe(code_text())
