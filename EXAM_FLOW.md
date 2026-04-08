# Exam System: End-to-End Flow

This document describes the full lifecycle of a question, exam, user attempt, and
evaluation in haiguru — covering data model relationships, question types, and
how information flows through the system.

---

## Phase 1 — Content & Question Creation

### Course Hierarchy

The curriculum is organised as a tree of `course_path_nodes` with `node_type`:

```
grade → subject → course
```

All content and questions are anchored to a course node via
`topics.course_path_node_id`. This hierarchy is also used to scope exam
templates and sessions.

### Topics & Content

Each course has `topics`. Each topic has `topic_contents` (videos, PDFs, text,
etc.). Topic content is embedded into `data_topic_content_vectors` (pgvector)
for RAG retrieval during evaluation.

Questions are linked to topics via `questions.topic_id`, enabling curriculum-
aware grading.

### Question Creation (Standalone)

Each row in `questions` represents one answerable question.

| Field | Description |
|---|---|
| `question_text` | The question prompt shown to the student |
| `question_type` | See table below |
| `options` (JSONB) | Answer choices for objective questions |
| `correct_answers` (JSONB) | Reference answer(s) — option IDs or expected text |
| `explanation` (String, nullable) | Shown in review UI (suppressed for essay); display only, does not drive grading |
| `difficulty` | `easy`, `medium`, or `hard` |
| `tags` (JSONB) | Optional metadata |
| `image_url` | Optional image attached to the question (nullable) |
| `topic_id` | FK → `topics.id`; links question to curriculum for RAG |

**Question types:**

| Type | Category | Description |
|---|---|---|
| `single_choice` | Objective | One correct option from a list |
| `multiple_choice` | Objective | One or more correct options |
| `true_false` | Objective | Binary correct/incorrect |
| `fill_in_the_blank` | Objective | Expected text stored in `correct_answers` |
| `essay` | Subjective | Long-form written answer; graded via LLM judge |

> `essay` covers all subjective answer formats (short or long). haiguru does
> not add a `paragraph` QuestionType — `paragraph_questions` remains purely a
> stimulus/context block entity, matching haisir exactly.

**Reference answer for subjective grading (`explanation` = display only):**

`explanation` is stored on the `questions` row and surfaced in the review UI
(suppressed for essay, same as haisir). It does **not** drive grading.

The LLM judge uses `correct_answers` as the model answer:
```
"; ".join(question.correct_answers)   ← model answer tokens joined for LLM judge
    ↓ if empty
RAG retrieval from topic_contents     ← future: retrieve relevant curriculum text
```

> ⚠️ If `correct_answers` is sparse or empty for an essay question, LLM judge
> grading quality degrades. Ensure essay questions have `correct_answers`
> populated with key points or a rubric summary.

### Paragraph Stimulus Creation

A `paragraph_questions` row is **not a question** — it is a **stimulus/context
block**: a reading passage, case study, or data table printed above a group of
related questions.

| Field | Description |
|---|---|
| `content` | Full stimulus text (the passage, case, or dataset) |
| `title` | Display title |
| `paragraph_type` | `reading_comprehension`, `case_study`, or `data_interpretation` |
| `question_ids` (ARRAY of UUID) | Ordered list of `questions.id` values belonging to this stimulus |
| `topic_id` | FK → `topics.id` |

Each sub-question in `question_ids` is a normal row in `questions` and can be
any type (objective or subjective).

```
paragraph_questions  (stimulus block)
  content: "Read the following passage and answer the questions..."
  paragraph_type: reading_comprehension
  question_ids: [q1_uuid, q2_uuid, q3_uuid]
    → q1: single_choice     "What is the author's tone?"
    → q2: essay             "Summarise the passage in your own words."
    → q3: fill_in_the_blank "The story is set in ___."
```

---

## Phase 2 — Exam Template Creation

An `exam_templates` row defines a reusable exam blueprint.

