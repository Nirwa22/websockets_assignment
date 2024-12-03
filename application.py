from caller_response import transcription
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, Request
from fastapi.websockets import WebSocketDisconnect
from openai import OpenAI
from prompt_template import template
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Start, Stream, Connect
import asyncio
import base64
import json
import os
import websockets

load_dotenv()
account_sid = os.environ["TWILIO_ACCOUNT_SID"]
auth_token = os.environ["TWILIO_AUTH_TOKEN"]
# Application.secret_key = os.getenv("APPLICATION_SECRET_KEY")
Api_key = os.getenv("Api_Token")
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
voice_id = "nPczCjzI2devNBz1zQrb"
model = 'eleven_turbo_v2_5'

client = Client(account_sid, auth_token)
client_openai = OpenAI()
application = FastAPI()

print("hello")

@application.get("/")
def home():
    return {"message": "Home_Route"}


@application.api_route("/initiate_call", methods=["POST", "GET"])
async def call():
    call_new = client.calls.create(twiml="""<Response>
                                                <Say>hello how are you today Nirwa</Say>
                                                    <Connect>
                                                        <Stream url=\"wss://4f48-2407-d000-a-ac33-d455-5481-f137-6d31.ngrok-free.app/streaming\" />
                                                    </Connect>
                                                <Say>Stream Ended</Say>
                                            </Response>""",
                                   to="+923365177871",
                                   from_="+17755737444",
                                   )
    return {"message": f"Call is initiated. Your call id is {str(call_new.sid)}"}


@application.websocket("/streaming")
async def output(websocket: WebSocket):
    try:
        # Confirms websocket handshake with twilio
        # Establishes persistent connection
        await websocket.accept()
        print("Client connected")
        await transcription(websocket)
    except WebSocketDisconnect:
        print("Client disconnected")