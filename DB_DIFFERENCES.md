# haiguru_db vs haisir_db — Schema Differences

Last updated: 2026-04-08

## Tables only in haisir_db (not in haiguru_db)

These are intentionally excluded from haiguru — they are outside the RAG system's scope.

| Table | Reason excluded |
|---|---|
| `assessments` | Planned for deprecation in haisir in favour of exams |
| `assessment_attempts` | Depends on `assessments` |
| `assessment_answers` | Depends on `assessments` |
| `user_metadata` | Auth/onboarding — not needed for RAG |
| `student_profiles` | User profile data — not needed for RAG |
| `teacher_profiles` | User profile data — not needed for RAG |
| `parent_profiles` | User profile data — not needed for RAG |
| `parent_child_links` | Social graph — not needed for RAG |
| `parent_link_codes` | Social graph — not needed for RAG |
| `class_invite_codes` | Class management — not needed for RAG |

## Tables only in haiguru_db (not in haisir_db)

| Table | Purpose |
|---|---|
| `data_topic_content_vectors` | pgvector store for RAG embeddings — managed by llama-index, excluded from alembic autogenerate |

## Column differences

Columns present in haiguru but absent in haisir — intentional divergences that will need to be added to haisir when assessments are dropped.

| Table | Column | haiguru | haisir | Reason |
|---|---|---|---|---|
| `questions` | `topic_id` | `UUID FK → topics.id` | absent | RAG ETL needs direct topic→question lookup; haisir currently does this via `assessments.question_ids` (being deprecated) |
| `paragraph_questions` | `topic_id` | `UUID FK → topics.id` | absent | Same reason |

## Migration history (haiguru)

| Revision | Description |
|---|---|
| `7aed2466e611` | Initial schema (full baseline — replaces prior 4-migration history) |