Key fields: `course_path_node_id`, `title`, `mode` (`static`/`dynamic`/`custom`),
`duration_minutes`, `passing_score`, `ruleset`.

Questions are added via `exam_template_questions`. Each row always has a
non-nullable `question_id` pointing to one `questions` row — matching haisir
exactly.

For paragraph stimulus blocks, each sub-question gets its own
`exam_template_questions` row (with `question_id` set) **at template authoring
time**. The `paragraph_question_id` column is still set on those rows to
indicate they belong to a stimulus block and should be displayed with it, but
`question_id` is never null.

| `question_id` | `paragraph_question_id` | Meaning |
|---|---|---|
| set | NULL | A single standalone question |
| set | set | A sub-question belonging to a stimulus block |

`order` and `points` are set per entry. The stimulus text itself is read from
`paragraph_questions.content` at display time using `paragraph_question_id`.

---

## Phase 3 — User Exam Attempt

### Session Initialisation

When a user starts an exam, an `exam_sessions` row is created
(`status: pending → ongoing`). The system then:

1. Queries all `exam_template_questions` for the template, ordered by `order`.
2. For each entry, creates one `exam_session_questions` row (always one-to-one —
   sub-questions were already expanded at template authoring time).
3. Each `exam_session_questions` row records: `exam_session_id`, `question_id`,
   `order`, `points` — with `user_answer`, `earned_points`, `is_correct` initially null.

### Answer Submission (mirrors haisir `submit_exam`)

The student submits all answers in one request. The submission endpoint:

1. Writes each answer to `exam_session_questions.user_answer` as a flat string:
   - Objective: comma-joined option IDs e.g. `"a"` or `"a,b"`
   - Subjective typed: full text string
   - Handwritten per-question image: `"image:/uploads/session_x_q_y.jpg"` — the
     `image:` prefix signals to the eval pipeline that OCR is required. Each
     `image:` entry points to exactly one question's answer image.

   > **Two handwritten submission paths:**
   > - **Sheet-splitting client**: scans the full answer sheet, automatically segments
   >   and OCRs per question, and writes plain text directly to `user_answer` (no
   >   `image:` prefix). The eval pipeline treats these identically to typed answers.
   > - **Per-question upload client**: student photographs or uploads one image per
   >   question. The `image:` prefix is set per `exam_session_questions` row; the
   >   eval pipeline OCRs each image individually at grading time.
2. Marks the session `status = "completed"` and sets `finished_at`.

> **Note:** This mirrors haisir's `POST /session/{session_id}/submit` exactly.
> In haisir, `earned_points` and `is_correct` for objective questions are persisted
> lazily on the answer-review GET request; essay questions remain ungraded until
> human review. haiguru matches this for objective questions and replaces human
> review with the `eval_pipeline` (LLM judge) for essay questions.

---

## Phase 4 — Evaluation Pipeline (`eval_pipeline`)

The eval pipeline is haiguru's functional equivalent of haisir's human-review
workflow: it grades essay answers using an LLM judge instead of a human reviewer,
and handles handwritten (image) submissions via OCR. It runs **after submission**,
grades all ungraded answers (where `exam_session_questions.earned_points IS NULL`),
and writes results back to the DB.

### When to run

- **Objective-only digital exam**: grading happens lazily on the answer-review
  GET request, identical to haisir. The eval pipeline is not required.
- **Essay questions**: run after session is submitted. The LLM judge replaces
  haisir's human-review step — this is the only intentional divergence from haisir.
- **Handwritten exam**: run after images have been submitted. Pipeline runs OCR
  first, then grades exactly as above.

### Steps

1. **Load session** (`load.py`):
   - Reads `exam_sessions` row.
   - Reads all `exam_session_questions` where `earned_points IS NULL`, joined to
     their `questions` rows.
   - For each, checks if `user_answer` starts with `"image:"` to detect image
     submissions.

