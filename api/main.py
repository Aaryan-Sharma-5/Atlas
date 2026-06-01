from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "healthy", "message": "Welcome to Atlas!"}
