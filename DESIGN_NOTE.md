# Design Note

## Key choices, and why

**Guardrails live in two places, deliberately.** A system prompt is a
suggestion; a function signature is a guarantee. So identity verification
and no-double-booking are enforced in `src/tools.py` itself — `book_appointment`
re-checks slot availability atomically, and every patient-scoped tool
requires a `patient_id` that only exists after `verify_patient` matched name
+ DOB. Softer judgment calls — tone, when to escalate ambiguous symptoms,
how to handle an angry patient, resisting prompt injection — are left to the
prompt/policy layer, because that's where they belong and where the
improvement loop can iterate on them safely. Conflating the two (e.g. relying
on the LLM to never leak another patient's PHI) is a real failure mode I
wanted to design out, not detect after the fact.

**The eval rubric is not a single LLM "vibes" score.** I split scoring into
correctness / safety / communication / no-hallucination, and biased toward
programmatic, structural checks (was the right tool called, did a claimed
booking actually correspond to a successful tool call) over a transcript-only
judge. A transcript-only judge can rate a warm, well-written refusal highly
even if the agent secretly called `book_appointment` anyway, and it can't
verify a factual claim against ground truth without seeing tool results. Every
safety-critical scenario here has a structural check tied to the tool log,
not just a judge's read of the prose. This is documented in `judge.py`'s
docstring rather than left implicit.

**The improvement loop maps each failure to one targeted rule**, not a vague
"be more careful." `src/improve.py` has an explicit failure→rule table, so
each policy addition is attributable to the scenario it was meant to fix,
which is what makes the before/after regression check meaningful — if an
unrelated scenario moves after a rule lands, that rule is the first suspect.
Some failures are explicitly marked as *not* prompt-fixable (e.g. PHI
isolation, which is already structurally enforced in `tools.py`) rather than
papered over with a redundant prompt rule.

**Mock backend, gated by the same policy file as the real one.** No API key
is required to run and grade the loop; `MockBackend` pattern-matches known
scenario intents but reads its behavior flags off the identical
`data/policies.json` the real system prompt is rendered from, so the loop
mechanics (detect failure → write rule → re-run → diff → regression check)
are real and identical to what a real-Claude run (`--mode real`,
`AnthropicBackend`) would exercise. What's simulated is language
understanding, not the improvement loop itself. I'd rather ship an honest,
fully-working mock loop than a real-model demo I can't guarantee reproduces.

## How the improvement loop works (recap)
1. Reset policy to v1 baseline → run 9 scenarios → `baseline.json`.
2. For each failing scenario, look up its targeted rule in `improve.py` and
   append it to `policies.json` (version bump + changelog).
3. Re-run the identical 9 scenarios → `after.json`.
4. Diff per-scenario scores; flag any negative delta as a regression.

## Before / after (checked into `results/`, reproducible via `run_eval_loop.py`)
```
Overall: 88.9 -> 94.4 (+5.5)
Pass rate: 88.9% -> 100.0%
medical_advice_boundary: 50 -> 100, all other scenarios unchanged, zero regressions
```

## One thing I'd change for a real clinic in production
Move identity verification from "name + DOB" to something that can't be
guessed from a public records search (MRN, or an OTP to the phone on file),
and add a rate limiter / lockout on `verify_patient` — right now a caller can
brute-force names against DOBs with no penalty, which is fine for a
take-home but not for a real intake line.

## Where AI helped vs. where I overrode it
AI (Claude) helped scaffold the tool schemas and the first draft of the
scenario list. I overrode/changed: the decision to split guardrails between
code and prompt rather than prompt-only (the first draft leaned entirely on
prompt instructions for PHI and double-booking, which I considered a
production risk); the judge design, since the first draft was a single
LLM-judge score and I split it into structural + heuristic checks after
noticing it couldn't distinguish "sounded safe" from "was safe"; and the
mock backend's honesty framing — I wanted it stated plainly that it's a
scripted stand-in, not glossed over as "the agent," since that distinction
matters for how much to trust the numbers.
