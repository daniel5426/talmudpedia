import sys
import os

backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)

from app.workers.livekit_worker import run_worker

if __name__ == "__main__":
    print("Starting LiveKit Voice Agent Worker...")
    run_worker()
