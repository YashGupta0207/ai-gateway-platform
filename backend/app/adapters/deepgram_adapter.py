from starlette.requests import Request
import json
import asyncio
import websockets

from app.adapters.base import BaseProviderAdapter, BuiltRequest, CredentialField


class DeepgramAdapter(BaseProviderAdapter):
    key = "deepgram"
    display_name = "Deepgram"

    @classmethod
    def credential_schema(cls) -> list[CredentialField]:
        return [
            CredentialField(
                name="api_key", label="API Key", field_type="secret",
                required=True, is_mandatory_primary=True,
                placeholder="Deepgram API key",
            ),
        ]

    async def build_request(self, *, incoming: Request, path: str, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        raise NotImplementedError("Deepgram REST API not fully implemented in this adapter yet.")

    async def handle_live_audio_websocket(self, *, websocket, credentials: dict[str, str], format: str, sample_rate: int) -> None:
        api_key = self.credential_value(credentials, 'api_key', 'deepgram_key')
        
        # Map linear16 to Deepgram's encoding
        encoding = "linear16" if format == "linear16" else format
        
        url = f"wss://api.deepgram.com/v1/listen?encoding={encoding}&sample_rate={sample_rate}&diarize=true"
        
        headers = {
            "Authorization": f"Token {api_key}"
        }
        
        async with websockets.connect(url, additional_headers=headers) as upstream_ws:
            async def forward_client_to_upstream():
                try:
                    while True:
                        message = await websocket.receive()
                        if "text" in message:
                            try:
                                data = json.loads(message["text"])
                                if data.get("text") == "stop":
                                    # Send CloseStream to Deepgram
                                    await upstream_ws.send(json.dumps({"type": "CloseStream"}))
                                    break
                            except json.JSONDecodeError:
                                pass
                        elif "bytes" in message:
                            await upstream_ws.send(message["bytes"])
                except Exception:
                    pass
                finally:
                    await upstream_ws.close()
                    
            async def forward_upstream_to_client():
                try:
                    async for message in upstream_ws:
                        if isinstance(message, str):
                            try:
                                data = json.loads(message)
                                if data.get("type") == "Results":
                                    channel = data.get("channel", {})
                                    alternatives = channel.get("alternatives", [])
                                    if alternatives:
                                        alt = alternatives[0]
                                        is_final = data.get("is_final", False)
                                        
                                        words = []
                                        if is_final:
                                            for w in alt.get("words", []):
                                                words.append({
                                                    "word": w.get("word", ""),
                                                    "start": w.get("start", 0.0),
                                                    "end": w.get("end", 0.0),
                                                    "confidence": w.get("confidence", 0.0)
                                                })
                                        
                                        # Deepgram diarization
                                        speaker = "Speaker 1"
                                        if words and "speaker" in alt.get("words", [])[0]:
                                            speaker = f"Speaker {alt['words'][0]['speaker']}"
                                            
                                        response = {
                                            "type": "transcript",
                                            "is_final": is_final,
                                            "speaker": speaker,
                                            "text": alt.get("transcript", ""),
                                            "confidence": alt.get("confidence", 0.0),
                                            "words": words
                                        }
                                        await websocket.send_json(response)
                            except json.JSONDecodeError:
                                pass
                except Exception:
                    pass
                    
            await asyncio.gather(
                forward_client_to_upstream(),
                forward_upstream_to_client(),
            )
