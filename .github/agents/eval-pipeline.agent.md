---
description: "Use when building eval_pipeline/ — the answer-sheet evaluation pipeline that grades exam sessions via OCR, objective grading, and LLM-based subjective judging."
name: "Eval Pipeline Agent"
tools: [read, edit, search, execute]
---

You are implementing the `eval_pipeline` package for haiguru — a post-submission grading pipeline that processes exam sessions containing objective, essay, and handwritten answers.

## Required reading before any work

- `docs/eval_pipeline_plan.md` — the authoritative implementation plan (module layout, CLI, steps 1–5, edge cases, implementation order)
- `docs/exam_flow.md` — end-to-end exam lifecycle (phases 1–5, answer formats, score storage)
- `agent_docs/data_model.md` — table hierarchy and column contracts

## What already exists

| File | What it provides |
|---|---|
| `shared/grading.py` | `grade_question(user_answer, points, question)` — dispatches by `question_type`, returns `(is_correct, earned_points)`. Returns `(None, 0.0)` for essay — **your job** is to handle essay via `judge.py`. |
| `shared/normalization.py` | `normalize_option_text()`, `options_match()` — used by grading |
| `glm_ocr/client.py` | `get_optimized_image_b64(path)`, `send_single_request(model, prompt, images_b64)` — reuse for OCR |
| `llm_factory.py` | `make_llm(model_name)` — creates LlamaIndex LLM with provider routing |
| `rag/retriever.py` | `build_retriever(top_k, filters)` — for RAG fallback when `correct_answers` is empty |
| `config.py` | Central env config — you need to add `EVAL_MODEL` here |
| `db/models.py` | `ExamSession`, `ExamSessionQuestion`, `Question` ORM classes |

## Package structure to build

```
eval_pipeline/
├── __init__.py
├── __main__.py      # CLI (argparse) + orchestration (_grade_one, main)
├── ocr.py           # run_ocr_for_answer(image_path, model) -> str
├── judge.py         # grade_subjective() + _parse_json_response() + RAG fallback
└── load.py          # load_session() + save_results() — DB read/write
```

Also modify: `config.py` (add `EVAL_MODEL`), `.env.example` (add `EVAL_MODEL=`)

## Critical implementation details

**Answer detection**: `user_answer` starting with `"image:"` means OCR is needed. Strip prefix to get filesystem path.

**Grading dispatch** (in `_grade_one`):
- Objective types (`single_choice`, `multiple_choice`, `true_false`, `fill_in_the_blank`): use `shared/grading.py` `grade_question()`
- `essay`: use `judge.py` `grade_subjective()`
- After OCR, overwrite `user_answer` with transcribed text, then grade normally

**LLM judge JSON parsing** (`judge.py`):
- Strip `<think>…</think>` blocks (qwen3 models emit these)
- Strip markdown fences
- Try `json.loads` first, then regex `r'\{[\s\S]*\}'` fallback
- On parse failure: return `JudgeResult(awarded=0.0, max_marks=points, remark="parse error")` + `warnings.warn`
- Clamp `awarded` to `[0.0, float(points)]`

**model_answer resolution** (`judge.py`):
```python
model_answer = "; ".join(question.correct_answers or [])
if not model_answer:
    # RAG fallback via rag/retriever.py
    warnings.warn(f"question {question.id}: correct_answers empty, using RAG fallback")
```

**save_results** (`load.py`): single transaction — update each `esq`, then re-sum ALL `earned_points` across ALL session questions (not just this run's), overwrite `exam_sessions.score`.

**Session filter**: only process `esq` rows where `earned_points IS NULL`. Raise if session `status != "completed"`.

## Constraints

- All DB operations use SQLAlchemy ORM sessions, not raw SQL
- Follow existing code patterns in `etl_pipeline/` and `rag/` for style
- Use `warnings.warn` for non-fatal issues, `RuntimeError` for fatal ones (e.g. missing image file)
- The `EVAL_MODEL` env var uses the same provider prefix convention as `RAG_MODEL`
