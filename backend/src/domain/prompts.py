"""Prompt templates for LLM interactions.

All prompts are stored here as constants for version control and auditability.
Each prompt includes clear instructions, expected output format, and examples.
"""

REGULATION_PARSE_PROMPT = """You are a Japanese tax regulation expert. Analyze the following
NTA (National Tax Agency) page content and identify any tax law changes compared to the
previous version.

## Current page content (new version):
{new_content}

## Previous page content (if available):
{old_content}

## Known calculation functions (for affected_function field):
{known_functions}

## Instructions:
1. Compare the new content against the previous content (if provided).
2. Identify ALL tax rule changes: threshold updates, rate changes, new deductions,
   new required fields, bracket changes, formula changes, or removed regulations.
3. For each change, specify which calculation function is affected using only the
   function names listed above.
4. If new user input fields are needed (e.g., a new deduction requires a count or amount
   the user must provide), mark it as NEW_FIELD_REQUIRED.
5. Assign a confidence score (0.0-1.0) for each identified change.
6. If the page content changed but NO actual tax rules changed (e.g., only formatting
   or navigation was updated), set no_changes_detected=true.
7. All descriptions must be in English.
8. The tax_year should be the year these changes apply to.

Respond with structured JSON matching the RegulationAnalysis schema.
"""


REGULATION_PARSE_PROMPT_FIRST_SNAPSHOT = """You are a Japanese tax regulation expert.
Analyze the following NTA (National Tax Agency) page content and extract all current
tax rules as structured data.

## Page content:
{content}

## Known calculation functions (for affected_function field):
{known_functions}

## Instructions:
1. Extract ALL tax rules present on this page: thresholds, rates, brackets, deduction
   formulas, eligibility criteria.
2. For each rule, identify which calculation function it corresponds to using only the
   function names listed above.
3. This is a BASELINE extraction (no previous version to compare against).
4. Set all change_type values to "THRESHOLD_UPDATE" for existing rules being cataloged.
5. Assign confidence scores based on how clearly the rule is stated on the page.
6. All descriptions must be in English.

Respond with structured JSON matching the RegulationAnalysis schema.
"""


# --- Code & Schema Generator (Phase 6D) ---
CODE_GENERATION_PROMPT = """You are a Python tax calculation expert. Generate an updated
pure Python function based on the following law change.

## Law Change:
- Type: {change_type}
- Affected function: {affected_function}
- Description: {description}
- Old value: {old_value}
- New value: {new_value}

## Current function code:
{current_code}

## Requirements:
1. The function must be a PURE Python function — no imports, no side effects, no I/O.
2. The function name must be exactly: {affected_function}
3. The function signature should match the current version (or add new parameters if NEW_FIELD_REQUIRED).
4. All amounts are in JPY (integers).
5. Include a Google-style docstring with:
   - Brief description of what the function calculates
   - The NTA regulation reference
   - The tax year this version applies to
6. Use clear variable names and comments for threshold boundaries.
7. Return ONLY the function definition — no imports, no class wrappers, no test code.

## Admin hints (if any):
{admin_hints}

Respond with structured JSON matching the CodeGenerationResult schema.
"""


SCHEMA_GENERATION_PROMPT = """You are a Japanese tax system expert. Based on the following
law changes, determine if any new user input fields are needed in the tax profile.

## Identified law changes:
{changes_json}

## Current ProfileDefinition fields:
{current_fields}

## Instructions:
1. For each law change of type NEW_FIELD_REQUIRED, propose a new field definition.
2. For threshold or rate changes, check if existing fields are sufficient.
3. Each new field needs: name (snake_case), type (int/float/bool/str), required flag,
   English description, Japanese description, and default value.
4. If no new fields are needed, return an empty new_fields list.
5. Check if any existing fields should be removed (rare — usually only on regulation removal).
6. Provide a clear rationale for the schema changes.

Respond with structured JSON matching the SchemaChangeProposal schema.
"""
