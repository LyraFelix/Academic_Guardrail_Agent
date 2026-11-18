"""Search-only spellings. Every match maps back to a slice of the supplied text."""

import re
from dataclasses import dataclass


_HAN = (r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
        r"\U00020000-\U0002fa1f\U00030000-\U000323af")
_HAN_CHARACTER = re.compile(f"[{_HAN}]")
_WORD = rf"[^\W{_HAN}]"  # Han delimits Latin/numeric tokens even without spaces.
_LETTER = r"[^\W\d_]"
_HYPHEN = r"[-\u2010\u2011]"
_WRAPPED = rf"(?<={_LETTER}){_HYPHEN}[ \t]*\r?\n[ \t]*(?={_LETTER})"
_JOIN = "\u00ad"  # Internal mark for an ambiguous printed line-end hyphen.
_LAYOUT = re.compile(
    rf"(?P<wrap>{_WRAPPED})|(?P<soft>\u00ad(?:[ \t]*\r?\n[ \t]*)?)|"
    rf"(?P<hyphen>(?<={_LETTER}){_HYPHEN}(?=[^\W_])|(?<=\d){_HYPHEN}(?={_LETTER}))|"
    r"(?P<space>\s+)|(?P<sign>[−+\-][ \t]*(?=\d))|.", re.DOTALL)


def _flexible_spelling(value: str) -> str:
    """At a printed line break a hyphen can join letters or separate compound parts."""
    parts = []
    for i, char in enumerate(value):
        if char == " ":
            parts.append(f"[ {_JOIN}]")
        elif char == _JOIN:
            parts.append(f"[ {_JOIN}]?")
        else:
            if i and char.isalpha() and value[i - 1].isalpha():
                parts.append(_JOIN + "?")
            parts.append(re.escape(char))
    return "".join(parts)


def whole_term_pattern(term: str, *, normalized: bool = False) -> re.Pattern:
    """Escape user punctuation and exclude Latin word and numeric fragments."""
    left = "" if _HAN_CHARACTER.fullmatch(term[0]) else rf"(?<!{_WORD})"
    right = "" if _HAN_CHARACTER.fullmatch(term[-1]) else rf"(?!{_WORD})"
    if normalized:
        # Do not take 'arm' from a possibly wrapped 'fore-\narm'.
        left = left + f"(?<!{_JOIN})" if left else ""
        right = right + f"(?!{_JOIN})" if right else ""
    pattern = left + (_flexible_spelling(term) if normalized else re.escape(term)) + right
    if term[0].isdigit():
        pattern = r"(?<!\d[.,])" + pattern
        if normalized:
            pattern = r"(?<![.+−-])" + pattern  # Also excludes the 25 in .25.
    if term[-1].isdigit():
        pattern += r"(?![.,]\d)"
    return re.compile(pattern, re.IGNORECASE)


@dataclass
class SearchView:
    source: str
    text: str
    starts: list[int]
    ends: list[int]

    def spans(self, pattern: re.Pattern) -> list[tuple[int, int]]:
        """Offsets are half-open, relative to the original unmodified passage."""
        found = []
        for match in pattern.finditer(self.text):
            start = self.starts[match.start()]
            end = self.ends[match.end() - 1]
            # An in-word hyphen is searchable as a space (model-12/model 12).
            # An unsigned numeric query still cannot take the 12 out of -12.
            if (self.text[match.start()].isdigit() and start
                    and self.source[start - 1] in "-−+‐‑"):
                continue
            found.append((start, end))
        return found


# Only the operator between two digits changes. Each operand retains its own
# coordinates (a match for one operand does not point at the whole expression).
_DIMENSION = re.compile(r"(?<=\d) *(?:×|x|by) *(?=\d)")
_CARDINALS = dict(zip("zero one two three four five six seven eight nine ten".split(),
                      map(str, range(11))))
_NUMBER_WORDS = (list(_CARDINALS) +
                 "eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen "
                 "twenty thirty forty fifty sixty seventy eighty ninety hundred thousand "
                 "million billion trillion point".split())
_NUMBER_WORD = "(?:" + "|".join(map(_flexible_spelling, _NUMBER_WORDS)) + ")"
# Read an entire written number. Only an isolated small cardinal is folded.
# This prevents 'two thousand' or 'twenty-two' becoming a search hit for 2.
_NUMBER_PHRASE = rf"{_NUMBER_WORD}(?:(?: and |[ {_JOIN}]){_NUMBER_WORD})*"
_SPELLINGS = {
    "batchnorm": ["bn", "batchnorm", "batch norm", "batch normalization", "batch normalisation",
                  "batchnormalization", "batchnormalisation"],
    "layernorm": ["ln", "layernorm", "layer norm", "layer normalization", "layer normalisation",
                  "layernormalization", "layernormalisation"],
    "convolution": ["conv", "convs", "convolution", "convolutions"],
    "pretrain": [prefix + word for prefix in ("pre", "pre ")
                 for word in ("train", "trains", "trained", "training")],
    "finetune": [prefix + word for prefix in ("fine", "fine ")
                 for word in ("tune", "tunes", "tuned", "tuning")],
}
_ALIASES = "|".join(f"(?P<{key}>{'|'.join(map(_flexible_spelling, words))})"
                    for key, words in _SPELLINGS.items())
_LEXICAL = re.compile(rf"(?<!{_WORD})(?<!{_JOIN})(?:{_ALIASES}|(?P<number>{_NUMBER_PHRASE}))"
                      rf"(?!{_WORD})(?!{_JOIN})")


def _layout_view(source: str) -> SearchView:
    parts, starts, ends = [], [], []
    for match in _LAYOUT.finditer(source):
        kind = match.lastgroup
        if kind == "soft":
            continue
        if kind == "wrap":
            value = _JOIN
        elif kind in {"space", "hyphen"}:
            value = " "
            if parts and parts[-1] == " ":
                ends[-1] = match.end()
                continue
        elif kind == "sign":
            value = "+" if match.group()[0] == "+" else "-"
        else:
            # Unicode casefold also expands presentation ligatures such as ﬁ;
            # it leaves meaningful symbols such as full-width percent distinct.
            value = match.group().casefold()
        parts.append(value)
        starts.extend([match.start()] * len(value))
        ends.extend([match.end()] * len(value))
    return SearchView(source, "".join(parts), starts, ends)


def _replace(view: SearchView, pattern: re.Pattern, *, dimensions: bool = False) -> SearchView:
    """Copy untouched coordinates; a folded word/operator maps to its full raw span."""
    parts, starts, ends = [], [], []
    cursor = 0
    for match in pattern.finditer(view.text):
        replacement = "×" if dimensions else match.lastgroup
        if replacement == "number":
            replacement = _CARDINALS.get(match.group().replace(_JOIN, ""))
        if not replacement or replacement == match.group():
            continue
        left, right = match.span()
        parts.extend((view.text[cursor:left], replacement))
        starts.extend(view.starts[cursor:left])
        starts.extend([view.starts[left]] * len(replacement))
        ends.extend(view.ends[cursor:left])
        ends.extend([view.ends[right - 1]] * len(replacement))
        cursor = right
    if not parts:
        return view
    parts.append(view.text[cursor:])
    starts.extend(view.starts[cursor:])
    ends.extend(view.ends[cursor:])
    return SearchView(view.source, "".join(parts), starts, ends)


def search_view(text: str) -> SearchView:
    """Build one mapped view; mixed wrapped words and compounds can match independently."""
    view = _replace(_layout_view(text), _LEXICAL)
    return _replace(view, _DIMENSION, dimensions=True)
