import ast
import warnings
from pathlib import Path
from typing import Optional


class VariableNameGenerator:
    def __init__(self):
        self._index = 0

    def next(self) -> str:
        result = ""
        n = self._index
        self._index += 1

        while True:
            result = chr(ord("a") + (n % 26)) + result
            n //= 26
            if n == 0:
                break

        return result


class DocstringRemover(ast.NodeTransformer):
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        if ast.get_docstring(node):
            node.body = node.body[1:]
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        if ast.get_docstring(node):
            node.body = node.body[1:]
        self.generic_visit(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        if ast.get_docstring(node):
            node.body = node.body[1:]
        self.generic_visit(node)
        return node


class TypeHintStripper(ast.NodeTransformer):
    def __init__(self):
        self._in_funcdef = False
        self._func_var_names = VariableNameGenerator()
        self._var_map: dict[str, str] = {}
        self._in_class = False

    def _is_magic(self, name: str) -> bool:
        return name.startswith("__") and name.endswith("__")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        arg_names = {arg.arg for arg in node.args.args}
        arg_names |= {arg.arg for arg in node.args.posonlyargs}
        arg_names |= {arg.arg for arg in node.args.kwonlyargs}
        if node.args.vararg:
            arg_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            arg_names.add(node.args.kwarg.arg)

        assigned_vars = []
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        if target.id not in arg_names:
                            assigned_vars.append(target.id)
            elif isinstance(child, (ast.For, ast.AsyncFor)):
                if isinstance(child.target, ast.Name):
                    if child.target.id not in arg_names:
                        assigned_vars.append(child.target.id)

        var_map = {}
        gen = VariableNameGenerator()
        for var in assigned_vars:
            if var not in arg_names and not self._is_magic(var):
                var_map[var] = gen.next()

        self._replace_vars(node, var_map, arg_names)

        node.args.posonlyargs = self._clear_annotations(node.args.posonlyargs)
        node.args.args = self._clear_annotations(node.args.args)
        node.args.vararg = self._clear_annotation(node.args.vararg)
        node.args.kwonlyargs = self._clear_annotations(node.args.kwonlyargs)
        node.args.kwarg = self._clear_annotation(node.args.kwarg)
        node.returns = None

        for default in node.args.defaults:
            self._strip_annotation(default)
        for default in node.args.kw_defaults:
            if default:
                self._strip_annotation(default)

        return node

    def _replace_vars(
        self, node: ast.AST, var_map: dict[str, str], arg_names: set[str]
    ) -> None:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                if child.id in var_map and child.id not in arg_names:
                    child.id = var_map[child.id]
            elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                if child.id in var_map:
                    child.id = var_map[child.id]

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        return self.visit_FunctionDef(node)

    def _clear_annotations(self, args: list[ast.arg]) -> list[ast.arg]:
        for arg in args:
            arg.annotation = None
        return args

    def _clear_annotation(self, arg: Optional[ast.arg]) -> Optional[ast.arg]:
        if arg:
            arg.annotation = None
        return arg

    def _strip_annotation(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            if hasattr(child, "annotation"):
                child.annotation = None

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.Assign:
        target = node.target
        if isinstance(target, ast.Name):
            new_assign = ast.Assign(
                targets=[ast.Name(id=target.id, ctx=ast.Store())],
                value=node.value,
                lineno=node.lineno,
                col_offset=node.col_offset,
            )
            return new_assign
        return node

    def visit_With(self, node: ast.With) -> ast.With:
        for item in node.items:
            item.optional_vars = None
        self.generic_visit(node)
        return node

    def visit_AsyncWith(self, node: ast.AsyncWith) -> ast.AsyncWith:
        for item in node.items:
            item.optional_vars = None
        self.generic_visit(node)
        return node


class SingleLineBodyConverter(ast.NodeTransformer):
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        if len(node.body) == 1 and isinstance(node.body[0], ast.Expr):
            expr = node.body[0]
            if isinstance(expr.value, ast.Constant):
                node.body = [ast.Return(value=expr.value)]
            elif not isinstance(
                expr.value,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.With,
                    ast.AsyncWith,
                    ast.Try,
                    ast.ClassDef,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                node.body = [ast.Return(value=expr.value)]

        elif len(node.body) == 2:
            if (
                isinstance(node.body[0], ast.Assign)
                and isinstance(node.body[-1], ast.Return)
                and node.body[-1].value is not None
            ):
                pass
            elif isinstance(node.body[0], ast.Expr) and not isinstance(
                node.body[0].value,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.With,
                    ast.AsyncWith,
                    ast.Try,
                    ast.ClassDef,
                ),
            ):
                node.body = [ast.Return(value=node.body[0].value)]

        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        return self.visit_FunctionDef(node)


def minify_code(code: str) -> str:
    lines = code.split("\n")
    result = []
    for line in lines:
        stripped = line.rstrip()
        if stripped:
            result.append(stripped)

    code = "\n".join(result)
    code = code.strip()

    lines = code.split("\n")
    processed = []
    final_result = []

    for line in lines:
        if (
            line.startswith("def ")
            or line.startswith("async def ")
            or line.startswith("class ")
        ):
            if processed:
                final_result.append(join_on_same_line(processed))
            processed = [line]
        elif line.strip() and not line.startswith(" ") and not line.startswith("\t"):
            if processed:
                final_result.append(join_on_same_line(processed))
            processed = [line]
        else:
            processed.append(line)

    if processed:
        final_result.append(join_on_same_line(processed))

    return "\n".join(final_result) + "\n"


def process_group(lines):
    if not lines:
        return ""

    first = lines[0]
    rest = lines[1:]

    if not rest:
        return first

    base_indent = len(rest[0]) - len(rest[0].lstrip()) if rest else 0
    is_class_body = first.startswith("class ")

    if is_class_body:
        parts = []
        current = [first]

        for line in rest:
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)

            if stripped.startswith(("def ", "async def ")):
                if current:
                    parts.append(process_method(current))
                    current = []
                current.append(line)
            elif current_indent == 0:
                if current:
                    parts.append(process_method(current))
                    current = []
                parts.append(line)
            else:
                current.append(line)

        if current:
            parts.append(process_method(current))

        return "\n".join(parts)

    base_indent = len(rest[0]) - len(rest[0].lstrip()) if rest else 0
    has_nested = any(
        stripped.startswith(("for ", "while ", "if ", "with ", "try", "except"))
        for line in rest
        for stripped in [line.lstrip()]
    )

    if has_nested:
        return first + "\n" + "\n".join(rest)

    buffer = []

    for line in rest:
        stripped = line.lstrip()
        current_indent = len(line) - len(stripped)

        is_return = stripped.startswith("return ")
        is_pass = stripped == "pass"
        is_break = stripped == "break"
        is_continue = stripped == "continue"
        is_raise = stripped.startswith("raise ")

        is_assign = (
            "=" in stripped
            and not stripped.startswith("==")
            and not stripped.startswith("!=")
            and not stripped.startswith("<=")
            and not stripped.startswith(">=")
            and not stripped.startswith("if ")
            and not stripped.startswith("while ")
            and not stripped.startswith("for ")
            and not stripped.startswith("import ")
            and not stripped.startswith("from ")
            and not stripped.startswith("class ")
            and not stripped.startswith("def ")
            and not stripped.startswith("async ")
            and not stripped.startswith("return=")
        )

        is_simple = (
            is_return or is_pass or is_break or is_continue or is_raise or is_assign
        )

        if is_simple and current_indent == base_indent:
            buffer.append(stripped)

    if buffer:
        body = ";".join(buffer)
        return first + body

    return first + "\n" + "\n".join(rest)


def process_method(lines):
    if not lines:
        return ""

    first = lines[0]
    rest = lines[1:]

    if not rest:
        return first

    buffer = []
    for line in rest:
        stripped = line.lstrip()
        buffer.append(stripped)

    if buffer:
        body = ";".join(buffer)
        return first + body

    return first + "\n" + "\n".join(rest)


def join_on_same_line(lines):
    if not lines:
        return ""

    if len(lines) == 1:
        return lines[0]

    first = lines[0]
    rest = lines[1:]

    if not rest:
        return first

    has_nested = any(
        line.lstrip().startswith(
            ("def ", "async def ", "for ", "while ", "if ", "with ", "try", "except")
        )
        for line in rest
    )

    if has_nested:
        parts = []
        current = [first]

        for line in rest:
            stripped = line.lstrip()
            if stripped.startswith(("def ", "async def ")):
                if current:
                    parts.append(process_group(current))
                current = [line]
            else:
                current.append(line)

        if current:
            parts.append(process_group(current))

        return "\n".join(parts)

    return process_group(lines)


def format_file_path(
    input_path: Path, output_dir: Path, in_place: bool = False
) -> Optional[Path]:
    try:
        source = input_path.read_text(encoding="utf-8")
    except Exception as e:
        warnings.warn(f"Failed to read {input_path}: {e}")
        return None

    try:
        tree = ast.parse(source, filename=str(input_path), type_comments=True)
    except SyntaxError as e:
        warnings.warn(f"Syntax error in {input_path}: {e}")
        return None

    tree = DocstringRemover().visit(tree)
    ast.fix_missing_locations(tree)

    tree = TypeHintStripper().visit(tree)
    ast.fix_missing_locations(tree)

    tree = SingleLineBodyConverter().visit(tree)
    ast.fix_missing_locations(tree)

    code = ast.unparse(tree)
    code = minify_code(code)

    if in_place:
        output_path = input_path
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        gitignore_path = output_dir / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text("*\n", encoding="utf-8")
        output_path = output_dir / input_path.name

    output_path.write_text(code, encoding="utf-8")
    return output_path


def format_file(
    input_path: Path, output_dir: Path, in_place: bool = False
) -> Optional[Path]:
    if not input_path.suffix == ".py":
        warnings.warn(f"Skipping non-Python file: {input_path}")
        return None
    return format_file_path(input_path, output_dir, in_place)


def format_directory(input_dir: Path, output_dir: Path, in_place: bool = False) -> int:
    if not in_place:
        output_dir.mkdir(parents=True, exist_ok=True)
        gitignore_path = output_dir / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text("*\n", encoding="utf-8")

    count = 0
    py_files = list(input_dir.rglob("*.py"))

    for py_file in py_files:
        if py_file.name.startswith("."):
            continue

        if in_place:
            result = format_file(py_file, output_dir, in_place=True)
        else:
            relative = py_file.relative_to(input_dir)
            file_output_dir = output_dir / relative.parent
            result = format_file(py_file, file_output_dir, in_place=False)

        if result:
            count += 1

    return count
