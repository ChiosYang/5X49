import os
import shutil
import httpx
from langchain_core.tools import tool
from typing import Dict, Any
from app.services.settings import get_media_dir

@tool
def get_unprocessed_files() -> list[str]:
    """Scan the Inbox directory and return a list of all unprocessed, messy video filenames. Use this tool first when asked to clear the inbox."""
    # Assuming the app runs in Docker, MEDIA_DIR is usually /media. 
    # For local development we use the settings/env.
    media_root = get_media_dir() or os.getenv("MEDIA_DIR", "/media")
    inbox_dir = os.path.join(media_root, "inbox")
    
    if not os.path.exists(inbox_dir):
        # Return empty list instead of a string to avoid confusing the ReAct agent
        return []
        
    try:
        files = os.listdir(inbox_dir)
        # Filter standard video extensions
        video_files = [f for f in files if f.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.ts'))]
        if not video_files:
            return []
        return video_files
    except Exception as e:
        return [f"Error reading inbox directory: {str(e)}"]

@tool
def search_movie_metadata(query: str, year: str = None) -> str:
    """When you are not sure about a movie's correct standard name and release year from a messy filename, call this tool to search TMDB for the standard information. This tool might use an LLM or an API hook under the hood."""
    # Since we lack a dedicated TMDB API key in this demo, we'll return a simulated response, 
    # but in reality, you would use httpx to call TMDB.
    # To make this real, the LLM itself usually knows or we can ask OpenRouter.
    # For simplicity, we just advise the LLM to use its own parametric memory if it doesn't need to actually ping an API,
    # But a true tool would look like this:
    import json
    return json.dumps({
        "status": "success", 
        "message": f"Please use your own internal knowledge to determine the exact title and year for '{query}' (approx year {year}). This search tool is currently a stub for demonstration."
    })

@tool
def rename_and_move_to_library(original_filename: str, standard_title: str, year: str) -> str:
    """
    Rename a messy file to the standard convention 'Title (Year)/Title (Year).ext' and move it to the formal media library.
    Use this tool ONLY after you are highly confident in the standard_title and year.
    Call this tool once for each file you process.
    """
    media_root = get_media_dir() or os.getenv("MEDIA_DIR", "/media")
    inbox_dir = os.path.join(media_root, "inbox")
    
    source_path = os.path.join(inbox_dir, original_filename)
    if not os.path.exists(source_path):
        return f"Error: Source file {original_filename} does not exist in {inbox_dir}."
        
    # extract extension
    ext = os.path.splitext(original_filename)[1]
    
    # Safe folder name (strip problematic chars) 
    safe_title = "".join([c for c in standard_title if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).strip()
    
    new_folder_name = f"{safe_title} ({year})"
    new_filename = f"{safe_title} ({year}){ext}"
    
    target_dir = os.path.join(media_root, new_folder_name)
    target_path = os.path.join(target_dir, new_filename)
    
    try:
        os.makedirs(target_dir, exist_ok=True)
        shutil.move(source_path, target_path)
        return f"Success: Moved '{original_filename}' to library as '{new_folder_name}/{new_filename}'"
    except Exception as e:
        return f"Error moving file: {str(e)}"
