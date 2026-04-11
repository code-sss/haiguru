# Data Model

Covers the full database schema, table hierarchy, and key column contracts.
Tables are defined in `db/models.py` (SQLAlchemy declarative). Schema managed by Alembic.

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

## Table Hierarchy

```
categories
  └── course_path_nodes  (self-referential: grade → subject → course)
        └── topics
              ├── topic_contents   (text pages from raw_response_*.md)
              └── questions        (exercises extracted from content)
                    └── paragraph_questions  (grouped questions under a passage)

exam_templates  (linked to a course_path_node)
  └── exam_template_questions

exam_sessions   (a user's attempt at an exam_template)
  └── exam_session_questions
```

## Key Column Contracts

- All primary keys are **UUID**.
- `course_path_nodes.node_type`: `grade` | `subject` | `course`
- `topic_contents.content_type`: `video` | `pdf` | `text` | `question` | `question_answer`
- `questions.question_type`: `single_choice` | `multiple_choice` | `true_false` | `fill_in_the_blank` | `essay` | `paragraph`
- `questions.options` and `correct_answers`: JSONB lists. Letter answers like `(b)` are resolved to option text during ETL.
- `paragraph_questions.question_ids`: `UUID[]` — ordered list of `questions.id` belonging to the passage.
- `exam_templates.mode`: `static` | `dynamic` | `custom`
- `exam_templates`: CHECK constraints — `duration_minutes > 0`, `passing_score` in `[0.0, 1.0]`
- `exam_sessions.status`: `pending` | `ongoing` | `completed` | `failed`
- `user_id` / `created_by`: string (Keycloak `sub` claim or plain identifier — TBD/not yet enforced)

## Gotchas

- `paragraph_questions.question_ids` is an ordered array — insertion order matters for rendering.
- `correct_answers` stores resolved text (not letters); raw letter answers are only present in OCR outputs.
- `user_id` enforcement is not yet implemented — treat it as advisory for now.
