# main.py
from fastapi import FastAPI, Depends
from fastapi.security import OAuth2PasswordRequestForm
from enum import Enum
from typing import Annotated
from .security import (
    get_current_active_user,
    login,
    User,
)


# Create an instance of the FastAPI class and assign it to the 'app' variable
app = FastAPI()

class ModelName(str, Enum):
    home = "home"
    login = "login"
    dashboard = "dashboard"
    profile = "profile"
    about = "about"
    contact = "contact"
    users = "users"



@app.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    return await login(form_data)


@app.post("/pages/{model_name}")
async def users(model_name: ModelName, details: User):
    if model_name == ModelName.login and details:
       return {
            "model_name": model_name,
            "username" :details.username,
            "email" : details.email,
            "fullname" : details.full_name
       }
    return {"model_name": model_name, "message": "This is not the login page"}



@app.get("/pages/{model_name}")
async def get_model(model_name: ModelName):
    if model_name == ModelName.home:
        return {"model_name": model_name, "message": "This is the home page"}
    if model_name.value == "login":
        return {"model_name": model_name, "message": "This is the login page"}
    if model_name == ModelName.dashboard:
        return {"model_name": model_name, "message": "This is the dashboard"}
    return {"model_name": model_name, "message": "This is some other page"}


# Define a path operation decorator
@app.get("/users/me")
async def read_user_me(current_user: Annotated[User, Depends(get_current_active_user)]):
    return current_user

@app.get("/users/{user_id}")
async def read_user(user_id : int):
    return {"Hello" : user_id}
