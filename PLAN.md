# Plan: eval_pipeline — Answer Sheet Evaluation

## Background

For a full description of the data model, question types, exam creation flow, and
how a user's answers are linked through the system, see [EXAM_FLOW.md](./EXAM_FLOW.md).

---

## Status

| Component | State |
|---|---|
| `db/models.py` | ✅ Done |
| `shared/grading.py` | ✅ Done |
| `llm_factory.py` | ✅ Done |
| `glm_ocr/` | ✅ Done |
| `etl_pipeline/` | ✅ Done |
| `embed_pipeline/` | ✅ Done |
| `rag/` | ✅ Done |
| `config.py` — add `EVAL_MODEL` | ⏳ Pending |
| `.env.example` — add `EVAL_MODEL=` | ⏳ Pending |
| `eval_pipeline/__init__.py` | ⏳ Pending |
| `eval_pipeline/load.py` | ⏳ Pending |
| `eval_pipeline/ocr.py` | ⏳ Pending |
| `eval_pipeline/judge.py` | ⏳ Pending |
| `eval_pipeline/__main__.py` | ⏳ Pending |

---

## Context
The eval pipeline is haiguru's functional equivalent of haisir's human-review
workflow. For **objective-only digital exams**, grading stays lazy (triggered on
the answer-review GET request), matching haisir exactly — the eval pipeline is
not required. The pipeline is needed only when a session contains **essay
questions** (LLM judge replaces human reviewer) or **handwritten image
submissions** (OCR pre-processes the answer before grading).

For handwritten exams, the image path is stored directly in
`exam_session_questions.user_answer` using an `image:` prefix (e.g.
`image:/uploads/session_x_q_y.jpg`). The pipeline detects the prefix, runs OCR,
overwrites `user_answer` with the transcribed text, then grades using the same
`shared/grading.py` logic as haisir. No schema change is required.

The Examora project (`C:\github\siva\Examora\core\evaluation\answer_evaluator.py`) was
consulted as a reference for the LLM judge prompt shape and JSON parsing strategy.

---

## Files to Create

```
eval_pipeline/
├── __init__.py      # module marker (1 line)
├── __main__.py      # CLI + orchestration
├── ocr.py           # OCR step (glm_ocr → concatenated text)
├── judge.py         # LLM judge: subjective grading + objective answer extraction
└── load.py          # DB read (load session) + DB write (save results)
```

## Files to Modify

| File | Change |
|------|--------|
| `config.py` | Add `EVAL_MODEL: str = os.getenv("EVAL_MODEL", TRANSFORM_MODEL)` after line 30 |
| `.env.example` | Add `EVAL_MODEL=` with comment |

---

## Required Schema Change

No schema change is required. The `image:` prefix convention uses the existing
`exam_session_questions.user_answer` column.

---

## CLI Interface

```bash
uv run python -m eval_pipeline \
    --session-id <uuid> \
    [--ocr-model glm-ocr-optimized] \
    [--eval-model openai://gpt-4o]
```

No `--images` flag — the pipeline detects image submissions via the `image:`
prefix in `exam_session_questions.user_answer`. No `--skip-ocr` flag — the
pipeline infers what to do from each `esq.user_answer` value. No `--user-id`
flag — read from `exam_sessions.user_id`.

---

## Pipeline Steps

### 1. `load.py` — `load_session(session_id) -> SessionData`
- Query `ExamSession` by id — raise `ValueError` if not found.
- Raise `ValueError` if `session.status != "completed"` (guard against grading
  in-progress or pending sessions).
- Load `exam_session_questions` rows where `earned_points IS NULL`, joined to
  their `questions` rows. These are the ungraded answers from submission.
- For each, check if `user_answer` starts with `"image:"` (image submission case).
- Return `SessionData(session_id, user_id, items: list[SessionItem])`.

`SessionItem` fields: `esq` (ORM), `question` (ORM), `image_path` (str | None,
extracted from `esq.user_answer` if prefixed).

