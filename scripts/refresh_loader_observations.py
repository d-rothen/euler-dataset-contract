"""Snapshot loader declarations without importing loading or array packages.

Run with --check against a checkout to detect upstream drift. The snapshot is
evidence, not an executable profile or a claim that an annotation is correct.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import operator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "fixtures/inventory/loader-observations.json"
VOCABULARY = ROOT / "fixtures/inventory/euler-loading-modality-types.json"


#: Arithmetic folded on numeric constants, e.g. ``2**24 - 1`` or ``_FAR / _MAX``.
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.USub: operator.neg, ast.UAdd: operator.pos}
#: Larger integer exponents are refused rather than evaluated.
_MAX_EXPONENT = 256


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class _Module:
    """An imported loader module: its constants (``alias.NAME``) and declarations.

    ``declarations`` maps each ``@modality_meta`` function to its annotation in
    the runtime ``_modality_meta`` shape, so ``alias.func._modality_meta[...]``
    (a GPU loader reusing its CPU counterpart's meta) resolves statically.
    """

    def __init__(self, constants: dict[str, Any], declarations: dict[str, dict[str, Any]]) -> None:
        self.constants = constants
        self.declarations = declarations


def _runtime_annotation(declaration: dict[str, Any]) -> dict[str, Any]:
    """The ``_modality_meta`` dict euler-loading's ``modality_meta`` decorator attaches."""
    return {
        "type": declaration.get("modality_type"),
        "dtype": declaration.get("dtype"),
        "hierarchical": declaration.get("hierarchical", False),
        "shape": declaration.get("shape"),
        "file_formats": declaration.get("file_formats") or [],
        "output_range": declaration.get("output_range"),
        "output_unit": declaration.get("output_unit"),
        "requires_meta": declaration.get("requires_meta") or [],
        "meta": declaration.get("meta") or {},
    }


def _is_modality_meta(decorator: ast.AST) -> bool:
    return (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "modality_meta"
    )


def _declarations(
    tree: ast.Module, constants: dict[str, Any], relative: str
) -> list[tuple[ast.FunctionDef, dict[str, Any]]]:
    """Return each ``@modality_meta`` function of *tree* with its literal declaration."""
    found = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not _is_modality_meta(decorator):
                continue
            try:
                declaration = {kw.arg: _literal(kw.value, constants) for kw in decorator.keywords}
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Nonliteral declaration at {relative}:{node.lineno}") from exc
            found.append((node, declaration))
    return found


def _literal(node: ast.AST, constants: dict[str, Any]) -> Any:
    """Evaluate a declaration without executing loader code.

    Beyond plain literals this resolves module constants (also ``alias.NAME``
    on an imported loader module), ``[value] * n``, ``list(...)`` /
    ``tuple(...)`` / ``len(...)`` of a literal, ``{**mapping}`` unpacking, and
    arithmetic (``+ - * / // % **``, unary ``-``/``+``) on numbers, the
    side-effect-free spellings loader annotations use. Anything else raises
    ``ValueError``.
    """
    if isinstance(node, ast.Name) and node.id in constants:
        value = constants[node.id]
        if isinstance(value, _Module):
            raise ValueError(f"{node.id} is a module, not a constant")
        return value
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        module = constants.get(node.value.id)
        if isinstance(module, _Module) and node.attr in module.constants:
            return module.constants[node.attr]
        raise ValueError(f"{ast.unparse(node)} is not a literal constant")
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "_modality_meta"
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
    ):
        module = constants.get(node.value.value.id)
        if isinstance(module, _Module) and node.value.attr in module.declarations:
            return json.loads(json.dumps(module.declarations[node.value.attr]))
        raise ValueError(f"{ast.unparse(node)} is not a declared loader annotation")
    if isinstance(node, ast.Subscript):
        container = _literal(node.value, constants)
        index = node.slice.value if isinstance(node.slice, getattr(ast, "Index", ())) else node.slice
        key = _literal(index, constants)
        try:
            return container[key]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"{ast.unparse(node)} cannot be looked up: {exc}") from exc
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal(item, constants) for item in node.elts]
    if isinstance(node, ast.Dict):
        result: dict[Any, Any] = {}
        for key, value in zip(node.keys, node.values):
            if key is None:  # ``**other`` unpacks a constant mapping
                unpacked = _literal(value, constants)
                if not isinstance(unpacked, dict):
                    raise ValueError(f"**{ast.unparse(value)} does not unpack a mapping")
                result.update(unpacked)
            else:
                result[_literal(key, constants)] = _literal(value, constants)
        return result
    if isinstance(node, ast.BinOp):
        left, right = _literal(node.left, constants), _literal(node.right, constants)
        if isinstance(node.op, ast.Mult):
            if isinstance(left, list) and type(right) is int:
                return left * right
            if isinstance(right, list) and type(left) is int:
                return right * left
        apply = _BINARY_OPERATORS.get(type(node.op))
        if apply is None or not (_is_number(left) and _is_number(right)):
            raise ValueError(f"{ast.unparse(node)} is not numeric constant arithmetic")
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise ValueError(f"{ast.unparse(node)} has a refused exponent")
        try:
            return apply(left, right)
        except ArithmeticError as exc:
            raise ValueError(f"{ast.unparse(node)} cannot be evaluated: {exc}") from exc
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        value = _literal(node.operand, constants)
        if not _is_number(value):
            raise ValueError(f"{ast.unparse(node)} is not numeric constant arithmetic")
        return _UNARY_OPERATORS[type(node.op)](value)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"list", "tuple", "len"}
        and len(node.args) == 1
        and not node.keywords
    ):
        value = _literal(node.args[0], constants)
        if node.func.id == "len":
            if not isinstance(value, (list, dict, str)):
                raise ValueError(f"{ast.unparse(node)} does not measure a literal")
            return len(value)
        if not isinstance(value, list):
            raise ValueError(f"{ast.unparse(node)} does not convert a sequence")
        return list(value)
    return ast.literal_eval(node)