2. **Per-question processing** (`ocr.py` + `judge.py` + `shared/grading.py`):

   | `esq.user_answer` | `question_type` | Action |
   |---|---|---|
   | starts with `"image:"` | objective | strip prefix → OCR image → overwrite `esq.user_answer` → `grade_question` |
   | starts with `"image:"` | essay | strip prefix → OCR image → overwrite `esq.user_answer` → `grade_subjective` |
   | set (no prefix) | objective | `grade_question(user_answer, correct_answers)` |
   | set (no prefix) | subjective | LLM judge: `grade_subjective(user_answer, model_answer, points)` |
   | null or empty | any | warn + grade as unanswered (0 pts) |

   > Each `image:` entry points to one question's answer image (per-question upload
   > path). OCR returns text for that question only — no extraction or isolation step
   > is needed. `grade_question` is responsible for normalizing OCR text (e.g.
   > `"option B"` → `"b"`); if it cannot, its scope should be expanded rather than
   > adding a separate normalization step in the eval pipeline.

3. **OCR detail** (`ocr.py`):
   - Strips the `"image:"` prefix from `user_answer` to get the filesystem path.
   - Encodes image as base64, sends to OCR model.
   - Overwrites `exam_session_questions.user_answer` with transcribed text.

4. **Grading detail** (`judge.py` + `shared/grading.py`):
   - **Objective**: `grade_question(user_answer, question.correct_answers)` — same logic as haisir's `shared/grading.py`, returns `(is_correct, earned_points)`.
   - **Subjective**: `grade_subjective(user_answer, model_answer, points)` via LLM judge, returns `(awarded, remark)`.
   - `model_answer` = `"; ".join(question.correct_answers or [])`. Falls back to RAG from `topic_contents` (future) if empty.
   - `explanation` is display-only — surfaced in review UI, suppressed for essay; it does not drive grading.

5. **Write results** (`load.py`):
   - Updates `exam_session_questions`: `earned_points`, `is_correct`,
     `user_answer` (OCR overwrites the `image:` prefix with transcribed text).

6. **Finalize session** (`load.py`):
   - Sums `earned_points` across all `exam_session_questions` for the session.
   - Stores the raw `total_earned` sum in `exam_sessions.score`, matching haisir.
     The ratio is computed at display time (same as haisir's
     `get_all_sessions_for_exam_template`).

---

## Phase 5 — Information Flow

```
categories
  └── course_path_nodes (grade → subject → course)
        └── topics
              ├── topic_contents ──→ data_topic_content_vectors (RAG / pgvector)
              ├── questions ◄────────────────────────────────────────────────────┐
              └── paragraph_questions (stimulus blocks)                          │
                    └── question_ids[] ─────────────────────────────────────→ questions

exam_templates
  └── exam_template_questions
        ├── question_id ────────────────────────────────────────────────────→ questions
        └── paragraph_question_id → paragraph_questions → question_ids[] → questions

                    [SESSION START]
exam_sessions  (one per user attempt)
  └── exam_session_questions  (one per question; stimulus sub-questions expanded)
        ├── question_id ───────────────────────────────────────────────────→ questions
        ├── order, points
        ├── user_answer       ← written at submission:
        │                        "a,b"           (objective)
        │                        "full text..."  (subjective typed)
        │                        "image:/path/to/scan.jpg"  (handwritten — image: prefix)
        ├── earned_points     ← written by eval pipeline
        └── is_correct        ← written by eval pipeline

                    [SUBMISSION — mirrors haisir submit_exam]
Student submits → exam_session_questions.user_answer populated for each question
Session status → "completed", finished_at set

                    [EVALUATION PIPELINE — equiv. of haisir human review]
eval_pipeline  (for sessions with essay questions or handwritten answers)
  reads esq where earned_points IS NULL
    ├── if user_answer starts with "image:" → strip prefix → OCR per-question image → overwrite user_answer
    ├── grade with shared/grading.py (objective) or LLM judge (essay)
    └── writes earned_points, is_correct → exam_session_questions
                                        → updates exam_sessions.score
```
