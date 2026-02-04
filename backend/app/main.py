# main.py
from fastapi import FastAPI, Depends
from enum import Enum
from pydantic import BaseModel
from typing import Annotated
from fastapi.security import OAuth2PasswordBearer
# Create an instance of the FastAPI class and assign it to the 'app' variable
app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl = "token")
class ModelName(str, Enum):
    home = "home"
    login = "login"
    dashboard = "dashboard"
    profile = "profile"
    about = "about"
    contact = "contact"

class User(BaseModel):
    username : str
    email : str | None = None 
    fullname : str | None = None

def fake_decode_token(token):
    return User(
        username = token + "fakedecoded",
        email = "john.example.com",
        fullname = "John Doe"
    )    

async def get_current_user(token : Annotated[str, Depends(oauth2_scheme)]):
    user = fake_decode_token(token)
    return user

@app.get("/")
async def read_items(current_user : Annotated[User, Depends(oauth2_scheme)]):
    return current_user
    

@app.post("/{model_name}")
async def users(model_name : ModelName, details: User):
    if model_name == ModelName.login and details:
       return {
            "model_name": model_name,
            "username" :details.username,
            "email" : details.email,
            "fullname" : details.fullname
       }
    return {"model_name": model_name, "message": "This is not the about page"}



@app.get("/{model_name}")
async def get_model(model_name : ModelName):
    if model_name == ModelName.home:
        return {"model_name": model_name, "message": "This is the home page"}
    if model_name.value == "login":
        return {"model_name": model_name, "message": "This is the login page"}
    if model_name == ModelName.dashboard:
        return {"model_name": model_name, "message": "This is the dashboard"}
    return {"model_name": model_name, "message": "This is some other page"}


# Define a path operation decorator
@app.get("/users/me")
async def read_user_me():
    return {"Hello": "me"}

@app.get("/users/{user_id}")
async def read_user(user_id : int):
    return {"Hello" : user_id}

@app.get("/{item_id}")
async def root(item_id : int):
    return {"Hello": item_id}

