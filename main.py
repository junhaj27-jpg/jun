from fastapi import FastAPI

from api.download_router import router as download_router
from api.generation_router import router as generation_router
from api.health_router import router as health_router


app = FastAPI(title="ALPLED Core")
app.include_router(health_router)
app.include_router(generation_router)
app.include_router(download_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
