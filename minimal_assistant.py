import logging

from dotenv import load_dotenv
from typing import AsyncIterable
from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
    metrics,
    tokenize
)
import re
import asyncio
import aiohttp
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import deepgram, openai, silero

load_dotenv()
logger = logging.getLogger("voice-assistant")


WORDS_PER_MINUTE = 180  # Average human speech rate
WORDS_PER_SECOND = WORDS_PER_MINUTE / 60


# Function to estimate audio length based on text
def estimate_audio_length(text):
    word_count = len(re.findall(r'\w+', text))  # Count words in text
    estimated_length = word_count / WORDS_PER_SECOND
    return estimated_length


async def send_length_to_server(length, text):
    """
    Sends estimated length to a validation server before TTS processing.
    Server trims the text if it exceeds 60 seconds.
    """
    API_URL = "https://2eb3-2409-4081-8416-6c06-1c48-4fb7-e9a-85f7.ngrok-free.app/validate-audio-length"

    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL, json={"length": length, "text": text}) as resp:
            return await resp.json()

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "You are a voice assistant created by LiveKit. Your interface with users will be voice. "
            "You should use short and concise responses, and avoiding usage of unpronouncable punctuation."
        ),
    )

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)


    async def before_tts_cb(agent: VoicePipelineAgent, text: str | AsyncIterable[str]):
        # This function will analyze the text and optimize it
        if isinstance(text, AsyncIterable):
            text = "".join([chunk async for chunk in text])  # Async generator to string

        if not isinstance(text, str):
            text = str(text)  # Ensure text is a string

        length = estimate_audio_length(text)
        response = await send_length_to_server(length, text)
        print(response)
        return tokenize.utils.replace_words(
            text=text, replacements={"livekit": r"<<l|aɪ|v|k|ɪ|t|>>"}
        )

    # wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")

    dg_model = "nova-3-general"
    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        # use a model optimized for telephony
        dg_model = "nova-2-phonecall"

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model=dg_model),
        llm=openai.LLM(),
        tts=openai.TTS(),
        chat_ctx=initial_ctx,
        before_tts_cb=before_tts_cb,
    )

    agent.start(ctx.room, participant)

    usage_collector = metrics.UsageCollector()

    @agent.on("metrics_collected")
    def _on_metrics_collected(mtrcs: metrics.AgentMetrics):
        metrics.log_metrics(mtrcs)
        usage_collector.collect(mtrcs)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: ${summary}")

    ctx.add_shutdown_callback(log_usage)

    await agent.say("Hey, how can I help you today?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )
