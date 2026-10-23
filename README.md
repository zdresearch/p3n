# p3n

The AI pen: writing skills for your AI agent.

| Skill | What it does |
|---|---|
| **[AI Detection](skills/ai-detection)** | Was text written by a person or a model? A score, a label (human, AI, AI-edited, humanized, mixed), a verdict, and the sentences and patterns that gave it away. |
| **[Deslop](skills/deslop)** | Makes text _say_ what it means: cuts filler, restatements and benefit tails, and asks for the facts a reader is missing. |
| **[Editorial](skills/editorial)** | Deslop, but with editorial context (e.g., technical, finance, etc.) and less AI sounding result. |
| **[Humanize](skills/humanize)** | Rewrites text to register less AI-generated, without changing what it says. |

## Install
Each folder in `skills/` is an agent skill: a `SKILL.md`, the rules and prompts, plus small scripts. For
Claude Code, link the skills into `~/.claude/skills/`:

```
git clone https://github.com/zdresearch/p3n && cd p3n
for s in skills/*; do ln -s "$PWD/$s" ~/.claude/skills/; done
```

Then ask your agent to "check draft.md for AI writing" or "run editorial on draft.md".

The scripts need Python 3.11+ with no dependencies. AI Detection and Humanize also use [`tropa-mini`](#ai-detection-oracle), an open-weights classifier, as AI detection oracle, plus PyTorch and about 2 GB of disk and memory:

```
pip install -r requirements-model.txt
```

## How it works
Your AI agent does the reading and writing (as usual), and hands the editorial, rewriting and checking parts to subagents on a small fast cheap model (Claude Haiku 5.5, or GPT-6 Luna at low reasoning effort).
A subagent has fresh context and reads the text cold, avoiding context creep and sloppiness. It is also fast, cheap and efficient enough for reading/writing.

**AI Detection** runs three checks, then a judge. The first check is a linter with ~60 rules that model-written text shows far more often than human text ([`rules.toml`](skills/ai-detection/rules.toml), each with a score). The second check uses the LLM rules from the same file via a subagent, for rules that are not static. AI detection oracle classifies the text as the third step.
Then the judge, another subagent, reads the text and the result of the three checks and issues the verdict score, the label, the verdict and the flagged sentences.

**Deslop and Editorial** split the text one sentence per line and label every line: `P3S2` is sentence 2 of paragraph
3. An editor subagent reads the labelled file with an audience brief in mind (i.e., who reads this text, and what for) and returns, per label, a change, a cut, a question or a note, plus a score of 0 to 100.
The writer agent (your agent that is running the skill) answers the questions, applies the changes as seen fit, and sends
the reworked text back.
The writer and the editor iterate in rounds until the score reaches 80 or 5 rounds.
The editor doesn't modify the text itself, it just asks questions and makes suggestions like a real-world editor.
The editorial rubrics are simple markdown ([deslop](skills/deslop/editor.md), [editorial](skills/editorial/editor.md)), they can be modified and tuned to specific work.

**Humanize** rewrites each paragraph by ~12 rules ([`rules.md`](skills/humanize/rules.md)). With AI detection oracle installed, it writes three versions of each paragraph with different emphasis, checks them, and keeps the lowest AI version.

## Hosted API
All skills are available as an API at `https://api.p3n.si/v1` and explained in more detail at [p3n.si](https://p3n.si). Multiple free calls per hour, with a paid model that is still very affordable:

```
curl https://api.p3n.si/v1/detect -H 'Content-Type: application/json' -d '{"text": "Paste AI generated text here."}'
```

The skills can use the API as well (provide them with an API key). This route is especially useful for AI detection and Humanize skills that require setting up oracles locally and may be slow.
We use the online versions ourselves despite having them installed locally! The local versions are only worth the effort if you are going to use the skill with significant volume.

## Versions
`skills/<skill>/VERSION` names the rules and prompts this repository holds. The hosted API runs the same ones under the same name, with the models they were tuned on; pin it with `"options": {"version": "detect-v1.4"}`.

## AI Detection Oracle
AI Detection and Humanize use [tropa-mini](https://huggingface.co/wasitaigeneratedcom/ai-text-detector-small) by
wasitaigenerated.com as the AI detection oracle: a DeBERTa-v3-large classifier with four classes (human, AI, AI-edited, humanized), Apache-2.0, derived from desklib/ai-text-detector-v1.01 and microsoft/deberta-v3-large (both MIT). It is downloaded from Hugging Face on first use.

## Tests
`python3 -m unittest discover tests`

## License
[MIT](LICENSE).
