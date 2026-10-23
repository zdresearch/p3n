---
name: deslop
description: Edit a text in editorial rounds so it says what it means. Cuts filler, restatements and benefit tails, and asks for the facts a reader is missing. Each round is scored 0-100. Use when asked to deslop, tighten, edit or review a draft, doc, README, PR description or email.
---

# Deslop

## Inputs
- **Text**: a file, or text the user provided.
- **Brief**: who reads the text and what for. If you don't know the brief and the audience from the writing's context, ask the user.
- **Target score**: the score that ends the edit. Default 80/100.

They come as the skill's arguments (`/deslop draft.md "the support team, learning the escalation rules" 90`) or from the conversation.

You are the writer. Spawn a subagent called editor on the cheapest model you have (e.g., Luna for ChatGPT, Haiku for Claude), ideally at low effort, and tell it to read `editor.md` in this folder as its instructions. Don't read `editor.md` yourself (context pollution): it is the editor's rubric, and everything you need from it is here in this file.

Label the text with `python3 scripts/split.py TEXT_FILE` or pipe the text in with `python3 scripts/split.py -`, and send it to the editor with the brief:

```
# The text to edit

BRIEF (who reads this and what for): <the brief>

<the labelled text>
```

The editor answers in rounds with one JSON object:

```
{"summary": "the state of the text and the most important thing to fix next",
 "progress": "after round 1: what the revision fixed, what is still open, what it broke",
 "items": [{"label": "P3S2" | "P3S2-S4" | "P3", "type": "change" | "cut" | "question" | "note",
            "proposal": "the replacement text (change)", "question": "what it needs to know (question)",
            "why": "the criterion, and what is wrong"}],
 "score": 0-100}
```

A change replaces the labelled sentence, range or paragraph with its proposal; a cut deletes it; a question needs an answer before the sentence can be fixed; a note is anything else.
P3S2 is sentence 2 of paragraph 3; H and B lines (headings, lists, tables, code) are generally not edited.

Use facts from your conversation; ask the user for facts you don't have rather than inventing them. When the user has no answer, keep the sentence as is.

Each round, the editor returns feedback per label and a score. Apply the feedback as you see fit, label the new text again, and send it back to the same subagent with the answers to its questions. Ask it to say in "progress" what the revision fixed, what is still open and what it broke, and to hold to what it asked for in earlier rounds. Keep the subagent alive for the whole edit.

Stop when the score reaches the target score, after 5 rounds, or when the score rose less than 5 points over the last two rounds. The user may ask to continue.

Show the rounds, score of each round, the summary, etc. to the user.

## Hosted API
Only if you can't spawn a subagent: the hosted p3n API runs the same editor. Read https://p3n.si/skills/deslop#for-ai-agents then, and follow it; it has the calls, the key and the free limit.

The user's p3n API key should live in `~/.config/p3n/key`.
