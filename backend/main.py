from fastapi import FastAPI

app = FastAPI(title="Rabbinic AI API", version="0.1.0")

@app.get("/")
def read_root():
    return {"message": "Welcome to the Rabbinic AI API", "status": "active"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
