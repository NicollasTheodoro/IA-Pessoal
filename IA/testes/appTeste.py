import requests
import pyaudio
from ollama import chat

import testes.captando_audio as captando_audio
import json as penny



api_key = "ap2_45d8b09d-5baf-45de-b0ba-eca28b3bed28"

url = "https://global.api.murf.ai/v1/speech/stream" # Global URL

# url = "https://in.api.murf.ai/v1/speech/stream" # Regional URL

with open("personalidade.json", "r", encoding="utf-8") as f:
    config = penny.load(f)

system_prompt = f"""
Você é {config['nome']}.
{config['descricao']}
{config['estilo_resposta']}

Regras:
"""

for regra in config["regras"]:
    system_prompt += f"- {regra}\n"

while True:

    mensagem = captando_audio.ouvir_mic()

    response = chat(
        model='phi3:mini',
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': mensagem}
        ],
    )

    print("Gerando resposta... ⛄")

    resposta = response.message.content

    print(resposta)

    response = requests.post(
    url,
    headers={"api-key": api_key},
    json={
        "text": resposta,
        "model": "FALCON",
        "voiceId": "Isadora",
        "multiNativeLocale": "pt-BR",
        "format": "PCM",
        "sampleRate": 24000
    },
    stream=True
    )

    # Audio format settings (must match your API output)
    SAMPLE_RATE = 24000  # Default sample rate for streaming
    CHANNELS = 1
    FORMAT = pyaudio.paInt16

    # Setup audio stream for playback
    pa = pyaudio.PyAudio()
    stream = pa.open(format=FORMAT, channels=CHANNELS, rate=SAMPLE_RATE, output=True)

    try:
        print("Starting audio playback...")
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                stream.write(chunk)
    except Exception as e:
        print(f"Error during streaming: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        print("Audio streaming and playback complete!")