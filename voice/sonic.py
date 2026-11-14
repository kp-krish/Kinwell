"""Amazon Nova 2 Sonic bidirectional streaming session.

One SonicSession per phone call. Wraps the event protocol:
sessionStart -> promptStart -> SYSTEM text -> USER audio (streamed) -> ... -> promptEnd -> sessionEnd

Callers push caller audio with send_audio() and receive model events through
the async callbacks passed to the constructor.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import boto3
from aws_sdk_bedrock_runtime.client import AsyncBedrockRuntimeClient as BedrockRuntimeClient
from aws_sdk_bedrock_runtime.config import AsyncBedrockRuntimeConfig
from smithy_http.aio.crt import AWSCRTHTTPClient
from aws_sdk_bedrock_runtime.models import (
    BidirectionalInputPayloadPart,
    InvokeModelWithBidirectionalStreamInputChunk,
    InvokeModelWithBidirectionalStreamOperationInput,
)

log = logging.getLogger("sonic")

DEFAULT_MODEL_ID = os.environ.get("NOVA_SONIC_MODEL_ID", "amazon.nova-2-sonic-v1:0")
DEFAULT_REGION = os.environ.get("AWS_REGION", "us-west-2")

# Phone audio is 8 kHz. Sonic accepts 8 kHz in; output rate is configurable.
INPUT_SAMPLE_RATE = int(os.environ.get("SONIC_INPUT_RATE", "8000"))
OUTPUT_SAMPLE_RATE = int(os.environ.get("SONIC_OUTPUT_RATE", "8000"))

AudioCb = Callable[[bytes], Awaitable[None]]
TextCb = Callable[[str, str, bool], Awaitable[None]]  # role, text, is_final
ToolCb = Callable[[str, dict], Awaitable[dict]]  # tool name, input -> result
SimpleCb = Callable[[], Awaitable[None]]


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: dict

    def to_event(self) -> dict:
        return {
            "toolSpec": {
                "name": self.name,
                "description": self.description,
                "inputSchema": {"json": json.dumps(self.schema)},
            }
        }


async def _client(region: str) -> BedrockRuntimeClient:
    """Build a client with credentials from boto3's chain (shared file locally,
    the ECS task role on Fargate). Resolved per call so rotated creds are picked up."""
    creds = boto3.Session().get_credentials().get_frozen_credentials()
    config = await AsyncBedrockRuntimeConfig.resolve(
        region=region,
        aws_access_key_id=creds.access_key,
        aws_secret_access_key=creds.secret_key,
        aws_session_token=creds.token,
        transport=AWSCRTHTTPClient(),
    )
    return BedrockRuntimeClient(config=config)


@dataclass
class SonicSession:
    system_prompt: str
    voice_id: str = "tiffany"
    tools: list[ToolSpec] = field(default_factory=list)
    on_audio: AudioCb | None = None
    on_text: TextCb | None = None
    on_tool: ToolCb | None = None
    on_interrupt: SimpleCb | None = None
    on_end: SimpleCb | None = None
    model_id: str = DEFAULT_MODEL_ID
    region: str = DEFAULT_REGION
    temperature: float = 0.7

    def __post_init__(self) -> None:
        self.prompt_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())
        self._stream = None
        self._reader: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()
        self.active = False
        self.transcript: list[dict] = []
        self._pending_tool: dict | None = None
        self._role: str | None = None
        self._final = True

    # ---------- sending ----------

    async def _send(self, event: dict) -> None:
        if not self._stream:
            return
        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=json.dumps(event).encode("utf-8"))
        )
        async with self._send_lock:
            await self._stream.input_stream.send(chunk)

    async def start(self) -> None:
        client = await _client(self.region)
        self._stream = await client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        self.active = True
        self._reader = asyncio.create_task(self._read_loop())

        await self._send({"event": {"sessionStart": {"inferenceConfiguration": {
            "maxTokens": 1024, "topP": 0.9, "temperature": self.temperature}}}})

        prompt_start: dict[str, Any] = {
            "promptName": self.prompt_name,
            "textOutputConfiguration": {"mediaType": "text/plain"},
            "audioOutputConfiguration": {
                "mediaType": "audio/lpcm",
                "sampleRateHertz": OUTPUT_SAMPLE_RATE,
                "sampleSizeBits": 16,
                "channelCount": 1,
                "voiceId": self.voice_id,
                "encoding": "base64",
                "audioType": "SPEECH",
            },
        }
        if self.tools:
            prompt_start["toolUseOutputConfiguration"] = {"mediaType": "application/json"}
            prompt_start["toolConfiguration"] = {"tools": [t.to_event() for t in self.tools]}
        await self._send({"event": {"promptStart": prompt_start}})

        await self._send_text_block(self.system_prompt, role="SYSTEM", interactive=False)

        # Open the caller's audio channel for the rest of the call.
        await self._send({"event": {"contentStart": {
            "promptName": self.prompt_name,
            "contentName": self.audio_content_name,
            "type": "AUDIO",
            "interactive": True,
            "role": "USER",
            "audioInputConfiguration": {
                "mediaType": "audio/lpcm",
                "sampleRateHertz": INPUT_SAMPLE_RATE,
                "sampleSizeBits": 16,
                "channelCount": 1,
                "audioType": "SPEECH",
                "encoding": "base64",
            },
        }}})

    async def _send_text_block(self, text: str, role: str, interactive: bool) -> None:
        name = str(uuid.uuid4())
        await self._send({"event": {"contentStart": {
            "promptName": self.prompt_name, "contentName": name, "type": "TEXT",
            "interactive": interactive, "role": role,
            "textInputConfiguration": {"mediaType": "text/plain"}}}})
        await self._send({"event": {"textInput": {
            "promptName": self.prompt_name, "contentName": name, "content": text}}})
        await self._send({"event": {"contentEnd": {
            "promptName": self.prompt_name, "contentName": name}}})

    async def send_user_text(self, text: str) -> None:
        """Inject a user text turn (used to make the agent speak first)."""
        await self._send_text_block(text, role="USER", interactive=True)

    async def send_audio(self, pcm16: bytes) -> None:
        if not self.active:
            return
        await self._send({"event": {"audioInput": {
            "promptName": self.prompt_name,
            "contentName": self.audio_content_name,
            "content": base64.b64encode(pcm16).decode("ascii")}}})

    async def _send_tool_result(self, tool_use_id: str, result: dict) -> None:
        name = str(uuid.uuid4())
        await self._send({"event": {"contentStart": {
            "promptName": self.prompt_name, "contentName": name, "interactive": False,
            "type": "TOOL", "role": "TOOL",
            "toolResultInputConfiguration": {
                "toolUseId": tool_use_id, "type": "TEXT",
                "textInputConfiguration": {"mediaType": "text/plain"}}}}})
        await self._send({"event": {"toolResult": {
            "promptName": self.prompt_name, "contentName": name,
            "content": json.dumps(result)}}})
        await self._send({"event": {"contentEnd": {
            "promptName": self.prompt_name, "contentName": name}}})

    async def close(self) -> None:
        if not self.active:
            return
        self.active = False
        try:
            await self._send({"event": {"contentEnd": {
                "promptName": self.prompt_name, "contentName": self.audio_content_name}}})
            await self._send({"event": {"promptEnd": {"promptName": self.prompt_name}}})
            await self._send({"event": {"sessionEnd": {}}})
            await self._stream.input_stream.close()
        except Exception as e:  # stream may already be closed by the service
            log.debug("close: %s", e)
        if self._reader:
            try:
                await asyncio.wait_for(self._reader, timeout=3)
            except (asyncio.TimeoutError, Exception):
                self._reader.cancel()

    # ---------- receiving ----------

    async def _read_loop(self) -> None:
        try:
            _, output = await self._stream.await_output()
            while True:
                result = await output.receive()
                if result is None:
                    break
                raw = getattr(getattr(result, "value", None), "bytes_", None)
                if not raw:
                    continue
                await self._handle(json.loads(raw.decode("utf-8")))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.exception("Sonic stream error: %s", e)
        finally:
            self.active = False
            if self.on_end:
                await self.on_end()

    async def _handle(self, msg: dict) -> None:
        ev = msg.get("event", {})
        if "contentStart" in ev:
            cs = ev["contentStart"]
            self._role = cs.get("role")
            extra = cs.get("additionalModelFields")
            self._final = True
            if extra:
                try:
                    self._final = json.loads(extra).get("generationStage") != "SPECULATIVE"
                except (ValueError, TypeError):
                    pass
        elif "textOutput" in ev:
            text = ev["textOutput"].get("content", "")
            role = ev["textOutput"].get("role", self._role or "")
            if '"interrupted"' in text and "true" in text:
                if self.on_interrupt:
                    await self.on_interrupt()
                return
            if self._final or role == "USER":
                self.transcript.append({"role": role, "text": text})
            if self.on_text:
                await self.on_text(role, text, self._final)
        elif "audioOutput" in ev:
            if self.on_audio:
                await self.on_audio(base64.b64decode(ev["audioOutput"]["content"]))
        elif "toolUse" in ev:
            self._pending_tool = ev["toolUse"]
        elif "contentEnd" in ev:
            ce = ev["contentEnd"]
            if ce.get("type") == "TOOL" and self._pending_tool:
                tool = self._pending_tool
                self._pending_tool = None
                asyncio.create_task(self._run_tool(tool))
            if ce.get("stopReason") == "INTERRUPTED" and self.on_interrupt:
                await self.on_interrupt()
        elif "completionEnd" in ev:
            log.info("completionEnd")

    async def _run_tool(self, tool: dict) -> None:
        name = tool.get("toolName", "")
        try:
            args = json.loads(tool.get("content") or "{}")
        except ValueError:
            args = {}
        log.info("tool call %s %s", name, args)
        try:
            result = await self.on_tool(name, args) if self.on_tool else {"error": "no tools"}
        except Exception as e:
            log.exception("tool %s failed", name)
            result = {"error": str(e)}
        await self._send_tool_result(tool["toolUseId"], result)
