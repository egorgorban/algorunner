"""Per-language test-program renderers: the single place where the
``(code, tests)`` strings handed to the executors are produced.

D-00c / EXEC-03: the CodeExecutor Protocol and both subprocess backends under
``tools/`` are unchanged; they already accept literal source for ``code`` and
``tests`` (Python: statements appended after ``code``; Go: statements placed in
a generated ``func main``). This module turns language-neutral StructuredCase
lists into those strings.

Safety (T-02-09-01): no LLM-authored text is interpolated into source except
(a) function names, after EntryPoint identifier validation, and (b) values and
labels through the type-directed literal renderers below (``ascii()`` for
Python, the escape-everything ``_go_string`` for Go).
"""

import json
import re
from typing import NamedTuple

from algorunner.schemas.solution import EntryPoint, StructuredCase
from algorunner.schemas.typespec import MAX_CASES, TypeNode

GO_HARNESS_IMPORTS = ("fmt", "math", "os", "reflect", "sort")
_MAX_ARGS_DESC = 300


class RenderedProgram(NamedTuple):
    code: str
    tests: str


def _validated(entry_point: EntryPoint, cases: list[StructuredCase]) -> list[StructuredCase]:
    if not cases:
        raise ValueError("refusing to render a program with zero test cases")
    if len(cases) > MAX_CASES:
        raise ValueError(f"{len(cases)} test cases exceed the maximum of {MAX_CASES}")
    return [entry_point.check_case(c) for c in cases]


# ------------------------------------------------------------------ Python

_PY_HELPERS = '''\
import math as _algorunner_math
import sys as _algorunner_sys


def _algorunner_eq(got, want):
    if isinstance(want, bool):
        return isinstance(got, bool) and got == want
    if isinstance(want, int):
        return isinstance(got, int) and not isinstance(got, bool) and got == want
    if isinstance(want, float):
        if isinstance(got, bool) or not isinstance(got, (int, float)):
            return False
        return _algorunner_math.isclose(got, want, rel_tol=1e-6, abs_tol=1e-6)
    if isinstance(want, list):
        if not isinstance(got, (list, tuple)) or len(got) != len(want):
            return False
        return all(_algorunner_eq(g, w) for g, w in zip(got, want))
    return isinstance(got, str) and got == want


def _algorunner_same(got, want, unordered):
    if unordered and isinstance(got, (list, tuple)) and isinstance(want, list):
        if len(got) != len(want):
            return False
        return sorted(ascii(x) for x in got) == sorted(ascii(x) for x in want)
    return _algorunner_eq(got, want)


def _algorunner_short(value):
    text = ascii(value)
    return text if len(text) <= 300 else text[:297] + "..."


def _algorunner_fail(index, label, args, detail):
    _algorunner_sys.stderr.write(
        "FAIL case %d (%s): args=%s %s\\n" % (index, ascii(label)[1:-1], args, detail)
    )

'''


def render_python_program(
    code_python: str, entry_point: EntryPoint, cases: list[StructuredCase]
) -> RenderedProgram:
    checked = _validated(entry_point, cases)
    literal = (
        "[\n"
        + "".join(
            f"    ({ascii(c.label)}, {ascii(c.args)}, {ascii(c.expected)}),\n" for c in checked
        )
        + "]"
    )
    tests = (
        _PY_HELPERS
        + f"_algorunner_cases = {literal}\n"
        + f"_algorunner_unordered = {entry_point.unordered_result!r}\n"
        + "_algorunner_failed = 0\n"
        + "for _algorunner_i, (_algorunner_label, _algorunner_args, _algorunner_want)"
        + " in enumerate(_algorunner_cases):\n"
        + "    _algorunner_desc = _algorunner_short(_algorunner_args)\n"
        + "    try:\n"
        + f"        _algorunner_got = {entry_point.python_name}(*_algorunner_args)\n"
        + "    except BaseException as _algorunner_exc:\n"
        + "        _algorunner_failed += 1\n"
        + "        _algorunner_fail(_algorunner_i, _algorunner_label, _algorunner_desc,\n"
        + "                         'raised=' + _algorunner_short(repr(_algorunner_exc)))\n"
        + "        continue\n"
        + "    if not _algorunner_same(_algorunner_got, _algorunner_want, _algorunner_unordered):\n"
        + "        _algorunner_failed += 1\n"
        + "        _algorunner_fail(_algorunner_i, _algorunner_label, _algorunner_desc,\n"
        + "                         'got=%s want=%s' % (_algorunner_short(_algorunner_got),\n"
        + "                                             _algorunner_short(_algorunner_want)))\n"
        + "if _algorunner_failed:\n"
        + "    _algorunner_sys.stderr.write('%d of %d cases failed\\n' % (_algorunner_failed, "
        + "len(_algorunner_cases)))\n"
        + "    _algorunner_sys.exit(1)\n"
        + "print('ALGORUNNER PASS %d/%d' % (len(_algorunner_cases), len(_algorunner_cases)))\n"
    )
    return RenderedProgram(code=code_python, tests=tests)


