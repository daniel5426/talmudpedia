import requests
import json

BASE_URL = "http://localhost:8000"

def verify_list_chats():
    print("Verifying List Chats...")
    try:
        response = requests.get(f"{BASE_URL}/chats")
        if response.status_code != 200:
            print(f"Failed to list chats: {response.text}")
            return
        
        chats = response.json()
        print(f"Found {len(chats)} chats.")
        
        if chats:
            first_chat = chats[0]
            print(f"First Chat: {json.dumps(first_chat, indent=2)}")
            
            if "id" in first_chat and isinstance(first_chat["id"], str):
                print("SUCCESS: 'id' field is present and is a string.")
            else:
                print("FAILURE: 'id' field is missing or not a string.")
                
            # Try to get history for this chat
            chat_id = first_chat.get("id")
            if chat_id:
                print(f"Getting history for {chat_id}...")
                hist_response = requests.get(f"{BASE_URL}/chats/{chat_id}")
                if hist_response.status_code == 200:
                    history = hist_response.json()
                    print(f"History retrieved. ID: {history.get('id')}")
                    if history.get("id") == chat_id:
                        print("SUCCESS: History ID matches.")
                    else:
                        print("FAILURE: History ID mismatch.")
                    
                    # Check for messages
                    messages = history.get("messages", [])
                    print(f"Messages count: {len(messages)}")
                    if messages:
                        last_msg = messages[-1]
                        print(f"Last message keys: {last_msg.keys()}")
                        if "citations" in last_msg:
                            print("SUCCESS: 'citations' field present in message.")
                        else:
                            print("WARNING: 'citations' field missing in message (might be user message or old).")
                else:
                    print(f"Failed to get history: {hist_response.text}")

        else:
            print("No chats to verify.")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    verify_list_chats()
