// Page v0 (#57): replay one recorded run in the Execution Explorer (D15).
//
// Everything shown is driven by two files:
//   - the recording (../recordings/scenario-06.json): one event per step, made
//     by record.py from a real run. The map, the four questions, the timeline
//     and the inspector are all read from its events.
//   - steps.json: each step's title and explanation, and each guard check's
//     one-line explanation, generated from docs/STEPS.md by build_steps.py.
//     The page writes no step explanations of its own.
// The scenario's name comes from ../scenarios/scenarios.json.
//
// Events become page steps (buildSteps):
//   - a guard check that passes is not a step: it's attached to the step next
//     to it, and lights its badge in the Python box while that step is shown;
//   - a guard check that catches something is a step of its own;
//   - the rule events of one hard screen are one step, and evaluate_job's own
//     call to Claude (request, reply, and any simulated failure) is one step.
//
// Claude's own words (its text, thinking, final answer, and the grader's reply)
// appear only under "Claude's response". Everywhere else they're replaced with
// a pointer to that tab.
//
// How it fits together: load() fetches the files and builds the steps, then
// show(i) draws step i. Play calls show(i + 1) every 2.5 s (1.25 s at 2×).

"use strict";

const RECORDING = "../recordings/scenario-06.json";
const STEPS = "steps.json";
const SCENARIOS = "../scenarios/scenarios.json";
const STEP_MS = 2500;          // at 1×, per the issue
const SEE_RESPONSE = "‹Claude's words: see the Claude's response tab›";

const WHO = { python: "Python", claude: "Claude", tool: "Tool" };
const RULE_NAMES = { remote: "remote", comp_floor: "salary floor" };
// Step ids whose consecutive events are shown together as one step.
const GROUPED = new Set(["hard_screen", "inner_grader"]);

const state = { trace: null, text: {}, checks: {}, steps: [], i: 0, playing: false, speed: 1, timer: null, tab: "state" };

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
const listWords = (items) => (items.length < 2 ? items.join("") : items.slice(0, -1).join(", ") + " and " + items.at(-1));

const isFault = (e) => !!(e.payload && typeof e.payload === "object" && "fault" in e.payload);
const isRule = (e) => !!(e.payload && typeof e.payload === "object" && "rule" in e.payload && "outcome" in e.payload);
const isCaught = (e) => !!(e.guard && e.guard.caught);
const isPassingCheck = (e) => !!(e.guard && !e.guard.caught);
const isErrorResult = (e) => e.crossing && e.crossing.kind === "tool_result" && e.payload && e.payload.is_error;

function faultChange(e) {
  const key = Object.keys(e.payload).find((k) => k !== "fault");
  return key ? { key, ...e.payload[key] } : { key: null };
}

// --- events → page steps --------------------------------------------------------------

function buildSteps(events) {
  const steps = [];
  const checks = [];   // [event, index of the step shown before it]
  for (const e of events) {
    if (isPassingCheck(e)) { checks.push([e, steps.length - 1]); continue; }
    const last = steps.at(-1);
    if (last && GROUPED.has(e.step_id) && last.step_id === e.step_id && last.pass === e.pass
        && last.events[0].parent === e.parent) {
      last.events.push(e);
    } else {
      steps.push({ step_id: e.step_id, pass: e.pass, events: [e], checks: [] });
    }
  }
  // A passing check belongs to the step after it (e.g. the pass count, before
  // the request), except a check inside a tool, which belongs to the tool's
  // step before it (e.g. the grader's checks, after its reply).
  for (const [e, before] of checks) {
    const prev = steps[before];
    const inside = e.parent && prev && prev.events.some((x) => x.parent === e.parent);
    const target = inside ? prev : steps[before + 1] || prev;
    target.checks.push(e);
  }
  for (const s of steps) {
    const ev = s.events;
    s.first = ev[0];
    s.actor = ev[0].actor;
    s.parent = ev[0].parent;
    s.crossings = ev.filter((e) => e.crossing);
    s.kinds = new Set(s.crossings.map((e) => e.crossing.kind));
    s.fault = ev.find(isFault) || null;
    s.caught = ev.find(isCaught) || null;
    s.rules = ev.filter(isRule);
    s.injected = ev.some((e) => e.injected);
    s.bad = !!(s.fault || s.caught || ev.some(isErrorResult));
    s.before = ev.find((e) => e.messages_before)?.messages_before || null;   // ?. stops at null instead of failing
    s.after = [...ev].reverse().find((e) => e.messages_after)?.messages_after || null;
    s.code = ev.find((e) => e.code)?.code || null;
  }
  return steps;
}