# ---------------------------------------------------------------------- Go

_GO_IMPORT_BLOCK_RE = re.compile(r"import\s*\(([^)]*)\)", re.DOTALL)
_GO_IMPORT_SINGLE_RE = re.compile(r'import\s+(?:\w+\s+)?"([^"]+)"')
_GO_QUOTED_PATH_RE = re.compile(r'"([^"]+)"')


def _existing_go_imports(code: str) -> set[str]:
    paths: list[str] = []
    for block in _GO_IMPORT_BLOCK_RE.findall(code):
        paths.extend(_GO_QUOTED_PATH_RE.findall(block))
    paths.extend(_GO_IMPORT_SINGLE_RE.findall(code))
    return set(paths)


def ensure_go_imports(code: str, required: tuple[str, ...]) -> str:
    """Injects one ``import (...)`` block after the ``package`` line for the
    packages in ``required`` that ``code`` does not already import (Go rejects
    both duplicate and unused imports)."""
    existing = _existing_go_imports(code)
    missing = [pkg for pkg in required if pkg not in existing]
    if not missing:
        return code
    import_block = "import (\n" + "".join(f'\t"{pkg}"\n' for pkg in missing) + ")\n"
    lines = code.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip().startswith("package "):
            return "".join(lines[: i + 1]) + "\n" + import_block + "".join(lines[i + 1 :])
    # No package line (malformed code): prepend; go build reports the real error.
    return import_block + code


_GO_HELPERS = '''
func algorunnerEqualValue(g, w reflect.Value) bool {
	if !g.IsValid() || !w.IsValid() {
		return g.IsValid() == w.IsValid()
	}
	if g.Type() != w.Type() {
		return false
	}
	switch w.Kind() {
	case reflect.Slice:
		if g.Len() != w.Len() {
			return false
		}
		for i := 0; i < w.Len(); i++ {
			if !algorunnerEqualValue(g.Index(i), w.Index(i)) {
				return false
			}
		}
		return true
	case reflect.Float64:
		a, b := g.Float(), w.Float()
		if math.IsNaN(a) || math.IsNaN(b) {
			return false
		}
		if a == b {
			return true
		}
		diff := math.Abs(a - b)
		return diff <= 1e-6 || diff <= 1e-6*math.Max(math.Abs(a), math.Abs(b))
	}
	return reflect.DeepEqual(g.Interface(), w.Interface())
}

func algorunnerEqual(got, want interface{}) bool {
	return algorunnerEqualValue(reflect.ValueOf(got), reflect.ValueOf(want))
}

func algorunnerKey(v reflect.Value) string {
	if v.Kind() == reflect.Slice {
		s := "["
		for i := 0; i < v.Len(); i++ {
			if i > 0 {
				s += ","
			}
			s += algorunnerKey(v.Index(i))
		}
		return s + "]"
	}
	if v.Kind() == reflect.String {
		return fmt.Sprintf("%q", v.String())
	}
	return fmt.Sprintf("%#v", v.Interface())
}

func algorunnerEqualUnordered(got, want interface{}) bool {
	g, w := reflect.ValueOf(got), reflect.ValueOf(want)
	if !g.IsValid() || !w.IsValid() || g.Kind() != reflect.Slice || w.Kind() != reflect.Slice ||
		g.Type() != w.Type() || g.Len() != w.Len() {
		return algorunnerEqual(got, want)
	}
	gk := make([]string, g.Len())
	wk := make([]string, w.Len())
	for i := 0; i < g.Len(); i++ {
		gk[i] = algorunnerKey(g.Index(i))
		wk[i] = algorunnerKey(w.Index(i))
	}
	sort.Strings(gk)
	sort.Strings(wk)
	for i := range gk {
		if gk[i] != wk[i] {
			return false
		}
	}
	return true
}

func algorunnerShort(v interface{}) string {
	r := []rune(fmt.Sprintf("%v", v))
	if len(r) > 300 {
		return string(r[:297]) + "..."
	}
	return string(r)
}

func algorunnerCheck(index int, label string, args string, unordered bool, run func() (interface{}, interface{})) (ok bool) {
	defer func() {
		if r := recover(); r != nil {
			fmt.Fprintf(os.Stderr, "FAIL case %d (%s): args=%s panic=%s\\n", index, label, args, algorunnerShort(r))
			ok = false
		}
	}()
	got, want := run()
	if unordered {
		ok = algorunnerEqualUnordered(got, want)
	} else {
		ok = algorunnerEqual(got, want)
	}
	if !ok {
		fmt.Fprintf(os.Stderr, "FAIL case %d (%s): args=%s got=%s want=%s\\n", index, label, args, algorunnerShort(got), algorunnerShort(want))
	}
	return ok
}
'''


