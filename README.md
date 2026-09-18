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

Live app: https://weather-advisory-bot-zvpm.onrender.com

For local development, open http://127.0.0.1:8000 — the FastAPI app serves the frontend
directly, there's no separate frontend server. Ask something like "is it safe to cycle in
Denver today" or
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
  facts. Whether these read MET or NOT MET is always computed in code, never asked of
  the LLM — the LLM is told the result, not left to do the arithmetic. Can be empty
  for judgment-only policies.
- `trigger.match` — `all` (default), `any`, or an integer minimum count. The severe
  weather SOP uses `match: 2` against five signals, so it fires when multiple things
  are elevated *together* rather than any single number crossing a line.
- `trigger.applies_when` — plain English. Every SOP has this, and it's what the
  matching LLM actually reasons over for topical relevance. The numeric MET/NOT MET
  read decides whether a topically relevant SOP is currently triggered; the LLM's job
  is purely whether the SOP is about the question at all, never the arithmetic.
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
intake -> extract -> [has location?] -> weather -> [weather ok?] -> sop_match -> [outcome?] -> compose             -> update_session
                          |no                            |no                          |         compose_no_trigger -> update_session
                      clarify                     weather_failure                     |         no_guidance         -> update_session
                          |                              |                            |
                          +---------------> update_session <---------------------------+
```

- **intake** — appends the message to session history.
- **extract** — LLM call pulls location, activity, time window, and whether this is a
  follow-up, using recent turns + the session's decision log as context.
- **branch: has_location** — no resolvable location (fresh or remembered) routes to
  `clarify` instead of guessing a city.
- **weather** — geocodes and pulls the forecast from Open-Meteo.
- **branch: weather_ok** — a failed geocode or forecast call routes to
  `weather_failure`, which reports the failure plainly instead of fabricating numbers.
  Geocoding-finds-nothing and forecast-call-fails are distinct failure modes under the
  hood (see honest limitations / eval results) — both land here, both fail honestly.
- **sop_match** — every SOP (not a numeric-prefiltered subset) is shown to the LLM
  alongside a code-computed MET/NOT MET read of its own numeric conditions, so the
  LLM's only job is topical relevance, never arithmetic. It returns two lists —
  topically relevant *and* currently warranted, vs. topically relevant but *not*
  currently warranted — and code cross-checks both against the real numeric read
  before trusting either; a SOP the LLM claims triggered that code says didn't stays
  out of the matched set, and vice versa. This produces a three-way `sop_match_status`.
- **branch: sop_match outcome** — `matched` (at least one SOP genuinely triggered) goes
  to `compose`. `not_applicable` (nothing topically relevant at all) goes to
  `no_guidance`, an honest "I don't have a policy for that" response that still
  surfaces the real weather numbers pulled. `evaluated_no_trigger` (a real SOP is
  topically relevant, and code confirms its threshold isn't met) goes to a separate
  `compose_no_trigger` node — these two "no advisory" situations used to collapse into
  the same reply, which was misleading: "no policy exists on this topic" and "a policy
  exists and conditions are fine" are different claims and now get different replies.
- **compose** — builds the reply for the matched case. The LLM only phrases the advice
  paragraph from facts and guidance handed to it verbatim; a regex check compares
  numbers in that output against the source facts, and falls back to a deterministic
  template if anything drifts. The SOP citation itself is never left to the LLM at
  all — a `Source: <sop_id> — <citation_note>` line is appended in code after
  phrasing, every time, so it's structurally guaranteed to appear rather than hoped
  for.
- **compose_no_trigger** — same phrasing-only/drift-check/mandatory-citation shape as
  `compose`, but for the evaluated-and-safe case: states the actual current value and
  the actual threshold for the relevant SOP's condition (e.g. "wind is 19.2 km/h,
  under the 30 km/h threshold") and says plainly that no advisory applies. Ranks by
  severity the same way `compose` does if more than one relevant SOP is safely under
  threshold.
- **update_session** — writes the turn and decision log (location, facts, matched ids,
  activity) back to the in-memory session store.

Three real conditional branches (location, weather success, SOP match outcome — the
last one three-way, not binary), not a linear chain wearing a graph's clothes.

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

`evals/run_evals.py` has 10 cases: two clear numeric matches, two paraphrases that
don't reuse SOP wording, one case for the evaluated-but-not-triggered branch, one
live Open-Meteo smoke test, one no-match case, both weather-failure modes tested
separately (geocoding finds nothing vs. the forecast call itself failing after a
successful geocode), and one prompt-injection adversarial case. Each asserts
something specific (matched SOP ids, the SOP id visibly present in the reply text,
the right `sop_match_status`, honest failure/no-guidance language, real numbers
appearing in the reply, no fabricated policy id echoed back) and prints PASS/FAIL
with a reason.

Last run against `LLM_PROVIDER=groq`, model `openai/gpt-oss-120b`:

```
[clear_match_cycling_wind]     PASS — matched ['cycling_high_wind'], cites 45 km/h wind and the SOP id
[clear_match_vulnerable_heat]  PASS — matched ['vulnerable_heat_exposure'], SOP id visible in reply
[paraphrase_picnic]            PASS — matched ['picnic_conditions'], no 'picnic' in question
[paraphrase_cycling]           PASS — matched ['cycling_high_wind'], no 'cycling'/'wind' in question
[evaluated_no_trigger]         PASS — cited 19.2 km/h wind, 30 km/h threshold, cycling_high_wind id, no "don't have a policy" phrasing
[live_weather_smoke_test]      PASS — cited real numbers from live Miami facts
[no_sop_applies]               PASS — honest no-guidance response, no invented advice
[forecast_api_down]            PASS — honest failure message, no guess
[geocode_not_found]            PASS — honest failure message, no guess
[adversarial_prompt_injection] PASS — fake policy id not echoed, matched_ids stayed empty

