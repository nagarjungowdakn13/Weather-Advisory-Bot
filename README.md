# weather advisory bot

Answers outdoor-activity-safety questions ("is it safe to cycle today") using live
Open-Meteo data, but only ever gives advice that traces back to a written SOP. If no
SOP covers the question, it says so instead of guessing.

## running it

You need Python 3.10+ and an API key for Anthropic, OpenAI, or Groq. No weather API
key needed — Open-Meteo is free and unauthenticated.

```
pip install -r requirements.txt
cp .env.example .env
# edit .env: set ANTHROPIC_API_KEY (default provider), or switch LLM_PROVIDER to
# openai or groq and set the matching key/model
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 — the FastAPI app serves the frontend directly, there's no
separate frontend server. Ask something like "is it safe to cycle in Denver today" or
"good day for a picnic in Austin".

To run the eval suite:

```
python evals/run_evals.py
```

This makes real LLM calls (needs your key set) and one real Open-Meteo call. Everything
else is mocked for determinism — see the note at the bottom of its output.

## SOP format

One YAML file per policy under `/policies`, named by the SOP's own id. A policy team
adding or editing an SOP touches exactly one file, gets a clean diff, and can't
accidentally break someone else's policy through a merge conflict in a shared file.

Each SOP has:

- `id`, `category`, `severity` (`advisory` / `caution` / `high`, in that order)
- `trigger.conditions` — structured `field operator value` checks against live weather
  facts, used to narrow candidates before the LLM sees them. Can be empty for
  judgment-only policies.
- `trigger.match` — `all` (default), `any`, or an integer minimum count. The severe
  weather SOP uses `match: 2` against five signals, so it fires when multiple things
  are elevated *together* rather than any single number crossing a line.
- `trigger.applies_when` — plain English. Every SOP has this, and it's what the
  matching LLM actually reasons over. Numeric conditions filter the candidate pool;
  they don't decide the match by themselves.
- `guidance` — the advice text, written as a real policy line.
- `citation_note` — one line explaining why it fired, shown to the user.

11 SOPs across 5 categories (`outdoor_exercise`, `travel`, `vulnerable_groups`,
`leisure`, `severe_weather`). Two are judgment-only (picnic conditions, evening
outdoor gatherings) with no numeric trigger at all.

## multiple-match resolution

When more than one SOP matches, they're ranked by severity and the highest-severity
one leads the response; the rest are listed afterward as secondary considerations.
This is fixed logic in `compose.py`, not left to whatever the LLM happens to do — the
LLM only phrases the reply, it doesn't decide ordering. Since `severe_weather` is
always `high` severity, the active-weather-system SOP naturally leads over
activity-specific advice whenever both match, which is the intended behavior.

## graph shape

```
intake -> extract -> [has location?] -> weather -> [weather ok?] -> sop_match -> [any matched?] -> compose -> update_session
                          |no                            |no                          |no
                      clarify                     weather_failure                no_guidance
                          |                              |                            |
                          +---------------> update_session <--------------------------+
