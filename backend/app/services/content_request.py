"""Version 2 bounded content/identity/metadata segmentation.

Hard clauses use the existing v2 parser, not the legacy v1 guard. Unsupported
or ambiguous leftovers stop execution. A router cannot repair or discard them.
"""
from dataclasses import dataclass, replace
import re
import unicodedata

from app.contracts.bound_search_plan import SearchPlan
from app.services.discovery_search import _LANGUAGES, unsupported_reason
from app.services.search_literals import hard_plan
from app.services.semantic_search import _safe
from app.services.content_clauses import guard_text, partition, reference_tail, parts, constraint_plan, unconsumed_mandatory


@dataclass(frozen=True)
class ContentRequest:
    hard: SearchPlan | None
    text: str
    reference: str | None = None
    issue: str | None = None
    is_content: bool = True
    reference_focus: str | None = None
    reference_year: int | None = None
    choice_titles: tuple[str, ...] = ()


_HARD_TAIL = re.compile(
    r"(?:[,;，；]\s*(?:(?:and|but)\s+|但是|但)?|\s+(?:(?:and|but)\s+)?)"
    r"(?=(?:before|after|since|through)\s+(?:18|19|20|21)\d{2}\b|"
    r"(?:under|over|at least|at most|less than|more than|shorter than|longer than)\s*\d|"
    r"(?:excluding|exclude|except|without|not(?!\s+(?:only|just|merely|simply|necessarily))|do not recommend)\b|"
    r"(?:starring|directed by)\s|(?:未看|已看)|"
    r"(?:片长|时长)?\d+\s*(?:分钟|小时)|(?:不超过|不少于|少于|超过)\s*\d|"
    r"(?:18|19|20|21)\d{2}年|(?:排除|不要(?!求))(?:由)?|由[^，。；]{1,100}(?:执导|主演))", re.I)
_HARD_CUE = re.compile(
    r"\b(?:unwatched|watched|unseen|starring|directed|excluding|exclude|except|without|not|"
    r"minutes?|hours?|runtime|duration|produced|written|dubbed|rating|rated|resolution)\b|"
    r"\b(?:before|after|since|through|between|under|over|at least|at most)\s+\d|"
    r"(?<!\d)(?:18|19|20|21)\d{2}(?:s\b|年|年代|\b)|"
    r"未看|已看|没看|看过|执导|导演|主演|出演|排除|不要(?!求)|不含|片长|分钟|小时|"
    r"制片|编剧|配音|语言为|语言是|评分|字幕|分辨率", re.I)
_SEMANTIC_NEGATION = re.compile(r"\b(?:without|except|excluding|not|never|no)\b|不要(?!求)|不是|并非|不含|没有|不涉及|不包含|排除", re.I)
_LANGUAGE_CONDITION = re.compile(rf"\bin\s+(?:{_LANGUAGES})\b|\b(?:{_LANGUAGES})[- ](?:language|speaking)\b|"
    r"\b(?:languages?|dubbed|dubbing|audio)\b|日语|法语|英语|韩语|中文|汉语|国语|德语|意大利语|西班牙语|粤语|配音", re.I)
_TOPIC = re.compile(r"\b(?:with a story about|whose story is about|about)\s+|关于|讲述|主题为|有关|围绕", re.I)
_REF_CUE = re.compile(r"\b(?:similar to|more like|like|liked|enjoyed|loved)\b|类似|像|我喜欢|我喜爱|喜欢|看完|想延续|吸引我|相近|相似|(?:想|请)?找(?:和|与)", re.I)
_OTHER = re.compile(r"\b(?:other|else|similar|recommend(?:ations?)?|suggest(?:ions?)?|like)\b|其他|别的|还可以|还有|类似|那样|那种|这样|推荐|建议|相近|相似|想找.{0,80}(?:片|电影)", re.I)
_QUOTED = re.compile(r"""《([^》]+)》|“([^”]+)”|"([^"]+)"|'([^']+)'""")


