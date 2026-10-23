"""Text to labelled slot form: one sentence per line in prose paragraphs, every line labelled.

P3S2 is sentence 2 of prose paragraph 3, H2 the second heading, B1 the first table, list, quote, HTML comment or code
block (each line of a block carries the block's label). Headings and blocks pass through untouched; the editor
refers to lines by label.
"""
from __future__ import annotations

import re

SENTENCE = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[`]*[A-Z0-9])")
PASSTHROUGH = re.compile(r"^(#|<!--|\||[-*+] |\d+[.)] |>|```|~~~)")
POINTER = re.compile(r"^(See|Read|Refer to) \S+\.(md|txt|rst|html)\b.{0,60}$")


def split_sentences(text: str) -> list[str]:
    out = []
    for line in text.split('\n'):
        out.extend(s.strip() for s in SENTENCE.split(line.strip()) if s.strip())
    return out


def blocks_of(text: str) -> list[tuple[str, str]]:
    """(kind, text) in order: 'prose' for a paragraph (its lines joined with newlines), 'raw' for a pass-through line."""
    out, cur, fence = [], [], False
    for line in text.split('\n'):
        if line.startswith(('```', '~~~')):
            if cur:
                out.append(('prose', '\n'.join(cur)))
                cur = []
            fence = not fence
            out.append(('raw', line))
            continue
        if fence or not line.strip() or PASSTHROUGH.match(line) or POINTER.match(line.strip()):
            if cur:
                out.append(('prose', '\n'.join(cur)))
                cur = []
            out.append(('raw', line))
            continue
        cur.append(line)
    if cur:
        out.append(('prose', '\n'.join(cur)))
    return out


def labelled(text: str) -> tuple[str, dict[str, str]]:
    """The labelled slot text, and label -> text (a sentence, a heading, or a whole block)."""
    out, index, p, h, b, in_block = [], {}, 0, 0, 0, None
    for kind, block in blocks_of(text):
        if kind == 'prose':
            p += 1
            in_block = None
            for i, s in enumerate(split_sentences(block), 1):
                out.append(f'P{p}S{i} {s}')
                index[f'P{p}S{i}'] = s
        elif not block.strip():
            out.append('')
            in_block = None
        elif block.startswith('#'):
            h += 1
            in_block = None
            out.append(f'H{h} {block}')
            index[f'H{h}'] = block
        else:
            if in_block is None:
                b += 1
                in_block = b
                index[f'B{b}'] = block
            else:
                index[f'B{in_block}'] += '\n' + block  # the whole block: an item on B2 may mean any of its lines
            out.append(f'B{in_block} {block}')
    return '\n'.join(out).rstrip('\n') + '\n', index


LIST = re.compile(r'^\s*([-*+] |\d+[.)] )')
WORD = re.compile(r"[a-z0-9]{3,}")


def _covered(unit: str, proposal: str) -> bool:
    """Whether a proposal already says what `unit` (a sentence or list item it did not name) says: most of the unit's
    words appear in it. The editor often rewrites a sentence together with the next one under one label."""
    words = set(WORD.findall(unit.lower()))
    return len(words) >= 3 and len(words & set(WORD.findall(proposal.lower()))) / len(words) >= 0.7


def apply(text: str, items: list[dict]) -> str:
    """The text with the editor's changes and cuts applied, by label: a sentence (P3S2), a range (P3S2-S4: the first
    line takes the proposal, the rest go) or a whole paragraph (P3). Labels always refer to the text as sent: slots
    keep their place and emptied ones drop at the end. A proposal that also rewrites the sentences (or the list items)
    right after its label takes them too, unless another item names them. Headings and other blocks are untouched."""
    blocks = blocks_of(text)
    paras = [split_sentences(b) if k == 'prose' else None for k, b in blocks]
    prose = [i for i, p in enumerate(paras) if p is not None]
    dropped: set[int] = set()  # raw blocks a proposal absorbed
    named = {str(it.get('label', '')) for it in items}
    for it in items:
        if it.get('type') not in ('change', 'cut'):
            continue
        new = '' if it['type'] == 'cut' else str(it.get('proposal') or '').strip()
        if it['type'] == 'change' and not new:
            continue
        m = re.fullmatch(r'P(\d+)(?:S(\d+)(?:-(?:P\1)?S(\d+))?)?', str(it.get('label', '')))
        if not m or int(m[1]) > len(prose):
            continue
        bi = prose[int(m[1]) - 1]
        sents = paras[bi]
        a, b = (1, len(sents)) if m[2] is None else (int(m[2]), int(m[3] or m[2]))
        if a > len(sents):
            continue
        b = min(b, len(sents))
        sents[a - 1] = new
        for i in range(a, b):
            sents[i] = ''
        if not new or len(split_sentences(new)) <= b - a + 1:
            continue
        while b < len(sents) and f'P{m[1]}S{b + 1}' not in named and sents[b] and _covered(sents[b], new):
            sents[b] = ''
            b += 1
        if b == len(sents):  # the paragraph's end: a list right after it may be folded in too
            j = bi + 1
            while j < len(blocks) and blocks[j][0] == 'raw' and LIST.match(blocks[j][1]) and _covered(blocks[j][1], new):
                dropped.add(j)
                j += 1
    out = []
    for i, ((kind, block), p) in enumerate(zip(blocks, paras)):
        if i in dropped:
            continue
        if kind == 'raw':
            out.append(block)
        elif any(p):
            out.append(' '.join(s for s in p if s))
        elif out and not out[-1].strip() and (i + 1 == len(blocks) or not blocks[i + 1][1].strip()):
            out.pop()  # a paragraph cut whole takes one blank line with it, unless a list or block follows directly
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).rstrip('\n') + '\n'


if __name__ == '__main__':  # python3 split.py FILE ('-' for stdin): print the labelled text
    import sys
    print(labelled(sys.stdin.read() if sys.argv[1:] == ['-'] else open(sys.argv[1], encoding='utf-8').read())[0], end='')
