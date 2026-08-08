import os
import json
import re
import requests
import config  # Ensures load_dotenv() is called
from pydantic import BaseModel
from typing import List, Dict
from utils.logger import get_logger

log = get_logger(__name__)

class PickVetting(BaseModel):
    player_name: str
    status: str
    reasoning: str

class VettingResponse(BaseModel):
    results: list[PickVetting]

def vet_top_picks(picks: List[Dict]) -> List[Dict]:
    """
    Sends top picks to Gemini for a 'second opinion' validation.
    Returns a list of structured dictionaries containing status and reasoning.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        log.warning("Gemini API key not found in .env. Skipping AI validation.")
        return []

    try:
        model_name = 'gemini-3.1-flash-lite-preview'
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        prompt = "You are an expert MLB betting analyst. Below are the top-rated picks for today's slate from our quantitative model.\n"
        prompt += "Vette these picks based on your internal knowledge of player health, recent performance, situational matchups, and weather.\n"
        prompt += "For each pick, flag the player as 'APPROVED' if it is a strong play, or 'REJECTED' if you have concerns.\n\n"
        prompt += "Return ONLY a raw JSON array of objects, with each object containing exactly 'player_name', 'status', and 'reasoning'. No markdown formatting.\n\n"
        
        for p in picks:
            prompt += f"- {p['player_name']} ({p['team']}): {p['prop_type']} {p['line']} {p['recommendation']} (Model Confidence: {p['confidence']}%)\n"
            prompt += f"  Model Reasoning: {', '.join(p.get('reasoning', []))}\n\n"
            
        log.info(f"Sending {len(picks)} picks to Gemini for validation...")
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.2
            }
        }
        
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        text_response = data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # Clean markdown code blocks if present
        text_response = re.sub(r'^```json\s*', '', text_response)
        text_response = re.sub(r'^```\s*', '', text_response)
        text_response = re.sub(r'\s*```$', '', text_response)
        
        parsed_data = json.loads(text_response)
        
        if isinstance(parsed_data, dict) and "results" in parsed_data:
            return parsed_data["results"]
        elif isinstance(parsed_data, list):
            return parsed_data
        else:
            return []
    except Exception as exc:
        log.error(f"Gemini validation failed: {exc}")
        return []