const crossing = (s, kind) => s.crossings.find((e) => e.crossing.kind === kind) || null;

// --- what a step says, in plain words --------------------------------------------------

function toolName(s) {
  const e = s.events.find((x) => x.payload && x.payload.tool) || state.steps.slice(0, state.steps.indexOf(s)).reverse()
    .flatMap((x) => x.events).find((x) => x.payload && x.payload.tool);
  return e ? e.payload.tool : "the tool";
}

function rulesSummary(s) {
  return listWords(s.rules.map((r) => `${RULE_NAMES[r.payload.rule] || spaced(r.payload.rule)} ${r.payload.outcome}`));
}

function stopReplyText(p) {
  const uses = (p.content || []).filter((b) => b.type === "tool_use").map((b) => b.name);
  if (uses.length) return { verb: `asked for ${listWords(uses)}`, has: `a request to run ${listWords(uses)}` };
  if (p.stop_reason === "end_turn") return { verb: "said it's done", has: "its final answer" };
  return { verb: `stopped for a reason labelled ${spaced(p.stop_reason)}`, has: "a reply the agent doesn't handle" };
}

// One line for the timeline.
function stepLabel(s) {
  const title = state.text[s.step_id] ? state.text[s.step_id].title : s.step_id;
  if (s.caught) return title;
  if (s.kinds.has("inner_api_request") || s.kinds.has("inner_api_response")) {
    return s.fault ? "Tool → Claude: grade this (reply replaced)" : "Tool → Claude: grade this";
  }
  if (s.rules.length) return `Hard rules: ${rulesSummary(s)}`;
  const c = s.crossings[0];
  if (c) {
    const p = c.payload || {};
    const what = { api_request: "request", api_response: p.stop_reason, tool_call: p.tool,
      tool_result: p.is_error ? "error" : "result" }[c.crossing.kind] || c.crossing.kind;
    return `${WHO[c.crossing.from]} → ${WHO[c.crossing.to]}: ${what}`;
  }
  return title;
}

// "Executing ·"
function executingText(s) {
  return s.actor === "tool" ? `${toolName(s)} (a tool)` : WHO[s.actor];
}

// "Has ·": what the executing component holds at this step.
function hasText(s) {
  const tool = toolName(s);
  if (s.caught) return s.step_id === "tool_failed" ? `the error ${tool} raised` : "a problem a check caught";
  if (s.fault) return "a broken reply in place of the grader's answer";
  if (s.kinds.has("inner_api_response")) return "the grader's answer";
  if (s.rules.length) return `the results of your hard rules: ${rulesSummary(s)}`;
  const c = s.crossings[0];
  if (c) {
    const p = c.payload || {};
    switch (c.crossing.kind) {
      case "api_request": return `${plural((p.messages || []).length, "message")} to send`;
      case "api_response": return stopReplyText(p).has;
      case "tool_call": return `${p.tool} and the details Claude filled in`;
      case "tool_result": {
        if (p.is_error) return `the error from ${p.tool}`;
        try { return `${p.tool}'s rating: ${JSON.parse(p.content).rating}`; } catch { return `${p.tool}'s result`; }
      }
    }
  }
  switch (s.step_id) {
    case "agent_starts": return "the job posting";
    case "conversation_setup": return `a new conversation with ${plural(s.after.length, "message")}`;
    case "save_turn": return "Claude's request, to add to the conversation";
    case "results_back": return lastResultFailed(s) ? "the error, to add to the conversation" : "the result, to add to the conversation";
    case "answer_returned": return "Claude's final answer";
  }
  return "nothing new";
}

