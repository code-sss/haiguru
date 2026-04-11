---
mode: agent
description: "Generate a pytest test for a haiguru module"
---

Generate a pytest test for the following:

**Module/function to test:** ${input:target:e.g. etl_pipeline/extract.py or a specific function name}
**What to test:** ${input:scenario:Describe the scenario or behaviour to test}

## Instructions

1. Read `tests/conftest.py` to understand existing fixtures and mocks
2. Read the target module to understand its interface
3. Follow these conventions:
   - Tests do **not** require a running database (`DATABASE_URL` is mocked in conftest)
   - External dependencies (Ollama, filesystem, DB) must be **mocked** using `unittest.mock`
   - Use `pytest.fixture` for shared setup
   - Each test function covers one clear scenario
4. Place the test in `tests/test_<module_name>.py`
5. Run `pytest tests/test_<module_name>.py` to confirm it passes
