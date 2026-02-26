from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from app.agents.tools import get_unprocessed_files, search_movie_metadata, rename_and_move_to_library
from app.services.settings import get_current_model, get_base_url
import os
from dotenv import load_dotenv

load_dotenv()

# We lazily initialize the LLM to use the latest settings/API keys available
def get_librarian_agent():
    api_key = os.getenv("OPENROUTER_API_KEY", os.getenv("OPENAI_API_KEY"))
    if not api_key:
        api_key = "dummy-key-for-testing"
        
    model_name = get_current_model()
    base_url = get_base_url()

    # For OpenAI/OpenRouter APIs
    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url
    )

    tools = [get_unprocessed_files, search_movie_metadata, rename_and_move_to_library]

    system_prompt = """
    You are the 5X49 Librarian Agent, a highly intelligent movie library assistant.
    Your primary job is to clean the user's Inbox directory and file unorganized movie files into the formal library.
    
    Follow these steps exactly:
    1. Call the `get_unprocessed_files` tool to see what needs to be organized.
    2. For each messy file returned:
       a. Identify the likely movie Title and Year from the messy filename (e.g., 'the.matrix.1999.1080p.mkv' -> The Matrix, 1999).
       b. Use your deep knowledge to verify the standard English or primary title of the movie. You can call the `search_movie_metadata` tool if you are unsure.
       c. Call the `rename_and_move_to_library` tool passing the original filename, the exact standard Title you determined, and the Year. Do this one by one for each file.
    3. Once all files are processed, finish by giving a brief, polite summary of what you accomplished.
    
    Think step-by-step. Do not make up file names that haven't been given to you by tools.
    """

    agent_executor = create_react_agent(llm, tools, prompt=system_prompt)
    return agent_executor
