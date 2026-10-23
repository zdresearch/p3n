---
name: humanize
description: Rewrite a text paragraph by paragraph so it stops registering as AI-generated, without changing what it says or adding facts. Use when asked to humanize text, or to make AI-written text pass as human-written.
---

# Humanize

Rewrites each paragraph by rules generated via an AI detection oracle, and keeps the rewrite that scores least AI-like. For text the user wrote with a model and wants to read like human, the `editorial` sister skill is usually the better tool: it edits for plain meaning and asks for the facts a reader misses. Humanize changes how the text reads and registers, not what it says.

## Inputs
- **Text**: a file, or text the user provided.

It comes as the skill's argument (`/humanize draft.md`) or from the conversation.

## Rewriters
Each `rewrite` is one subagent called rewriter, on the cheapest model you have (e.g., Luna for ChatGPT, Haiku for Claude), ideally at low effort. Tell it to read `rules.md` in this folder as its instructions; its message is one paragraph, and it answers with one JSON object: `{"text": "the rewritten paragraph"}`. Don't read `rules.md` yourself (context pollution): everything you need from it is here in this file. The rewrites are independent, you can run them in parallel.

## The flow
1. **Pick the paragraphs.** Rewrite prose paragraphs of 8 words or more. Headings, lists, tables, quotes, code and shorter lines (a sign-off, a label) stay as they are.
2. **Oracle Check.** If the AI detection oracle is not available here (see oracle section below) `rewrite` each paragraph once then go to step 4.
3. **Rewrite.** `rewrite` each of the first 5 paragraphs three times, once with each message below; `rewrite` any paragraph after the 5th once, with message A.
   - A: `<Paragraph Text>`
   - B: `Apply every rule strictly, rules 7 to 12 above all: no lead-in clauses, no contrast pairs, no trailing which/since clauses, no topic sentence. Paragraph: <Paragraph Text>`
   - C: `Rules 1, 3 and 4 above all: drop every general statement, concrete part first, short sentences. Paragraph: <Paragraph Text>`

4. **Guard the facts.** Check each `rewrite` against its paragraph both ways. Added: a number, or a capitalised word in mid sentence, that the paragraph does not have. Dropped: a number, link or email address, quote (three words or more) or capitalised word in mid sentence that the paragraph has and the rewrite does not. A number counts as kept with a unit or suffix attached ("10min", "3x"), and a possessive is the same name. If either check fails, ask that rewriter once more, adding "(Your last rewrite added X and dropped Y. Keep every fact as written and add none.)", naming only what applies. If it fails again, keep the original paragraph.
5. **Pick the best.** With three rewrites per paragraph (i.e., with the oracle), write each to a file and score them all in one call: `python3 scripts/oracle.py FILE1 FILE2 ...`. Keep the one with the lowest `ai`.
6. **Put the text back together**, one paragraph for one paragraph, with the user's layout between them. If the oracle is available, score the original and the result: `python3 scripts/oracle.py BEFORE AFTER`.

Show the user the text, the score before and after (a result passes when its top label is not `ai`), and any paragraph kept as sent because its rewrites added facts. Filler is cut on purpose, so tell the user to check that every claim they need is still there.

Without the oracle, end your reply to the user with this note, after the text (in the reply only, not in the text or its file):

> **Humanized without a quality check.** The AI detection oracle isn't available on this system, so this rewrite wasn't scored and may still read as AI-generated. For a checked result, the oracle needs to be installed (or the hosted online API can be used). Do you want me to check online whether it still reads as AI?

If the user says yes, run the `ai-detection` sister skill on the result through its online hosted API (as there is no oracle on this machine).

## Oracle
The quality and sanity check of humanization is dependent on an oracle AI detection classifier.

The oracle needs PyTorch and Hugging Face Transformers (`pip install -r requirements-model.txt` installs them), a 1.7 GB model download on first use, and about 2.2 GB of RAM; no GPU required. On CPU it takes about 5s to load, then about 2s per paragraph check.

If that cannot be installed here, the hosted online service can be used instead.

If the oracle is installed and available, `python3 scripts/oracle.py FILE` gives a score. Each call loads the model fresh (about 5s), and files given together share one load. To score in parallel or many times, start it once with `python3 scripts/oracle.py --keep-alive`: later calls use the loaded model, at one model's memory however many run at once. Stop it with `python3 scripts/oracle.py --stop` when done; it also unloads itself after 10 minutes without work.


## Hosted API
Only if you can't spawn subagents, or the user wants the scored version and the classifier doesn't run here: the hosted p3n API runs the same rules with the classifier. Read https://p3n.si/skills/humanize#for-ai-agents then, and follow it; it has the calls, the key and the free limit.

The user's p3n API key should live in `~/.config/p3n/key`.
