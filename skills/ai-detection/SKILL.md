---
name: ai-detection
description: Check whether a text was written by a person or by AI. Returns a probability, a label (human, AI, AI-edited, humanized, mixed), a plain-language verdict, the sentences that read as AI-written and the patterns behind them. Use when asked whether something was written by AI, to run an AI detector or AI check on a text, to check a draft before sending it, or to see what gives a text away.
---

# AI Detection

Three checks, then a judge. (1) A linter matches 61 patterns that AI-written text shows far more often than human text; (2) a reader subagent finds 20 more that need reading rather than matching; (3) an AI detection oracle classifies the whole text. A judge subagent then reads the text with all three results and gives the verdict.

## Inputs
- **Text**: a file, or text the user provided.

It comes as the skill's argument (`/ai-detection draft.md`) or from the conversation.

## Subagents
Two subagents, `reader` and `judge`, each on the cheapest model you have (e.g., Luna for ChatGPT, Haiku for Claude), ideally at low effort. Each reads its own instructions file in this folder. Don't read `reading.md`, `judge.md` or `rules.toml` yourself (context pollution): everything you need is here in this file, and the scripts read `rules.toml` automatically.

The judge has to read the text cold: if you wrote or edited the text, or talked about it with the user, you are not a fair judge of it, so never judge it yourself.

**reader**: tell it to read `reading.md` as its instructions. Its message:

```
PATTERNS:
<the output of: python3 scripts/lint.py --reading-rules>

PASSAGE:
"""
<the text>
"""
```

It answers with one JSON object: `{"hits": [{"rule": "...", "quote": "exact words from the text", "why": "..."}]}`.

**judge**: tell it to read `judge.md` as its instructions. Its message:

```
<the output of step 3 below>

<the oracle's output, if it ran>

DOCUMENT:
"""
<the text>
"""
```

It answers with one JSON object:

```
{"ai": 0-1, "label": "human" | "ai" | "ai_edited" | "humanized" | "mixed",
 "verdict": "one or two sentences",
 "confidence": {"level": "low" | "medium" | "high", "reason": "..."},
 "sentences": [{"text": "exact quote", "why": "..."}],
 "agent": {"family": "claude" | "openai" | "gemini" | "other" | "unknown", "why": "..."}}
```

## The flow
1. **Oracle Check.** `python3 scripts/oracle.py TEXT_FILE` (see oracle section below). If it runs, keep its output for the judge. If it doesn't, go on without it.
2. **Reader.** Spawn the reader and save its JSON answer to a file. The linter runs in step 3, with the reader's hits.
3. **Linter.** `python3 scripts/lint.py TEXT_FILE --reading HITS_FILE` (pipe pasted text in with `-` instead of a file). It runs the scripted checks and scores the reader's hits with them. It drops quotes that are not in the text, and hits a scripted rule already counted. If the reader failed, leave out `--reading`.
4. **Judge.** Spawn the judge with the output of step 3, the oracle's output if it ran, and the text.
5. **Check the judge's answer.** Drop any sentence that is not an exact quote from the text. If the judge fails twice and the oracle ran, report the oracle's score alone, with low confidence.

Show the user the score as a percentage, the label and the verdict. Quote the sentences it flags with the reason for each, and name the main patterns (the linter's hits with the most points). Don't claim more certainty than the confidence level says: a score is a probability, not a verdict on a person, and careful human writing trips some patterns too.

Without the oracle, end your reply to the user with this note, after the result (in the reply only, not in any file):

> **Detected without the oracle.** The AI detection oracle isn't available on this system, so this result comes from the pattern checks and the judge alone, and is less reliable on short or edited text. For a full check, the oracle needs to be installed (or the hosted online API can be used). Do you want me to check online?

If the user says yes, use the Hosted API below.

## Oracle
The AI detection oracle is a classifier that labels a whole text human, AI, AI-edited or humanized. It is the strongest of the three checks on longer text.

The oracle needs PyTorch and Hugging Face Transformers (`pip install -r requirements-model.txt` installs them), a 1.7 GB model download on first use, and about 2.2 GB of RAM; no GPU required. On CPU it takes about 5s to load, then about 2s per paragraph-sized text.

If the oracle is installed and available, `python3 scripts/oracle.py FILE` gives its result. Each call loads the model fresh (about 5s), and files given together share one load. To check many texts, or in parallel, start it once with `python3 scripts/oracle.py --keep-alive`: later calls use the loaded model, at one model's memory however many run at once. Stop it with `python3 scripts/oracle.py --stop` when done; it also unloads itself after 10 minutes without work.

## Hosted API
Use it only if you can't spawn subagents, if the user asks for an online check, or if a sister skill sends you here: the hosted p3n API runs the same checks with the oracle. Read https://p3n.si/skills/detect#for-ai-agents then, and follow it; it has the calls, the key and the free limit.

The user's p3n API key should live in `~/.config/p3n/key`.
