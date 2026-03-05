import discord
import asyncio
import os
from brain.actions import Think
from brain.personality import Personality

# =============================
# CONFIGURAÇÃO SEGURA
# =============================

TOKEN = os.getenv("DISCORD_TOKEN")  # Coloque o token em variável de ambiente
BOT_NAME = "alice"

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

client = discord.Client(intents=intents)

# =============================
# INICIALIZA SUA IA
# =============================

personality = Personality()
brain = Think(personality)

# =============================
# EVENTOS
# =============================

@client.event
async def on_ready():
    print(f"Logado como {client.user}")
    print("Alice está online 😈")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.lower()

    # ==========================================
    # 🔵 ENTRAR NA CALL
    # ==========================================
    if "entra" in content:
        if not message.author.voice:
            await message.channel.send("Você precisa estar em uma call.")
            return

        channel = message.author.voice.channel

        if message.guild.voice_client:
            await message.channel.send("Já estou em uma call 😏")
            return

        try:
            await channel.connect(timeout=10, reconnect=True)
            await message.channel.send("Entrei na call 😈")
        except Exception as e:
            print("Erro ao conectar:", e)
            await message.channel.send("Não consegui entrar na call 😕")
        return

    # ==========================================
    # 🔴 SAIR DA CALL
    # ==========================================
    if "sai" in content:
        if message.guild.voice_client:
            await message.guild.voice_client.disconnect()
            await message.channel.send("Saí da call.")
        else:
            await message.channel.send("Eu nem estou em call 👀")
        return

    # ==========================================
    # 🧠 LLM - RESPONDER QUANDO CHAMADA
    # ==========================================
    if client.user in message.mentions or BOT_NAME in content:

        clean_content = message.content.replace(f"<@{client.user.id}>", "").strip()

        if not clean_content:
            clean_content = "Olá"

        async with message.channel.typing():
            try:
                dados = await asyncio.to_thread(brain.generate, clean_content)

                if not dados:
                    await message.channel.send("Não consegui entender 😕")
                    return

                brain.comandos(dados)

                texto = dados.get("resposta") or "..."
                await message.channel.send(texto)

            except Exception as e:
                print("Erro:", e)
                await message.channel.send("Algo deu errado 😔")

# =============================
# RODAR BOT
# =============================

if __name__ == "__main__":
    if not TOKEN:
        print("ERRO: Defina a variável de ambiente DISCORD_TOKEN")
    else:
        client.run(TOKEN)


        