### 2. `ocr.py` — `run_ocr_for_answer(image_path, model) -> str`
- Loads image from the given local filesystem path.
- `get_optimized_image_b64(path)` + `send_single_request(model, OCR_PROMPT, [b64])`.
- Returns transcribed text; caller writes result to `esq.user_answer`.
- OCR prompt: `"Transcribe the handwritten text exactly, preserving question numbers and answers."`

### 3. `judge.py` — LLM calls

**`grade_subjective(question_text, model_answer, student_answer, points, llm) -> JudgeResult`**
- Prompt (see shape below) → `llm.complete(prompt).text`.
- Strip `<think>…</think>` blocks (qwen3 models), strip markdown fences, parse JSON.
- `_parse_json_response` 2-phase: `json.loads(stripped)` first, then `re.search(r'\{[\s\S]*\}', text)`.
- On parse failure: `JudgeResult(awarded=0.0, max_marks=points, remark="parse error")` + `warnings.warn`.
- Clamp `awarded` to `[0.0, float(points)]`.


**Subjective judge prompt:**
```
You are a strict exam evaluator. Grade the student's answer.

Question: {question_text}
Model answer: {model_answer}
Student answer: {student_answer}
Max marks: {points}

Return only valid JSON:
{"awarded": <float>, "max_marks": <int>, "remark": "<brief feedback>"}
```


### 4. `__main__.py` — Orchestration (`_grade_one` + `main`)

`QuestionResult` fields: `esq_id` (UUID), `earned_points` (float),
`is_correct` (bool | None), `user_answer` (str | None — set when OCR ran).

`_grade_one(item: SessionItem, llm, ocr_model) -> QuestionResult`:

| `esq.user_answer` | `question_type` | Action |
|---|---|---|
| starts with `"image:"` | objective | strip prefix → OCR per-question image → overwrite `esq.user_answer` → `grade_question` |
| starts with `"image:"` | essay | strip prefix → OCR per-question image → overwrite `esq.user_answer` → `grade_subjective` |
| set (no prefix) | objective | `grade_question(user_answer, correct_answers)` — same as haisir |
| set (no prefix) | essay | `grade_subjective(user_answer, model_answer, points)` via LLM |
| null or empty | any | warn + grade as unanswered (0 pts) |

> `image:` is per `exam_session_questions` row (per-question upload path). OCR
> returns text for one question only — no extraction step needed. `grade_question`
> is responsible for normalizing OCR text (e.g. `"option B"` → `"b"`); if a case
> cannot be handled, expand `grade_question` scope rather than adding a pipeline step.

Objective = `{single_choice, multiple_choice, true_false, fill_in_the_blank}`  
Subjective = `{essay}`

`model_answer` = `"; ".join(question.correct_answers or [])` (explanation is display-only — not used for grading).

### 5. `load.py` — `save_results(session_id, results)`
Single transaction (`with Session(engine) as session: … session.commit()`):

1. For each `QuestionResult`:
   - Update `exam_session_questions`: `earned_points`, `is_correct`,
     `user_answer` (OCR overwrites the `image:` prefix with transcribed text).
2. Re-query `exam_session_questions` rows to sum `earned_points`.
3. Update `exam_sessions.score` with the raw `total_earned` sum, matching
   haisir. The ratio is computed at display time.

---

## Key Reused Utilities

| Utility | File | Usage |
|---------|------|-------|
| `get_optimized_image_b64` | `glm_ocr/client.py` | Load & encode images for OCR |
| `send_single_request` | `glm_ocr/client.py` | Non-streaming OCR call to Ollama |
| `make_llm` | `llm_factory.py` | Create LlamaIndex LLM for grading |
| `grade_question` | `shared/grading.py` | Grade objective questions |
| `DATABASE_URL`, `EVAL_MODEL`, etc. | `config.py` | Config |
| `db.models.*` | `db/models.py` | ORM classes |

