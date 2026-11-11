# job-evaluator — Spec

Living document. Update it in the same PR as any change to behavior, tools, or prompts.

## Purpose

Given one job posting, return a rating (STRONG / WORTH REVIEWING / IGNORE) with reasons, or flag the posting for manual review if information needed to rate it is missing.

## Criteria (current)

- STRONG: remote, $180K+ base, and builds my AI consulting practice
- WORTH REVIEWING: meets two of the three
- IGNORE: meets one or none

## Architecture

- **Outer loop (`run_agent`)** — the agent. Calls Claude with tools, dispatches tool requests, appends results, repeats until `end_turn`.
- **Inner call (inside `evaluate_job`)** — a one-off Claude call with the rubric, no tools, no loop. Its conversation is discarded after it returns.

API calls per typical run: 3 (2 outer, 1 inner).

## What the model sees (context spec)

| Call | System prompt | Tools | Messages |
|---|---|---|---|
| Outer (Claude #1) | "You help Justin triage job postings. Use the tools provided." | `evaluate_job`, `flag_for_review` | Job posting, then each tool request + result |
| Inner (Claude #2) | `RUBRIC` (criteria above + "respond with JSON only") | none | Job details assembled from the tool input |

Claude #1 never sees `RUBRIC`. Claude #2 never sees the tool descriptions or the outer conversation.

## Tools

| Tool | Use when (description given to Claude) | Inputs | Returns |
|---|---|---|---|
| `evaluate_job` | Posting has enough info to rate: company, role, location/remote, compensation | company, role_title, job_description (required); location, remote, compensation | `{rating, reasons}` |
| `flag_for_review` | Key info (compensation, remote) is missing or ambiguous | company, role_title, missing_info | `{status: "flagged", ...}` |

## Rules: prompt vs code

| Rule | Where it lives now | Where it should live |
|---|---|---|
| $180K base floor | Prompt (`RUBRIC`) | Code — deterministic (issue #6) |
| Remote required | Prompt (`RUBRIC`) | Code — deterministic (issue #6) |
| Builds consulting practice | Prompt (`RUBRIC`) | Prompt — needs judgment |

## Success criteria

- Runs end to end without error on a complete posting → rating returned
- On a posting with no compensation → flagged, not rated
- (To add with tracing) every run produces a trace showing each tool requested and its result

## Known gaps

Tracked as issues: markdown-fence parsing, multiple tool_use blocks, tool errors crash the loop, `max_tokens` not handled.
