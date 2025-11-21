import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def test_chat_flow():
    print("Testing Chat Flow...")
    
    # 1. Create a chat (by sending a message)
    print("\n1. Creating Chat...")
    payload = {"message": "Hello, testing chat creation."}
    try:
        # This is a streaming endpoint, so we just trigger it and get the ID from headers or list
        # Actually, the endpoint returns a StreamingResponse.
        # We can't easily get the ID from the stream in this script without parsing.
        # But we can list chats afterwards.
        response = requests.post(f"{BASE_URL}/chat", json=payload, stream=True)
        if response.status_code != 200:
            print(f"Failed to create chat: {response.text}")
            return
        
        # Read a bit of the stream to ensure it started
        for line in response.iter_lines():
            if line:
                print("Stream started.")
                break
        
        # 2. List chats
        print("\n2. Listing Chats...")
        response = requests.get(f"{BASE_URL}/chats")
        if response.status_code != 200:
            print(f"Failed to list chats: {response.text}")
            return
        
        chats = response.json()
        if not chats:
            print("No chats found.")
            return
        
        latest_chat = chats[0]
        print(f"Latest Chat: {json.dumps(latest_chat, indent=2)}")
        
        if "id" not in latest_chat:
            print("ERROR: 'id' field missing in chat object!")
            return
        
        chat_id = latest_chat["id"]
        print(f"Chat ID: {chat_id}")
        
        # 3. Get Chat History
        print(f"\n3. Getting History for {chat_id}...")
        response = requests.get(f"{BASE_URL}/chats/{chat_id}")
        if response.status_code != 200:
            print(f"Failed to get history: {response.text}")
            return
        
        history = response.json()
        print(f"History ID: {history.get('id')}")
        if history.get("id") != chat_id:
             print(f"ERROR: History ID mismatch! Expected {chat_id}, got {history.get('id')}")
        
        # 4. Delete Chat
        print(f"\n4. Deleting Chat {chat_id}...")
        response = requests.delete(f"{BASE_URL}/chats/{chat_id}")
        if response.status_code != 200:
            print(f"Failed to delete chat: {response.text}")
            return
        
        print("Delete successful.")
        
        # 5. Verify Deletion
        response = requests.get(f"{BASE_URL}/chats/{chat_id}")
        if response.status_code == 404:
            print("Verification successful: Chat not found.")
        else:
            print(f"ERROR: Chat still exists or error: {response.status_code}")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_chat_flow()
