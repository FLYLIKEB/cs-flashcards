from __future__ import annotations

import random
import re
from typing import Any, Iterable, Literal

QuestionType = Literal["short", "subjective", "multiple_choice", "essay"]

SUPPORTED_QUESTION_TYPES: tuple[QuestionType, ...] = ("short", "subjective", "multiple_choice", "essay")
QUESTION_TYPE_ALIASES: dict[str, QuestionType] = {
    "short": "short",
    "short_answer": "short",
    "주관식": "short",
    "단답형": "short",
    "subjective": "subjective",
    "descriptive": "subjective",
    "서술형": "subjective",
    "multiple_choice": "multiple_choice",
    "mcq": "multiple_choice",
    "objective": "multiple_choice",
    "객관식": "multiple_choice",
    "essay": "essay",
    "논술형": "essay",
}

QUESTION_TYPE_LABELS: dict[QuestionType, str] = {
    "short": "주관식",
    "subjective": "서술형",
    "multiple_choice": "객관식",
    "essay": "논술형",
}


def normalize_question_types(types: Iterable[str] | None) -> list[QuestionType]:
    if not types:
        return list(SUPPORTED_QUESTION_TYPES)
    normalized: list[QuestionType] = []
    invalid: list[str] = []
    for raw in types:
        key = str(raw or "").strip().lower()
        value = QUESTION_TYPE_ALIASES.get(key)
        if not value:
            invalid.append(str(raw))
            continue
        if value not in normalized:
            normalized.append(value)
    if invalid:
        raise ValueError(f"Unsupported question type: {', '.join(invalid)}")
    return normalized or list(SUPPORTED_QUESTION_TYPES)


def normalize_card_ids(card_ids: Iterable[str] | None) -> set[str] | None:
    if not card_ids:
        return None
    selected = {str(card_id).strip() for card_id in card_ids if str(card_id or "").strip()}
    return selected or None


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def first_sentence(value: Any, *, fallback: str = "") -> str:
    text = clean_text(value)
    if not text:
        return fallback
    match = re.search(r"(.+?[.!?。]|.+?(?:다|요)\.)", text)
    if match:
        return match.group(1).strip()
    return text[:220].rstrip() + ("…" if len(text) > 220 else "")


def summarize_detail(value: Any, *, limit: int = 520) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip()
    return f"{cut}…"


def parse_related_concepts(value: Any) -> list[str]:
    text = str(value or "")
    bracketed = re.findall(r"\[\[([^\]]+)\]\]", text)
    if bracketed:
        return [clean_text(item) for item in bracketed if clean_text(item)]
    return [clean_text(part) for part in re.split(r"[,;/]", text) if clean_text(part)]


def card_term(card: dict[str, str]) -> str:
    return clean_text(card.get("term")) or clean_text(card.get("english")) or clean_text(card.get("id"))


def question_id(card: dict[str, str], question_type: QuestionType, seed: int | None) -> str:
    suffix = "auto" if seed is None else str(seed)
    return f"q-{clean_text(card.get('id'))}-{question_type}-{suffix}"


def base_question(card: dict[str, str], question_type: QuestionType, seed: int | None) -> dict[str, Any]:
    return {
        "id": question_id(card, question_type, seed),
        "card_id": clean_text(card.get("id")),
        "type": question_type,
        "type_label": QUESTION_TYPE_LABELS[question_type],
        "term": card_term(card),
        "category": clean_text(card.get("category")),
        "importance": clean_text(card.get("importance")),
        "difficulty": clean_text(card.get("difficulty")),
        "bok_appeared": clean_text(card.get("bok_appeared")),
    }


