// Page v0 (#57): replay one recorded run in the Execution Explorer (D15).
//
// Everything shown is driven by two files:
//   - the recording (../recordings/scenario-06.json): one event per step, made
//     by record.py from a real run. The map, the four questions, the timeline
//     and the inspector are all read from its events.
//   - steps.json: each step's title and explanation, generated from
//     docs/STEPS.md by build_steps.py. The page writes no explanations of its own.
// The scenario's name comes from ../scenarios/scenarios.json.
//
// Claude's own words (its text, thinking, final answer, and the grader's reply)
// appear only under "Claude's response". Everywhere else they're replaced with
// a pointer to that tab.
//
// How it fits together: load() fetches the files, then show(i) renders event i.
// Play calls show(i + 1) every 2.5 s (1.25 s at 2×) until the last event.

"use strict";

const RECORDING = "../recordings/scenario-06.json";
const STEPS = "steps.json";
const SCENARIOS = "../scenarios/scenarios.json";
const STEP_MS = 2500;          // at 1×, per the issue
const SEE_RESPONSE = "‹Claude's words: see the Claude's response tab›";

const WHO = { python: "Python", claude: "Claude", tool: "Tool" };

const state = { trace: null, steps: {}, events: [], i: 0, playing: false, speed: 1, timer: null, tab: "state" };

// --- small helpers --------------------------------------------------------------

// Build a DOM element: el("span", {class: "x"}, "text", child, ...). Text is
// always set as text, never as HTML, so nothing in a recording can inject markup.
function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "style") node.style.cssText = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : String(c));
  }
  return node;
}

const $ = (id) => document.getElementById(id);
const shortId = (id) => (id && id.length > 12 ? id.slice(0, 10) + "…" : id || "");
const truncate = (s, n) => (s.length > n ? s.slice(0, n).trimEnd() + "…" : s);
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const spaced = (name) => name.replace(/_/g, " ");
const errorType = (text) => String(text).split(":")[0];

// The fault event: where faults.py changed something ({fault, <what>: {real, injected}}).
const isFault = (e) => !!(e.payload && typeof e.payload === "object" && "fault" in e.payload);
const isRule = (e) => !!(e.payload && typeof e.payload === "object" && "rule" in e.payload && "outcome" in e.payload);
const isErrorResult = (e) => e.crossing && e.crossing.kind === "tool_result" && e.payload && e.payload.is_error;
const isBad = (e) => (e.guard && e.guard.caught) || isErrorResult(e) || isFault(e);

function faultChange(e) {
  const key = Object.keys(e.payload).find((k) => k !== "fault");
  return key ? { key, ...e.payload[key] } : { key: null };
}

// --- what each event says, in a few words ------------------------------------------

function crossingShort(e) {
  const p = e.payload || {};
  switch (e.crossing.kind) {
    case "api_request": return "request";
    case "api_response": return p.stop_reason || "reply";
    case "tool_call": return p.tool;
    case "tool_result": return p.is_error ? "error" : "result";
    case "inner_api_request": return "grade this";
    case "inner_api_response": return "reply";
    default: return e.crossing.kind;
  }
}

// One line for the timeline.
function stepLabel(e) {
  if (e.crossing) return `${WHO[e.crossing.from]} → ${WHO[e.crossing.to]}: ${crossingShort(e)}`;
  if (e.guard) return `${e.guard.caught ? "Caught" : "Check"}: ${spaced(e.guard.name)}`;
  if (isRule(e)) return `Rule: ${spaced(e.payload.rule)} · ${e.payload.outcome}`;
  if (isFault(e)) {
    const change = faultChange(e);
    return `Simulated failure: ${change.key ? spaced(change.key) + " replaced" : e.payload.fault}`;
  }
  const step = state.steps[e.step_id];
  return step ? step.title : e.step_id;
}

