import os
import config  # Ensures load_dotenv() is called
import google.generativeai as genai
from typing import List, Dict
from utils.logger import get_logger

log = get_logger(__name__)

def vet_top_picks(picks: List[Dict]) -> str:
    """
    Sends top picks to Gemini for a 'second opinion' validation.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "[red]Gemini API key not found in .env. Skipping AI validation.[/]"

    try:
        # Explicitly configure using the key from env
        genai.configure(api_key=api_key)
        
        # Using gemini-3.1-flash-lite-preview (2026 compatible)
        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        
        # Prepare the batch prompt
        prompt = "You are an expert MLB betting analyst. Below are the top-rated picks for today's slate from our quantitative model.\n"
        prompt += "Vette these picks based on your internal knowledge of player health, recent performance, situational matchups, and weather.\n"
        prompt += "For each pick, state if you AGREE or DISAGREE and provide a brief expert rationale.\n\n"
        
        for p in picks:
            prompt += f"- {p['player_name']} ({p['team']}): {p['prop_type']} {p['line']} {p['recommendation']} (Model Confidence: {p['confidence']}%)\n"
            prompt += f"  Model Reasoning: {', '.join(p.get('reasoning', []))}\n\n"
        
        prompt += "Please provide a concise, batch response."
        
        log.info(f"Sending {len(picks)} picks to Gemini for validation...")
        response = model.generate_content(prompt)
        return response.text
    except Exception as exc:
        log.error(f"Gemini validation failed: {exc}")
        return f"AI Validation Error: {exc}"