def generate_short_answer(card: dict[str, str], *, seed: int | None = None) -> dict[str, Any]:
    term = card_term(card)
    definition = first_sentence(card.get("definition"), fallback=f"{term}의 핵심 설명")
    question = base_question(card, "short", seed)
    question.update(
        {
            "prompt": "다음 설명에 해당하는 CS 개념명을 쓰시오.",
            "body": definition,
            "answer": term,
            "acceptable_answers": [item for item in [term, clean_text(card.get("english"))] if item],
            "explanation": clean_text(card.get("definition")),
            "rubric": ["핵심 개념명을 정확히 쓴다.", "영문명이 있는 경우 영문명도 정답으로 인정할 수 있다."],
        }
    )
    return question


def generate_subjective(card: dict[str, str], *, seed: int | None = None) -> dict[str, Any]:
    term = card_term(card)
    category = clean_text(card.get("category")) or "CS"
    related = parse_related_concepts(card.get("related_concepts"))[:3]
    rubric = [
        f"{term}의 정의와 목적을 설명한다.",
        "동작 방식, 활용 상황, 장단점 중 하나 이상을 포함한다.",
    ]
    if related:
        rubric.append(f"관련 개념({', '.join(related)})과의 차이나 연결점을 언급한다.")
    if clean_text(card.get("exam_note")):
        rubric.append(clean_text(card.get("exam_note")))
    answer_parts = [clean_text(card.get("definition")), summarize_detail(card.get("detailed_explanation"))]
    question = base_question(card, "subjective", seed)
    question.update(
        {
            "prompt": f"{term}의 의미와 활용을 서술하시오.",
            "body": f"{category} 관점에서 {term}이 무엇인지, 왜 중요한지 설명하시오.",
            "answer": " ".join(part for part in answer_parts if part),
            "explanation": clean_text(card.get("exam_note")) or clean_text(card.get("definition")),
            "rubric": rubric,
        }
    )
    return question