def _go_string(text: str) -> str:
    out = ['"']
    for ch in text:
        cp = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif 0x20 <= cp <= 0x7E:
            out.append(ch)
        elif 0xD800 <= cp <= 0xDFFF:
            out.append("\\uFFFD")
        elif cp <= 0xFFFF:
            out.append(f"\\u{cp:04X}")
        else:
            out.append(f"\\U{cp:08X}")
    out.append('"')
    return "".join(out)


def _go_type(node: TypeNode) -> str:
    if node.kind == "list":
        assert node.element is not None
        return "[]" + _go_type(node.element)
    return {"int": "int", "float": "float64", "bool": "bool", "str": "string"}[node.kind]


def _go_literal(value: object, node: TypeNode) -> str:
    if node.kind == "int":
        return f"int({value})"
    if node.kind == "float":
        return f"float64({value!r})"
    if node.kind == "bool":
        return "true" if value else "false"
    if node.kind == "str":
        assert isinstance(value, str)
        return _go_string(value)
    assert node.element is not None and isinstance(value, list)
    items = ", ".join(_go_literal(v, node.element) for v in value)
    return f"{_go_type(node)}{{{items}}}"


def render_go_program(
    code_go: str, entry_point: EntryPoint, cases: list[StructuredCase]
) -> RenderedProgram:
    checked = _validated(entry_point, cases)
    param_nodes = entry_point.param_nodes()
    return_node = entry_point.return_node()
    unordered = "true" if entry_point.unordered_result else "false"
    lines = ["algorunnerFailed := 0"]
    for i, case in enumerate(checked):
        call_args = ", ".join(
            _go_literal(a, n) for a, n in zip(case.args, param_nodes, strict=True)
        )
        desc = json.dumps(case.args)
        if len(desc) > _MAX_ARGS_DESC:
            desc = desc[: _MAX_ARGS_DESC - 3] + "..."
        lines.append(
            f"if !algorunnerCheck({i}, {_go_string(case.label)}, {_go_string(desc)}, {unordered},"
            f" func() (interface{{}}, interface{{}}) {{ return {entry_point.go_name}({call_args}),"
            f" {_go_literal(case.expected, return_node)} }}) {{\n\talgorunnerFailed++\n}}"
        )
    n = len(checked)
    lines.append(
        "if algorunnerFailed > 0 {\n"
        f'\tfmt.Fprintf(os.Stderr, "%d of %d cases failed\\n", algorunnerFailed, {n})\n'
        "\tos.Exit(1)\n}\n"
        f'fmt.Println("ALGORUNNER PASS {n}/{n}")'
    )
    code = ensure_go_imports(code_go, GO_HARNESS_IMPORTS)
    if not code.endswith("\n"):
        code += "\n"
    return RenderedProgram(code=code + _GO_HELPERS, tests="\n".join(lines))
