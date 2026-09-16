"""
Groq Cloud Configuration
"""

import os
from dotenv import load_dotenv
from groq import Groq

# Load environment variables
load_dotenv()

# Model constants
MODEL_COMPOUND = "groq/compound"
MODEL_LLAMA = "openai/gpt-oss-120b"

def get_groq_client():
    """
    Initialize and return Groq client
    
    Returns:
        Groq client instance
    """
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in .env file. Please add your API key.")
    
    return Groq(api_key=api_key)

def get_tavily_api_key():
    """
    Get Tavily API key for search functionality
    
    Returns:
        Tavily API key or None
    """
    return os.getenv('TAVILY_API_KEY')
