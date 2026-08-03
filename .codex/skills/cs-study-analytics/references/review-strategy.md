# Review Strategy

## Priority scoring

Use this relative order:

1. Incorrect cards (`known_status=X`).
2. Unreviewed cards with `importance=상`.
3. BOK cards (`bok_appeared=O`).
4. High difficulty cards.
5. Cards with older `last_reviewed` timestamps.
6. Category balance so one domain does not crowd out all others unless the user requested it.

## Study set shapes

- 15-minute sprint: 10 cards, mostly incorrect/high-importance.
- 30-minute session: 25-35 cards, mix of weak category and unreviewed important cards.
- Final review: BOK + importance `상` + current incorrect cards.

## Reporting

Use Korean by default. Keep each recommendation tied to concrete card IDs and terms.
Do not expose private paths unless useful for verification.
