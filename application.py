from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, Request
from fastapi.websockets import WebSocketDisconnect
from openai import AsyncOpenAI
from prompt_template import template
from twilio.rest import Client
# from WebSocket.exceptions import ConnectionClosedOK
import asyncio
import base64
import json
import os
import websockets

load_dotenv()
account_sid = os.environ["TWILIO_ACCOUNT_SID"]
auth_token = os.environ["TWILIO_AUTH_TOKEN"]
# Application.secret_key = os.getenv("APPLICATION_SECRET_KEY")
Api_key = os.getenv("Api_key")
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

client = Client(account_sid, auth_token)
client_openai = AsyncOpenAI()
application = FastAPI()

print("hello")

@application.get("/")
def home():
    return {"message": "Home_Route"}


@application.api_route("/initiate_call", methods=["POST", "GET"])
async def call(request: Request):
    api = request.headers.get("Authorization")
    if api == Api_key:
        call_new = client.calls.create(twiml="""<Response>
                                                    <Say>Welcome! I am your AI voice assistant. How are you today?</Say>
                                                        <Connect>
                                                            <Stream url=\"wss://57d2-2407-d000-a-ac33-b17c-c133-548f-1f78.ngrok-free.app/streaming\" />
                                                        </Connect>
                                                    <Say>Stream Ended</Say>
                                                </Response>""",
                                       to="+923365177871",
                                       from_="+12705697708",
                                       )
        return {"message": f"Call is initiated. Your call id is {str(call_new.sid)}"}
    elif api and api != Api_key:
        return {"message": "Unauthorized Access"}
    else:
        return {"message": "Api key needed"}


