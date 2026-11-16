"""Locked ingestion-only hypotheses, no gold, query or mutable configuration."""
import importlib.util
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = load('legacy_ingestion')
accepted = load('accepted_ingestion')


def packed(text, *, limit, max_paragraphs=None, break_at_heading=False):
    """Nonoverlapping exact spans; long original single lines remain indivisible."""
    rows = legacy.chunks(text)  # original bounds and line validation always run
    lines = text.split('\n')
    result = []
    group = []
    def flush():
        if group:
            first, last = group[0][0], group[-1][1]
            result.append((first, last, '\n'.join(lines[first-1:last])))
            group.clear()
    for row in rows:
        heading = re.match(r' {0,3}#{1,6}[ \t]+\S', row[2]) is not None
        trial = '\n'.join(lines[(group[0][0] if group else row[0])-1:row[1]])
        if group and ((max_paragraphs is not None and len(group) >= max_paragraphs)
                      or (break_at_heading and heading)
                      or len(trial.encode('utf-8')) > limit):
            flush()
        group.append(row)
    flush()
    return result


def pair_paragraphs(text):
    return packed(text, limit=1200, max_paragraphs=2)


def heading_sections(text):
    return packed(text, limit=1200, break_at_heading=True)


def bounded_600(text):
    return packed(text, limit=600)


CHUNKERS = {'accepted_89f115c': accepted.chunks,
            'pair_paragraphs': pair_paragraphs,
            'heading_sections': heading_sections,
            'bounded_600': bounded_600,
            'legacy_74ee976': legacy.chunks}

DESCRIPTIONS = {
 'accepted_89f115c': 'Accepted parser: whole source when normalized UTF8<=1200; otherwise original paragraph chunks.',
 'pair_paragraphs': 'Pair at most two adjacent original chunks when the complete contiguous source span is <=1200 UTF8 bytes. Nonoverlapping; applies to every source length.',
 'heading_sections': 'Greedily join adjacent original chunks into exact contiguous spans <=1200 UTF8 bytes; start a new span at each Markdown heading. Nonoverlapping; applies to every source length.',
 'bounded_600': 'Greedily join adjacent original chunks into exact contiguous spans <=600 UTF8 bytes (fixed half of existing target). Nonoverlapping; original indivisible lines may exceed target.',
 'legacy_74ee976': 'Historical reference only: original paragraph/heading splitting, unchanged current retrieval algorithm.'}
