"""Grading logic for exam questions.

Type-dispatched grading with weighted scoring and partial credit support.
Works with haiguru's SQLAlchemy model instances directly.
"""

from eval_pipeline.normalization import normalize_option_text, options_match


def grade_question(user_answer: str | None, points: int, question) -> tuple[bool | None, float]:
    """Grade a single exam question based on its type.

    Args:
        user_answer: The student's answer string (comma-separated option IDs for choice
                     questions, plain text for fill_in_the_blank, None for unanswered).
        points: Max points assigned to this question in the session.
        question: A haiguru Question ORM instance with question_type, options (JSONB list
                  of {id, text} dicts), and correct_answers (JSONB list of option ID strings).

    Returns:
        (is_correct, earned_points).
        is_correct is None for essay questions (pending manual review).
    """
    qt = question.question_type
    if qt in ("single_choice", "true_false"):
        return _grade_choice(user_answer, points, question)
    elif qt == "multiple_choice":
        return _grade_multiple_choice(user_answer, points, question)
    elif qt == "fill_in_the_blank":
        return _grade_fill_in_blank(user_answer, points, question)
    else:  # essay, paragraph
        return None, 0.0


def _get_user_answer_ids(user_answer: str | None) -> list[str]:
    """Parse comma-separated user answer IDs."""
    return [s.strip() for s in (user_answer or "").split(",") if s.strip()]


def _get_option_id_to_text(question) -> dict[str, str]:
    """Build a map from option ID to option text from JSONB options list."""
    return {str(opt["id"]): opt.get("text", "") for opt in (question.options or [])}


def _grade_choice(user_answer: str | None, points: int, question) -> tuple[bool, float]:
    """Grade single_choice or true_false (exact set match)."""
    option_map = _get_option_id_to_text(question)
    user_ids = _get_user_answer_ids(user_answer)
    correct_ids = question.correct_answers or []

    user_texts = [str(option_map.get(aid, aid)) for aid in user_ids]
    correct_texts = [str(option_map.get(aid, aid)) for aid in correct_ids]

    is_correct = options_match(user_texts, correct_texts)
    earned = float(points) if is_correct else 0.0
    return is_correct, earned


def _grade_multiple_choice(user_answer: str | None, points: int, question) -> tuple[bool, float]:
    """Grade multiple_choice with partial credit.

    Formula: max(0, (correct_selected - wrong_selected) / total_correct) * points
    """
    correct_set = set(question.correct_answers or [])
    user_ids = set(_get_user_answer_ids(user_answer))

    total_correct = len(correct_set)
    if total_correct == 0:
        is_correct = len(user_ids) == 0
        return is_correct, float(points) if is_correct else 0.0

    correct_selected = len(user_ids & correct_set)
    wrong_selected = len(user_ids - correct_set)

    ratio = max(0.0, (correct_selected - wrong_selected) / total_correct)
    earned = ratio * points
    is_correct = correct_selected == total_correct and wrong_selected == 0
    return is_correct, earned


def _grade_fill_in_blank(user_answer: str | None, points: int, question) -> tuple[bool, float]:
    """Grade fill_in_the_blank by normalized text match."""
    user_text = normalize_option_text(user_answer)
    if not user_text:
        return False, 0.0

    for correct in (question.correct_answers or []):
        if normalize_option_text(correct) == user_text:
            return True, float(points)

    return False, 0.0