@application.websocket("/streaming")
async def output(websocket: WebSocket):
    try:
        await websocket.accept() # Establishes persistent connection
        print("Client connected")

        async def twilio_call_response(caller_ws=websocket):
            incoming_audio = asyncio.Queue()
            id_queue = asyncio.Queue()
            # ulaw_8000 is mostly used for twilio inputs
            async with websockets.connect(
                    "wss://api.deepgram.com/v1/listen?model=nova&punctuate=true&encoding=mulaw&sample_rate=8000&language=en-US",
                    extra_headers={"Authorization": "Token " + os.getenv("DEEPGRAM_API_KEY")}) as deepgram_ws:
                async def incoming_audio_twilio():
                    while True:
                        try:
                            message = await caller_ws.receive_text()
                            extract_message = json.loads(message)
                            if extract_message["event"] == "connected":
                                await caller_ws.send_text(f"Connected to Twilio")
                                print("Twilio connection confirmed")
                            if extract_message["event"] == "start":
                                user_id = extract_message["streamSid"]
                                await id_queue.put(user_id)
                                print(f"Stream id is {user_id}")
                            if extract_message["event"] == "media":
                                # print(extract_message)
                                payload = extract_message["media"]["payload"]
                                audio_chunk = base64.b64decode(payload)
                                await caller_ws.send_text(f"Received audio from the user: {type(audio_chunk)}")
                                # print(f"deepgram info: {type(audio_chunk)}, {type(payload)}")
                                await incoming_audio.put(audio_chunk)
                            elif extract_message["event"] == "stop":
                                print(extract_message)
                                print("call ended")
                                await caller_ws.close()
                                # break
                        except Exception as e:
                            print(f"Twilio Message:{e}")
                            break

                async def twilio_to_deepgram():
                    print("sending to deepgram")
                    while True:
                        try:
                            audio_chunk = await incoming_audio.get()
                            await deepgram_ws.send(audio_chunk)
                        except Exception as e:
                            return {"message(twilio2deepgram)", e}
                            break

                async def deepgram_speech2text():
                    print("connected to deepgram")
                    async def text_chunker(chunks):
                        """Split text into chunks, ensuring to not break sentences."""
                        splitters = (".", ",", "?", "!", ";", ":", "—", "-", "(", ")", "[", "]", "}", " ")
                        buffer = ""
                        async for text in chunks:
                            if buffer.endswith(splitters):
                                yield buffer + " "
                                buffer = text
                            elif text.startswith(splitters):
                                yield buffer + text[0] + " "
                                buffer = text[1:]
                            else:
                                buffer += text

                                if buffer:
                                    yield buffer + " "

                    async def text_iterator(ans):
                        async for chunk in ans:
                            delta = chunk.choices[0].delta
                            yield delta.content

                    while True:
                        try:
                            print(" Welcome: Deepgram")
                            data = await deepgram_ws.recv()
                            response = json.loads(data)
                            print(response)
                            if "channel" in response:
                                transcript = response["channel"]["alternatives"][0]["transcript"]
                                if transcript:
                                    print(f"Here is Transcript:{transcript}")
                                    print("sending to openai")
                                    response_openai = await client_openai.chat.completions.create(
                                        model="gpt-4o-mini",
                                        messages=[{"role": "system", "content": template},
                                                  {"role": "user", "content": str(transcript)}
                                                  ],
                                        temperature=1,
                                        stream=True)

                                    # async for chunk in response_openai:
                                    #     delta = chunk.choices[0].delta
                                    async for new_chunk in text_chunker(text_iterator(response_openai)):
                                        yield new_chunk
                                else:
                                    print("No transcript")
                        except Exception as e:
                            print(f"Deepgram error: {e}")
                            break

                async with websockets.connect(
                        "wss://api.elevenlabs.io/v1/text-to-speech/nPczCjzI2devNBz1zQrb/stream-input?model_id=eleven_turbo_v2_5&output_format=ulaw_8000", ping_interval=30) as elevenlabs_ws:
                    async def send_to_elevenlabs():
                        print("Connected to elevenlabs")
                        while True:
                            try:
                                await elevenlabs_ws.send(json.dumps({
                                    "text": " ",
                                    "voice_settings": {
                                        "stability": 0.5,
                                        "similarity_boost": 0.8
                                    },
                                    "xi_api_key": ELEVENLABS_API_KEY}))
                                async for word in deepgram_speech2text():
                                    print(f"word: {word}")
                                    response_chunk = {"text": word, "try_trigger_generation": True}
                                    await elevenlabs_ws.send(json.dumps(response_chunk))
                                    print(f"SENT TO EL: {response_chunk}")
                                # await elevenlabs_ws.send(json.dumps({}))
                                await elevenlabs_ws.send(json.dumps({"flush": True}))
                                # await elevenlabs_ws.send(json.dumps({"text": ""}))
                            except websockets.exceptions.ConnectionClosed:
                                print("Connection closed")
                                break

                    async def elevenlabs_text_to_speech():
                        print("connected to elevenlabs")
                        while True:
                            try:
                                response = await elevenlabs_ws.recv()
                                print("here is the response")
                                data = json.loads(response)
                                # print(data)
                                if data.get("audio"):
                                    chunk = base64.b64decode(data["audio"])
                                    print(f"Here is your audio chunk:{chunk}")
                                    yield chunk
                                    # yield base64.b64decode(data["audio"]
                                elif data.get("isFinal"):
                                    break
                                    # await elevenlabs_ws.close()
                            except Exception as e:
                                print(f"Elevenlabs error 2: {e}")
                                break

                    async def send_to_user():
                        while True:
                            print("Audio going to user")
                            try:
                                print("hi")
                                stream_id = await id_queue.get()
                                print(f"Here is the stream_id: {stream_id} and {type(stream_id)}")
                                async for user_response_chunk in elevenlabs_text_to_speech():
                                    print(f"User_chunk_info : {type(user_response_chunk)}")
                                    media_event = {"event": "media",
                                                   "streamSid": stream_id,
                                                   "media": {
                                                       "payload": base64.b64encode(user_response_chunk).decode(
                                                           "utf-8")}}
                                    await caller_ws.send_text(json.dumps(media_event))
                                    print("Redirecting to the user")
                                print("hello")
                            except Exception as e:
                                print(f"User_error: {e}")
                                break

                    await asyncio.gather(incoming_audio_twilio(),
                                         twilio_to_deepgram(),
                                         send_to_elevenlabs(),
                                         send_to_user()
                                         )
                    # send_to_user(caller_ws, response_queue))
                    await caller_ws.close()
        await twilio_call_response()
    except WebSocketDisconnect:
        print("Client disconnected")