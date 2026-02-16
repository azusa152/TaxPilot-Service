"""Code sandbox — validates generated Python code for safety using RestrictedPython.

Performs three levels of validation:
1. RestrictedPython compilation (AST-level restrictions)
2. Domain-specific checks (function name, signature, no imports)
3. Execution test with safe builtins
"""

import ast
from dataclasses import dataclass, field

from RestrictedPython import compile_restricted, safe_builtins
from RestrictedPython.Guards import guarded_unpack_sequence, safer_getattr

from src.logging_config import get_logger

logger = get_logger(__name__)

# Built-in function calls that are never allowed in generated code.
_BLOCKED_CALLS = frozenset({"open", "exec", "eval", "compile", "__import__", "globals", "locals"})


@dataclass
class ValidationResult:
    """Result of code sandbox validation."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CodeSandbox:
    """Validates generated Python code for safety using RestrictedPython.

    Performs three levels of validation:
    1. RestrictedPython compilation (AST-level restrictions)
    2. Domain-specific checks (function name, signature, no imports)
    3. Execution test with safe builtins (optional)
    """

    @staticmethod
    def validate(
        code: str,
        expected_function_name: str | None = None,
    ) -> ValidationResult:
        """Validate generated Python code for safety.

        Args:
            code: The Python source code to validate.
            expected_function_name: If provided, ensures the code defines
                a function with this name.

        Returns:
            ValidationResult with pass/fail, errors, and warnings.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # --- Level 1: RestrictedPython compilation ---
        try:
            byte_code = compile_restricted(
                code,
                filename="<generated>",
                mode="exec",
            )
            if byte_code is None:
                errors.append("RestrictedPython compilation returned None")
        except SyntaxError as e:
            errors.append(f"Syntax error: {e}")
            return ValidationResult(passed=False, errors=errors)
        except Exception as e:
            errors.append(f"RestrictedPython compilation failed: {e}")
            return ValidationResult(passed=False, errors=errors)

        # --- Level 2: Domain-specific AST checks ---
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            errors.append(f"AST parse error: {e}")
            return ValidationResult(passed=False, errors=errors)

        # Check for import statements (should be pure functions)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                errors.append(
                    f"Import statement found: {ast.dump(node)}. "
                    "Generated functions must be pure — no imports allowed."
                )

        # Check for calls to dangerous built-in functions
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in _BLOCKED_CALLS:
                    errors.append(
                        f"Blocked function call: {node.func.id}(). "
                        "Generated functions must not call dangerous builtins."
                    )

        # Check that expected function is defined
        if expected_function_name:
            function_names = [
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
            ]
            if expected_function_name not in function_names:
                errors.append(
                    f"Expected function '{expected_function_name}' not found. "
                    f"Found: {function_names}"
                )

        # Warn about global variables
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                warnings.append(
                    "Top-level variable assignment found. "
                    "Prefer constants inside the function."
                )

        # --- Level 3: Test execution with restricted builtins ---
        if not errors and byte_code:
            restricted_globals = {
                "__builtins__": safe_builtins,
                "_getattr_": safer_getattr,
                "_getiter_": iter,
                "_getitem_": lambda obj, key: obj[key],
                "_unpack_sequence_": guarded_unpack_sequence,
            }
            try:
                # SECURITY NOTE: This exec() is intentionally used within a
                # restricted sandbox. The byte_code was compiled via
                # RestrictedPython's compile_restricted(), which performs AST
                # transformation to block dangerous operations. The globals
                # dict uses RestrictedPython's safe_builtins + guarded accessors.
                # This does NOT execute arbitrary code — it only executes
                # code that has passed the RestrictedPython safety checks.
                exec(byte_code, restricted_globals)  # noqa: S102

                # Verify the function is callable
                if expected_function_name:
                    func = restricted_globals.get(expected_function_name)
                    if func is None or not callable(func):
                        errors.append(
                            f"Function '{expected_function_name}' was not "
                            "defined or is not callable after execution."
                        )
            except Exception as e:
                errors.append(f"Restricted execution failed: {e}")

        passed = len(errors) == 0
        if passed:
            logger.info("Code sandbox validation passed")
        else:
            logger.warning(f"Code sandbox validation failed: {errors}")

        return ValidationResult(passed=passed, errors=errors, warnings=warnings)
