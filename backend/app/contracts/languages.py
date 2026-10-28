"""Film language facts: original language and spoken dialogue are distinct."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

ISO_639_1 = frozenset('aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu'.split())
LANGUAGE_LABELS = {
 'en':('English','英语'),'ja':('Japanese','日语'),'zh':('Chinese','中文'),
 'yue':('Cantonese','粤语'),
 'pa':('Punjabi','旁遮普语'),'ur':('Urdu','乌尔都语'),'la':('Latin','拉丁语'),
 'ko':('Korean','韩语'),'fr':('French','法语'),'de':('German','德语'),
 'es':('Spanish','西班牙语'),'it':('Italian','意大利语'),'ru':('Russian','俄语'),
 'pt':('Portuguese','葡萄牙语'),'hi':('Hindi','印地语'),'ar':('Arabic','阿拉伯语'),
 'sv':('Swedish','瑞典语'),'no':('Norwegian','挪威语'),'da':('Danish','丹麦语'),
 'fi':('Finnish','芬兰语'),'nl':('Dutch','荷兰语'),'th':('Thai','泰语'),
 'vi':('Vietnamese','越南语'),'id':('Indonesian','印度尼西亚语'),
 'he':('Hebrew','希伯来语'),'pl':('Polish','波兰语'),'tr':('Turkish','土耳其语'),
}

def language_code(value):
    if not isinstance(value,str) or value not in ISO_639_1 | {'yue'}:
        raise ValueError('Expected an ISO 639-1 language code')
    return value

class LanguageCondition(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['original','spoken']='spoken'
    code: str=Field(strict=True,min_length=2,max_length=3)
    exclude: bool=Field(default=False,strict=True)
    _code=field_validator('code')(language_code)

def tmdb_language_snapshots(details):
    """Missing/null preserves prior observations; valid empty withdraws them.

    Reject a malformed supplied snapshot atomically. Country, title locale and
    edition audio/dubbing tracks never become film dialogue facts.
    """
    snapshots={}
    original=details.get('original_language')
    if original is not None:
        snapshots['original']=() if original=='' else (language_code('yue' if original=='cn' else original),)
    spoken=details.get('spoken_languages')
    if spoken is not None:
        if not isinstance(spoken,list) or any(not isinstance(x,dict) for x in spoken):
            raise ValueError('Invalid spoken language snapshot')
        snapshots['spoken']=tuple(sorted({language_code('yue' if x.get('iso_639_1')=='cn' else x.get('iso_639_1')) for x in spoken}))
    return snapshots