# Closed recommendation vocabulary, not a stop-word remover. A whole segment
# must contain only these words; ANY unknown/content/constraint word keeps the
# complete segment as a focus. Theme, style, plot and negation are deliberately
# absent. Token boundaries prevent partial matches inside substantive words.
_REFERENCE_SCAFFOLD_EN = frozenset("""
    a an the any some another other others more else something anything similar
    film films movie movies recommendation recommendations suggestion suggestions
    what which what's can could would should may will i i'd me my you your we us
    watch see try recommend suggest find give get have is are be do to for next
    please thanks thank very much lot if possible and
""".split())
_REFERENCE_SCAFFOLD_ZH = re.compile(
    r"电影|影片|片子|推荐|建议|类似|相似|其他|其它|别的|还有|有没有|"
    r"什么|哪些|能不能|能否|可否|可以|接下来|接着|一些|一部|几部|观看|看看|"
    r"谢谢|多谢|麻烦|拜托|我|你|您|有|还|能|看|找|给|再|点|的|请|吗|呢|吧|了")
_REFERENCE_SCAFFOLD_TOKENS = re.compile(
    r"[a-z]+(?:'[a-z]+)?|[\u3400-\u9fff]+|[^\s,.;:!?，。；：！？—–-]")


def _reference_scaffold(text):
    tokens = _REFERENCE_SCAFFOLD_TOKENS.findall(text.casefold().replace("’", "'"))
    return bool(tokens) and all(word in _REFERENCE_SCAFFOLD_EN
                               or not _REFERENCE_SCAFFOLD_ZH.sub("", word) for word in tokens)


def _reference_focus(aspect, tail):
    parts = [part.strip(" 的,，。；.!?！？") for part in (aspect, tail)]
    parts = [part for part in parts if part and not _reference_scaffold(part)]
    return " ".join(parts) or None


def short_keyword(question):
    scaffold = re.search(r"\b(?:movies?|films?|about|similar|like|plot|story|theme|mood)\b|"
                         r"电影|影片|关于|剧情|故事|主题|推荐|类似", question, re.I)
    return not scaffold and len(re.findall(r"[A-Za-z0-9]+", question)) <= 1 and len(question) <= 12


def _reference(text, mentions):
    quoted = [{"title": next(v for v in m.groups() if v is not None), "start": m.start(), "end": m.end()}
              for m in _QUOTED.finditer(text)]
    candidates = quoted + ([m for m in mentions(text) if not any(m["start"] < q["end"] and q["start"] < m["end"] for q in quoted)]
                           if mentions else [])
    # Qualify title identity before classifying references. A numeric local
    # title can also match the adjacent parenthesized year; that span is not a
    # second film mention. Other title mentions keep their ambiguity guards.
    year_spans = []
    for row in candidates:
        match = re.match(r"\s*\(((?:18|19|20)\d{2}|2100)\)", text[row["end"]:])
        if match:
            year_spans.append((row["end"] + match.start(), row["end"] + match.end()))
    candidates = [row for row in candidates if not any(
        left <= row["start"] and row["end"] <= right for left, right in year_spans)]
    relevant = []
    for row in candidates:
        before, after = text[:row["start"]], text[row["end"]:]
        if re.search(r"(?:\b(?:excluding|except|not)|排除|不要)\s*$", before, re.I):
            continue
        if (re.search(r"(?:\b(?:similar to|more like|like)\s*|类似(?:于)?\s*|像\s*)$", before, re.I)
                or _REF_CUE.search(before + after) and (_OTHER.search(after) or _reference_scaffold(after))
                or re.match(r"(?:那样|那种|这样|这样的电影|类似的电影|相似的电影)", after)):
            relevant.append(row)
    if len(relevant) > 1:
        return None, "ambiguous_reference"
    if relevant:
        anchor = relevant[0]
        for other in candidates:
            if other is anchor or other["start"] < anchor["end"]:
                continue
            if re.fullmatch(r"\s*(?:and|or|&|和|与|、)\s*", text[anchor["end"]:other["start"]], re.I):
                return None, "ambiguous_reference"
        return relevant[0], None
    if quoted:
        first = quoted[0]
        if re.search(r"(?:\b(?:similar to|like)\s*|类似(?:于)?\s*|像\s*)$", text[:first["start"]], re.I):
            return first, None
    plain = re.search(r"(?:\b(?:similar to|like)\s+|类似(?:于)?\s*)(.+)$", text, re.I)
    if plain:
        return {"title": plain[1].strip(" .。!?！？"), "start": plain.start(1), "end": len(text)}, None
    return None, None


