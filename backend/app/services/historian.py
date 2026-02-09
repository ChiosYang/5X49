import json
import os
import time
import requests
from openai import OpenAI
from dotenv import load_dotenv

# 加载环境变量
# Fix: Running from 'backend/' directory via uvicorn
load_dotenv(".env.local")

# API Keys
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "z-ai/glm-4.5-air:free")

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

# ==========================================
# 1. 基础工具 (The Tools)
# ==========================================

def get_movie_metadata(movie_name, tmdb_id=None):
    """获取电影的基础信息：年份、ID、关键词、流派"""
    print(f"  🎬 [TMDB]正在查找电影: {movie_name} (TMDB ID: {tmdb_id})...")
    
    try:
        data = None
        # Priority 1: Direct lookup by TMDB ID
        if tmdb_id:
            url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
            resp = requests.get(url, params={"api_key": TMDB_API_KEY, "language": "en-US"})
            if resp.status_code == 200:
                data = resp.json()
                print(f"  ✅ [TMDB] ID match: {data.get('title')}")
            else:
                print(f"  ⚠️ [TMDB] ID lookup failed for {tmdb_id}, falling back to search.")

        # Priority 2: Search by Name
        if not data:
            url = "https://api.themoviedb.org/3/search/movie"
            params = {"api_key": TMDB_API_KEY, "query": movie_name, "language": "en-US"}
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
    def __init__(self):
        self.model = MODEL_NAME

    def analyze_genealogy(self, movie_name, tmdb_id=None):
        print(f"\n🏛️ --- 正在构建《{movie_name}》的电影谱系 ---\n")
        start_time = time.time()
        
        # Step 1: 获取本体信息
        t0 = time.time()
        metadata = get_movie_metadata(movie_name, tmdb_id=tmdb_id)
        if not metadata:
            return None
        t1 = time.time()
        print(f"  ⏱️ TMDB Data Fetch: {t1 - t0:.2f}s")
            
        print(f"  ✅ 锁定目标: {metadata['title']} ({metadata['year']})")
        
        # Step 2: 溯源与推演 (LLM Drafting)
        prompt = f"""
        你是电影史学家。请深度分析电影《{metadata['title']}》({metadata['year']})。
        
        任务：
        0. [Thought Chain]: 展示你的思考过程。先列出该电影的关键元素，然后联想其可能的前身和后世影响，最后筛选出最确信的联系。
        1. [Genre Definition]: 重新定义它的流派。不仅仅是官方的(如Sci-Fi)，请给出一个更学术、更精准的“微流派”定义(Micro-Genre)。
        2. [Influence Impact]: 用一段话总结它在电影史上的地位和影响力。
        3. [Ancestors]: 列出 2 部在 {metadata['year']} 年之前上映的，对其有重大视觉/主题影响的电影。
        4. [Descendants]: 列出 2 部在 {metadata['year']} 年之后上映的，深受其影响的电影。
        
        CRITICAL INSTRUCTIONS:
        - 只输出你**非常确信 (High Confidence)** 的公认联系。
        - 必须包含：title, year, relation_type (Visual/Narrative/Theme), reason (一句简短解释)。

        输出为标准的 JSON 格式：
        {{
            "thought_chain": "...",
            "micro_genre": "...",
            "influence_impact": "...",
            "ancestors": [{{"title": "...", "year": 19xx, "type": "...", "reason": "..."}}],
            "descendants": [{{"title": "...", "year": 20xx, "type": "...", "reason": "..."}}]
        }}
        """
        
        print(f"  🧠 [Historian] Using model: {self.model}")
        print(f"  🧠 [Historian] Sending request to LLM...")
        t2 = time.time()
        
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        t3 = time.time()
        print(f"  ⏱️ LLM Generation: {t3 - t2:.2f}s")
        print(f"  ⏱️ Total Process: {t3 - start_time:.2f}s")
        
        try:
            timeline = json.loads(response.choices[0].message.content)
            # Merge TMDB metadata
            timeline['tmdb_metadata'] = metadata
            return timeline
        except:
            print("  ❌ LLM 输出格式错误，无法解析。")
            return None