function lastResultFailed(s) {
  const added = s.after && s.after.at(-1);
  return !!(added && Array.isArray(added.content) && added.content.some((b) => b.type === "tool_result" && b.is_error));
}

// What a step did, in the past tense: used for the next step's "Because ·".
function doneText(s) {
  const tool = toolName(s);
  if (s.caught) return s.step_id === "tool_failed" ? `${tool} raised an error` : "a check caught a problem";
  if (s.fault) return "the grader's reply was replaced with broken text (a simulated failure)";
  if (s.kinds.has("inner_api_response")) return "the grader answered";
  if (s.rules.length) return s.rules.some((r) => r.payload.outcome === "failed") ? "one of your hard rules failed" : "your hard rules passed";
  const c = s.crossings[0];
  if (c) {
    const p = c.payload || {};
    switch (c.crossing.kind) {
      case "api_request": return "Python sent the conversation to Claude";
      case "api_response": return `Claude ${stopReplyText(p).verb}`;
      case "tool_call": return `Python called ${p.tool}`;
      case "tool_result": return p.is_error ? `${p.tool} failed` : `${p.tool} returned its result`;
    }
  }
  switch (s.step_id) {
    case "agent_starts": return "the agent started with a job posting";
    case "conversation_setup": return "Python set up the conversation";
    case "save_turn": return "Python saved Claude's request";
    case "results_back": return lastResultFailed(s) ? "Python added the error to the conversation" : "Python added the result to the conversation";
  }
  return state.text[s.step_id] ? state.text[s.step_id].title : s.step_id;
}

// "Next ·": the next step's title from STEPS.md, except a tool's result, whose
// step title ("Python runs the tool…") would read wrong at that point.
function nextText(s) {
  const result = crossing(s, "tool_result");
  if (result) return `${result.payload.tool}'s ${result.payload.is_error ? "error" : "result"} goes back to Python`;
  return state.text[s.step_id]?.title || s.step_id;
}

// "This request carries: …", built from a request's payload.
function carriesText(s) {
  const req = crossing(s, "api_request") || crossing(s, "inner_api_request");
  if (!req) return null;
  const p = req.payload || {};
  const parts = [];
  if (p.system) parts.push("the system prompt");
  const tools = p.tools || [];
  parts.push(tools.length ? `${plural(tools.length, "tool")} (${tools.join(", ")})` : "no tools");
  parts.push(plural((p.messages || []).length, "message"));
  return `This request carries: ${parts.join(", ")}.`;
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
    default:
      return e.crossing.kind;
  }
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

// The conversation as it stood at step i (the latest messages_after so far).
function messagesAt(i) {
  for (let j = i; j >= 0; j--) if (state.steps[j].after) return state.steps[j].after;
  return null;
}

// --- rendering ------------------------------------------------------------------------

function show(i) {
  state.i = Math.max(0, Math.min(i, state.steps.length - 1));
  const s = state.steps[state.i];
  renderMap(s);
  renderFacts();
  renderTimeline();
  renderExplanation(s);
  renderTab();
  $("back").disabled = state.i === 0;
  $("next").disabled = state.i === state.steps.length - 1;
}

