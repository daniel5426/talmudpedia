import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

try:
    print("Testing models.list() (Non-streaming, simple GET)...")
    response = client.models.list()
    print("Success!")
except Exception as e:
    print(f"Error: {e}")