def unique_cards_by_term(cards: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for card in cards:
        term = card_term(card)
        key = term.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(card)
    return unique


def distractor_groups(card: dict[str, str], all_cards: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    answer = card_term(card).lower()
    related = {item.lower() for item in parse_related_concepts(card.get("related_concepts"))}
    candidates = [c for c in all_cards if card_term(c).lower() != answer]
    related_cards = [c for c in candidates if card_term(c).lower() in related]
    same_category = [c for c in candidates if clean_text(c.get("category")) == clean_text(card.get("category"))]
    same_difficulty = [c for c in candidates if clean_text(c.get("difficulty")) == clean_text(card.get("difficulty"))]
    return [
        unique_cards_by_term(related_cards),
        unique_cards_by_term(same_category),
        unique_cards_by_term(same_difficulty),
        unique_cards_by_term(candidates),
    ]


def select_distractors(
    card: dict[str, str],
    all_cards: list[dict[str, str]],
    *,
    rng: random.Random,
    limit: int = 3,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    seen = {card_term(card).lower()}
    for group in distractor_groups(card, all_cards):
        shuffled = group[:]
        rng.shuffle(shuffled)
        for candidate in shuffled:
            term_key = card_term(candidate).lower()
            if not term_key or term_key in seen:
                continue
            selected.append(candidate)
            seen.add(term_key)
            if len(selected) >= limit:
                return selected
    return selected


def generate_multiple_choice(
    card: dict[str, str],
    all_cards: list[dict[str, str]],
    *,
    rng: random.Random | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    rng = rng or random.Random(seed)
    term = card_term(card)
    selected = select_distractors(card, all_cards, rng=rng, limit=3)
    choices = [term] + [card_term(item) for item in selected]
    if len(choices) < 4:
        fallbacks = ["해당 없음", "모두 맞음", "판단 불가"]
        for fallback in fallbacks:
            if fallback not in choices and len(choices) < 4:
                choices.append(fallback)
    rng.shuffle(choices)
    definition = first_sentence(card.get("definition"), fallback=f"{term}에 대한 설명")
    answer_index = choices.index(term)
    question = base_question(card, "multiple_choice", seed)
    question.update(
        {
            "prompt": "다음 설명에 해당하는 개념으로 가장 적절한 것을 고르시오.",
            "body": definition,
            "choices": choices,
            "answer": term,
            "answer_index": answer_index,
            "explanation": clean_text(card.get("definition")),
            "rubric": ["정답 개념과 오답 개념의 정의 차이를 구분한다."],
        }
    )
    return question


def generate_essay(card: dict[str, str], *, seed: int | None = None) -> dict[str, Any]:
    term = card_term(card)
    related = parse_related_concepts(card.get("related_concepts"))[:3]
    related_clause = f", {', '.join(related)}와의 관계를 포함해" if related else ""
    rubric = [
        f"{term}의 정의와 핵심 목적을 제시한다.",
        "실무 또는 시험 맥락에서 중요한 이유를 설명한다.",
        "한계, 오해하기 쉬운 점, 비교 개념 중 하나 이상을 논한다.",
    ]
    if related:
        rubric.append(f"비교 개념으로 {', '.join(related)} 중 하나 이상을 활용한다.")
    if clean_text(card.get("exam_note")):
        rubric.append(clean_text(card.get("exam_note")))
    answer_parts = [
        clean_text(card.get("definition")),
        summarize_detail(card.get("detailed_explanation"), limit=760),
        clean_text(card.get("exam_note")),
    ]
    question = base_question(card, "essay", seed)
    question.update(
        {
            "prompt": f"{term}에 대해 논술하시오.",
            "body": f"{term}의 개념, 활용 맥락{related_clause} 체계적으로 논하시오.",
            "answer": " ".join(part for part in answer_parts if part),
            "explanation": clean_text(card.get("exam_note")) or clean_text(card.get("definition")),
            "rubric": rubric,
        }
    )
    return question


def generate_question_for_type(
    question_type: QuestionType,
    card: dict[str, str],
    all_cards: list[dict[str, str]],
    *,
    rng: random.Random,
    seed: int | None,
) -> dict[str, Any]:
    if question_type == "short":
        return generate_short_answer(card, seed=seed)
    if question_type == "subjective":
        return generate_subjective(card, seed=seed)
    if question_type == "multiple_choice":
        return generate_multiple_choice(card, all_cards, rng=rng, seed=seed)
    if question_type == "essay":
        return generate_essay(card, seed=seed)
    raise ValueError(f"Unsupported question type: {question_type}")


def generate_questions(
    cards: list[dict[str, str]],
    *,
    card_ids: Iterable[str] | None = None,
    types: Iterable[str] | None = None,
    count: int = 10,
    seed: int | None = None,
) -> dict[str, Any]:
    selected_ids = normalize_card_ids(card_ids)
    question_types = normalize_question_types(types)
    filtered_cards = [card for card in cards if not selected_ids or clean_text(card.get("id")) in selected_ids]
    if selected_ids:
        existing = {clean_text(card.get("id")) for card in filtered_cards}
        missing = sorted(selected_ids - existing)
        if missing:
            raise KeyError(", ".join(missing))
    if not filtered_cards:
        return {"questions": [], "summary": {"requested": count, "generated": 0, "available_cards": 0}}

    rng = random.Random(seed)
    ordered_cards = filtered_cards[:]
    rng.shuffle(ordered_cards)
    ordered_types = question_types[:]
    rng.shuffle(ordered_types)

    generated: list[dict[str, Any]] = []
    for card in ordered_cards:
        for question_type in ordered_types:
            generated.append(generate_question_for_type(question_type, card, cards, rng=rng, seed=seed))
    rng.shuffle(generated)

    safe_count = max(1, min(int(count or 10), 100))
    questions = generated[:safe_count]
    return {
        "questions": questions,
        "summary": {
            "requested": safe_count,
            "generated": len(questions),
            "available_cards": len(filtered_cards),
            "types": question_types,
            "seed": seed,
        },
    }
