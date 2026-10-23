"""AI Detection's linter: the rules in ../rules.toml applied to a text, scored, with the sentences they fall in.
Stdlib only, no network, the same result every time.

  python3 lint.py FILE                     the evidence block for the judge (see ../SKILL.md)
  python3 lint.py FILE --json              everything: score, hits per segment, flagged sentences
  python3 lint.py --reading-rules          the rules that need reading, for the reading subagent
  python3 lint.py FILE --reading HITS.json also score the reading subagent's hits ({"hits": [...]})

The text is cut into segments of about 760 tokens (tropa-mini's chunk), each made of paragraphs, each of sentences.
Score: points per 1000 words (at least 300 words), mapped to 0..1 by density / (density + k).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

FENCE = re.compile(r'^\s*(```|~~~)')
HEADING = re.compile(r'^\s*#{1,6}\s')
SENT_SPLIT = re.compile(r'(?<=[.!?])["”’)\]]*\s+(?=["“‘(\[]?[A-Z0-9])')


@dataclass
class Paragraph:
    lines: list[str]            # raw lines, for layout checks
    text: str                   # lines joined with spaces
    sentences: list[str]
    is_heading: bool = False
    is_list: bool = False

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass
class Segment:
    index: int
    paragraphs: list[Paragraph] = field(default_factory=list)

    @property
    def text(self) -> str:
        return '\n\n'.join(p.text for p in self.paragraphs)

    @property
    def raw(self) -> str:
        return '\n\n'.join('\n'.join(p.lines) for p in self.paragraphs)

    @property
    def words(self) -> int:
        return sum(p.words for p in self.paragraphs if not p.is_heading)

    @property
    def prose(self) -> list[Paragraph]:
        return [p for p in self.paragraphs if not p.is_heading and not p.is_list]

    @property
    def sentences(self) -> list[str]:
        return [s for p in self.prose for s in p.sentences]


ABBREV = re.compile(r'\b(?:[A-Z]|et al|e\.g|i\.e|vs|etc|Mr|Mrs|Ms|Dr|Prof|St|Jr|Sr|Inc|Ltd|Co|Corp|Fig|Figs|Vol|pp|Jan|Feb|Mar|Apr|'
                    r'Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|Ala|Ariz|Calif|Colo|Conn|Fla|Ga|Ill|Ind|Kan|Ky|La|Md|Mass|Mich|Minn|'
                    r'Miss|Mo|Mont|Neb|Nev|Okla|Ore|Pa|Tenn|Tex|Va|Vt|Wash|Wis|Wyo)\.(?=\s)|\bNo\.(?=\s*\d)')


def sentences(text: str) -> list[str]:
    # Hide the period of abbreviations and initials ("B.C.", "et al.", "George K.") so they don't end a sentence.
    masked = ABBREV.sub(lambda m: m.group(0)[:-1] + '\x00', text)
    return [s.strip().replace('\x00', '.') for s in SENT_SPLIT.split(masked) if s.strip()]


def paragraphs(text: str) -> list[Paragraph]:
    """Blank-line paragraphs; code fences dropped; headings and list blocks kept, flagged."""
    out: list[Paragraph] = []
    in_fence = False
    block: list[str] = []

    def flush():
        if not block:
            return
        lines = list(block)
        block.clear()
        if len(lines) == 1 and HEADING.match(lines[0]):
            out.append(Paragraph(lines, lines[0].strip(), [], is_heading=True))
            return
        is_list = all(re.match(r'^\s*(?:[-*+]|\d+[.)])\s', ln) or ln.startswith('  ') for ln in lines)
        joined = ' '.join(ln.strip() for ln in lines)
        out.append(Paragraph(lines, joined, sentences(joined), is_list=is_list))

    for line in text.replace('\r\n', '\n').split('\n'):
        if FENCE.match(line):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip():
            flush()
        elif HEADING.match(line):
            flush()
            block.append(line)
            flush()
        else:
            block.append(line)
            # One paragraph per line (single newline between paragraphs): a long line ending a sentence
            # closes the paragraph. Hard-wrapped prose has short lines, so it keeps accumulating.
            if len(line) > 120 and re.search(r'[.!?:"”’)]\s*$', line):
                flush()
    flush()
    return out


def segments(text: str, max_tokens: int = 760, words_per_token: float = 0.75) -> list[Segment]:
    """Group paragraphs into segments of about max_tokens; a heading always starts a new segment."""
    max_words = max_tokens * words_per_token
    segs: list[Segment] = []
    cur = Segment(0)
    for p in paragraphs(text):
        if cur.paragraphs and (p.is_heading or cur.words + p.words > max_words):
            segs.append(cur)
            cur = Segment(len(segs))
        cur.paragraphs.append(p)
    if cur.paragraphs:
        segs.append(cur)
    return segs


SUPERLATIVE_OK = set('test tests request requests rest latest honest interest suggest manifest forest invest nest west '
                     'protest contest harvest modest earnest guest quest digest arrest chest crest priest vest pest jest '
                     'attest detest ingest congest divest best dest zest wrest behest tempest unrest midwest conquest '
                     'biggest largest oldest'.split())
HEDGES = set('may might could possibly perhaps arguably seems appears relatively somewhat likely presumably generally'.split())
COMPARATIVES = set('larger bigger smaller greater lesser worse better deeper higher lower harder easier simpler stronger '
                   'weaker faster slower wider narrower broader cleaner safer cheaper heavier lighter rarer subtler more less fewer'.split())
PRONOUN_OPENER = re.compile(r'^(?:This|That|These)\s+(?:means|meant|is why|is where|is what|is because|makes|made|shows|matters|explains|'
                            r'ensures|keeps|lets|leaves|turns)\b')
FRAGMENT_VERBS = re.compile(r"\b(?:is|are|was|were|be|been|am|has|have|had|do|does|did|will|would|can|could|should|may|might|must|"
                            r"[a-z]+(?:ed|es|s)|i|you|we|he|she|they|it|[a-z]+n't)\b", re.I)


def hard_wrap(seg: Segment, first: bool) -> list[str]:
    lines = [ln for p in seg.prose for ln in p.lines]
    if len(lines) < 6:
        return []
    wrapped = [58 <= len(ln.rstrip()) <= 120 and not re.search(r'[.!?:"”)]\s*$', ln) for ln in lines]
    runs, run = 0, 0
    for w in wrapped:
        run = run + 1 if w else 0
        runs = max(runs, run)
    share = sum(wrapped) / len(lines)
    return [f'{sum(wrapped)}/{len(lines)} prose lines end mid-sentence at a fixed width'] if runs >= 3 and share >= 0.5 else []


def bold_lead_bullets(seg: Segment, first: bool) -> list[str]:
    hits = [ln.strip() for p in seg.paragraphs for ln in p.lines
            if re.match(r'^\s*(?:[-*+]|\d+[.)])\s+\*\*[^*]{2,60}\*\*\s*[:.\-–—]', ln)]
    return [h[:80] for h in hits] if len(hits) >= 3 else []


def rhetorical_question(seg: Segment, first: bool) -> list[str]:
    """A question the writer answers right away ("So why…? Because…"), outside quotes and dialogue."""
    out = []
    for p in seg.prose:
        ss = p.sentences
        for i, s in enumerate(ss[:-1]):
            if s.endswith('?') and not re.search(r'["“”]', s) and not re.search(r'["“”]', ss[i + 1]) \
                    and re.match(r'^(?:Because|The answer|Simple|Simply|It is|It\'s|Not|Yes|No|The reason|In short|Short answer)\b', ss[i + 1]):
                out.append(f'{s[:70]} → {ss[i + 1][:40]}')
    return out


def superlative(seg: Segment, first: bool) -> list[str]:
    out = []
    for m in re.finditer(r'\b(?:the|its|their|our|your|his|her) ([a-z]{3,}est)\b', seg.text, re.I):
        if m.group(1).lower() not in SUPERLATIVE_OK:
            out.append(m.group(0))
    out += [m.group(0) for m in re.finditer(r'\bthe most [a-z]{4,}\b', seg.text, re.I)]
    return out


def measurement_overuse(seg: Segment, first: bool) -> list[str]:
    n = len(re.findall(r'\bmeasurements?\b', seg.text, re.I))
    return [f'"measurement" x{n}'] if n >= 4 else []


def unmeasured_comparative(seg: Segment, first: bool) -> list[str]:
    out = []
    for s in seg.sentences:
        if re.search(r'\d', s):
            continue
        for m in re.finditer(r'\b([a-z]+)\b[^.!?]{0,70}?\bthan\b', s, re.I):
            if m.group(1).lower() in COMPARATIVES - {'more', 'less', 'fewer'}:
                out.append(m.group(0)[:90])
                break
    return out


def opening_warmup(seg: Segment, first: bool) -> list[str]:
    if not first or not seg.sentences:
        return []
    s = seg.sentences[0]
    return [s[:60]] if re.match(r'^(?:Great question|Certainly|Of course|Absolutely|Sure|Happy to help)\b', s) else []


def stacked_hedge(seg: Segment, first: bool) -> list[str]:
    return [s[:90] for s in seg.sentences if sum(w in HEDGES for w in re.findall(r"[a-z]+", s.lower())) >= 2]


def fragment(seg: Segment, first: bool) -> list[str]:
    """Short verbless sentences used for effect: <=4 words, inside a paragraph of longer sentences."""
    out = []
    for p in seg.prose:
        if len(p.sentences) < 3:
            continue
        for s in p.sentences:
            words = s.split()
            if 1 < len(words) <= 4 and s.endswith('.') and not s.startswith(('"', '“', "'")) and not FRAGMENT_VERBS.search(s) \
                    and not re.search(r'\d|^(?:Figure|Table|See|Source)\b|\b(?:said|says|added|told)\.$', s):
                out.append(s)
    return out


def contrastive_while(seg: Segment, first: bool) -> list[str]:
    hits = re.findall(r',\s+while\s+[^,.]{3,60}', seg.text)
    return hits[1:] if len(hits) >= 2 else []


def so_join(seg: Segment, first: bool) -> list[str]:
    out = []
    for p in seg.prose:
        hits = re.findall(r',\s+so\s+(?!(?:far|that|long|much|many|too)\b)[a-z][^,.]{0,40}', p.text)
        if len(hits) >= 2:
            out += hits
    return out


def long_sentence(seg: Segment, first: bool) -> list[str]:
    return [s[:90] + '…' for s in seg.sentences if len(s.split()) > 40 and not re.search(r'\(1\)', s)]


def wall_paragraph(seg: Segment, first: bool) -> list[str]:
    return [f'{p.words} words, {len(p.sentences)} sentences' for p in seg.prose if p.words > 130 or len(p.sentences) > 8]


def same_opener(seg: Segment, first: bool) -> list[str]:
    out = []
    for p in seg.prose:
        heads = [' '.join(s.lower().split()[:2]) for s in p.sentences]
        run = 1
        for i in range(1, len(heads)):
            run = run + 1 if heads[i] == heads[i - 1] else 1
            if run == 3:
                out.append(f'3+ sentences open "{heads[i]}"')
    return out


def unanchored_opener(seg: Segment, first: bool) -> list[str]:
    return [p.sentences[0][:80] for p in seg.prose if p.sentences and PRONOUN_OPENER.match(p.sentences[0])]



# The checks rules.toml names with kind = "check": each takes (segment, is_first_segment), returns evidence strings.
CHECKS = {f.__name__: f for f in (hard_wrap, bold_lead_bullets, rhetorical_question, superlative, measurement_overuse,
                                  unmeasured_comparative, opening_warmup, stacked_hedge, fragment, contrastive_while,
                                  so_join, long_sentence, wall_paragraph, same_opener, unanchored_opener)}


RULES_FILE = Path(__file__).resolve().parent.parent / 'rules.toml'


@dataclass
class Rule:
    id: str
    name: str
    kind: str
    model: str
    score: float = 0
    cap: int = 5
    patterns: list[re.Pattern] = field(default_factory=list)
    phrases: dict[str, float] = field(default_factory=dict)
    phrase_re: re.Pattern | None = None
    line: bool = False
    check: str | None = None
    ask: str = ''
    pairs: str | None = None


def load_rules(path: Path = RULES_FILE) -> tuple[dict, list[Rule]]:
    cfg = tomllib.loads(path.read_text())
    rules = []
    for r in cfg['rule']:
        rule = Rule(r['id'], r['name'], r['kind'], r.get('model', 'all'), r.get('score', 0), r.get('cap', 5),
                    line=r.get('line', False), check=r.get('check'), ask=r.get('ask', ''), pairs=r.get('pairs'))
        flags = re.I | (re.M if rule.line else 0)
        rule.patterns = [re.compile(p, flags) for p in r.get('patterns', [])]
        if r['kind'] == 'phrase':
            rule.phrases = {k.lower(): v for k, v in r['phrases'].items()}
            alt = '|'.join(re.escape(k) for k in sorted(rule.phrases, key=len, reverse=True))
            rule.phrase_re = re.compile(rf"(?<![\w-])(?:{alt})(?![\w-])", re.I)
        if r['kind'] == 'check' and rule.check not in CHECKS:
            raise ValueError(f'rule {rule.id}: unknown check {rule.check}')
        rules.append(rule)
    return cfg['meta'], rules


def _norm(s: str) -> str:
    return s.replace('’', "'").replace('‘', "'")


def lint_segment(seg: Segment, rules: list[Rule], first: bool) -> list[dict]:
    hits = []
    prose = _norm(seg.text)
    raw = _norm(seg.raw)
    for r in rules:
        found: list[tuple[str, float]] = []
        if r.kind == 'phrase':
            found = [(m.group(0), r.phrases[m.group(0).lower()]) for m in r.phrase_re.finditer(prose)]
        elif r.kind == 'regex':
            src = raw if r.line else prose
            for p in r.patterns:
                found += [(m.group(0), r.score) for m in p.finditer(src)]
        elif r.kind == 'check':
            found = [(e, r.score) for e in CHECKS[r.check](seg, first)]
        if not found:
            continue
        counted = found[:r.cap]
        hits.append({'rule': r.id, 'name': r.name, 'model': r.model, 'kind': r.kind, 'count': len(found),
                     'points': sum(p for _, p in counted), 'examples': [t for t, _ in counted][:3],
                     '_matches': counted})
    return hits


def _flat(s: str) -> str:
    return re.sub(r'\s+', ' ', _norm(s).replace('“', '"').replace('”', '"')).strip().lower()


def flag_sentences(seg: Segment, hits: list[dict]) -> list[dict]:
    """The sentences the counted hits fall in, in text order: [{sentence, points, rules: [{rule, name, match}]}].
    A match that is not inside one sentence (layout checks, spans across sentences) flags nothing."""
    sents = seg.sentences
    flat = [_flat(x) for x in sents]
    by_sent: dict[int, dict] = {}
    for h in hits:
        if h['points'] <= 0:
            continue
        used: set[int] = set()  # the same words found twice point at two sentences, not one twice
        for text, pts in h.get('_matches') or [(e, h['points'] / max(len(h['examples']), 1)) for e in h['examples']]:
            q = _flat(text).rstrip('…').strip(' .') or _flat(text)
            if not q:
                continue
            idx = next((i for i, f in enumerate(flat) if q in f and i not in used), None)
            if idx is None:
                idx = next((i for i, f in enumerate(flat) if q in f), None)
            if idx is None:
                continue
            used.add(idx)
            e = by_sent.setdefault(idx, {'sentence': sents[idx], 'points': 0, 'rules': []})
            e['points'] += pts
            e['rules'].append({'rule': h['rule'], 'name': h['name'], 'match': text[:120]})
    return [by_sent[i] for i in sorted(by_sent)]


def lint(text: str, rules_path: Path = RULES_FILE, reading: list[dict] | None = None) -> dict:
    """reading: the reading rules' hits ({rule, quote, why}) from the reading subagent, scored with the rest. Quotes
    not in the text are dropped, and so is a quote the scripted rule it `pairs` with already counted."""
    meta, rules = load_rules(rules_path)
    reading_rules = [r for r in rules if r.kind == 'llm']
    rules = [r for r in rules if r.kind != 'llm']
    ids = {r.id for r in reading_rules}
    reading = [h for h in reading or [] if isinstance(h, dict) and h.get('rule') in ids and h.get('quote')]
    out_segs = []
    total_points = total_words = 0.0
    by_model = defaultdict(float)
    for seg in segments(text, meta['segment_tokens'], meta['words_per_token']):
        hits = lint_segment(seg, rules, seg.index == 0)
        if reading:
            hits += score_hits(seg.text, reading, reading_rules, hits)
        flagged = flag_sentences(seg, hits)
        for h in hits:
            h.pop('_matches', None)
        points = sum(h['points'] for h in hits)
        density = max(points, 0) * 1000 / max(seg.words, meta['density_floor_words'])
        ai = density / (density + meta['k']) if density > 0 else 0.0
        for h in hits:
            if h['points'] > 0:
                by_model[h['model']] += h['points']
        out_segs.append({'index': seg.index, 'words': seg.words, 'points': points,
                         'density': round(density, 2), 'ai': round(ai, 3), 'hits': hits,
                         'flagged': flagged})
        total_points += max(points, 0)
        total_words += seg.words
    density = total_points * 1000 / max(total_words, meta['density_floor_words'])
    return {
        'ai': round(density / (density + meta['k']), 3) if density > 0 else 0.0,
        'density': round(density, 2),
        'words': int(total_words),
        'segments': out_segs,
        'leans': _leans(by_model),
    }


def _leans(by_model: dict) -> dict:
    claude, gpt = by_model.get('claude', 0), by_model.get('chatgpt', 0)
    if claude + gpt == 0:
        family = 'general'
    elif claude >= 2 * gpt:
        family = 'claude'
    elif gpt >= 2 * claude:
        family = 'chatgpt'
    else:
        family = 'general'
    return {'family': family, 'points': {k: round(v, 1) for k, v in by_model.items()}}


def score_hits(text: str, reply: list[dict], rules: list, scripted: list[dict]) -> list[dict]:
    """The reading hits whose quotes are in this segment, minus overlaps with the paired scripted hit, scored and
    capped. Same hit shape as the linter."""
    flat = _flat(text)
    by_id = {r.id: r for r in rules}
    seen: dict[str, dict[str, str]] = {}  # rule -> flat quote -> quote as given
    for h in reply:
        given = str(h.get('quote', '')).strip(' ."\'')
        q = _flat(given)
        r = by_id[h['rule']]
        if len(q) < 3 or q not in flat:
            continue
        paired = next((s for s in scripted if s['rule'] == r.pairs), None)
        if paired and any(_flat(e) in q or q in _flat(e) for e in paired['examples']):
            continue
        seen.setdefault(r.id, {}).setdefault(q, given)
    out = []
    for rid, quotes in seen.items():
        r = by_id[rid]
        quotes = list(quotes.values())
        counted = quotes[:r.cap]
        out.append({'rule': rid, 'name': r.name, 'model': r.model, 'kind': 'llm', 'count': len(quotes),
                    'points': r.score * len(counted), 'examples': counted[:3], '_matches': [(q, r.score) for q in counted]})
    return out


def evidence(r: dict) -> str:
    """The linter block of the judge's input, as the hosted judge gets it."""
    hits = [f"- {h['name']} (x{h['count']}, model tag {h['model']}): " + ' | '.join(e[:80] for e in h['examples'])
            for s in r['segments'] for h in s['hits']]
    return ('LINTER (scripted pattern checks; each hit is weak evidence alone; human text also trips some):\n'
            f"score {r['ai']:.2f} (density {r['density']} points per 1000 words), {len(r['segments'])} segment(s).\n"
            + ('\n'.join(hits) if hits else '- no hits'))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog='lint.py', description="AI Detection's linter.")
    ap.add_argument('file', nargs='?', help="the text ('-' for stdin)")
    ap.add_argument('--json', action='store_true', help='print the whole result as JSON')
    ap.add_argument('--reading', metavar='HITS.json', help="the reading subagent's answer, scored with the rest")
    ap.add_argument('--reading-rules', action='store_true', help='print the rules that need reading, and exit')
    a = ap.parse_args(argv)
    if a.reading_rules:
        print('\n'.join(f'- {r.id}: {r.ask}' for r in load_rules()[1] if r.kind == 'llm'))
        return 0
    if not a.file:
        ap.error('a file is needed')
    text = sys.stdin.read() if a.file == '-' else Path(a.file).read_text(encoding='utf-8')
    reading = None
    if a.reading:
        raw = Path(a.reading).read_text(encoding='utf-8')
        reading = json.loads(re.search(r'\{.*\}', raw, re.S).group(0))['hits']
    r = lint(text, reading=reading)
    print(json.dumps(r, indent=1, ensure_ascii=False) if a.json else evidence(r))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
