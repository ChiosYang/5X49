import json
import os
import time
import requests
from openai import OpenAI
from dotenv import load_dotenv
from dataclasses import dataclass

from app.contracts.analysis_v2 import AnalysisV2Input, AnalysisV2Output

# 加载环境变量
# Fix: Running from 'backend/' directory via uvicorn
load_dotenv(".env.local")

# API Keys
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

# Import settings service for dynamic model selection
from app.services.settings import get_current_model, get_base_url, get_language

# Initialize OpenAI client with dynamic base URL
def get_client():
    """Get OpenAI client with current base URL"""
    return OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url=get_base_url()
    )


ANALYSIS_PROMPT_VERSION = "genealogy-v2.v1"


@dataclass(frozen=True)
class AnalysisModelConfiguration:
    provider: str
    model: str


@dataclass(frozen=True)
class AnalysisGenerationResult:
    output: AnalysisV2Output
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    currency: str | None = None

# ==========================================
# 1. 基础工具 (The Tools)
# ==========================================

def get_movie_metadata(movie_name, tmdb_id=None, lang="en"):
    """获取电影的基础信息：年份、ID、关键词、流派"""
    print(f"  🎬 [TMDB]正在查找电影: {movie_name} (TMDB ID: {tmdb_id}, Lang: {lang})...")
    
    try:
        data = None
        # Priority 1: Direct lookup by TMDB ID
        if tmdb_id:
            url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
            tmdb_lang = "zh-CN" if lang == "zh" else "en-US"
            resp = requests.get(url, params={"api_key": TMDB_API_KEY, "language": tmdb_lang})
            if resp.status_code == 200:
                data = resp.json()
                print(f"  ✅ [TMDB] ID match: {data.get('title')}")
            else:
                print(f"  ⚠️ [TMDB] ID lookup failed for {tmdb_id}, falling back to search.")

        # Priority 2: Search by Name
        if not data:
            url = "https://api.themoviedb.org/3/search/movie"
            tmdb_lang = "zh-CN" if lang == "zh" else "en-US"
            params = {"api_key": TMDB_API_KEY, "query": movie_name, "language": tmdb_lang}
            resp = requests.get(url, params=params)
            search_data = resp.json()
            if search_data.get('results'):
                data = search_data['results'][0]

        if data:
            movie_id = data['id']
            release_date = data.get('release_date', '')
            year = int(release_date[:4]) if release_date else 0
            
            # Fetch Keywords
            keywords_url = f"https://api.themoviedb.org/3/movie/{movie_id}/keywords"
            k_resp = requests.get(keywords_url, params={"api_key": TMDB_API_KEY})
            keywords = [k['name'] for k in k_resp.json().get('keywords', [])][:5]
            
            # Fetch Genres (if not already full details)
            # If we did direct lookup, genres are already in 'data' as list of dicts/names?
            # Direct lookup returns genres as list of objects [{"id": 18, "name": "Drama"}...]
            # Search result returns genre_ids list [18, ...]
            
            genres = []
            if 'genres' in data: # Direct lookup format
                genres = [g['name'] for g in data['genres']]
            else: # Search result format, need details
                details_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
                d_resp = requests.get(details_url, params={"api_key": TMDB_API_KEY})
                if d_resp.status_code == 200:
                    genres = [g['name'] for g in d_resp.json().get('genres', [])]

            return {
                "id": movie_id,
                "title": data['title'],
                "year": year,
                "overview": data['overview'],
                "keywords": keywords,
                "genres": genres
            }
    except Exception as e:
        print(f"  ❌ TMDB Error: {e}")
    return None

