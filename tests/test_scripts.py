"""The skills' scripts: the linter and the splitter (stdlib, no network), and the copies that must stay identical.
python3 -m unittest discover tests"""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / 'skills'


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


lint = load(SKILLS / 'ai-detection' / 'scripts' / 'lint.py')
split = load(SKILLS / 'deslop' / 'scripts' / 'split.py')
MODEL_TEXT = ("In today's fast-paced world, we must delve into the rich tapestry of ideas — a robust and seamless "
              "approach. This is not just a tool; it's a testament to innovation.")


class LintTest(unittest.TestCase):
    def test_model_text_scores_and_names_its_patterns(self):
        r = lint.lint(MODEL_TEXT)
        rules = {h['rule'] for s in r['segments'] for h in s['hits']}
        self.assertGreater(r['ai'], 0.5)
        self.assertTrue({'unicode-dash', 'ai-filler'} <= rules, rules)

    def test_plain_text_scores_nothing(self):
        r = lint.lint('I walked to the bakery this morning and the line was out the door, so I gave up and made toast.')
        self.assertEqual(r['ai'], 0.0)

    def test_abbreviations_do_not_end_sentences(self):
        self.assertEqual(lint.sentences('Dr. Smith met George K. Lee at 5 p.m. on Main St. today. Then he left.'),
                         ['Dr. Smith met George K. Lee at 5 p.m. on Main St. today.', 'Then he left.'])

    def test_every_rule_loads(self):
        meta, rules = lint.load_rules()
        kinds = [r.kind for r in rules]
        self.assertEqual((len(rules), kinds.count('llm')), (81, 20))
        self.assertTrue(all(r.check in lint.CHECKS for r in rules if r.kind == 'check'))

    def test_reading_hits_count_only_real_quotes(self):
        text = 'The team leveraged the cache. Then we went home early.'
        rule = next(r for r in lint.load_rules()[1] if r.kind == 'llm' and not r.pairs)
        hits = [{'rule': rule.id, 'quote': 'Then we went home early', 'why': 'x'},
                {'rule': rule.id, 'quote': 'words that are not there', 'why': 'x'},
                {'rule': 'no-such-rule', 'quote': 'The team', 'why': 'x'}]
        found = [h for s in lint.lint(text, reading=hits)['segments'] for h in s['hits'] if h['kind'] == 'llm']
        self.assertEqual([(h['rule'], h['count']) for h in found], [(rule.id, 1)])

    def test_command_line(self):
        run = lambda *a: subprocess.run([sys.executable, str(SKILLS / 'ai-detection' / 'scripts' / 'lint.py'), *a],
                                        input=MODEL_TEXT, capture_output=True, text=True, check=True).stdout
        self.assertTrue(run('-').startswith('LINTER (scripted pattern checks'))
        self.assertGreater(json.loads(run('-', '--json'))['ai'], 0.5)
        self.assertEqual(len(run('--reading-rules').splitlines()), 20)


class SplitTest(unittest.TestCase):
    TEXT = '# Title\n\nFirst sentence here. Second one follows.\n\n- a list item\n\nAnother paragraph.\n'

    def test_labels(self):
        slots, index = split.labelled(self.TEXT)
        self.assertEqual(slots.splitlines(), ['H1 # Title', '', 'P1S1 First sentence here.', 'P1S2 Second one follows.',
                                              '', 'B1 - a list item', '', 'P2S1 Another paragraph.'])
        self.assertEqual(index['P1S2'], 'Second one follows.')


class CopiesTest(unittest.TestCase):
    """Each skill folder works on its own (link one into ~/.claude/skills), so shared scripts are copies."""

    def test_copies_are_identical(self):
        for a, b in [('deslop/scripts/split.py', 'editorial/scripts/split.py'),
                     ('ai-detection/scripts/tropa.py', 'humanize/scripts/tropa.py'),
                     ('ai-detection/scripts/oracle.py', 'humanize/scripts/oracle.py')]:
            self.assertEqual((SKILLS / a).read_bytes(), (SKILLS / b).read_bytes(), f'{a} and {b} differ')


if __name__ == '__main__':
    unittest.main()