def _content_issue(content, context=None):
    guarded = guard_text(content, context)
    if unconsumed_mandatory(guarded):
        return "incomplete_request"
    if _SEMANTIC_NEGATION.search(guarded):
        return "unsupported_content_negation"
    if _LANGUAGE_CONDITION.search(guarded) or re.fullmatch(r"in\s+[A-Z][A-Za-z-]+", guarded.strip()):
        return "unsupported_filter"
    if _HARD_CUE.search(guarded):
        return "incomplete_request"


def _protected_topic_prefix(prefix, context, lookup):
    # A later "about" can follow a complete narrative contrast sentence. Only
    # proven contrast/soft clauses, complete hard plans and closed introduction
    # scaffolds can precede it; unknown factual fragments stay hard errors.
    clauses = list(parts(prefix))
    changed = False
    for clause in clauses:
        if not clause:
            continue
        guarded = guard_text(clause, context)
        if guarded != clause:
            if _content_issue(clause, context):
                return False
            changed = True
            continue
        plan, issue = hard_plan(clause, lookup, allow_languages=True)
        if plan is not None and not issue:
            continue
        if re.fullmatch(r"(?:I mean|I am looking for|I'm looking for) (?:a|the) (?:story|film|movie)", clause, re.I):
            continue
        return False
    return changed


def _parsed(prefix, content, suffix, lookup, reference=None):
    if not content:
        return ContentRequest(None, content, issue="ambiguous_request")
    def content_guard(value, context=None):
        return _content_issue(value, ("story " if reference else "") + (context or content))
    segmented = partition(content, lookup, content_guard, hard_context=prefix + " ; " + suffix)
    if segmented is not None:
        extra, content, issue = segmented
        if issue:
            return ContentRequest(None, content or "", issue=issue)
        suffix = (extra or "") + " ; " + suffix
    issue = content_guard(content)
    if issue:
        return ContentRequest(None, content, issue=issue)
    plan, issue = constraint_plan(prefix + " ; " + suffix, lookup)
    return ContentRequest(plan, content, reference, issue)


def _alternative_request(text, lookup, mentions):
    if not mentions:
        return None
    clauses = list(parts(text))
    for index, clause in enumerate(clauses):
        found = mentions(clause)
        if len(found) != 2:
            continue
        masked = clause
        for row in reversed(found):
            masked = masked[:row["start"]] + " TITLE " + masked[row["end"]:]
        # Consume the whole uncertainty declaration, never an arbitrary tail
        # that might also carry a year, language or exclusion requirement.
        if not re.fullmatch(
            r"(?:(?:英文名|片名)\s*)?(?:我)?(?:记不清|不确定)(?:是)?\s*TITLE\s*(?:还是|或是|或者)\s*TITLE[ .!?！？]*|"
            r"(?:I(?: am|'m)?\s+)?(?:am )?(?:not sure|can['’]t remember)(?: whether| if)?\s*TITLE\s+or\s+TITLE[ .!?！？]*",
            masked.strip(), re.I):
            continue
        names = tuple(row["title"] for row in found)
        body = ",".join(clauses[:index] + clauses[index + 1:]).strip(" ,;。.!?！？")
        quote = _QUOTED.search(body)
        if quote and re.fullmatch(r"(?:请)?(?:帮我)?找(?:那部|这部)?\s*|(?:please )?(?:find|show me)(?: the)?(?: film| movie)?\s*", body[:quote.start()], re.I) and not body[quote.end():].strip():
            # Literal uncertainty needs a more specific title/year, not a
            # semantic reference selection or a guessed recommendation.
            return ContentRequest(None, text, issue="ambiguous_film")
        parsed = split_content_request(body, lookup=lookup, mentions=mentions)
        if parsed.choice_titles:
            # Independent uncertainty declarations cannot overwrite each other,
            # even if a recursively parsed declaration was otherwise valid.
            return ContentRequest(None, text, issue="ambiguous_reference")
        if parsed.reference and not parsed.issue:
            return replace(parsed, choice_titles=names)
        return ContentRequest(None, text, issue="ambiguous_reference")
    return None