class FilmHistorian:
    def __init__(self, *, client_factory=None):
        # Production keeps the dynamic client; isolated evaluation can pin a
        # provider endpoint without changing global settings.
        self._client_factory = client_factory or get_client

    def analysis_configuration(self) -> AnalysisModelConfiguration:
        base_url = get_base_url().casefold()
        if "openrouter.ai" in base_url:
            provider = "openrouter"
        elif "api.openai.com" in base_url:
            provider = "openai"
        else:
            provider = "openai_compatible"
        return AnalysisModelConfiguration(provider=provider, model=get_current_model())

    def analyze_v2(
        self,
        analysis_input: AnalysisV2Input,
        *,
        configuration: AnalysisModelConfiguration | None = None,
    ) -> AnalysisGenerationResult:
        configuration = configuration or self.analysis_configuration()
        schema = AnalysisV2Output.model_json_schema()
        prompt = (
            "You are a film historian. Return only one JSON object that validates against the "
            "provided Analysis V2 schema. Do not include hidden reasoning. Use concise, user-visible "
            "rationales. Use direction=subject_to_target for influences on the subject film and "
            "direction=target_to_subject for later films influenced by the subject. Concept targets "
            "must always use subject_to_target. Prefer tmdb.movie identifiers for film targets when "
            "you are certain; otherwise include display_name and release_year so the reference can "
            "enter review. Evidence URLs must be public HTTP(S) sources.\n\n"
            f"INPUT:\n{analysis_input.model_dump_json()}\n\n"
            f"OUTPUT JSON SCHEMA:\n{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
        )
        client = self._client_factory()
        response = client.chat.completions.create(
            model=configuration.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content
        if not raw_content:
            raise ValueError("Analysis provider returned an empty response")
        output = AnalysisV2Output.model_validate_json(raw_content)
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        raw_cost = getattr(usage, "cost", None)
        try:
            estimated_cost = float(raw_cost) if raw_cost is not None else None
        except (TypeError, ValueError):
            estimated_cost = None
        if estimated_cost is not None and estimated_cost < 0:
            estimated_cost = None
        return AnalysisGenerationResult(
            output=output,
            input_tokens=input_tokens if isinstance(input_tokens, int) and input_tokens >= 0 else None,
            output_tokens=output_tokens if isinstance(output_tokens, int) and output_tokens >= 0 else None,
            estimated_cost=estimated_cost,
            currency="USD" if estimated_cost is not None else None,
        )

    def analyze_genealogy(self, movie_name, tmdb_id=None):
        # Get current model dynamically on each analysis
        self.model = get_current_model()
        print(f"\n🏛️ --- 正在构建《{movie_name}》的电影谱系 ---")
        print(f"🤖 使用模型: {self.model}\n")
        start_time = time.time()
        
        # Step 1: 获取本体信息
        t0 = time.time()
        lang = get_language()
        metadata = get_movie_metadata(movie_name, tmdb_id=tmdb_id, lang=lang)
        if not metadata:
            return None
        t1 = time.time()
        print(f"  ⏱️ TMDB Data Fetch: {t1 - t0:.2f}s")
            
        print(f"  ✅ 锁定目标: {metadata['title']} ({metadata['year']})")
        
        # Step 2: 溯源与推演 (LLM Drafting)
        lang_instruction = (
            "请务必使用 **中文** 进行深度的分析，并输出所有内容。" if lang == "zh"
            else "You are a film historian. Please deeply analyze the movie. ALL analysis, descriptions, and outputs MUST be strictly in **English**."
        )

        prompt = f"""
        你是电影史学家。请深度分析电影《{metadata['title']}》({metadata['year']})。
        
        {lang_instruction}
        
        任务：
        1. [Genre Definition]: 重新定义它的流派。不仅仅是官方的(如Sci-Fi)，请给出一个更学术、更精准的“微流派”定义(Micro-Genre)。
        2. [Influence Impact]: 用一段话总结它在电影史上的地位和影响力。
        3. [Ancestors]: 列出 2 部在 {metadata['year']} 年之前上映的，对其有重大视觉/主题影响的电影。
        4. [Descendants]: 列出 2 部在 {metadata['year']} 年之后上映的，深受其影响的电影。
        
        CRITICAL INSTRUCTIONS:
        - 只输出你**非常确信 (High Confidence)** 的公认联系。
        - 必须包含:title, year, relation_type (Visual/Narrative/Theme), reason (一句简短解释)。

        输出为标准的 JSON 格式：
        {{
            "micro_genre": "...",
            "influence_impact": "...",
            "ancestors": [{{"title": "...", "year": 19xx, "type": "...", "reason": "..."}}],
            "descendants": [{{"title": "...", "year": 20xx, "type": "...", "reason": "..."}}]
        }}
        """
        
        print(f"  🧠 [Historian] Using model: {self.model}")
        print(f"  🌐 [API] Base URL: {get_base_url()}")
        print(f"  🧠 [Historian] Sending request to LLM...")
        t2 = time.time()
        
        # Get fresh client with current base_url
        client = get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        t3 = time.time()
        print(f"  ⏱️ LLM Generation: {t3 - t2:.2f}s")
        print(f"  ⏱️ Total Process: {t3 - start_time:.2f}s")
        
        try:
            raw_content = response.choices[0].message.content
            timeline = json.loads(raw_content)
            # Merge TMDB metadata
            timeline['tmdb_metadata'] = metadata
            return timeline
        except json.JSONDecodeError as e:
            print(f"  ❌ LLM 输出格式错误，无法解析 JSON")
            print(f"  ❌ 错误详情: {e}")
            return None
        except Exception as e:
            print(f"  ❌ 未知错误: {e}")
            return None
