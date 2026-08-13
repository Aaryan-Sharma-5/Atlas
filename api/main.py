from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings  
from api.routes.entities import router as entities_router
from api.routes.query import router as query_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router)
app.include_router(entities_router)


@app.get("/")
def read_root():
    return {"status": "healthy", "message": "Welcome to Atlas!"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=settings.port)