// The tag drawn on an arrow for a crossing.
function arrowLabel(e) {
  const p = e.payload || {};
  switch (e.crossing.kind) {
    case "api_request":
      return `request · ${plural((p.messages || []).length, "message")}`;
    case "api_response": {
      const uses = (p.content || []).filter((b) => b.type === "tool_use");
      if (uses.length) return [p.stop_reason, ...uses.map((b) => `${shortId(b.id)} · ${b.name}`)].join(" · ");
      return `${p.stop_reason} · final answer`;
    }
    case "tool_call": {
      const [k, v] = Object.entries(p.arguments || {})[0] || [];
      return k ? `${p.tool}(${k}="${truncate(String(v), 9)}")` : `${p.tool}()`;
    }
    case "tool_result":
      if (p.is_error) return `${errorType(p.content)} · ${shortId(p.tool_use_id)}`;
      try { return `result · ${JSON.parse(p.content).rating}`; } catch { return "result"; }
    case "inner_api_request":
      return "grade this";
    case "inner_api_response":
      return `↩ reply · ${p.stop_reason}`;
    default:
      return e.crossing.kind;
  }
}

// What the executing component holds at this step ("Has ·").
function hasText(e) {
  const p = e.payload || {};
  if (e.guard) return `the check ${e.guard.checked}`;
  if (isRule(e)) return `the rule ${p.checked}`;
  if (isFault(e)) return "a broken grader reply, put there on purpose";
  if (e.crossing) {
    switch (e.crossing.kind) {
      case "api_request": return `${plural((p.messages || []).length, "message")} to send`;
      case "api_response": return `Claude's reply · stop_reason ${p.stop_reason}`;
      case "tool_call": return `${p.tool} and the arguments Claude filled in`;
      case "tool_result": return p.is_error ? `the error from ${p.tool}` : `${p.tool}'s result`;
      case "inner_api_request": return "the rubric and the job";
      case "inner_api_response": return "the grader's reply";
    }
  }
  if (e.messages_after) return `messages[] · ${plural(e.messages_after.length, "message")}`;
  if ("job_text" in p) return "the job posting";
  if ("ended_by" in p) return `the final answer · ended by ${p.ended_by}`;
  return "—";
}

// What led to this step ("Because ·"): a caught guard's message, the fault, or the step before.
function becauseText(i) {
  const e = state.events[i];
  if (e.guard && e.guard.caught) return { text: e.guard.message, bad: true };
  if (isFault(e)) return { text: `a simulated failure (${e.payload.fault})`, bad: true };
  if (e.injected) {
    const caught = lastInPass(i, (x) => x.guard && x.guard.caught);
    if (caught) return { text: caught.guard.message, bad: true };
  }
  if (i === 0) return { text: "a job posting was handed to the agent" };
  return { text: stepLabel(state.events[i - 1]) };
}

function lastInPass(i, test) {
  for (let j = i; j >= 0 && state.events[j].pass === state.events[i].pass; j--) {
    if (test(state.events[j])) return state.events[j];
  }
  return null;
}

// --- Claude's own words: shown only in "Claude's response" --------------------------

function claudeWords(e) {
  const p = e.payload;
  if (!p || typeof p !== "object") return null;
  if (e.actor === "claude" && Array.isArray(p.content)) return { blocks: p.content };
  if (e.step_id === "answer_returned" && typeof p.text === "string") return { final: p.text };
  if (isFault(e)) {
    const change = faultChange(e);
    if (typeof change.real === "string") return { replaced: change.real, injected: change.injected };
  }
  return null;
}

// The payload with Claude's words swapped for a pointer to that tab.
function payloadView(e) {
  if (e.payload === null || e.payload === undefined) return null;
  const p = JSON.parse(JSON.stringify(e.payload));
  if (e.actor === "claude" && Array.isArray(p.content)) {
    p.content = p.content.map((b) => (b.type === "tool_use" ? b : { type: b.type, [b.type]: SEE_RESPONSE }));
  }
  if (e.step_id === "answer_returned" && typeof p.text === "string") p.text = SEE_RESPONSE;
  if (isFault(e)) {
    const key = faultChange(e).key;
    if (key && typeof p[key].real === "string") p[key].real = SEE_RESPONSE;
  }
  if (Array.isArray(p.messages)) {
    p.messages = p.messages.map((m) => (m.role === "assistant" && Array.isArray(m.content)
      ? { ...m, content: m.content.map((b) => (b.type === "text" || b.type === "thinking" ? { type: b.type, [b.type]: SEE_RESPONSE } : b)) }
      : m));
  }
  return p;
}

