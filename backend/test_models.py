import os
import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def test_model(model_name):
    print(f"Testing model: {model_name}")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        # Just a simple listing or a small completion
        response = client.models.retrieve(model_name)
        print(f"Success for {model_name}!")
    except Exception as e:
        print(f"Error for {model_name}: {e}")

if __name__ == "__main__":
    test_model("gpt-4o")
    test_model("gpt-5.1")
