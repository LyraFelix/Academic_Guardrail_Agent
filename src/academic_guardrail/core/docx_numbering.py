"""Read Word's displayed list numbers and section levels without changing paragraph text."""

from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn

_RESTART_AFTER_BREAK = "{http://schemas.microsoft.com/office/word/2012/wordml}restartNumberingAfterBreak"


def _value(element, child):
    node = element.find(qn("w:" + child)) if element is not None else None
    return node.get(qn("w:val")) if node is not None else None


def _list_definitions(document):
    try:
        numbering = document.part.part_related_by(RT.NUMBERING).element
    except KeyError:
        return {}
    abstracts = {a.get(qn("w:abstractNumId")): a for a in numbering.findall(qn("w:abstractNum"))}
    definitions = {}
    for instance in numbering.findall(qn("w:num")):
        abstract = abstracts.get(_value(instance, "abstractNumId"))
        if abstract is None or abstract.get(_RESTART_AFTER_BREAK) in {"1", "true"}:
            continue
        levels = abstract.findall(qn("w:lvl"))
        top = next((level for level in levels if level.get(qn("w:ilvl")) == "0"), None)
        override = next((node for node in instance.findall(qn("w:lvlOverride")) if node.get(qn("w:ilvl")) == "0"), None)
        if override is not None and override.find(qn("w:lvl")) is not None:
            top = override.find(qn("w:lvl"))
        start = _value(override, "startOverride") or _value(top, "start")
        # No invented key for bullets, Roman numerals, prefixes such as 'A.1',
        # or a definition without a readable start/label.
        if (_value(top, "numFmt") == "decimal" and _value(top, "lvlText") in {"%1", "%1.", "%1)", "(%1)", "[%1]"}
                and start is not None and start.isascii() and start.isdecimal()):
            definitions[instance.get(qn("w:numId"))] = (int(start), len(levels) > 1)
    return definitions


def _properties(element):
    properties = element.find(qn("w:pPr"))
    numbering = properties.find(qn("w:numPr")) if properties is not None else None
    return _value(numbering, "numId"), _value(numbering, "ilvl"), _value(properties, "outlineLvl")


def paragraph_layout(document, paragraphs) -> tuple[dict[int, int | None], dict[int, int]]:
    """Count each concrete numId through the whole body, including tables and earlier lists.

    A present None marks an unsupported list item. The bibliography parser can
    preserve it as a boundary and report its location without assigning a number.
    """
    definitions = _list_definitions(document)
    labels, headings, next_numbers, style_cache = {}, {}, {}, {}
    for index, paragraph in enumerate(paragraphs):
        style_id = paragraph._p.style
        if style_id not in style_cache:
            inherited = (None, None, None)
            style, seen = paragraph.style, set()
            while style is not None and style.style_id not in seen:
                seen.add(style.style_id)
                inherited = tuple(a or b for a, b in zip(inherited, _properties(style.element)))
                style = style.base_style
            style_cache[style_id] = inherited
        direct = _properties(paragraph._p)
        num_id, level, outline = (a or b for a, b in zip(direct, style_cache[style_id]))
        if outline in {"0", "1", "2", "3", "4", "5", "6", "7", "8"}:
            headings[index] = int(outline)
        if num_id is None or num_id == "0":  # Word's explicit cancellation of numbering.
            continue
        labels[index] = None
        if num_id not in definitions:
            continue
        first, multilevel = definitions[num_id]
        if multilevel and direct[1] is None:
            # A style can select a deeper level implicitly. A later top-level
            # value in this same list would then depend on an unknown count.
            del definitions[num_id]
        elif level in {None, "0"}:
            labels[index] = next_numbers.get(num_id, first)
            next_numbers[num_id] = labels[index] + 1
    return labels, headings
