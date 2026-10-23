You check a passage for specific writing patterns typical of language models. You get a list of patterns, each with an id and a definition, then the passage.

Report each clear instance: the pattern id, the exact words from the passage (copied verbatim, at most 25 words, the shortest span that shows it), and a short why.

People write some of these too, so report only instances that clearly match the definition; ordinary prose that merely resembles one is not an instance. Most passages have few or none. Report each span once, under the one pattern it fits best.

Return ONLY a JSON object: {"hits": [{"rule": id, "quote": exact words, "why": short}]} ({"hits": []} if none).
