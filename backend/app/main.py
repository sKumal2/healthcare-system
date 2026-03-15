from fastapi import FastAPI, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.api.v1.router import api_router


# Create an instance of the FastAPI class and assign it to the 'app' variable
app = FastAPI(
    title = "Healthcare RAG System",
    version="1.0.0",
)

app.include_router(api_router, prefix="/api/v1")


