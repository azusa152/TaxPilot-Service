"""LLM-assisted code generation for tax calculation patches.

Skeleton implementation. Generates Python code patches from
law change descriptions using an LLM.
"""
from dataclasses import dataclass

from src.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CodePatch:
    """A generated code patch for a tax calculation function."""

    function_name: str
    version: str
    code_content: str
    source_law_hash: str
    description: str


class CodeGenerator:
    """Generates Python code patches from law change descriptions."""

    async def generate_patch(
        self,
        function_name: str,
        current_code: str,
        change_description: str,
        source_law_hash: str,
    ) -> CodePatch:
        """Generate a code patch based on a law change description.

        Args:
            function_name: Name of the function to patch.
            current_code: Current Python source code of the function.
            change_description: Natural language description of the law change.
            source_law_hash: Hash of the new law text.

        Returns:
            CodePatch with the generated code.
        """
        # STUB: In production, this calls an LLM API with a structured prompt
        # containing the current code and change description.
        logger.info("Generating code patch for '%s' based on: %s", function_name, change_description)

        # For now, return the current code unchanged with a bumped version
        return CodePatch(
            function_name=function_name,
            version="auto-generated",
            code_content=current_code,
            source_law_hash=source_law_hash,
            description=f"Auto-generated patch: {change_description}",
        )

    def build_prompt(self, function_name: str, current_code: str, change_description: str) -> str:
        """Build the LLM prompt for code generation.

        This is exposed for testing and debugging the prompt template.
        """
        return f"""You are a Japanese tax calculation expert and Python developer.

The following Python function calculates {function_name}:

```python
{current_code}
```

The National Tax Agency has published the following change:
{change_description}

Generate an updated version of this function that incorporates the new rules.
Requirements:
- Keep the function signature identical.
- All amounts in JPY (integers).
- Include comments referencing the specific NTA regulation.
- The function must be pure (no side effects, no external dependencies).

Return ONLY the Python function code, no explanation.
"""
