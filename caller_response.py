import asyncio
import base64
import json
import os
import websockets
from dotenv import load_dotenv
load_dotenv()


async def twilio_to_deepgram(deepgram_ws, incoming_audio):
    print("sending to deepgram")
    try:
        while True:
            audio_chunk = await incoming_audio.get()
            await deepgram_ws.send(audio_chunk)
    except Exception as e:
        return {"message", e}


async def transcription(caller_ws):
    incoming_audio = asyncio.Queue()
    async with websockets.connect(
            "wss://api.deepgram.com/v1/listen?model=nova&punctuate=true&encoding=mulaw&sample_rate=8000&language=en-US",
            extra_headers={"Authorization": "Token " + os.getenv("DEEPGRAM_API_KEY")}) as deepgram_ws:
        async def incoming_audio_twilio():
            try:
                while True:
                    message = await caller_ws.receive_text()
                    extract_message = json.loads(message)
                    #print(extract_message)
                    # if extract_message["event"] == "connected" or extract_message["event"] == "start":
                    #     print("Connected to Twilio")
                    if extract_message["event"] == "media":
                        #print(extract_message)
                        payload = extract_message["media"]["payload"]
                        audio_chunk = base64.b64decode(payload)
                        await incoming_audio.put(audio_chunk)
                    elif extract_message["event"] == "stop":
                        print(extract_message)
                        print("call ended")
                        # break
            except Exception as e:
                print(f"Twilio Message:{e}")

        async def deepgram_speech_to_text():
            print("connected to deepgram")
            try:
                async for message in deepgram_ws:
                    response = json.loads(message)
                    print(response)
                    if "channel" in response:
                        transcript = response["channel"]["alternatives"][0]["transcript"]
                        if transcript:
                            print(f"Here is Transcript:{transcript}")
                        else:
                            print("No transcript. Websocket connection closing")
                            await caller_ws.close()

                    else:
                        print(response)
                        # await caller_ws.close()
            except Exception as e:
                return {"Deepgram message", e}

        await asyncio.gather(incoming_audio_twilio(),
                             twilio_to_deepgram(deepgram_ws, incoming_audio),
                             deepgram_speech_to_text()
                             )

        # Send to openai
            async def send_to_openai():
                async for transcript in websocket.iter_text():
                     try:
                         completion = client_openai.chat.completions.create(
                             model="gpt-4o-mini",
                             messages=[{"role": "system", "content": template},
                                      {"role": "user", "content": str(transcript)}
                                       ],
                             stream=True
                         )
                         async for chunk in completion:
                             await websocket.send(str(chunk.choices[0].delta.content))
                     except Exception:
                         print("error in openai")
                         await websocket.close()
        async with websockets.connect(
                 f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id={model}") as elevenlabs_ws:
             async def elevenlabs_text2speech():
                 bos_message = {
                     "text": " ",
                     "voice_settings": {
                         "stability": 0.5,
                         "similarity_boost": 0.8
                     },
                     "xi_api_key": ELEVENLABS_API_KEY,  # Replace with your API key
                 }
                 await elevenlabs_ws.send(json.dumps(bos_message))
                 message = await elevenlabs_ws.recv()
                 await elevenlabs_ws.send(json.dumps(message))
                 eos_message = {
                     "text": ""
                 }
                 await elevenlabs_ws.send(json.dumps(eos_message))
                 while True:
                     try:
                         response = await elevenlabs_ws.recv()
                         data = json.loads(response)
                         if data["audio"]:
                             chunk = base64.b64decode(data["audio"])
                             await websocket.send_bytes(chunk)
        #                 else:
        #                     print("No audio found")
        #                 await elevenlabs_ws.close()
        #             except Exception:
        #                 print("error in elevenlabs")
        #
        # #await asyncio.gather(send_to_openai(), elevenlabs_text2speech())