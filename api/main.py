from fastapi import FastAPI

from api.routes.entities import router as entities_router
from api.routes.query import router as query_router

app = FastAPI()
app.include_router(query_router)
app.include_router(entities_router)

@app.get("/")
def read_root():
    return {"status": "healthy", "message": "Welcome to Atlas!"}
