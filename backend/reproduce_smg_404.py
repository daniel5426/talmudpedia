import requests
import sys

BASE_URL = "http://localhost:8000/api"

def reproduce():
    print("Attempting to fetch 'Sefer Mitzvot Gadol, Positive Commandments:2'")
    
    # URL encoded: Sefer%20Mitzvot%20Gadol%2C%20Positive%20Commandments%3A2
    # This matches the user's failed log entry
    url = f"{BASE_URL}/source/Sefer Mitzvot Gadol, Positive Commandments:2"
    
    try:
        r = requests.get(url)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print("✅ Success! 404 Not Reproducible.")
            data = r.json()
            print(f"HeRef: {data.get('he_ref')}")
            print(f"Ref: {data.get('pages', [{}])[0].get('ref')}")
        else:
            print("❌ Failure! Reproduced 404.")
            print(r.text)
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    reproduce()