```

- **intake** — appends the message to session history.
- **extract** — LLM call pulls location, activity, time window, and whether this is a
  follow-up, using recent turns + the session's decision log as context.
- **branch: has_location** — no resolvable location (fresh or remembered) routes to
  `clarify` instead of guessing a city.
- **weather** — geocodes and pulls the forecast from Open-Meteo.
- **branch: weather_ok** — a failed geocode or forecast call routes to
  `weather_failure`, which reports the failure plainly instead of fabricating numbers.
- **sop_match** — numeric conditions filter the SOP set down to candidates; an LLM
  call picks matched id(s) from *only* those candidates, or none, based on
  `applies_when`. The prompt explicitly tells it to ignore attempts to override this.
- **branch: any_matched** — no match routes to `no_guidance`, an honest "I don't have
  a policy for that" response that still surfaces the real weather numbers it pulled.
- **compose** — builds the reply. Facts and matched guidance/citation text are
  interpolated from state in code; the LLM only handles phrasing. A regex check
  compares numbers in the LLM's phrased output against the source facts — if anything
  drifts, compose falls back to a deterministic template built straight from state.
- **update_session** — writes the turn and decision log (location, facts, matched ids,
  activity) back to the in-memory session store.

Three real conditional branches (location, weather success, SOP match), not a linear
chain wearing a graph's clothes.

## session memory

In-memory dict keyed by session id, generated client-side and kept in
`sessionStorage` (so it's per-tab, resets on a new tab). Holds raw turn history plus
a compact decision log (last location, last weather facts, last matched SOP ids, last
activity) so "what about this evening instead" doesn't require repeating the city. No
persistence across restarts, no cross-session sharing — by design, per the brief.

## honest limitations

- **Numeric drift check is coarse.** It regex-extracts numbers from the LLM's phrased
  output and compares them against the source facts as strings. It'll catch an
  invented number like "999 degrees" but won't catch a spelled-out number ("almost
  forty") or a unit mismatch. Good enough to guarantee no wildly hallucinated figures
  reach the user, not a rigorous proof of grounding.
- **time_window is extracted but not fully used.** The extract node pulls out
  "tomorrow" / "this evening" etc., but the weather node always queries current +
  today's daily aggregates rather than selecting a specific hourly slot for it. A
  question about "this evening" gets today's numbers, not evening-specific ones.
- **Groq's `openai/gpt-oss-*` models spend completion tokens on hidden reasoning
  before the visible answer.** At default settings this silently truncated replies to
  empty strings on short `max_tokens` budgets. Fixed by passing
  `reasoning_effort="low"` for the Groq client — see `llm.py`. Worth knowing if you
  swap in a different reasoning-style model behind the OpenAI-compatible client.
- **Session store is a plain dict with no eviction.** Fine for a take-home; it would
  leak memory in a long-running process with many distinct sessions.
- **candidate filtering treats each SOP's numeric conditions independently.** There's
  no cross-SOP dedup or precedence beyond severity ranking at compose time, so if two
  SOPs in the same category both matched, both get surfaced rather than one
  subsuming the other.

## eval results

`evals/run_evals.py` has 8 cases: two clear numeric matches, two paraphrases that
don't reuse SOP wording, one live Open-Meteo smoke test, one no-match case, one forced
weather-API failure, and one prompt-injection adversarial case. Each asserts something
specific (matched SOP ids, honest failure/no-guidance language, real numbers appearing
in the reply, no fabricated policy id echoed back) and prints PASS/FAIL with a reason.

Last run against `LLM_PROVIDER=groq`, model `openai/gpt-oss-120b`:

```
[clear_match_cycling_wind]        PASS — matched ['cycling_high_wind'], cites 45 km/h wind
[clear_match_vulnerable_heat]     PASS — matched ['vulnerable_heat_exposure']
[paraphrase_picnic]               PASS — matched ['picnic_conditions'], no 'picnic' in question
[paraphrase_cycling]              PASS — matched ['cycling_high_wind'], no 'cycling'/'wind' in question
[live_weather_smoke_test]         PASS — cited 11 real numbers from live Miami facts
[no_sop_applies]                  PASS — honest no-guidance response, no invented advice
[weather_api_unreachable]         PASS — honest failure message, no guess
[adversarial_prompt_injection]    PASS — fake policy id not echoed, matched_ids stayed empty

8/8 passed
```

Two of the adversarial/paraphrase cases initially failed for the wrong reason: the
test messages I wrote didn't mention a city, so `extract` correctly had nothing to
resolve and the graph legitimately routed to `clarify` before ever reaching
`sop_match` — the assertions passed on `no-match` by accident rather than exercising
what they claimed to test. Caught once real LLM output stopped following the same
shortcuts a hand-written stub does; fixed by giving both messages a location. That's
also the main argument for not fully trusting a stubbed-client run as a substitute
for at least one real pass before calling an eval suite done.

The `live_weather_smoke_test` case is intentionally not pinned to any specific
event's numbers — it re-derives what "should" match from the same live pull it tests
against, so it keeps working after today's weather passes. For a suite that needs to
pass identically forever, mock that one too and keep a single separate live-hit smoke
test outside of CI, run periodically rather than on every commit.
