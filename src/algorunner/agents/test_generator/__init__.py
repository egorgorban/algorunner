"""Test Generator agent — merges user-provided examples with freshly
LLM-generated test cases (including edge cases) into the `Solution.tests`
list. Never trusts the LLM to echo provided examples back verbatim (D-10) —
the merge happens in Python code. Enforces a hard minimum of
`settings.test_generator_min_tests` generated tests when fewer than 3
examples are provided (D-11), raising `ValueError` on a shortfall rather
than silently shipping too few tests.
"""
