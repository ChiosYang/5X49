"""Lexical matches against the current visible synopsis, with verbatim evidence."""
import re

from app.services.content_request import split_content_request
from app.services.retrieval_policy import LexicalIndex, RetrievalPolicy, anchor_count, features, substantive
from app.services.semantic_search import _safe


def plot_request(question, local):
    _safe(question, 600)
    # Keep preference, reference and unrecognised metadata requests on their
    # existing paths. A topic clause may still have strict filters on either side.
    if re.search(r"\b(?:similar|recommend|mood|style|featuring|favorites?|good|best|like)\b|"
                 r"类似|相似|推荐|治愈|风格|口味|偏好|像.+那样|看完|我喜欢|"
                 r"\b(?:sort(?:ed)? by|newest|oldest)\b|按片名|年份[升降]序|最[新早]优先", question, re.I):
        return None
    topic = re.search(r"\b(?:about|plot|story)\b|关于|讲述|围绕|故事|想看|找一部|.{5}的电影", question, re.I)
    prose = (len(re.findall(r"[\u3400-\u9fff]", question)) >= 6 and not re.search(r"电影|影片", question)
             or len(question.split()) >= 5 and not re.search(r"\b(?:films?|movies?)\b", question, re.I))
    if not topic and not prose:
        return None
    parsed = split_content_request(question, lookup=local.reference_candidates)
    if re.search(r"\b(?:under|over|before|after)\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|"
                 r"\w+teen|\w+ty|hundred|thousand)\b|\b(?:not|without|except)\b|不是|排除|不要", parsed.text, re.I):
        return None
    if parsed.is_content and parsed.hard is not None and not parsed.issue and not parsed.reference:
        return parsed
    return None


# Normalise a small set of colloquial equivalents on both sides. Spaces keep
# adjacent CJK concepts independent. Nothing in this vocabulary identifies a film.
_EQUIVALENTS = (
    (r"送错|错送|误送", "误送"),
    (r"午饭|午餐", "午餐"),
    (r"交(?:上|到)?朋友|成为(?:了)?朋友|建立(?:了)?友谊|结下友谊", "友谊"),
    (r"听不见|听不到|听力(?:损失|受损|丧失)|失去听力|失聪", "听力损失"),
    (r"脚踏车|单车|自行车", "自行车"),
    (r"\b(?:los(?:es?|ing)|lost) (?:his |her |their )?hearing\b", "hearing loss"),
)
_SCAFFOLD = re.compile(r"想看|找一部|渐渐|逐渐|重新|只好|因为|两个人|的电影|的故事")


def _terms_text(text):
    for pattern, form in _EQUIVALENTS:
        text = re.sub(pattern, " " + form + " ", text, flags=re.I)
    return _SCAFFOLD.sub(" ", text).strip()


def _passages(text):
    # Preserve source offsets, including punctuation. Long sentences get
    # overlapping windows so evidence on a window boundary is still visible.
    for paragraph in re.finditer(r"[^\r\n]+", text):
        value = paragraph.group().strip()
        previous = None
        for sentence in re.finditer(r"[^.!?。！？]+[.!?。！？]*", value):
            segment = sentence.group().strip()
            if segment != value and len(segment) <= 240:
                yield segment
            if previous is not None and sentence.end() - previous <= 240:
                yield value[previous:sentence.end()].strip()
            previous = sentence.start()
        for start in range(0, len(value), 120):
            yield value[start:start + 240].strip()
            if start + 240 >= len(value):
                break


def rank_synopses(query, rows):
    originals = {key: text for key, text in rows if text and text.strip()}
    query = _terms_text(query)
    wanted = substantive(features(query))
    if not wanted or not originals:
        return []
    texts = {key: _terms_text(text) for key, text in originals.items()}
    index = LexicalIndex(texts, dict.fromkeys(texts, ()), RetrievalPolicy())
    searchable = wanted.intersection(index.df)
    phrases = set(re.findall(r"(?=([\u3400-\u9fff]{4}))", query))
    ranked = []
    for key, text in originals.items():
        if not wanted.intersection(index.terms[key]):
            continue
        best_weight, excerpt = 0., None
        for passage in _passages(text):
            normalized = texts[key] if passage == text else _terms_text(passage)
            terms = index.terms[key] if passage == text else features(normalized)
            matched = wanted.intersection(terms)
            # A full phrase can be one anchor. Otherwise require independent
            # clues in the very passage shown on the card.
            if not matched:
                continue
            complete_word = len(wanted) == 1 and next(iter(matched)).startswith("w:")
            if not complete_word and query.casefold() not in normalized.casefold():
                if len(matched) / len(wanted) < .18 or index.coverage(searchable, matched) < .45:
                    continue
                if not any(part in normalized for part in phrases) and anchor_count(query, matched) < 2:
                    continue
            weight = sum(index.idf(term) for term in sorted(matched))
            if weight > best_weight or (weight == best_weight and len(passage) < len(excerpt)):
                best_weight, excerpt = weight, passage
        if excerpt is not None:
            ranked.append((index.evidence(query, key).bm25, key, excerpt))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [(key, excerpt) for _, key, excerpt in ranked[:5]]
