"""Deterministic spoken-number → digits conversion for Russian and Kazakh.

Why this exists: when a phone number is dictated by voice, the speech engine
transcribes it as number *words* ("сегіз жеті жүз жетпіс бес …"), and asking the
LLM to turn those words back into an exact digit string is unreliable — it will
occasionally corrupt a digit. For a banking recipient number that is not
acceptable. Converting number-words to digits is a deterministic transform, so
it belongs in code, not the model.

`spoken_to_digits` rewrites every run of number-words in a text as its digit
groups (each grammatical number becomes one space-separated group). Consecutive
dictated groups therefore stay adjacent, which lets `phone_from_text` reassemble
a phone number by concatenating adjacent digit tokens.

Scope: cardinals up to the hundred-thousands (covers phone groups and amounts
like "бес мың" = 5000). Ordinals and fractions are intentionally left alone.
"""
from __future__ import annotations

import re
from itertools import product

from orchestrator.services import validators

# Token kinds:
#   u  unit (0-9)
#   t  ten  (10, 20 … 90)   — a "clean" ten, may take a trailing unit
#   x  teen (11-19)         — Russian single words; unit slot already filled
#   hr hundred, value baked in (Russian сто…девятьсот = 100…900)
#   hk hundred marker (Kazakh жүз = ×100, multiplier is the preceding unit)
#   k  thousand (×1000)

_RU: dict[str, tuple[str, int]] = {
    "ноль": ("u", 0), "нуль": ("u", 0),
    "один": ("u", 1), "одна": ("u", 1), "одно": ("u", 1),
    "два": ("u", 2), "две": ("u", 2), "три": ("u", 3), "четыре": ("u", 4),
    "пять": ("u", 5), "шесть": ("u", 6), "семь": ("u", 7), "восемь": ("u", 8),
    "девять": ("u", 9),
    "десять": ("t", 10),
    "одиннадцать": ("x", 11), "двенадцать": ("x", 12), "тринадцать": ("x", 13),
    "четырнадцать": ("x", 14), "пятнадцать": ("x", 15), "шестнадцать": ("x", 16),
    "семнадцать": ("x", 17), "восемнадцать": ("x", 18), "девятнадцать": ("x", 19),
    "двадцать": ("t", 20), "тридцать": ("t", 30), "сорок": ("t", 40),
    "пятьдесят": ("t", 50), "шестьдесят": ("t", 60), "семьдесят": ("t", 70),
    "восемьдесят": ("t", 80), "девяносто": ("t", 90),
    "сто": ("hr", 100), "двести": ("hr", 200), "триста": ("hr", 300),
    "четыреста": ("hr", 400), "пятьсот": ("hr", 500), "шестьсот": ("hr", 600),
    "семьсот": ("hr", 700), "восемьсот": ("hr", 800), "девятьсот": ("hr", 900),
    "тысяча": ("k", 1000), "тысячи": ("k", 1000), "тысяч": ("k", 1000),
}

_KK: dict[str, tuple[str, int]] = {
    "нөл": ("u", 0), "ноль": ("u", 0),
    "бір": ("u", 1), "екі": ("u", 2), "үш": ("u", 3), "төрт": ("u", 4),
    "бес": ("u", 5), "алты": ("u", 6), "жеті": ("u", 7), "сегіз": ("u", 8),
    "тоғыз": ("u", 9),
    "он": ("t", 10), "жиырма": ("t", 20), "отыз": ("t", 30), "қырық": ("t", 40),
    "елу": ("t", 50), "алпыс": ("t", 60), "жетпіс": ("t", 70), "сексен": ("t", 80),
    "тоқсан": ("t", 90),
    "жүз": ("hk", 100),
    "мың": ("k", 1000),
}

# A Kazakh transcript may sprinkle in Russian numerals; Russian text never uses
# the Kazakh word "он" (which means "he" in Russian), so the merge is one-way.
_LEXICONS = {"kk": {**_RU, **_KK}, "ru": _RU}

_TOKEN_RE = re.compile(r"\w+|\W+", re.UNICODE)


def _lexicon(lang: str) -> dict[str, tuple[str, int]] | None:
    return _LEXICONS.get((lang or "")[:2].lower())


