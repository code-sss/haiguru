# Plan: eval_pipeline — Answer Sheet Evaluation

## Background

For the full data model, question types, exam creation flow, and how answers
flow through the system, see [exam_flow.md](./exam_flow.md).
Review decisions that shaped this plan are in [decisions.md](./decisions.md).

---

## What Already Exists

| Component | State | Notes |
|---|---|---|
| `db/models.py` | Done | Schema for sessions, questions, templates |
| `shared/grading.py` | Done | `grade_question()` — objective grading with partial credit |
| `shared/normalization.py` | Done | Text normalization helpers |
| `llm_factory.py` | Done | `make_llm()` — provider routing (Ollama/OpenAI/Anthropic/Together) |
| `glm_ocr/client.py` | Done | `get_optimized_image_b64()`, `send_single_request()` for OCR |
| `config.py` | Done | Central env config |
| `embed_pipeline/` | Done | Topic content → pgvector embeddings |
| `rag/` | Done | Hybrid retrieval + synthesis |

---

## What To Build

```
eval_pipeline/
├── __init__.py      # module marker
├── __main__.py      # CLI + orchestration
├── ocr.py           # per-question image → text via Ollama vision model
├── judge.py         # LLM judge for subjective grading
└── load.py          # DB read (load session) + DB write (save results)
```

Also modify:
- `config.py` — add `EVAL_MODEL`
- `.env.example` — add `EVAL_MODEL=`

---

## CLI Interface

```bash
uv run python -m eval_pipeline \
    --session-id <uuid> \
    [--ocr-model glm-ocr-optimized] \
    [--eval-model openai://gpt-4o]
```

No `--images` flag — pipeline detects image submissions via `image:` prefix
in `exam_session_questions.user_answer`. No `--skip-ocr` — inferred per row.

---

## Pipeline Steps

### Step 1: `load.py` — `load_session(session_id) -> SessionData`

- Query `ExamSession` by id. Raise if not found.
- Raise if `session.status != "completed"`.
- Load `exam_session_questions` rows where `earned_points IS NULL`, joined to
  their `questions` rows (the ungraded answers).
- For each row, check if `user_answer` starts with `"image:"`.
- Return `SessionData(session_id, user_id, items: list[SessionItem])`.

`SessionItem`: `esq` (ORM), `question` (ORM), `image_path` (str | None).

### Step 2: `ocr.py` — `run_ocr_for_answer(image_path, model) -> str`

- Load image from local filesystem path.
- `get_optimized_image_b64(path)` + `send_single_request(model, OCR_PROMPT, [b64])`.
- Return transcribed text; caller overwrites `esq.user_answer`.
- OCR prompt: `"Transcribe the handwritten text exactly, preserving question numbers and answers."`

