# haisir ↔ haiguru Exam Flow Mapping

This document maps the haiguru exam flow (described in `EXAM_FLOW.md`) to its
haisir counterpart and highlights every point of divergence.

---

## Phase 1 — Content & Question Creation

| Concept | haisir | haiguru | Status |
|---|---|---|---|
| Course hierarchy | `grade → subject → course` via `course_path_nodes` | Same | ✅ Match |
| Topics / TopicContents | `topics`, `topic_contents` | Same | ✅ Match |
| Question fields | `question_text`, `question_type`, `options`, `correct_answers`, `explanation`, `difficulty`, `tags`, `image_url` | Same fields | ✅ Match |
| Paragraph stimulus | `paragraph_questions` — separate entity, not a question type | Same concept | ✅ Match |
| Question types | 5 types: `single_choice`, `multiple_choice`, `true_false`, `fill_in_the_blank`, `essay` | Same 5 types — no `paragraph` QuestionType added | ✅ Match |
| Vector embeddings | None | `data_topic_content_vectors` (pgvector) for RAG grading | ⚠️ **D2** |

### D2 — pgvector / RAG

haiguru defines `data_topic_content_vectors` to embed topic content for RAG
retrieval as the last-resort reference answer fallback during LLM grading.
haisir has no such table.

---

## Phase 2 — Exam Template Creation

| Concept | haisir | haiguru | Status |
|---|---|---|---|
| `exam_templates` fields | `mode`, `ruleset`, `duration_minutes`, `passing_score`, `course_path_node_id` | Same | ✅ Match |
| `exam_template_questions` — standalone | `question_id` set (non-nullable in domain model) | `question_id` set, `paragraph_question_id` null | ✅ Match |
| `exam_template_questions` — paragraph stimulus | Sub-questions pre-exploded at authoring time; each row has `question_id` set + `paragraph_question_id` to indicate stimulus ownership | Same — `question_id` always non-null; `paragraph_question_id` set on stimulus sub-question rows | ✅ Match |

---

## Phase 3 — Session Initialisation

| Concept | haisir | haiguru | Status |
|---|---|---|---|
| `exam_sessions` row creation | `status: pending → ongoing` | Same | ✅ Match |
| Static mode — question iteration | Iterates `exam_template_questions`, maps each `question_id` to an `exam_session_questions` row | Same | ✅ Match |
| `exam_session_questions` schema | `exam_session_id`, `question_id`, `order`, `points`, `user_answer`, `is_correct`, `earned_points` | Same schema | ✅ Match |
| Image answer storage | Not supported | `user_answer` stores an `"image:/path/..."` prefix sentinel at submission; no separate table | ⚠️ **D4** |

### D4 — Image answer encoding

haiguru encodes handwritten image submissions inline in `user_answer` using an
`"image:"` prefix (e.g. `"image:/uploads/session_x_q_y.jpg"`). Each row stores
one question's image — the prefix is per `exam_session_questions` row, not a
whole-sheet sentinel. The field is never null on submission; the prefix acts as
an inline type tag. haisir has no image-answer concept and no equivalent column.

> **Two handwritten paths:** a sheet-splitting client segments and OCRs the full
> sheet automatically and writes plain text directly to `user_answer` (no prefix,
> no eval pipeline OCR). The per-question upload client sets the `image:` prefix;
> the eval pipeline OCRs each image at grading time.

### Answer Submission (`POST /session/{session_id}/submit`)

Both haisir and haiguru:
- Write `user_answer` as a flat string per question (comma-joined option IDs for
  objective, free text for subjective).
- Set `session.status = "completed"` and `finished_at`.

| Concept | haisir | haiguru | Status |
|---|---|---|---|
| `user_answer` written at submit | ✅ | ✅ | ✅ Match |
| `earned_points` / `is_correct` written at submit | ✗ — deferred | ✗ — deferred (lazy GET for objective; eval pipeline for essay/handwritten) | ✅ Match ⚠️ **D5** |