// --- messages[] -------------------------------------------------------------------

function messageLine(m, n) {
  if (typeof m.content === "string") {
    const what = m.content.startsWith("Evaluate this job posting") ? "job posting" : "text";
    return { text: `[${n}] ${m.role} · ${what}`, bad: false };
  }
  const parts = m.content.map((b) => {
    if (b.type === "tool_use") return `tool_use ${shortId(b.id)}`;
    if (b.type === "tool_result") return `tool_result ${shortId(b.tool_use_id)}${b.is_error ? " · is_error" : ""}`;
    return b.type;
  });
  const bad = m.content.some((b) => b.type === "tool_result" && b.is_error);
  return { text: `[${n}] ${m.role} · ${parts.join(" + ")}`, bad };
}

// The conversation as it stood at event i (the latest messages_after so far).
function messagesAt(i) {
  for (let j = i; j >= 0; j--) if (state.events[j].messages_after) return state.events[j].messages_after;
  return null;
}

// --- rendering ------------------------------------------------------------------------

function show(i) {
  state.i = Math.max(0, Math.min(i, state.events.length - 1));
  const e = state.events[state.i];
  renderMap(e);
  renderFacts();
  renderTimeline();
  renderExplanation(e);
  renderTab();
  $("back").disabled = state.i === 0;
  $("next").disabled = state.i === state.events.length - 1;
}

function renderMap(e) {
  const i = state.i;
  const events = state.events;

  // API calls so far.
  let main = 0, inner = 0;
  for (let j = 0; j <= i; j++) {
    const k = events[j].crossing && events[j].crossing.kind;
    if (k === "api_request") main++;
    if (k === "inner_api_request") inner++;
  }
  $("map-status").textContent = (e.pass === 0 ? "Before the loop" : `Pass ${e.pass}`)
    + ` · API calls so far: ${main + inner} (${main} main, ${inner} inside the tool)`;

  // Which component is executing.
  for (const who of ["claude", "python", "tool"]) $(`box-${who}`).classList.toggle("active", e.actor === who);

  // The latest crossing of each kind in this pass, the fault if there was one,
  // and the caught guard if there was one.
  const latest = {};
  let fault = null, caught = null;
  for (let j = i; j >= 0 && events[j].pass === e.pass; j--) {
    const x = events[j];
    if (x.crossing && !latest[x.crossing.kind]) latest[x.crossing.kind] = x;
    if (!fault && isFault(x)) fault = x;
    if (!caught && x.guard && x.guard.caught) caught = x;
  }
  const next = events[i + 1];

  // The four arrows between the boxes.
  for (const kind of ["api_request", "api_response", "tool_call", "tool_result"]) {
    const node = $(`arrow-${kind}`);
    let cls = "", label = null;
    if (next && next.crossing && next.crossing.kind === kind && next.pass === e.pass) {
      cls = "preview"; label = `next · ${arrowLabel(next)}`;
      if (isErrorResult(next)) cls += " error";
    } else if (latest[kind]) {
      cls = latest[kind] === e ? "current" : "done";
      label = arrowLabel(latest[kind]);
      if (isErrorResult(latest[kind])) cls += " error";
    }
    node.className = `arrow ${cls}`;
    const line = el("div", { class: "line" },
      node.dataset.dir === "left" ? el("span", { class: "head" }) : null,
      el("span", { class: "shaft" }),
      node.dataset.dir === "right" ? el("span", { class: "head" }) : null);
    // Requests: tag above the line; replies: tag below (as in the mockup).
    const tag = label ? el("span", { class: "tag" }, label) : null;
    const goesOut = kind === "api_request" || kind === "tool_call";
    node.replaceChildren(...(goesOut ? [tag, line] : [line, tag]).filter(Boolean));
  }

  // The dashed path underneath: evaluate_job's own call to Claude.
  const innerNow = e.crossing && e.crossing.kind.startsWith("inner_");
  const innerSeen = latest.inner_api_request || latest.inner_api_response;
  const innerBox = $("inner");
  innerBox.className = "inner" + (fault ? " error" : innerNow ? " current" : innerSeen ? " done" : "");
  const tag = $("inner-tag");
  if (fault) {
    tag.hidden = false;
    tag.className = "tag error";
    tag.textContent = "↩ broken JSON · Simulated failure";
  } else if (latest.inner_api_response) {
    tag.hidden = false;
    tag.className = "tag" + (latest.inner_api_response === e ? " current" : "");
    tag.textContent = arrowLabel(latest.inner_api_response);
  } else {
    tag.hidden = true;
  }

  // Box statuses.
  const toolCall = latest.tool_call, toolResult = latest.tool_result;
  setStatus("claude", e.actor === "claude" ? "replying" : "waiting");
  setStatus("python", e.actor === "python" ? "executing" : "waiting");
  if (toolResult && toolResult.payload.is_error) setStatus("tool", `${toolResult.payload.tool} failed`, true);
  else if (caught && caught.parent === null && toolCall) setStatus("tool", `${toolCall.payload.tool} failed`, true);
  else if (toolCall && !toolResult) setStatus("tool", `running ${toolCall.payload.tool}`);
  else if (toolResult) setStatus("tool", `${toolResult.payload.tool} done`);
  else setStatus("tool", "idle");

  // Guard badges: the one checking now is lit; a caught one stays lit (red)
  // for the rest of its pass.
  for (const badge of $("guards").children) {
    const name = badge.dataset.guard;
    badge.className = "guard"
      + (caught && caught.guard.name === name ? " caught" : "")
      + (e.guard && e.guard.name === name && !e.guard.caught ? " checking" : "");
  }
}

