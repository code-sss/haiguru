# exam_flow.md Review — Decisions

Tracking decisions made while reviewing exam_flow.md (haiguru) against
EXAM_FLOW_HAISIR.md (haisir). Goal: haiguru should only **extend** haisir
(not modify), with the primary extension being LLM/RAG grading for essay
questions.

---

## Issues

### 15. `GET /session/{id}/answers` grading path — DECIDED: route through eval_pipeline

**Problem:** exam_flow.md describes a lazy-grading mutating GET that calls `grade_question()` inline (matching haisir). This creates two parallel grading paths — one in the API handler, one in `eval_pipeline` — with `shared/grading.py` as the bridge. Any grading bug would need to be fixed in two places, and `eval_pipeline`'s re-sum (Decision #1) could conflict with the GET's inline `_finalize_session()` call.

**Decision:** The `GET /session/{id}/answers` endpoint does **not** do inline grading. Instead it invokes `eval_pipeline` (as a function call, not a subprocess) and waits for results before returning. `eval_pipeline` remains the single authoritative grading path for all sessions — objective and subjective alike.

**Consequences:**
- `shared/grading.py` is only imported by `eval_pipeline/` — no second consumer from the API layer.
- `_finalize_session()` is removed; score is always written by `eval_pipeline.load.save_results()`.
- The GET endpoint is no longer mutating in the haisir sense — it reads results that eval_pipeline has already written, or triggers eval_pipeline synchronously if grading hasn't run yet.

### 1. Score finalization race condition — DECIDED: eval_pipeline re-sums

### 14. `answers` table — DECIDED: remove

**Problem:** `Answer` model exists in `db/models.py` but is never imported or used anywhere in the codebase. It's a standalone single-question answer system unrelated to the exam session flow.

**Decision:** Remove from schema and all docs. Assessments were already dropped (decision #5), and the entire exam grading flow uses `exam_session_questions` exclusively. No code references this model.

### 13. `ExamTemplateQuestion.question_id` nullable — DECIDED: fix schema

**Problem:** `db/models.py` has `question_id = Column(..., nullable=True)` but both docs say it's always non-null.

**Decision:** Change schema to `nullable=False` to match the docs. Generate an Alembic migration.

### 12. Explicit statement that objective grading is unchanged — DECIDED: add

**Decision:** Add a one-liner to exam_flow.md stating objective grading uses the same `grade_question()` logic as haisir — only the essay path diverges.

### 11. Score percentage conversion — DECIDED: doc gap, add to exam_flow.md

**Problem:** Haisir documents `round(score / total_marks * 100)` for session history display. haiguru's doc omits it.

**Decision:** Add to exam_flow.md.

### 10. Multiple-choice partial credit formula — DECIDED: doc gap, add to exam_flow.md

**Problem:** Haisir documents the exact partial credit formula for multiple_choice. haiguru's doc omits it but should use identical objective grading.

**Decision:** Add the formula to exam_flow.md's grading section.

### 9. `paragraph_questions` — DECIDED: add missing fields to exam_flow.md

**Problem:** `tags` (JSONB) and `difficulty` (String) exist in schema but are missing from exam_flow.md's `paragraph_questions` field table. `topic_id` is already listed correctly.

**Decision:** Add `tags` and `difficulty` to the field table in exam_flow.md.

### 8. `GET /session/{id}/questions` endpoint — DECIDED: doc gap, add to exam_flow.md

**Problem:** Haisir documents this endpoint (paragraph grouping reconstruction, image encoding). haiguru's doc skips it.

**Decision:** Add endpoint documentation to exam_flow.md, matching haisir's description.

### 7. Dynamic exam ruleset — DECIDED: doc gap, add haisir's ruleset docs

**Problem:** `ruleset` JSON column exists on both `ExamTemplate` and `ExamSession` but exam_flow.md doesn't document the structure.

**Decision:** Add haisir's ruleset documentation (`topics`, `difficulty_distribution`, `tags`) to exam_flow.md as-is — same structure.

### 6. `exam_templates` ownership/visibility fields — DECIDED: doc gap, add to exam_flow.md

**Problem:** Schema has `description`, `created_by`, `is_active`, `owner_type`, `owner_id`, `organization_id`, `purpose` on `exam_templates`. exam_flow.md omits all of them.

**Decision:** Add the missing fields to exam_flow.md to match the schema.

### 5. Assessments table — DECIDED: intentionally dropped

**Problem:** haisir has `assessments`, `AssessmentAttempt`, `AssessmentAnswer` tables (topic-scoped practice sets). haiguru's schema has none of these.

**Decision:** Intentionally dropped. haiguru focuses on exam grading with LLM/RAG. Document this as a known omission in exam_flow.md.

### 4. OCR normalization — DECIDED: open gap

**Problem:** The doc says `grade_question` should normalize OCR text (e.g. `"option B"` → `"b"`) but doesn't define concrete rules.

**Decision:** Flag as an open implementation gap in exam_flow.md. Define normalization rules when building the OCR pipeline.

### 2. Empty `correct_answers` on essay questions — DECIDED: RAG two-layer

**Problem:** If an essay question has empty `correct_answers`, the LLM judge has no model answer and produces unreliable scores.

**Decision:** Two-layer approach:
- **Template authoring time:** When an essay question with empty `correct_answers` is added to a template, auto-generate a model answer using RAG (retrieve from `topic_contents` via `question.topic_id`). Author sees the generated answer and can edit/approve before saving. Warn but don't block.
- **eval_pipeline time (fallback):** If `correct_answers` is still empty, fall back to live RAG retrieval from `topic_contents`. Log a warning but don't block grading.

Template authoring = RAG + human review (quality path). eval_pipeline = live RAG (fallback, with warning).

### 3. `questions.topic_id` — DECIDED: keep (option A)

**Problem:** haiguru adds `topic_id` FK on `questions` (haisir doesn't have it). Is this an unwanted modification?

**Decision:** Keep `topic_id` (nullable). It is additive, doesn't break haisir behavior, and is required for RAG retrieval (`question.topic_id → topic → topic_contents → vectors`). A question pinned to one topic is acceptable — the `topic_id` still points to relevant curriculum content even if reused elsewhere.

### 1. Score finalization race condition

**Problem:** When a session has both objective + essay questions, `GET /session/{id}/answers` may run `_finalize_session()` before `eval_pipeline` has graded essays — writing an incomplete `score`. Later, `eval_pipeline` grades essays but there's no defined coordination.

**Decision:** `eval_pipeline` always does a full re-sum of all `earned_points` across all `exam_session_questions` and overwrites `exam_sessions.score`, regardless of whether `_finalize_session()` already ran. This makes `eval_pipeline` the authoritative final scorer for any session it processes.
