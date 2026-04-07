"""Query rewriter + intent classifier for the RAG pipeline.

Given a raw user query, returns:
  - rewritten_query : retrieval-optimised string (keyword-dense, no filler words)
  - intent          : one of "definition" | "computation" | "explanation"

Intent meanings:
  definition  — user wants a definition, formula, or factual statement (quote verbatim)
  computation — user wants a specific value computed / a problem solved (apply rules, show working)
  explanation — user wants a concept explained or compared (synthesise in own words)
"""

from __future__ import annotations

import json
import re

from llama_index.core.llms import LLM

_REWRITE_PROMPT = """\
You are a query preprocessor for an educational content search system.

Given a student's question, output a JSON object with exactly two keys:
  "rewritten_query" : a retrieval-optimised version of the question.
                      - Remove conversational filler ("what is", "can you", "please", etc.)
                      - Keep subject-specific keywords and numbers
                      - Add closely related synonyms or alternative phrasings that might appear in a textbook
                      - Keep it concise (under 20 words)
  "intent"          : one of exactly three values:
                      "definition"  — asking for a definition, meaning, property, or formula
                      "computation" — asking to solve a specific problem, calculate a value, or find an unknown
                      "explanation" — asking how/why something works, or for a concept to be explained

Respond with ONLY the raw JSON object — no markdown, no commentary.

Examples:
  Input : "what is an absolute value?"
  Output: {{"rewritten_query": "absolute value integer definition", "intent": "definition"}}

  Input : "what must be subtracted from -3 to get -9"
  Output: {{"rewritten_query": "integer subtraction subtract -3 result -9 find unknown", "intent": "computation"}}

  Input : "explain how negative numbers work on a number line"
  Output: {{"rewritten_query": "negative numbers number line representation integers", "intent": "explanation"}}

Now process this query:
  Input : "{query}"
  Output:"""


def rewrite(query: str, llm: LLM) -> tuple[str, str]:
    """Return (rewritten_query, intent) for the given raw query.

    Falls back to (original query, "explanation") if the LLM response cannot be parsed.
    """
    prompt = _REWRITE_PROMPT.format(query=query.replace('"', '\\"'))
    response = llm.complete(prompt)
    raw = response.text.strip()

    # Strip markdown code fences if the model adds them despite instructions
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        data = json.loads(raw)
        rewritten = str(data["rewritten_query"]).strip()
        intent = str(data["intent"]).strip().lower()
        if intent not in ("definition", "computation", "explanation"):
            intent = "explanation"
        return rewritten, intent
    except Exception:
        # Graceful fallback — retrieval still works, just less optimised
        return query, "explanation"