function setStatus(who, text, failed) {
  const node = $(`status-${who}`);
  node.textContent = text;
  node.classList.toggle("failed", !!failed);
}

function renderFacts() {
  const i = state.i, e = state.events[i];
  $("fact-executing").replaceChildren(el("span", { class: `who-${e.actor}` }, WHO[e.actor]));
  $("fact-has").textContent = hasText(e);
  const because = becauseText(i);
  $("fact-because").replaceChildren(el("span", { class: because.bad ? "bad" : null }, because.text));
  const next = state.events[i + 1];
  $("fact-next").textContent = next ? stepLabel(next) : "the run ends";
}

function renderTimeline() {
  const list = $("timeline");
  if (!list.children.length) buildTimeline(list);
  for (const row of list.querySelectorAll(".tl-step")) {
    const j = Number(row.dataset.index);
    row.classList.toggle("current", j === state.i);
    row.classList.toggle("future", j > state.i);
    row.setAttribute("aria-current", j === state.i ? "step" : "false");
  }
  // Keep the current step in view, scrolling only the timeline (not the page).
  const row = list.querySelector(".tl-step.current");
  if (row) {
    const top = row.offsetTop - list.offsetTop;
    if (top < list.scrollTop || top + row.offsetHeight > list.scrollTop + list.clientHeight) {
      list.scrollTop = top - list.clientHeight / 2;
    }
  }
}

function buildTimeline(list) {
  let pass = null;
  state.events.forEach((e, j) => {
    if (e.pass !== pass) {
      pass = e.pass;
      list.append(el("div", { class: "tl-pass" }, pass === 0 ? "START" : `PASS ${pass}`));
    }
    const color = { python: "var(--green)", claude: "var(--violet)", tool: "var(--orange)" }[e.actor];
    const row = el("button", {
      type: "button", class: "tl-step" + (e.parent ? " nested" : "") + (isBad(e) ? " bad" : ""),
      "data-index": j, style: `--c: ${color}`, title: `${e.id} · ${e.step_id}`,
    }, el("span", { class: "dot" }), el("span", { class: "lbl" }, stepLabel(e)),
    e.injected ? el("span", { class: "sim-mark", title: "Simulated failure" }, "simulated") : null);
    row.addEventListener("click", () => { show(j); restartTimer(); });
    list.append(row);
  });
}

