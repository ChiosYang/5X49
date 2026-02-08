import json
from ddgs import DDGS
from openai import OpenAI
import os
import requests
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(".env.local")

# 1. 初始化客户端 (使用 OpenRouter)
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

# ==========================================
# 第一步：定义工具 (The "Hands")
# ==========================================
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "你的KEY")

def get_tmdb_data(resource_type, query_or_id, sub_type=None, filter_path=None, filter_query=None):
    """
    混合动力 TMDB 获取器：Enum 路由 + 动态过滤
    """
    params = {"api_key": TMDB_API_KEY, "language": "zh-CN"}
    endpoint = ""

    if resource_type == "search_movie":
        endpoint = "/search/movie"
        params["query"] = query_or_id
    elif resource_type == "search_person":
        endpoint = "/search/person"
        params["query"] = query_or_id
    elif resource_type == "movie":
        endpoint = f"/movie/{query_or_id}"
        if sub_type: endpoint += f"/{sub_type}"
    elif resource_type == "person":
        endpoint = f"/person/{query_or_id}"
        if sub_type: endpoint += f"/{sub_type}"

    url = f"https://api.themoviedb.org/3{endpoint}"
    print(f"\n[系统日志] Agent 调用 API: {endpoint}")
    if filter_path:
        print(f"[系统日志] 正在执行硬过滤: 路径={filter_path} 条件={filter_query}")

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        # 动态过滤逻辑
        if filter_path and filter_path in data:
            result_list = data[filter_path]
            if isinstance(result_list, list) and filter_query:
                result_list = [
                    item for item in result_list 
                    if all(str(item.get(k)) == str(v) for k, v in filter_query.items())
                ]
            data = result_list

        if isinstance(data, list):
            data = data[:50]

        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return f"TMDB 数据获取失败: {e}"

def web_search(query):
    print(f"\n[系统日志] 正在搜索互联网: {query}...")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        return f"搜索失败: {str(e)}"

# ==========================================
# 第二步：定义工具 (The "Manual")
# ==========================================

tools = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": { "type": "string", "description": "关键词" }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tmdb_data",
            "description": "获取 TMDB 电影/人物数据。警告：查询 'movie_credits' 时必须配合 filter_path='crew' 和 filter_query={'job': 'Director'} 以过滤掉 Thanks 致谢名单等脏数据！",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_type": {
                        "type": "string",
                        "enum": ["search_movie", "search_person", "movie", "person"],
                        "description": "资源大类"
                    },
                    "query_or_id": {
                        "type": "string",
                        "description": "搜索词或 ID"
                    },
                    "sub_type": {
                        "type": "string",
                        "enum": ["credits", "recommendations", "movie_credits", "images"],
                        "description": "子类别。查作品集必选 movie_credits"
                    },
                    "filter_path": {
                        "type": "string",
                        "enum": ["crew", "cast"],
                        "description": "过滤路径。查导演必填 'crew'，查演员必填 'cast'"
                    },
                    "filter_query": {
                        "type": "object",
                        "description": "匹配条件。如查导演设为 {'job': 'Director'}"
                    }
                },
                "required": ["resource_type", "query_or_id"]
            }
        }
    }
]

# ==========================================
# 第三步：构建 Agent 的思考与执行循环 (The "Brain" & "Loop")
# ==========================================

def run_agent(user_query):
    system_prompt = """你是一个极其严谨的电影数据专家。你严禁给出错误的信息。

工作准则：
1. **拒绝脏数据（核心）**：TMDB 的作品集数据包含大量 Thanks（致谢）噪音。你**必须**在调用 get_tmdb_data 时通过过滤参数将其剔除。
   - 正确调用示例：get_tmdb_data(resource_type='person', sub_type='movie_credits', filter_path='crew', filter_query={'job': 'Director'})
   - 错误调用示例：不带 filter_path 和 filter_query 直接查作品集（这会导致你把致谢名单当成导演作品）。
2. **两步检索**：先 search_person 拿 ID，再查作品集。
3. **身份核实**：只列出真正由其执导（Director）或出演（Cast）的作品。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query}
    ]
    print(f"用户: {user_query}")

    available_functions = {
        "web_search": web_search,
        "get_tmdb_data": get_tmdb_data
    }

    max_steps = 8
    search_count = 0
    max_searches = 2
    
    for step in range(max_steps):
        response = client.chat.completions.create(
            model=os.getenv("MODEL_NAME"),
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        response_message = response.choices[0].message
        messages.append(response_message)

        if response_message.tool_calls:
            print(f"[系统日志] Step {step + 1}: Agent 决定调用工具")
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_to_call = available_functions.get(function_name)
                
                if not function_to_call: continue

                try:
                    function_args = json.loads(tool_call.function.arguments)
                    print(f"[系统日志] 执行: {function_name}(**{function_args})")
                    
                    if function_name == "web_search":
                        if search_count >= max_searches:
                            messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": function_name, "content": "搜索上限。"})
                            continue
                        search_count += 1

                    function_response = function_to_call(**function_args)
                    
                    if not isinstance(function_response, str):
                        function_response = json.dumps(function_response, ensure_ascii=False)
                        
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    })
                except Exception as e:
                    messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": function_name, "content": str(e)})
            continue
        else:
            return response_message.content

    return "达到最大步数。"

if __name__ == "__main__":
    final_answer = run_agent("告诉我维纶纽瓦有哪些电影？")
    print("-" * 50)
    print(f"Agent 回答:\n{final_answer}")