function renderMap(s) {
  const steps = state.steps.slice(0, state.i + 1);
  const inPass = steps.filter((x) => x.pass === s.pass);

  // API calls so far.
  const count = (kind) => steps.filter((x) => x.kinds.has(kind)).length;
  const main = count("api_request"), inner = count("inner_api_request");
  $("map-status").textContent = (s.pass === 0 ? "Before the loop" : `Pass ${s.pass}`)
    + ` · API calls so far: ${main + inner} (${main} main, ${inner} inside the tool)`;

  // Which component is executing.
  for (const who of ["claude", "python", "tool"]) $(`box-${who}`).classList.toggle("active", s.actor === who);

  // The four arrows: only what's crossing at this step.
  for (const kind of ["api_request", "api_response", "tool_call", "tool_result"]) {
    const node = $(`arrow-${kind}`);
    const e = crossing(s, kind);
    node.className = "arrow" + (e ? " current" : "") + (e && isErrorResult(e) ? " error" : "");
    const line = el("div", { class: "line" },
      node.dataset.dir === "left" ? el("span", { class: "head" }) : null,
      el("span", { class: "shaft" }),
      node.dataset.dir === "right" ? el("span", { class: "head" }) : null);
    const tag = e ? el("span", { class: "tag", title: kind === "api_request" ? carriesText(s) : null }, arrowLabel(e)) : null;
    // Requests: tag above the line; replies: tag below (as in the mockup).
    const goesOut = kind === "api_request" || kind === "tool_call";
    node.replaceChildren(...(goesOut ? [tag, line] : [line, tag]).filter(Boolean));
  }

  // evaluate_job's own call to Claude: drawn only during that call.
  const innerReq = crossing(s, "inner_api_request"), innerRes = crossing(s, "inner_api_response");
  $("inner").hidden = !(innerReq || innerRes);
  if (innerReq || innerRes) {
    $("inner-req").title = carriesText(s) || "";
    const res = $("inner-res");
    res.hidden = !innerRes;
    if (s.fault) { res.className = "tag error"; res.textContent = "↩ broken JSON · Simulated failure"; }
    else if (innerRes) { res.className = "tag"; res.textContent = `↩ reply · ${innerRes.payload.stop_reason}`; }
    drawInnerPath();
  }

  // Box statuses.
  const events = inPass.flatMap((x) => x.events);
  const call = [...events].reverse().find((e) => e.crossing && e.crossing.kind === "tool_call");
  const result = [...events].reverse().find((e) => e.crossing && e.crossing.kind === "tool_result");
  const caught = [...inPass].reverse().find((x) => x.caught)?.caught || null;
  setStatus("claude", s.actor === "claude" ? "replying" : "waiting");
  setStatus("python", s.actor === "python" ? "executing" : "waiting");
  if ((result && result.payload.is_error) || (caught && caught.step_id === "tool_failed")) setStatus("tool", `${toolName(s)} failed`, true);
  else if (call && (!result || events.indexOf(result) < events.indexOf(call))) setStatus("tool", `running ${call.payload.tool}`);
  else if (result) setStatus("tool", `${result.payload.tool} done`);
  else setStatus("tool", "idle");

  // Guard badges: the checks that passed at this step light up for a moment,
  // each with its one-line explanation; a caught guard stays lit (red) for the
  // rest of its pass.
  const passed = new Set(s.checks.map((e) => e.guard.name));
  for (const badge of $("guards").children) {
    const name = badge.dataset.guard;
    badge.className = "guard" + (caught && caught.guard.name === name ? " caught" : "");
    if (passed.has(name)) {
      void badge.offsetWidth;     // restart the flash animation on every step
      badge.classList.add("checking");
    }
  }
  $("checks").replaceChildren(...s.checks.map((e) => el("div", { class: "check" },
    el("span", { class: "check-name" }, `✓ ${spaced(e.guard.name)}`), " ",
    state.checks[e.guard.name] || "")));
}

// The dashed path Tools → Python → Claude, under the boxes. It's drawn from
// where the boxes actually are, so it follows the layout at any width.
function drawInnerPath() {
  const box = $("inner"), area = $("inner-svg");
  const left = box.getBoundingClientRect().left;
  const mid = (id) => { const r = $(id).getBoundingClientRect(); return r.left + r.width / 2 - left; };
  const t = mid("box-tool"), p = mid("box-python"), c = mid("box-claude");
  const width = box.clientWidth, low = 26, r = 8;
  const leg = (from, to) => `M ${from} 2 V ${low - r} Q ${from} ${low} ${from - r} ${low} H ${to + r} Q ${to} ${low} ${to} ${low - r} V 10`;
  const head = (x) => `${x - 6},11 ${x + 6},11 ${x},1`;
  area.setAttribute("viewBox", `0 0 ${width} 34`);
  // Only numbers go into this markup (no text from the recording), so setting
  // it directly is safe; the browser parses it as SVG inside the <svg>.
  area.innerHTML = `<path class="leg" d="${leg(t, p + 10)}"/><polygon class="leg-head" points="${head(p + 10)}"/>`
    + `<path class="leg" d="${leg(p - 10, c)}"/><polygon class="leg-head" points="${head(c)}"/>`;
}