function renderExplanation(e) {
  const step = state.steps[e.step_id];
  $("step-num").textContent = step ? `STEP ${step.number} · ${e.step_id}` : e.step_id;
  $("step-title").textContent = step ? step.title : e.step_id;
  // `code` in STEPS.md is shown as code; everything else as plain text.
  const parts = (step ? step.text : "No explanation in docs/STEPS.md for this step.").split("`");
  $("step-text").replaceChildren(...parts.map((part, n) => (n % 2 ? el("code", {}, part) : part)));
  const sim = $("sim");
  sim.hidden = !e.injected;
  sim.textContent = state.trace.fault ? `Simulated failure · ${state.trace.fault}` : "Simulated failure";
}

// --- inspector tabs ------------------------------------------------------------------

function renderTab() {
  const e = state.events[state.i];
  for (const b of $("tabs").children) {
    b.setAttribute("aria-selected", String(b.dataset.tab === state.tab));
    if (b.dataset.tab === "claude") b.classList.toggle("has", !!claudeWords(e));
  }
  const body = $("tab-body");
  const render = { state: stateTab, code: codeTab, payload: payloadTab, claude: claudeTab }[state.tab];
  body.replaceChildren(...[render(e)].flat());
}

function stateTab(e) {
  const before = e.messages_before || messagesAt(state.i);
  const after = e.messages_after || before;
  if (!after) return el("p", { class: "note" }, "messages[] doesn't exist yet at this step.");
  const grew = after.length - (before ? before.length : 0);
  const column = (title, list, count, isAfter) => el("div", { class: "state-col" },
    el("div", { class: "state-head" }, el("span", {}, `${title} · messages[]`),
      el("span", { class: isAfter && grew ? "grew" : null }, isAfter && grew ? `${count} · +${grew}` : count)),
    (list || []).map((m, n) => {
      const line = messageLine(m, n);
      const added = isAfter && n >= after.length - grew && grew > 0;
      return el("div", { class: "msg" + (added ? " added" : "") + (added && line.bad ? " bad" : "") }, line.text);
    }));
  return el("div", { class: "state" },
    column("BEFORE", before, before ? before.length : 0, false),
    el("div", { class: "state-arrow", "aria-hidden": "true" }, "→"),
    column("AFTER", after, after.length, true));
}

function codeTab(e) {
  if (!e.code) return el("p", { class: "note" }, "No code runs here: this is Claude deciding, on Anthropic's servers.");
  const first = e.code.line;
  return [
    el("div", { class: "where" }, `${e.code.file}:${first} · marker # STEP: ${e.code.marker} · commit ${state.trace.git_commit}`),
    el("pre", {}, e.code.lines.map((text, n) => [el("span", { class: "ln" }, String(first + n)), text, "\n"])),
  ];
}

function payloadTab(e) {
  const out = [];
  const p = payloadView(e);
  out.push(el("div", { class: "sub" }, "PAYLOAD"));
  out.push(p === null ? el("p", { class: "note" }, "No payload at this step.") : el("pre", {}, JSON.stringify(p, null, 2)));
  if (e.guard) out.push(el("div", { class: "sub" }, "GUARD"), el("pre", {}, JSON.stringify(e.guard, null, 2)));
  if (e.tokens) out.push(el("div", { class: "sub" }, "TOKENS"), el("pre", {}, JSON.stringify(e.tokens, null, 2)));
  out.push(el("div", { class: "sub" }, "EVENT"),
    el("pre", {}, JSON.stringify({ id: e.id, pass: e.pass, step_id: e.step_id, actor: e.actor,
      crossing: e.crossing, parent: e.parent, injected: e.injected }, null, 2)));
  return out;
}

