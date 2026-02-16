from src.infrastructure.code_generator import CodeGenerator


async def test_generate_patch_should_return_code_patch():
    generator = CodeGenerator()
    patch = await generator.generate_patch(
        function_name="calc_basic_deduction",
        current_code="def calc_basic_deduction(income):\n    return 480_000\n",
        change_description="Basic deduction increased to 500,000 for 2025",
        source_law_hash="abc123",
    )
    assert patch.function_name == "calc_basic_deduction"
    assert patch.source_law_hash == "abc123"
    assert patch.code_content is not None


def test_build_prompt_should_contain_function_and_change():
    generator = CodeGenerator()
    prompt = generator.build_prompt(
        function_name="calc_basic_deduction",
        current_code="def calc_basic_deduction(income):\n    return 480_000\n",
        change_description="Basic deduction increased to 500,000",
    )
    assert "calc_basic_deduction" in prompt
    assert "500,000" in prompt
    assert "Return ONLY the Python function code" in prompt
