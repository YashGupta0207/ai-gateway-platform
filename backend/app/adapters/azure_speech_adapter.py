from starlette.requests import Request

from app.adapters.base import BaseProviderAdapter, BuiltRequest, CredentialField


class AzureSpeechAdapter(BaseProviderAdapter):
    key = "azure_speech"
    display_name = "Azure Speech"

    @classmethod
    def credential_schema(cls) -> list[CredentialField]:
        return [
            CredentialField(
                name="api_key", label="API Key", field_type="secret",
                required=True, is_mandatory_primary=True,
                placeholder="Azure Speech API key",
            ),
            CredentialField(
                name="region", label="Region", field_type="text",
                required=True, is_mandatory_primary=False,
                placeholder="e.g., eastus",
            ),
        ]

    async def build_request(self, *, incoming: Request, path: str, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        region = self.credential_value(credentials, 'region', 'azure_region')
        api_key = self.credential_value(credentials, 'api_key', 'azure_key', 'azure_speech_key')
        
        if path and path != "/":
            if "speechtotext" in path or "transcriptions" in path:
                base_url = f"https://{region}.api.cognitive.microsoft.com/{path.lstrip('/')}"
            else:
                base_url = f"https://{region}.stt.speech.microsoft.com/{path.lstrip('/')}"
        else:
            base_url = f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
        
        content_type = incoming.headers.get("content-type", "audio/wav")
        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": content_type,
            "Accept": "application/json",
        }
        
        # Azure requires language parameter, default to en-US if not provided
        params = dict(incoming.query_params)
        if "language" not in params:
            params["language"] = "en-US"
            
        return BuiltRequest(
            method=incoming.method,
            url=base_url,
            headers=headers,
            params=params,
            content=body,
            is_streaming=False,
        )

    def build_websocket_request(self, *, incoming: Request, path: str, credentials: dict[str, str]) -> tuple[str, dict[str, str]]:
        region = self.credential_value(credentials, 'region', 'azure_region')
        api_key = self.credential_value(credentials, 'api_key', 'azure_key', 'azure_speech_key')
        
        # Azure Speech WebSocket URL
        url = f"wss://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
        
        # Append query params from incoming request
        query_string = incoming.url.query
        if query_string:
            url = f"{url}?{query_string}"
            if "language=" not in url:
                url += "&language=en-US"
        else:
            url += "?language=en-US"
            
        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
        }
        return url, headers

    def normalize_usage(self, content: bytes) -> dict[str, int | float]:
        import json
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            return super().normalize_usage(content)
        
        # Azure Speech REST API returns Duration in 100-nanosecond units
        # Fast Transcription API returns duration as ISO 8601 string (e.g., "PT42S")
        duration_seconds = 0
        if "duration" in payload and isinstance(payload["duration"], str) and payload["duration"].startswith("PT"):
            import re
            match = re.match(r'PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?', payload["duration"])
            if match:
                h = float(match.group(1) or 0)
                m = float(match.group(2) or 0)
                s = float(match.group(3) or 0)
                duration_seconds = h * 3600 + m * 60 + s
        else:
            duration_ticks = payload.get("Duration", 0)
            duration_seconds = duration_ticks / 10_000_000
        
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": int(duration_seconds), "estimated_cost": 0.0}

    async def build_audio_request(self, *, incoming: Request, body: bytes, credentials: dict[str, str]) -> BuiltRequest:
        form = await incoming.form()
        file_field = form.get("file")
        if not file_field or not hasattr(file_field, "read"):
            raise ValueError("Missing 'file' in multipart form data")
            
        audio_bytes = await file_field.read()
        
        region = self.credential_value(credentials, 'region', 'azure_region')
        api_key = self.credential_value(credentials, 'api_key', 'azure_key', 'azure_speech_key')
        
        base_url = f"https://{region}.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe?api-version=2024-11-15"
        
        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
            "Accept": "application/json",
        }
        
        params = dict(incoming.query_params)
        language = params.get("language")
        if not language:
            language = form.get("language")
            if not language or not isinstance(language, str):
                language = "en-US"
                
        import json
        definition = {
            "locales": [language]
        }
        
        filename = getattr(file_field, "filename", None) or "audio.wav"
        files = {
            "audio": (filename, audio_bytes, file_field.content_type or "audio/wav"),
            "definition": (None, json.dumps(definition), "application/json")
        }
                
        return BuiltRequest(
            method="POST",
            url=base_url,
            headers=headers,
            files=files,
            is_streaming=False,
        )

    def normalize_audio_response(self, content: bytes) -> tuple[bytes, dict[str, int | float]]:
        import json
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            return content, self.normalize_usage(content)
            
        usage = self.normalize_usage(content)
        
        text = payload.get("DisplayText", "")
        if not text and "combinedRecognizedPhrases" in payload:
            phrases = payload["combinedRecognizedPhrases"]
            if phrases and isinstance(phrases, list) and len(phrases) > 0:
                text = phrases[0].get("display", "")
        
        openai_response = {
            "text": text
        }
        
        return json.dumps(openai_response).encode("utf-8"), usage

    async def handle_live_audio_websocket(self, *, websocket, credentials: dict[str, str], format: str, sample_rate: int) -> dict[str, int | float]:
        import azure.cognitiveservices.speech as speechsdk
        import asyncio
        import json
        
        region = self.credential_value(credentials, 'region', 'azure_region')
        api_key = self.credential_value(credentials, 'api_key', 'azure_key', 'azure_speech_key')
        
        speech_config = speechsdk.SpeechConfig(subscription=api_key, region=region)
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_OutputFormatOption, "Detailed")
        
        # Configure format and sample rate
        stream_format = speechsdk.audio.AudioStreamFormat(samples_per_second=sample_rate, bits_per_sample=16, channels=1)
        push_stream = speechsdk.audio.PushAudioInputStream(stream_format=stream_format)
        audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
        
        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        
        loop = asyncio.get_running_loop()
        
        def handle_event(evt, is_final):
            try:
                result = evt.result
                if result.reason == speechsdk.ResultReason.RecognizedSpeech or result.reason == speechsdk.ResultReason.RecognizingSpeech:
                    # Parse detailed JSON if available
                    words = []
                    confidence = 0.0
                    
                    if result.properties:
                        json_str = result.properties.get(speechsdk.PropertyId.SpeechServiceResponse_JsonResult)
                        if json_str:
                            try:
                                parsed = json.loads(json_str)
                                if "NBest" in parsed and len(parsed["NBest"]) > 0:
                                    best = parsed["NBest"][0]
                                    confidence = best.get("Confidence", 0.0)
                                    if "Words" in best:
                                        for w in best["Words"]:
                                            # Azure offset is in 100-nanosecond units
                                            start = w.get("Offset", 0) / 10_000_000
                                            duration = w.get("Duration", 0) / 10_000_000
                                            words.append({
                                                "word": w.get("Word", ""),
                                                "start": start,
                                                "end": start + duration,
                                                "confidence": w.get("Confidence", 0.0)
                                            })
                            except json.JSONDecodeError:
                                pass
                    
                    response = {
                        "type": "transcript",
                        "is_final": is_final,
                        "speaker": "Speaker 1", # Azure doesn't provide speaker diarization in standard recognition
                        "text": result.text,
                        "confidence": confidence,
                        "words": words if is_final else []
                    }
                    
                    # Send to websocket safely from another thread
                    asyncio.run_coroutine_threadsafe(websocket.send_json(response), loop)
            except Exception as e:
                print(f"Error handling Azure event: {e}")
                
        speech_recognizer.recognizing.connect(lambda evt: handle_event(evt, False))
        speech_recognizer.recognized.connect(lambda evt: handle_event(evt, True))
        
        speech_recognizer.start_continuous_recognition()
        
        total_bytes = 0
        try:
            while True:
                message = await websocket.receive()
                if "text" in message:
                    try:
                        data = json.loads(message["text"])
                        if data.get("text") == "stop":
                            break
                    except json.JSONDecodeError:
                        pass
                elif "bytes" in message:
                    total_bytes += len(message["bytes"])
                    push_stream.write(message["bytes"])
        finally:
            speech_recognizer.stop_continuous_recognition()
            push_stream.close()
            
        duration_seconds = total_bytes / (sample_rate * 2) if format == "linear16" else total_bytes / sample_rate
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": int(duration_seconds), "estimated_cost": 0.0}