function claudeTab(e) {
  const words = claudeWords(e);
  if (!words) return el("p", { class: "note" }, "Claude didn't produce anything at this step.");
  if (words.final) return [el("div", { class: "sub" }, "CLAUDE'S FINAL ANSWER, RETURNED BY PYTHON"), el("div", { class: "words" }, words.final)];
  if (words.replaced !== undefined) {
    return [
      el("div", { class: "sub" }, "THE GRADER'S REAL REPLY (KEPT IN THE RECORDING)"),
      el("div", { class: "words" }, words.replaced),
      el("p", { class: "note", style: "margin-top: 10px" }, `Simulated failure: the code was handed this instead: ${JSON.stringify(words.injected)}`),
    ];
  }
  const who = e.parent ? "THE GRADER (evaluate_job's own call)" : "CLAUDE (main conversation)";
  const out = [el("div", { class: "sub" }, `${who} · stop_reason ${e.payload.stop_reason}`)];
  for (const b of words.blocks) {
    if (b.type === "text") out.push(el("div", { class: "sub" }, "TEXT"), el("div", { class: "words" }, b.text));
    else if (b.type === "thinking") {
      out.push(el("div", { class: "sub" }, "THINKING"),
        el("div", { class: "words" + (b.thinking ? "" : " empty") }, b.thinking || "(empty: the API returned no thinking text)"));
    } else if (b.type === "tool_use") {
      out.push(el("div", { class: "sub" }, `TOOL REQUEST · ${b.name} · ${b.id}`), el("pre", {}, JSON.stringify(b.input, null, 2)));
    } else out.push(el("div", { class: "sub" }, b.type.toUpperCase()), el("pre", {}, JSON.stringify(b, null, 2)));
  }
  return out;
}

// --- playback -------------------------------------------------------------------------

function setPlaying(on) {
  state.playing = on && state.i < state.events.length - 1;
  $("play").textContent = state.playing ? "❚❚ Pause" : "▶ Play";
  restartTimer();
}

function restartTimer() {
  clearTimeout(state.timer);
  if (!state.playing) return;
  state.timer = setTimeout(() => {
    show(state.i + 1);
    setPlaying(state.i < state.events.length - 1);
  }, STEP_MS / state.speed);
}

function wireControls() {
  $("play").addEventListener("click", () => setPlaying(!state.playing));
  $("next").addEventListener("click", () => { show(state.i + 1); restartTimer(); });
  $("back").addEventListener("click", () => { show(state.i - 1); restartTimer(); });
  $("speed").addEventListener("click", () => {
    state.speed = state.speed === 1 ? 2 : 1;
    $("speed").textContent = `${state.speed}×`;
    restartTimer();
  });
  for (const b of $("tabs").children) {
    b.addEventListener("click", () => { state.tab = b.dataset.tab; renderTab(); });
  }
  document.addEventListener("keydown", (ev) => {
    if (ev.target.closest && ev.target.closest("button") && ev.key === " ") return;
    if (ev.key === "ArrowRight") { show(state.i + 1); restartTimer(); }
    else if (ev.key === "ArrowLeft") { show(state.i - 1); restartTimer(); }
    else if (ev.key === " ") { ev.preventDefault(); setPlaying(!state.playing); }
  });
}

// --- start ----------------------------------------------------------------------------

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

async function load() {
  try {
    const [trace, steps] = await Promise.all([getJSON(RECORDING), getJSON(STEPS)]);
    const scenarios = await getJSON(SCENARIOS).catch(() => []);
    state.trace = trace;
    state.events = trace.events;
    state.steps = steps.steps;

    const number = Number(String(trace.scenario).replace(/\D/g, ""));
    const scenario = scenarios.find((s) => s.id === number);
    $("eyebrow").textContent = `SCENARIO ${number || trace.scenario}`
      + (scenario ? ` · ${scenario.name.toUpperCase()}` : "")
      + (trace.fault ? " · SIMULATED FAILURE" : "");

    // One badge per guard this run checks, in the order they first appear.
    const names = [...new Set(trace.events.filter((e) => e.guard).map((e) => e.guard.name))];
    $("guards").replaceChildren(...names.map((n) => el("span", { class: "guard", "data-guard": n, title: n }, spaced(n))));

    wireControls();
    show(0);
    window.explorer = { show, state, setPlaying };   // for checking the page by hand from the console
  } catch (err) {
    const box = $("load-error");
    box.hidden = false;
    box.textContent = `Couldn't load the run (${err.message}). Serve job-evaluator/ with `
      + "`python -m http.server` and open /site/.";
  }
}

load();
