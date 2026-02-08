import json
import os
from openai import OpenAI
from dotenv import load_dotenv
from ddgs import DDGS

# 加载环境变量
load_dotenv(".env.local")

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

def search_web(query):
    """真实联网搜索"""
    print(f"  🔍 [搜索中] {query}...")
    try:
        results = list(DDGS().text(query, max_results=2))
        return results if results else []
    except Exception as e:
        print(f"  ❌ 搜索失败: {e}")
        return []

class StyleExplorerAgent:
    def __init__(self):
        self.model = os.getenv("MODEL_NAME", "z-ai/glm-4.5-air:free")

    def verify_hypothesis(self, movie_a, movie_b, connection_type):
        """
        核心验证逻辑：搜索 A 和 B 的关系证据
        """
        print(f"\n🕵️ [Agent 思考] 正在验证假设：'{movie_a}' 是否受 '{movie_b}' 的 {connection_type} 影响？")
        
        # 构造验证性搜索词
        query = f"\"{movie_a}\" director interview \"{movie_b}\" influence {connection_type}"
        search_results = search_web(query)
        
        if not search_results:
            print("  ⚠️ 无直接证据，尝试放宽搜索...")
            query = f"\"{movie_a}\" influenced by \"{movie_b}\""
            search_results = search_web(query)

        # 让 LLM 根据搜索结果判断真伪
        verification_prompt = f"""
        你是一个极其严谨的事实核查员。
        
        假设：电影《{movie_a}》受电影《{movie_b}》的 [{connection_type}] 方面影响。
        
        搜索证据：
        {json.dumps(search_results, ensure_ascii=False)}
        
        请判断：证据是否支持该假设？
        1. 如果支持，请引用原文中的一句话。
        2. 如果不支持或证据不足，请直接说“证据不足”。
        
        输出格式：简短的一句话结论。
        """
        
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": verification_prompt}]
        )
        
        conclusion = response.choices[0].message.content
        print(f"  ✅ [核查结果] {conclusion}")
        return "证据不足" not in conclusion

    def run_demo(self):
        print("🎬 --- 启动 Style Explorer (带事实核查) ---\n")
        
        # Case 1: 真实存在的联系
        self.verify_hypothesis("Dune (2021)", "Lawrence of Arabia", "Visual Style")
        
        # Case 2: 容易混淆/错误的联系 (测试幻觉)
        # 很多 AI 会误以为《星际穿越》受《星球大战》直接视觉影响，其实是《2001太空漫游》
        self.verify_hypothesis("Interstellar", "Star Wars A New Hope", "Cinematography")

if __name__ == "__main__":
    agent = StyleExplorerAgent()
    agent.run_demo()