---

## Edge Cases

| Case | Handling |
|------|---------|
| No ungraded `esq` rows for session | warn + exit 0 (nothing to do) |
| `esq.user_answer` null or empty | warn + grade as unanswered (0 pts) |
| `user_answer` starts with `image:` but file missing | `RuntimeError` → exit 1 |
| Question missing from DB | `warnings.warn` + skip that row |
| LLM JSON parse failure | Fallback `JudgeResult(awarded=0, remark="parse error")` + warn |
| `awarded > points` from LLM | Clamped to `[0.0, float(points)]` |
| DB transaction failure | Session auto-rollback; no partial writes |

---

## Verification

```bash
# 1. Student submits exam digitally (writes to exam_session_questions.user_answer,
#    marks session completed — same as haisir submit_exam):
#    POST /session/{session_id}/submit  with list of answers

# 2. For handwritten exams: save image to filesystem, set esq.user_answer to
#    "image:/uploads/session_x_q_y.jpg" for the relevant question rows.

# 3. Run the evaluation pipeline (grades all esq rows where earned_points IS NULL):
uv run python -m eval_pipeline --session-id <uuid>

# 4. Check DB results:
# SELECT esq.order, esq.user_answer, esq.is_correct, esq.earned_points
# FROM exam_session_questions esq WHERE esq.exam_session_id = '<uuid>';
# SELECT score FROM exam_sessions WHERE id = '<uuid>';
```

---

## Implementation Goals — Dependency Graph

Goals are ordered by dependency. Each node lists what must exist before it can
be started (→ blocked by) and what it unlocks (→ enables).

```
[✅] shared/grading.py          objective grading logic
[✅] glm_ocr/client.py          OCR + text LLM calls
[✅] llm_factory.py             LLM provider routing
[✅] db/models.py               ORM + schema
[✅] embed_pipeline/            topic content vectors (pgvector)
[✅] rag/                       retrieval + synthesis

──────────────────────────────────────────────────────────────────
IMMEDIATE — eval_pipeline (blocked by nothing new)
──────────────────────────────────────────────────────────────────

  [⏳] config.py: add EVAL_MODEL
       → enables: judge.py, __main__.py

  [⏳] eval_pipeline/load.py
       → blocked by: db/models.py ✅
       → provides: load_session(), save_results()

  [⏳] eval_pipeline/ocr.py
       → blocked by: glm_ocr/client.py ✅
       → provides: run_ocr_for_answer()

  [⏳] eval_pipeline/judge.py
       → blocked by: llm_factory.py ✅, EVAL_MODEL config ⏳
       → provides: grade_subjective(), extract_objective_answer()

  [⏳] eval_pipeline/__main__.py
       → blocked by: load.py ⏳, ocr.py ⏳, judge.py ⏳,
                     shared/grading.py ✅
       → completes: eval_pipeline

──────────────────────────────────────────────────────────────────
NEXT — after eval_pipeline is complete
──────────────────────────────────────────────────────────────────

  [ ] llm_feedback column (schema migration)
      → blocked by: eval_pipeline ⏳ (remark produced but not persisted)
      → change: add nullable Text column to ExamSessionQuestion
      → enables: structured review UI showing LLM remarks

  [ ] RAG fallback in judge.py
      → blocked by: embed_pipeline ✅, eval_pipeline ⏳
      → change: when correct_answers is empty for essay, retrieve
        relevant topic_contents via pgvector and pass as model_answer
      → enables: grading essay questions that have no rubric

  [ ] HTTP API (FastAPI)
      → blocked by: eval_pipeline ⏳
      → endpoints needed:
          POST /session/{id}/submit       (write user_answer, set completed)
          GET  /session/{id}/answers      (lazy obj. grading — matches haisir)
          GET  /sessions?template={id}    (list sessions, compute ratio at display)
      → enables: front-end / mobile integration
```