> **Open gap (Decision #4):** `grade_question` is responsible for normalizing
> OCR text (e.g. `"option B"` → `"b"`). Concrete normalization rules will be
> defined when building this step. Until then, OCR'd objective answers may
> score incorrectly if text doesn't match expected option IDs.

### Step 3: `judge.py` — LLM subjective grading

**`grade_subjective(question_text, model_answer, student_answer, points, llm) -> JudgeResult`**

- Build prompt (see below) → `llm.complete(prompt).text`.
- Strip `<think>…</think>` blocks (qwen3 models), strip markdown fences, parse JSON.
- `_parse_json_response`: try `json.loads(stripped)` first, then
  `re.search(r'\{[\s\S]*\}', text)` fallback.
- On parse failure: `JudgeResult(awarded=0.0, max_marks=points, remark="parse error")`
  + `warnings.warn`.
- Clamp `awarded` to `[0.0, float(points)]`.

**Judge prompt:**
```
You are a strict exam evaluator. Grade the student's answer.

Question: {question_text}
Model answer: {model_answer}
Student answer: {student_answer}
Max marks: {points}

Return only valid JSON:
{"awarded": <float>, "max_marks": <int>, "remark": "<brief feedback>"}
```

**`model_answer` resolution (Decision #2):**
```
model_answer = "; ".join(question.correct_answers or [])
if not model_answer:
    # RAG fallback — retrieve from topic_contents via question.topic_id
    model_answer = rag_retrieve_model_answer(question.topic_id, question.question_text)
    warnings.warn(f"question {question.id}: correct_answers empty, using RAG fallback")
```

The RAG fallback uses the existing `rag/retriever.py` to fetch relevant
`topic_contents` chunks and joins them as the model answer. This is the
safety-net path (Decision #2); the quality path is populating `correct_answers`
at template authoring time.

### Step 4: `__main__.py` — Orchestration

**`_grade_one(item: SessionItem, llm, ocr_model) -> QuestionResult`**

| `esq.user_answer` | `question_type` | Action |
|---|---|---|
| starts with `"image:"` | objective | strip prefix → OCR → overwrite `user_answer` → `grade_question()` |
| starts with `"image:"` | essay | strip prefix → OCR → overwrite `user_answer` → `grade_subjective()` |
| set (no prefix) | objective | `grade_question(user_answer, points, question)` |
| set (no prefix) | essay | `grade_subjective(question_text, model_answer, user_answer, points, llm)` |
| null or empty | any | warn + grade as unanswered (0 pts) |

Objective = `{single_choice, multiple_choice, true_false, fill_in_the_blank}`
Subjective = `{essay}`

`QuestionResult`: `esq_id` (UUID), `earned_points` (float), `is_correct` (bool | None),
`user_answer` (str | None — set when OCR overwrote the image: prefix).

### Step 5: `load.py` — `save_results(session_id, results)`

Single transaction:

1. For each `QuestionResult`:
   - Update `exam_session_questions`: `earned_points`, `is_correct`,
     `user_answer` (OCR text replaces `image:` prefix).
2. **Re-sum ALL `earned_points`** across all `exam_session_questions` for the
   session (not just the ones graded in this run).
3. Overwrite `exam_sessions.score` with the total.

> **Decision #1:** `eval_pipeline` always performs a full re-sum and overwrites
> `exam_sessions.score`, regardless of whether `_finalize_session()` already
> ran from the lazy-grading GET. This makes `eval_pipeline` the authoritative
> final scorer for any session it processes.

---

## Key Reused Utilities

| Utility | File | Usage |
|---|---|---|
| `get_optimized_image_b64` | `glm_ocr/client.py` | Load & encode images for OCR |
| `send_single_request` | `glm_ocr/client.py` | Non-streaming OCR call to Ollama |
| `make_llm` | `llm_factory.py` | Create LlamaIndex LLM for judge |
| `grade_question` | `shared/grading.py` | Grade objective questions (identical to haisir) |
| `DATABASE_URL`, `EVAL_MODEL` | `config.py` | Config |
| `db.models.*` | `db/models.py` | ORM classes |

---

## Edge Cases

| Case | Handling |
|---|---|
| No ungraded `esq` rows for session | warn + exit 0 |
| `esq.user_answer` null or empty | warn + grade as unanswered (0 pts) |
| `user_answer` starts with `image:` but file missing | `RuntimeError` → exit 1 |
| Question missing from DB | `warnings.warn` + skip row |
| LLM JSON parse failure | `JudgeResult(awarded=0, remark="parse error")` + warn |
| `awarded > points` from LLM | Clamped to `[0.0, float(points)]` |
| `correct_answers` empty for essay | RAG fallback + warn (Decision #2) |
| `_finalize_session()` already set score | `eval_pipeline` re-sums and overwrites (Decision #1) |
| DB transaction failure | Session auto-rollback; no partial writes |

---

## Verification

```bash
# 1. Student submits exam (writes user_answer, sets session completed)
# 2. For handwritten: set esq.user_answer = "image:/uploads/session_x_q_y.jpg"

# 3. Run evaluation:
uv run python -m eval_pipeline --session-id <uuid>

# 4. Check results:
# SELECT esq.order, esq.user_answer, esq.is_correct, esq.earned_points
# FROM exam_session_questions esq WHERE esq.exam_session_id = '<uuid>';
# SELECT score FROM exam_sessions WHERE id = '<uuid>';
```

---

## Implementation Order

```
[1] ✓ config.py: add EVAL_MODEL
      .env.example: add EVAL_MODEL=

[2] ✓ eval_pipeline/load.py
      → load_session(), save_results()
      → depends on: db/models.py (done)

[3] ✓ eval_pipeline/ocr.py
      → run_ocr_for_answer()
      → depends on: glm_ocr/client.py (done)

[4] ✓ eval_pipeline/judge.py
      → grade_subjective(), _parse_json_response(), RAG fallback
      → depends on: llm_factory.py (done), rag/retriever.py (done), EVAL_MODEL [1]

[5] ✓ eval_pipeline/__main__.py
      → _grade_one(), main()
      → depends on: [2], [3], [4], shared/grading.py (done)
```

**Status: Complete** — all five steps implemented.

---

## Future (out of scope for this plan)

- `llm_feedback` column on `exam_session_questions` — persist LLM `remark`
  for review UI (requires schema migration)
- RAG-assisted `correct_answers` generation at template authoring time
  (Decision #2, quality path)
- HTTP API endpoints (FastAPI)
