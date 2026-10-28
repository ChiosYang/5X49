"""Bounded literal language grammar. Bare nationality adjectives stay countries."""
import re
from app.contracts.languages import LANGUAGE_LABELS

ALIASES={label.casefold():code for code,labels in LANGUAGE_LABELS.items() for label in labels}
ALIASES.update({'汉语':'zh','普通话':'zh','mandarin':'zh','国语':'zh','廣東話':'yue','广东话':'yue','粵語':'yue','广州话':'yue'})
WORDS='|'.join(re.escape(x) for x in sorted(ALIASES,key=len,reverse=True))
NEG=r'(?:not|without|excluding|exclude|不要|排除|不含|不包含|不是)'
PATTERN=re.compile(
 rf'(?P<neg>{NEG}\s*)?(?:(?P<original>original\s+language\s*(?:is|of|:)?\s*|原始语言(?:为|是|[:：])?\s*|原语言(?:为|是|[:：])?\s*)'
 rf'|(?P<spoken>spoken\s+language\s*(?:is|of|:)?\s*|in\s+|片中语言(?:为|是|[:：])?\s*|包含\s*|含有\s*)|(?P<bare>))'
 rf'(?P<language>{WORDS})(?P<suffix>[- ]language\b|\s*(?:对白|对话|电影|影片))?',re.I)

def has_language_request(text):
    if re.search(r"\blanguages?\b|原始语言|片中语言",text,re.I):return True
    return any(m.group('original') or m.group('spoken') or m.group('suffix') or not m.group('language').isascii()
               for m in PATTERN.finditer(text))

def strip_language_clauses(text):
    found=[]
    for m in reversed(list(PATTERN.finditer(text))):
        if not (m.group('original') or m.group('spoken') or m.group('suffix') or not m.group('language').isascii()):
            continue
        # English names are protected by the caller; letters inside another
        # word and partial language prefixes never qualify as a clause.
        if m.group('language').isascii() and (m.start()>0 and text[m.start()-1].isalnum()
                or m.end()<len(text) and text[m.end()].isalnum()):continue
        item={'kind':'original' if m.group('original') else 'spoken',
              'code':ALIASES[m.group('language').casefold()],'exclude':bool(m.group('neg'))}
        found.insert(0,item);text=text[:m.start()]+' '+text[m.end():]
    return text,found