def split_content_request(question, *, lookup=None, mentions=None):
    _safe(question, 600)
    text = unicodedata.normalize("NFKC", question).strip()
    alternative = _alternative_request(text, lookup, mentions)
    if alternative is not None:
        return alternative
    ref, issue = _reference(text, mentions)
    if issue:
        return ContentRequest(None, text, issue=issue)
    if ref:
        before, after = text[:ref["start"]], text[ref["end"]:]
        year_match = re.match(r"\s*\(((?:18|19|20)\d{2}|2100)\)", after)
        reference_year = int(year_match[1]) if year_match else None
        if year_match:
            after = after[year_match.end():]
        after = reference_tail(after, ref["title"])
        cues = list(_REF_CUE.finditer(before))
        prefix = before[:cues[-1].start()] if cues else before
        aspect = before[cues[-1].end():] if cues else ""
        if _HARD_CUE.search(guard_text(aspect)) or _LANGUAGE_CONDITION.search(guard_text(aspect)):
            return ContentRequest(None, text, issue="incomplete_request")
        if re.fullmatch(r"\s*(?:I|我|Something|More)\s*", prefix, re.I) or _reference_scaffold(prefix):
            prefix = ""
        # Every remaining prefix is a hard clause or an unhandled constraint.
        # Lack of a word such as "film" cannot authorize silently dropping it.
        prefix = re.sub(r"(?:找)?与\s*$", "", prefix)
        split = _HARD_TAIL.search(after)
        focus = after[:split.start()] if split else after
        suffix = after[split.end():] if split else ""
        focus = re.sub(r"^(?:那样|那种|这样|一样|的电影|的影片|电影|影片)", "", focus).strip(" 的,。；.!?！？")
        reference_focus = _reference_focus(aspect, focus)
        content = reference_focus or ref["title"]
        parsed = _parsed(prefix, content, suffix, lookup, ref["title"])
        # Years or role-like words inside the known reference title are literal.
        if not reference_focus and parsed.issue in {"incomplete_request", "unsupported_filter"}:
            plan, issue = hard_plan(prefix + " " + suffix, lookup)
            return ContentRequest(plan, ref["title"], ref["title"], issue, reference_year=reference_year)
        return ContentRequest(parsed.hard, parsed.text, parsed.reference, parsed.issue,
                              parsed.is_content, parsed.text if reference_focus else None, reference_year)
    topic = _TOPIC.search(text)
    if topic:
        if _protected_topic_prefix(text[:topic.start()].strip(), text, lookup):
            segmented = partition(text, lookup, _content_issue)
            if segmented is not None:
                hard, content, issue = segmented
                if issue:
                    return ContentRequest(None, text, issue=issue)
                return _parsed(hard, content, "", lookup)
            return _parsed("", text, "", lookup)
        tail = text[topic.end():]
        split = _HARD_TAIL.search(tail)
        content = (tail[:split.start()] if split else tail).strip(" 的,。；.!?！？")
        suffix = tail[split.end():] if split else ""
        return _parsed(text[:topic.start()], content, suffix, lookup)
    # Only a complete factual prefix establishes a comma/colon boundary.
    for boundary in re.finditer(r"[,;:，；：]", text):
        prefix, tail = text[:boundary.start()], text[boundary.end():].strip()
        if not re.search(r"\b(?:films?|movies?|released|directed|starring|minutes?|runtime)\b|电影|影片|上映|执导|导演|片长|分钟", prefix, re.I):
            continue
        plan, prefix_issue = hard_plan(prefix, lookup)
        if not prefix_issue and plan != SearchPlan(version="search-plan.v2") and tail:
            split = _HARD_TAIL.search(tail)
            content = (tail[:split.start()] if split else tail).strip(" 的,。；.!?！？")
            suffix = tail[split.end():] if split else ""
            return _parsed(prefix, content, suffix, lookup)
    segmented = partition(text, lookup, _content_issue)
    if segmented is not None:
        hard, content, issue = segmented
        if issue:
            return ContentRequest(None, text, issue=issue)
        return _parsed(hard, content, "", lookup)
    plan, plan_issue = hard_plan(text, lookup)
    if not plan_issue:
        return ContentRequest(plan, "", is_content=False)
    issue = _content_issue(text)
    if issue:
        return ContentRequest(None, text, issue=issue)
    reason = unsupported_reason(guard_text(text))
    if reason in {"unsupported_filter", "non_search", "negation"}:
        return ContentRequest(None, text, issue=reason)
    if reason == "multiple_values" and not re.search(r"\b(?:story|stories|theme|plot|about)\b|想看|故事|剧情|证词|记忆|感知", text, re.I):
        return ContentRequest(None, text, issue=reason)
    return ContentRequest(SearchPlan(version="search-plan.v2"), text)
