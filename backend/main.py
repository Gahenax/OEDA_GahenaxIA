from fastapi import FastAPI
from gahenax_app.api.gahenax_api import router
import uvicorn

app = FastAPI(title="Gahenax Core API (v1.1.1)")

app.include_router(router)

@app.get("/")
async def root():
    return {"status": "ONLINE", "system": "Gahenax Core v1.1.1", "paradigm": "P over NP Governed"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