### D5 — Eval pipeline replaces human review for essay questions

haiguru's `eval_pipeline` is the functional equivalent of haisir's human-review
workflow: both are deferred, post-submission steps for answers that cannot be
auto-graded at submission time. Objective grading matches haisir exactly.

| Question type | haisir | haiguru |
|---|---|---|
| Objective | Lazy on `GET /session/{id}/answers`; `_build_answer_results` calls `grade_question()` and persists | Same — lazy on review GET ✅ |
| Essay | Pending manual human review (`is_correct = None`, 0 pts until reviewed) | `eval_pipeline` runs LLM judge — replaces human reviewer (D6) |
| Handwritten | Not supported | `eval_pipeline` runs OCR then grades (D7) |

---

## Phase 4 — Grading / Evaluation

| Concept | haisir | haiguru | Status |
|---|---|---|---|
| Objective grading (`grade_question`) | `shared/grading.py`: exact match for `single_choice`/`true_false`, partial credit for `multiple_choice`, normalised text for `fill_in_the_blank` | Same module, same logic | ✅ Match |
| `essay` grading | Returns `(None, 0.0)` — pending manual human review | LLM judge (`grade_subjective`) writes `earned_points` + remark | ⚠️ **D6** |
| OCR | None | `ocr.py` detects `user_answer.startswith("image:")`, strips prefix, OCRs image, overwrites `user_answer` with transcribed text, then grades normally | ⚠️ **D7** |
| `explanation` field | Display-only in review UI (suppressed for `essay`); does not drive grading | Same — display-only; LLM judge uses `correct_answers`, not `explanation` | ✅ Match |

### D6 — Automated subjective grading

haisir marks `essay` as `is_correct = None` (manual human review required),
earning 0 points until reviewed. haiguru calls an LLM judge for `essay`;
`grade_subjective(user_answer, model_answer, points)` returns a numeric
`earned_points` and a remark that is persisted to the DB.

### D7 — OCR pipeline

haiguru's eval pipeline checks whether `user_answer` starts with `"image:"`.
If so, it strips the prefix to obtain the filesystem path, encodes the image as
base64, sends it to the OCR model, and overwrites `user_answer` with the
transcribed text. Because the `image:` prefix is per question (per-question
upload path), each OCR call returns text for exactly one question's answer — no
extraction or isolation step is needed. `grade_question` is responsible for
normalizing the OCR text into the expected answer format (e.g. `"option B"` →
`"b"`); if it cannot handle a case, its scope should be expanded. haisir has no
image-answer or OCR concept.

---

## Phase 5 — Score Finalisation

| Concept | haisir | haiguru | Status |
|---|---|---|---|
| Sum `earned_points` → `exam_sessions.score` | `_finalize_session()` called from `get_exam_answers` | Same — on review GET (objective) or in `load.py` eval pipeline (essay/handwritten) | ✅ Match |
| Score unit stored | Raw earned-mark sum; ratio computed at display time in `get_all_sessions_for_exam_template` | Same — raw earned-mark sum stored; ratio computed at display time | ✅ Match |

---

## Divergence Summary

| ID | Area | haisir behaviour | haiguru extension |
|---|---|---|---|
| **D2** | Vector store | None | `data_topic_content_vectors` (pgvector) for RAG |
| **D4** | Image answers | Not supported | `user_answer = "image:/path/..."` inline prefix; no extra table |
| **D5** | Grading approach | Objective: lazy on review GET; Essay: manual human review pending | Objective: same; Essay: `eval_pipeline` LLM judge replaces human reviewer |
| **D6** | Subjective grading | `essay` → `(None, 0.0)`, manual review | `essay` graded by LLM judge |
| **D7** | OCR | None | Detects `image:` prefix → strips → OCRs → overwrites `user_answer` → grades |
