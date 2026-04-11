---
mode: agent
description: "Generate an Alembic migration for a schema change in db/models.py"
---

Generate an Alembic migration for the following schema change:

**Change description:** ${input:change_description:Describe the schema change, e.g. "add difficulty column to exercises table"}

## Instructions

1. Read `db/models.py` to understand the current schema
2. Read `agent_docs/data_model.md` for context
3. Apply the requested change to `db/models.py`:
   - All new PKs must be UUID
   - Add nullable/default values where appropriate
   - Follow existing column naming style
4. Run: `uv run alembic revision --autogenerate -m "${input:change_description}"`
5. Review the generated migration in `alembic/versions/`
6. Run: `uv run alembic upgrade head`
7. Report what changed and show the final migration file
