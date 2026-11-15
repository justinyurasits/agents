# agents

Small agents built to learn, and to show, how agent loops work. One folder per agent: each one small, traced and documented.

## The job evaluator

[job-evaluator](job-evaluator/) is an agent that reads a job posting and rates it. Claude decides which tool to use (rate it, look up the company, or flag it for a person), and Python runs the tools, applies the hard rules in code, and keeps the conversation. Nine scenarios, five normal runs and four where a failure is injected on purpose, were recorded from real runs. A page replays them step by step: who's executing, what crossed between Claude, Python and the tools, and how each failure was handled.

**Watch it:** [justinyurasits.github.io/agents/job-evaluator/site/](https://justinyurasits.github.io/agents/job-evaluator/site/)

## Run it locally

You need Python 3.12 and your own Anthropic API key.

```bash
git clone https://github.com/justinyurasits/agents.git
cd agents/job-evaluator
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                   # then put your key in .env
```

`.env` holds your key and is ignored by git. Never commit it.

```bash
python agent.py                        # rate the built-in sample posting, step by step
python record.py 1                     # record scenario 1 (real API calls) and check it
python -m http.server 8000             # then open localhost:8000/site/ to watch the recorded runs
python -m unittest discover -s tests   # the tests: no API calls, no key needed
```

The page plays the committed recordings and makes no API calls. For the browser tests, `pip install -r requirements-dev.txt` and `python -m playwright install chromium`. [job-evaluator/README.md](job-evaluator/README.md) has the rest.

## How it's built

I wrote the first version of the agent by hand, to learn the loop. After that, Claude Code wrote the code from GitHub issues I wrote, and I made the decisions and reviewed every change before it merged.

- [CLAUDE.md](CLAUDE.md): the rules Claude Code follows in this repo.
- [DECISIONS.md](job-evaluator/docs/DECISIONS.md): every design decision, with the options and the reasoning.
- [LEARNINGS.md](LEARNINGS.md): what building these agents has taught me.
- [BUILD_LOG.md](job-evaluator/docs/BUILD_LOG.md): the dated working log of what I did, what broke, and what I learned.