def _numbers_from_run(run: list[tuple[str, int]]) -> list[int]:
    """Split a run of number-tokens into the sequence of numbers it spells.

    Dictated phone groups arrive as one long run of cardinals; a new number
    starts whenever a token cannot grammatically extend the current one (e.g. a
    unit right after another unit). "бес мың" stays one number (5000); "сегіз
    жеті жүз" splits into 8 and 700.
    """
    numbers: list[int] = []
    th = h = t = u = 0
    unit_locked = started = False

    def flush() -> None:
        nonlocal th, h, t, u, unit_locked, started
        if started:
            numbers.append(th * 1000 + h + t + u)
        th = h = t = u = 0
        unit_locked = started = False

    for kind, val in run:
        if kind == "u":
            if u != 0 or unit_locked:
                flush()
            u = val
        elif kind == "t":
            if t != 0 or u != 0 or unit_locked:
                flush()
            t = val
        elif kind == "x":  # teen fills both the ten and the unit slot
            if t != 0 or u != 0 or unit_locked:
                flush()
            t = val
            unit_locked = True
        elif kind == "hr":  # Russian hundred, value already 100-900
            if h != 0 or t != 0 or u != 0 or unit_locked:
                flush()
            h = val
        elif kind == "hk":  # Kazakh жүз, multiplied by the preceding unit
            # The unit just before жүз is its multiplier ("төрт жүз" = 400), so
            # take it back out of the current number before closing that number.
            mult = u if 1 <= u <= 9 else 1
            u = 0
            if h != 0 or t != 0:
                flush()
            h = mult * 100
            unit_locked = False
        elif kind == "k":  # thousand scales everything gathered so far
            group = th * 1000 + h + t + u
            th = group or 1
            h = t = u = 0
            unit_locked = False
        started = True

    flush()
    return numbers


def spoken_to_digits(text: str, lang: str) -> str:
    """Rewrite number-words in `text` as digit groups; leave everything else.

    Each grammatical number becomes one space-separated digit group, so adjacent
    dictated groups (a phone number) stay adjacent as separate digit tokens.
    """
    lex = _lexicon(lang)
    if not lex:
        return text

    out: list[str] = []
    run: list[tuple[str, int]] = []
    pending_ws = ""  # whitespace held after a number-word: kept if the run ends

    def drain() -> None:
        nonlocal pending_ws
        if run:
            out.append(" ".join(str(n) for n in _numbers_from_run(run)))
            run.clear()
        if pending_ws:
            out.append(pending_ws)
            pending_ws = ""

    for tok in _TOKEN_RE.findall(text):
        if tok.strip() == "":  # whitespace — never breaks a run
            if run:
                pending_ws += tok
            else:
                out.append(tok)
            continue
        entry = lex.get(tok.lower()) if tok.isalpha() else None
        if entry is not None:
            pending_ws = ""  # inter-word space between two number-words is dropped
            run.append(entry)
        else:
            drain()
            out.append(tok)
    drain()
    return "".join(out)


def _digit_group_runs(text: str) -> list[list[str]]:
    """Runs of adjacent whitespace-separated pure-digit tokens, groups kept."""
    runs: list[list[str]] = []
    current: list[str] = []
    for tok in text.split():
        if tok.isdigit():
            current.append(tok)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def _expansions(group: str) -> list[tuple[str, ...]]:
    """Alternative readings of one greedily-parsed digit group.

    Spoken cardinals are ambiguous at group boundaries: "четыреста тридцать
    три" / "төрт жүз отыз үш" is one number (433) but is also exactly how the
    two groups "400, 33" are dictated — same words, same audio. The greedy
    parse merges them; the phone-shape search below may need the split
    reading back, so each merged group also offers its decomposition.
    """
    options: list[tuple[str, ...]] = [(group,)]
    if len(group) == 3 and group[0] != "0" and group[1:] != "00":
        # 433 → 400 + 33 (hundred, then the spoken remainder)
        options.append((group[0] + "00", str(int(group[1:]))))
    elif len(group) == 2 and group[0] != "0" and group[1] != "0":
        # 55 → 50 + 5
        options.append((group[0] + "0", group[1]))
    return options


_MAX_COMBOS = 512


def _phone_from_groups(groups: list[str]) -> str | None:
    """Find a valid KZ phone among the readings of a run of digit groups.

    Tries the plain concatenation first (zero splits), then combinations with
    the fewest group expansions — so an already-valid number is never altered,
    and a merged group is only split when that is what makes the shape valid.
    """
    choices = [_expansions(g) for g in groups]
    total = 1
    for c in choices:
        total *= len(c)
    if total > _MAX_COMBOS:  # degenerate input — only try the plain reading
        choices = [(c[0],) for c in choices]
    combos = sorted(
        product(*choices), key=lambda combo: sum(len(parts) - 1 for parts in combo)
    )
    for combo in combos:
        digits = "".join("".join(parts) for parts in combo)
        if validators.is_valid("phone", digits):
            return digits
    return None


def phone_from_text(text: str, lang: str) -> str | None:
    """Deterministically pull a Kazakhstan phone number out of `text`.

    Works for both dictated words ("сегіз жеті жүз …") and typed digits
    ("+7 701 234 5678", "8 775 815 55 76") by first converting any number-words
    to digits, then reassembling adjacent digit groups into a valid KZ phone
    shape (resolving merged-group ambiguity). Returns None if none is found.
    """
    normalized = spoken_to_digits(text, lang)
    for groups in _digit_group_runs(normalized):
        phone = _phone_from_groups(groups)
        if phone:
            return phone
    return None
