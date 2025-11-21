import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def test_chat_stream():
    print("Testing Chat Stream...")
    
    payload = {"message": "Hello, are you working?"}
    try:
        print("Sending request...")
        response = requests.post(f"{BASE_URL}/chat", json=payload, stream=True)
        print(f"Response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return

        print("Reading stream...")
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                print(f"Received: {decoded_line}")
                try:
                    data = json.loads(decoded_line)
                    if data['type'] == 'token':
                        sys.stdout.write(data['content'])
                        sys.stdout.flush()
                except:
                    pass
        print("\nStream finished.")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_chat_stream()