function setStatus(who, text, failed) {
  const node = $(`status-${who}`);
  node.textContent = text;
  node.classList.toggle("failed", !!failed);
}

function renderFacts() {
  const i = state.i, s = state.steps[i];
  $("fact-executing").replaceChildren(el("span", { class: `who-${s.actor}` }, executingText(s)));
  $("fact-has").textContent = hasText(s);
  const because = i === 0 ? "a job posting was handed to the agent" : doneText(state.steps[i - 1]);
  $("fact-because").replaceChildren(el("span", { class: i > 0 && state.steps[i - 1].bad ? "bad" : null }, because));
  const next = state.steps[i + 1];
  $("fact-next").textContent = next ? nextText(next) : "the run ends";
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
  state.steps.forEach((s, j) => {
    if (s.pass !== pass) {
      pass = s.pass;
      list.append(el("div", { class: "tl-pass" }, pass === 0 ? "START" : `PASS ${pass}`));
    }
    const color = { python: "var(--green)", claude: "var(--violet)", tool: "var(--orange)" }[s.actor];
    const row = el("button", {
      type: "button", class: "tl-step" + (s.parent ? " nested" : "") + (s.bad ? " bad" : ""),
      "data-index": j, style: `--c: ${color}`, title: `${s.events.map((e) => e.id).join(", ")} · ${s.step_id}`,
    }, el("span", { class: "dot" }), el("span", { class: "lbl" }, stepLabel(s)),
    s.injected ? el("span", { class: "sim-mark", title: "Simulated failure" }, "simulated") : null);
    row.addEventListener("click", () => { show(j); restartTimer(); });
    list.append(row);
  });
}

function renderExplanation(s) {
  const step = state.text[s.step_id];
  $("step-num").textContent = step ? `STEP ${step.number} · ${s.step_id}` : s.step_id;
  $("step-title").textContent = step ? step.title : s.step_id;
  // `code` in STEPS.md is shown as code; everything else as plain text.
  const parts = (step ? step.text : "No explanation in docs/STEPS.md for this step.").split("`");
  $("step-text").replaceChildren(...parts.map((part, n) => (n % 2 ? el("code", {}, part) : part)));
  const carries = carriesText(s);
  $("carries").hidden = !carries;
  $("carries-text").textContent = carries || "";
  const sim = $("sim");
  sim.hidden = !s.injected;
  sim.textContent = state.trace.fault ? `Simulated failure · ${state.trace.fault}` : "Simulated failure";
}

// --- inspector tabs ------------------------------------------------------------------

function renderTab() {
  const s = state.steps[state.i];
  for (const b of $("tabs").children) {
    const on = b.dataset.tab === state.tab;
    b.setAttribute("aria-selected", String(on));
    if (on) $("tab-desc").textContent = b.dataset.desc;
    if (b.dataset.tab === "claude") b.classList.toggle("has", s.events.some(claudeWords));
  }
  const render = { state: stateTab, code: codeTab, payload: payloadTab, claude: claudeTab }[state.tab];
  $("tab-body").replaceChildren(...[render(s)].flat());
}

