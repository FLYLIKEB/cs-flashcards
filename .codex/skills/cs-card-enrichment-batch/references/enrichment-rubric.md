# Enrichment Rubric

## Required output JSONL keys

Each line must be valid JSON with:

- `id`: existing card ID from the input workset.
- `definition`: improved one-sentence Korean definition.
- `detailed_explanation`: detailed text starting with `의미:` and containing `활용:`.
- `review_passed`: boolean. Use `true` only after self-review.
- `review_notes`: concise note about why the row passes or what was changed.

## Definition standard

Good definitions include:

- concept purpose or role;
- operating context;
- distinguishing boundary from adjacent concepts;
- a friendly first explanation that a learner can understand before memorizing details;
- no list-like fragments unless unavoidable.

Avoid:

- vague openings such as “~는 중요한 개념입니다”;
- definitions that only translate the English term;
- multiple unrelated clauses that become two or more sentences.

## Detailed explanation standard

Use exactly two visible sections:

```text
의미: ... 활용: ...
```

Good detailed explanations include:

- a 4-5 paragraph/sentence learning flow, while keeping only the two visible section labels `의미:` and `활용:`;
- a friendly opening that says what problem the concept solves or why it is needed;
- a simple example or analogy when it makes the concept easier to understand;
- the core mechanism, condition, or internal distinction with key terms in Korean and English where useful;
- a comparison point useful for written exams/interviews, including adjacent concepts or evolved models;
- a finance/public-sector/operations example when natural;
- one caution about misuse, limits, failure modes, or tradeoffs.

Avoid:

- stale format `동작/활용:`;
- boilerplate repeated across many cards;
- unsupported law/regulation claims unless source material is present;
- vendor-specific claims unless the card is vendor-specific.
- overly compressed encyclopedia summaries that only define the term without explaining the learner's "why/how/where it fails/where it is used" questions.

## Friendly study style

For each enriched card, aim for the RNN-style explanation quality:

1. `definition`: one substantial Korean sentence that states the concept, the data/system context, and the key distinguishing mechanism.
2. `의미:`: explain in a learner-friendly flow:
   - why the concept exists or what limitation it solves;
   - a short intuitive example when helpful;
   - the internal mechanism or operating principle;
   - important variants, comparisons, or boundaries;
   - limitations or failure modes.
3. `활용:`: explain practical uses, exam/interview framing, and one operational caution.
4. Do not add Markdown headings, bullets, citations, or numbered lists inside the CSV field unless the user explicitly asks for display-ready Markdown; keep the field plain text with `의미:` and `활용:` labels.
5. When external summaries such as Wikipedia, vendor docs, or official docs are used, reflect the source basis in `review_notes` or the batch review file rather than cluttering the card text with citation markers.

## Batch acceptance

A batch passes only when:

- output line count equals input line count;
- IDs are identical and unique;
- every `review_passed` is `true`;
- no existing progress columns are changed;
- the validator script passes.