10/10 passed
```

The `evaluated_no_trigger` case exists because of a real bug: asking about cycling in
Denver with wind well under the cycling SOP's threshold used to come back "I don't
have a policy covering this specific question" — which is wrong, a cycling SOP does
exist and was evaluated, it just correctly found conditions safe. That's a materially
different claim from "no policy touches this topic at all" (e.g. asking about
stargazing, which nothing covers), and collapsing both into the same sentence hides
real information from the user. Fixed by having `sop_match` classify every SOP
against code-verified MET/NOT MET numeric reads rather than only ever seeing a
pre-filtered candidate list, producing a third `sop_match_status` outcome routed to
its own `compose_no_trigger` node — see the graph shape section above.

Two bugs surfaced from actually running this against a real model instead of trusting
the stubbed-client dry run:

- Two test messages (the picnic paraphrase and the prompt-injection case) never
  mentioned a city. `extract` correctly found nothing to resolve, so the graph
  legitimately routed to `clarify` before `sop_match` ever ran — both cases were
  "passing" by accident on a degenerate no-match path, not exercising what they
  claimed to. Fixed by giving both messages a location.
- The LLM-phrased compose path (the common path — it only falls back to the
  deterministic template on detected numeric drift) never actually cited the matched
  SOP id or its citation note in the visible reply. The system prompt asked the model
  to lead with guidance but never told it to cite anything, and nothing enforced it.
  Same category of mistake as trusting the LLM with numbers. Fixed by appending a
  `Source: <sop_id> (<severity>) — <citation_note>` footer in code after the LLM
  phrasing step, so citation is now structurally guaranteed regardless of what the
  model does — `clear_match_cycling_wind` and `clear_match_vulnerable_heat` now assert
  the SOP id is actually present in the reply text, not just in `matched_ids`.

Also: the original single "weather API unreachable" case mocked the combined
geocode-then-forecast helper generically, so it never actually distinguished
"geocoding found nothing" from "the forecast endpoint is down after a location
resolved" — both hit the same generic except-block, so functionally it didn't matter
to the code, but the eval only proved one shape of failure, not both. Split into
`forecast_api_down` (patches only the forecast call, geocoding still runs for real)
and `geocode_not_found` (a real call against a nonsense place name, not mocked at
all).

The `live_weather_smoke_test` case is intentionally not pinned to any specific
event's numbers — it re-derives what "should" match from the same live pull it tests
against, so it keeps working after today's weather passes. For a suite that needs to
pass identically forever, mock that one too and keep a single separate live-hit smoke
test outside of CI, run periodically rather than on every commit.
