"""tropa-mini, the AI-text classifier AI Detection and Humanize use, on this machine. Optional: it needs torch and
transformers (pip install -r requirements-model.txt at the repository root) and downloads ~1.7 GB of weights from
Hugging Face on first use. CPU is enough. Without it, the hosted API runs it for you.

  python3 tropa.py FILE              the classifier block of the judge's input (see ai-detection/SKILL.md)
  python3 tropa.py FILE FILE...      one line per file, the model loaded once (Humanize's candidates)
  python3 tropa.py FILE... --json    everything

Model: wasitaigeneratedcom/ai-text-detector-small (tropa-mini, Apache-2.0; derived from desklib/ai-text-detector-v1.01
and microsoft/deberta-v3-large, both MIT). DeBERTa-v3-large with a 4-way head over mean-pooled hidden states. Text is
cut into 760-token chunks; labels are averaged weighted by chunk length.
Result: {"ai", "labels": {human, ai, ai_edited, humanized}, "chunks": [{tokens, labels}], "model", "version"}.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
from pathlib import Path

REPO = os.environ.get('TROPA_MINI_REPO', 'wasitaigeneratedcom/ai-text-detector-small')
LABELS = ['human', 'ai', 'ai_edited', 'humanized']
CHUNK = 760

_model = None
_lock = threading.Lock()


def available() -> bool:
    """Whether torch and transformers are installed, so tropa-mini can run here."""
    return all(importlib.util.find_spec(m) for m in ('torch', 'transformers'))


def _load():
    for k, v in {'TRANSFORMERS_VERBOSITY': 'error', 'HF_HUB_DISABLE_PROGRESS_BARS': '1', 'TOKENIZERS_PARALLELISM': 'false'}.items():
        os.environ.setdefault(k, v)
    import warnings
    warnings.filterwarnings('ignore', category=FutureWarning)
    import torch
    import torch.nn as nn
    from transformers import AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel

    class Detector(PreTrainedModel):
        config_class = AutoConfig
        _tied_weights_keys = []

        @property
        def all_tied_weights_keys(self):
            return {}

        def __init__(self, config):
            super().__init__(config)
            self.model = AutoModel.from_config(config)
            self.classifier = nn.Linear(config.hidden_size, getattr(config, 'detector_num_labels', 1))

        def forward(self, input_ids, attention_mask=None, **kw):
            h = self.model(input_ids, attention_mask=attention_mask)[0]
            m = attention_mask.unsqueeze(-1).float()
            return self.classifier((h * m).sum(1) / m.sum(1))

    device = os.environ.get('TROPA_DEVICE') or ('cuda' if torch.cuda.is_available() else
                                                'mps' if torch.backends.mps.is_available() else 'cpu')
    tok = AutoTokenizer.from_pretrained(REPO)
    return torch, tok, Detector.from_pretrained(REPO).eval().to(device), device


def load():
    """Load the model now (seconds to minutes; a download the first time). score() does it on first call."""
    global _model
    with _lock:
        if _model is None:
            if not available():
                raise RuntimeError('tropa-mini needs torch and transformers: pip install -r requirements-model.txt '
                                   '(or use the hosted API)')
            _model = _load()
    return _model


def score(text: str) -> dict:
    """tropa-mini's labels for the text."""
    if not text.strip():
        raise ValueError('no text to score')
    torch, tok, model, device = load()
    with _lock:
        ids = tok(text, add_special_tokens=False)['input_ids']
        chunks, total, acc = [], 0, None
        for i in range(0, max(len(ids), 1), CHUNK):
            c = ids[i:i + CHUNK]
            enc = tok(tok.decode(c), truncation=True, max_length=CHUNK + 8, return_tensors='pt').to(device)
            with torch.inference_mode():
                p = torch.softmax(model(**enc), dim=-1)[0].cpu()
            chunks.append({'tokens': len(c), 'labels': dict(zip(LABELS, [round(x, 5) for x in p.tolist()]))})
            acc = p * len(c) if acc is None else acc + p * len(c)
            total += len(c)
    labels = dict(zip(LABELS, [round(x, 5) for x in (acc / max(total, 1)).tolist()]))
    return {'ai': round(1 - labels['human'], 5), 'labels': labels, 'chunks': chunks, 'model': 'tropa-mini', 'version': REPO}


def is_ai(r: dict) -> bool:
    """Humanize's bar: anything but "ai" as the top label passes (human, humanized, ai_edited)."""
    L = r['labels']
    return max(L, key=L.get) == 'ai'


def evidence(r: dict) -> str:
    """The classifier block of the judge's input, as the hosted judge gets it."""
    lab = ', '.join(f'{k} {v:.3f}' for k, v in r['labels'].items())
    return ('DETECTOR MODEL (tropa-mini, a fine-tuned classifier; strong on essays, stories and news, '
            f'but it sometimes calls human fiction AI with high confidence):\nai {r["ai"]:.3f}; labels {lab}')


def main(argv: list[str]) -> int:
    as_json = '--json' in argv
    files = [a for a in argv if a != '--json']
    if not files:
        sys.exit('usage: python3 tropa.py FILE... [--json]')
    try:
        out = {f: score(sys.stdin.read() if f == '-' else Path(f).read_text(encoding='utf-8')) for f in files}
    except (RuntimeError, ValueError, OSError) as e:
        sys.exit(f'tropa-mini: {e}')
    if as_json:
        print(json.dumps(out if len(files) > 1 else out[files[0]], indent=1))
    elif len(files) == 1:
        print(evidence(out[files[0]]))
    else:
        for f, r in out.items():
            top = max(r['labels'], key=r['labels'].get)
            print(f"{f}\tai {r['ai']:.3f}\t{top}{'' if is_ai(r) else ' (passes)'}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
