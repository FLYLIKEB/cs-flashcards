# Question bank audit common rules

Apply these rules to exactly one question row bundle.

## Goal
Make the row genuinely solvable/usable in the app and keep every DB column clean.

## Required checks
1. `prompt` must be the clean question stem only.
2. `body` must contain only problem context/data/code/table/conditions needed to solve.
3. `answer` must contain the final correct answer only; no `답:`, no placeholder, no irrelevant prose.
4. `explanation` must contain supporting reasoning only; remove irrelevant or wrong text.
5. `question_type`, `choices`, and `answer_index` must agree.
6. `keywords` must be concise domain terms; prefer existing flashcard terms/english already present in the linked `card` when relevant.
7. `category`, `topic`, `issuer`, `section`, `source_location`, `points`, `expected_time_seconds`, `answer_guide` must stay valid and consistent.
8. Remove noise such as markdown artifacts, duplicated numbered choices in `body`, answer leakage in `body`, `AI답변` markers, placeholder symbols, and generic phrases.

## Multiple-choice rules
- Keep numbered options in `choices` only.
- Remove duplicated `1. ... 2. ...` option text from `body` unless the line is required context such as code/table/input data.
- `answer_index` must point to the actual correct option.

## Incomplete-source conversion rule
If the original row is not realistically solvable because the necessary source data is missing, convert it into an explicit concept question:
- rewrite `prompt` into a clean concept/definition/explanation question,
- in `body` add exactly two plain lines:
  - `변환 메모: 원문 정보가 불완전하여 실전형 문제 대신 개념문제로 변환함.`
  - `원문 제목: <original prompt without markdown heading markers>`
- clear `choices` and `answer_index` when it is no longer multiple-choice,
- set `question_type` to `short` or `subjective` as appropriate,
- provide a grounded `answer` and `explanation`.

## Card/keyword rules
- If `card.term` / `card.english` clearly matches the question, keep or align `card_id` and include those terms in `keywords` when natural.
- Do not invent a `card_id` when the match is weak.
- `keywords` should be short noun phrases, not whole sentences or boilerplate question fragments.
- Remove duplicates and generic junk like `다음 중`, `설명하시오`, `옳은 것은`, `특징은`, `문제`, `답`.

## Output contract
- Edit only `proposed_row` and `audit` in the bundle JSON.
- `audit.status` must be `clean`, `fixed`, or `converted`.
- `audit.issues` must briefly list what was wrong.
- `audit.changes` must briefly list what you changed.
- Preserve valid fields when no correction is needed.