function stateTab(s) {
  const before = s.before || messagesAt(state.i);
  const after = s.after || before;
  if (!after) return el("p", { class: "note" }, "There's no messages list yet at this step.");
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

function codeTab(s) {
  if (!s.code) return el("p", { class: "note" }, "No code runs here: this is Claude deciding, on Anthropic's servers.");
  const first = s.code.line;
  return [
    el("div", { class: "where" }, `${s.code.file}:${first} · marker # STEP: ${s.code.marker} · commit ${state.trace.git_commit}`),
    el("pre", {}, s.code.lines.map((text, n) => [el("span", { class: "ln" }, String(first + n)), text, "\n"])),
  ];
}

function payloadTab(s) {
  const out = [];
  for (const e of s.events) {
    const p = payloadView(e);
    const label = e.crossing ? `${WHO[e.crossing.from]} → ${WHO[e.crossing.to]} · ${e.crossing.kind}` : e.step_id;
    out.push(el("div", { class: "sub" }, `${e.id} · ${label}${e.injected ? " · simulated" : ""}`));
    if (p !== null) out.push(el("pre", {}, JSON.stringify(p, null, 2)));
    if (e.guard) out.push(el("pre", {}, JSON.stringify({ guard: e.guard }, null, 2)));
    if (e.tokens) out.push(el("pre", {}, JSON.stringify({ tokens: e.tokens }, null, 2)));
    if (p === null && !e.guard && !e.tokens) out.push(el("p", { class: "note" }, "Nothing crossed: this step changes the messages list (see State change)."));
  }
  if (s.checks.length) {
    out.push(el("div", { class: "sub" }, "CHECKS THAT PASSED AT THIS STEP"),
      el("pre", {}, JSON.stringify(s.checks.map((e) => ({ id: e.id, guard: e.guard })), null, 2)));
  }
  return out;
}

function claudeTab(s) {
  const out = [];
  for (const e of s.events) {
    const words = claudeWords(e);
    if (!words) continue;
    if (words.final) out.push(el("div", { class: "sub" }, "CLAUDE'S FINAL ANSWER, RETURNED BY PYTHON"), el("div", { class: "words" }, words.final));
    else if (words.replaced !== undefined) {
      out.push(el("div", { class: "sub" }, "THE GRADER'S REAL REPLY (KEPT IN THE RECORDING)"),
        el("div", { class: "words" }, words.replaced),
        el("p", { class: "note", style: "margin-top: 10px" }, `Simulated failure: the code was handed this instead: ${JSON.stringify(words.injected)}`));
    } else {
      const who = e.parent ? "THE GRADER (evaluate_job's own call)" : "CLAUDE (main conversation)";
      out.push(el("div", { class: "sub" }, `${who} · stop_reason ${e.payload.stop_reason}`));
      for (const b of words.blocks) {
        if (b.type === "text") out.push(el("div", { class: "sub" }, "TEXT"), el("div", { class: "words" }, b.text));
        else if (b.type === "thinking") {
          out.push(el("div", { class: "sub" }, "THINKING"),
            el("div", { class: "words" + (b.thinking ? "" : " empty") }, b.thinking || "(empty: the API returned no thinking text)"));
        } else if (b.type === "tool_use") {
          out.push(el("div", { class: "sub" }, `TOOL REQUEST · ${b.name} · ${b.id}`), el("pre", {}, JSON.stringify(b.input, null, 2)));
        } else out.push(el("div", { class: "sub" }, b.type.toUpperCase()), el("pre", {}, JSON.stringify(b, null, 2)));
      }
    }
  }
  return out.length ? out : el("p", { class: "note" }, "Claude didn't produce anything at this step.");
}

// --- playback -------------------------------------------------------------------------

function setPlaying(on) {
  state.playing = on && state.i < state.steps.length - 1;
  $("play").textContent = state.playing ? "❚❚ Pause" : "▶ Play";
  restartTimer();
}

function restartTimer() {
  clearTimeout(state.timer);
  if (!state.playing) return;
  state.timer = setTimeout(() => {
    show(state.i + 1);
    setPlaying(state.i < state.steps.length - 1);
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
  window.addEventListener("resize", () => { if (!$("inner").hidden) drawInnerPath(); });
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
    state.text = steps.steps;
    state.checks = steps.checks || {};
    state.steps = buildSteps(trace.events);

    const number = Number(String(trace.scenario).replace(/\D/g, ""));
    const scenario = scenarios.find((s) => s.id === number);
    $("eyebrow").textContent = `SCENARIO ${number || trace.scenario}`
      + (scenario ? ` · ${scenario.name.toUpperCase()}` : "")
      + (trace.fault ? " · SIMULATED FAILURE" : "");

    // One badge per guard this run checks, in the order they first appear.
    const names = [...new Set(trace.events.filter((e) => e.guard).map((e) => e.guard.name))];
    $("guards").replaceChildren(...names.map((n) => el("span", { class: "guard", "data-guard": n, title: state.checks[n] || n }, spaced(n))));

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