def snapshot(loading_root: Path) -> dict[str, Any]:
    records = []
    sources = {}
    constant_cache: dict[str, dict[str, Any]] = {}
    handle_cache: dict[str, _Module] = {}

    def module_handle(path: Path) -> _Module:
        """Constants and runtime-shaped declarations of an imported loader module."""
        relative = path.relative_to(loading_root).as_posix()
        if relative not in handle_cache:
            constants = literal_constants(path)
            tree = ast.parse(path.read_bytes(), filename=relative)
            handle_cache[relative] = _Module(
                constants,
                {
                    node.name: _runtime_annotation(declaration)
                    for node, declaration in _declarations(tree, constants, relative)
                },
            )
        return handle_cache[relative]

    def literal_constants(path: Path) -> dict[str, Any]:
        relative = path.relative_to(loading_root).as_posix()
        if relative in constant_cache:
            return constant_cache[relative]
        data = path.read_bytes()
        sources[relative] = hashlib.sha256(data).hexdigest()
        constants: dict[str, Any] = {}
        constant_cache[relative] = constants
        for node in ast.parse(data, filename=relative).body:
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and (node.module or "").startswith("euler_loading.loaders.")
            ):
                package = loading_root.joinpath(*node.module.split("."))
                dependency = package.with_suffix(".py")
                if dependency.is_file():
                    imported = literal_constants(dependency)
                    for alias in node.names:
                        if alias.name in imported:
                            constants[alias.asname or alias.name] = imported[alias.name]
                elif package.is_dir():
                    # ``from euler_loading.loaders.cpu import synscapes as _cpu``
                    for alias in node.names:
                        submodule = package / f"{alias.name}.py"
                        if submodule.is_file():
                            constants[alias.asname or alias.name] = module_handle(submodule)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                try:
                    value = _literal(node.value, constants)
                except (ValueError, TypeError):
                    continue
                for target in targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = value
        return constants

    for backend in ("cpu", "gpu"):
        directory = loading_root / "euler_loading/loaders" / backend
        files = sorted(directory.glob("*.py"))
        if not files:
            raise ValueError(f"No loader sources found in {directory}")
        for path in files:
            if path.name.startswith("_"):
                continue
            relative = path.relative_to(loading_root).as_posix()
            data = path.read_bytes()
            sources[relative] = hashlib.sha256(data).hexdigest()
            tree = ast.parse(data, filename=relative)
            constants = literal_constants(path)
            for node, declaration in _declarations(tree, constants, relative):
                records.append(
                    {
                        "loader": path.stem,
                        "function": node.name,
                        "backend": backend,
                        "source": relative,
                        "line": node.lineno,
                        "declared": declaration,
                    }
                )
    catalog_path = loading_root / "euler_loading/loaders/generate/loaders.json"
    catalog_bytes = catalog_path.read_bytes()
    catalog = json.loads(catalog_bytes)
    return {
        "contract": {"kind": "loader_observations", "version": "1.0"},
        "provenance": {
            "repository": "euler-loading",
            "method": "AST literal extraction; no loader execution",
            "consumed_by_runtime": False,
            "catalog_path": catalog_path.relative_to(loading_root).as_posix(),
            "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        },
        "sources": dict(sorted(sources.items())),
        "observations": records,
        "catalog": catalog["supportedLoaders"],
    }


def vocabulary(observations: dict[str, Any]) -> dict[str, Any]:
    existing = json.loads(VOCABULARY.read_text())
    entries = observations["catalog"]
    types: dict[str, list[str]] = {}
    functions = set()
    for loader in entries:
        for entry in loader["modalities"]:
            functions.add(entry["function"])
            types.setdefault(entry["type"], []).append(
                f"{loader['name']}.{entry['function']}"
            )
    existing["provenance"]["sha256"] = observations["provenance"]["catalog_sha256"]
    existing["loaders"] = sorted(loader["name"] for loader in entries)
    existing["modality_types"] = {
        key: sorted(set(value)) for key, value in sorted(types.items())
    }
    existing["loader_function_names"] = sorted(functions)
    return existing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("loading_root", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    observed = snapshot(args.loading_root.resolve())
    outputs = {OUTPUT: observed, VOCABULARY: vocabulary(observed)}
    for path, value in outputs.items():
        text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not path.is_file() or path.read_text() != text:
                raise SystemExit(f"Stale loader evidence: {path.relative_to(ROOT)}")
        else:
            path.write_text(text)
    print(
        f"{'Checked' if args.check else 'Recorded'} {len(observed['observations'])} loader declarations"
    )


if __name__ == "__main__":
    main()
