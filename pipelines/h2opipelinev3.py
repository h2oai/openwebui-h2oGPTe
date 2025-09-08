##This pipeline will connect user to a H2OGPTE Collection with document ingestion support
import os
import time
import threading
import queue
from typing import List, Optional, Union, Generator, Dict, Any
from pydantic import BaseModel
import requests

try:
    from h2ogpte import H2OGPTE
    from h2ogpte.types import PartialChatMessage, ChatMessage
except ImportError:
    print("h2ogpte package not installed. Install with: pip install h2ogpte")
    H2OGPTE = None
    PartialChatMessage = None
    ChatMessage = None


class Pipeline:
    """Streamlined H2OGPTE Pipeline with document ingestion capability"""
    
    class Valves(BaseModel):
        """Configuration parameters"""
        H2OGPTE_API_KEY: str = ""
        H2OGPTE_URL: str = ""
        COLLECTION_ID: str = ""  # Optional collection ID
        AUTO_CREATE_COLLECTION: bool = True  # Auto-create collection if not set
        DEFAULT_COLLECTION_NAME: str = "AutoDocs"
        DEBUG_MODE: bool = False
        STREAM_TIMEOUT: int = 60
        INGESTION_TIMEOUT: int = 300  # 5 minutes timeout for ingestion

    def __init__(self):
        self.type = "manifold"
        self.id = "h2ogpte_single"
        self.name = ""
        
        self.valves = self.Valves(
            **{
                "H2OGPTE_API_KEY": os.getenv("H2OGPTE_API_KEY", ""),
                "H2OGPTE_URL": os.getenv("H2OGPTE_URL", "https://h2ogpte.genai.h2o.ai"),
                "COLLECTION_ID": os.getenv("COLLECTION_ID", ""),
                "AUTO_CREATE_COLLECTION": os.getenv("AUTO_CREATE_COLLECTION", "true").lower() == "true",
                "DEFAULT_COLLECTION_NAME": os.getenv("DEFAULT_COLLECTION_NAME", "OpenWebUI Documents"),
                "DEBUG_MODE": os.getenv("DEBUG_MODE", "false").lower() == "true",
                "STREAM_TIMEOUT": int(os.getenv("STREAM_TIMEOUT", "60")),
                "INGESTION_TIMEOUT": int(os.getenv("INGESTION_TIMEOUT", "300")),
            }
        )
        self.client: Optional[H2OGPTE] = None
        self.current_collection_id: Optional[str] = None
        self.uploaded_files: Dict[str, str] = {}  # Track uploaded files: {file_path: collection_id}

    def log_debug(self, message: str) -> None:
        if self.valves.DEBUG_MODE:
            print(f"[H2OGPTE] {message}")

    async def on_startup(self) -> None:
        if not self.valves.H2OGPTE_API_KEY:
            print("H2OGPTE_API_KEY not set")
        if H2OGPTE is None:
            print("h2ogpte package not available")

    async def on_shutdown(self) -> None:
        self.client = None

    async def on_valves_updated(self) -> None:
        self.client = None
        self.current_collection_id = None
        # Reset uploaded files when configuration changes
        self.uploaded_files.clear()

    def pipelines(self) -> List[Dict[str, str]]:
        """Return available pipeline models - called during startup"""
        try:
            return [{"id": "h2ogpte", "name": "H2OGPTe"}]
        except Exception as e:
            print(f"Error in pipelines method: {e}")
            return [{"id": "h2ogpte", "name": "H2OGPTe"}]

    def init_client(self) -> None:
        if not self.valves.H2OGPTE_API_KEY or not self.valves.H2OGPTE_URL or H2OGPTE is None:
            raise ValueError("Missing configuration or h2ogpte package")
        
        if self.client is None:
            self.client = H2OGPTE(
                address=self.valves.H2OGPTE_URL,
                api_key=self.valves.H2OGPTE_API_KEY,
            )
            self.log_debug("Client initialized")

    def _validate_collection_id(self, collection_id: str) -> Optional[str]:
        """Validate and return collection ID or None"""
        if not collection_id or collection_id.lower() in ["none", "", "null"]:
            return None
        # Basic UUID format validation
        if len(collection_id) < 8 or not any(c.isalnum() for c in collection_id):
            self.log_debug(f"Invalid collection ID format: {collection_id}")
            return None
        return collection_id

    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers for API requests"""
        return {
            "Authorization": f"Bearer {self.valves.H2OGPTE_API_KEY}"
        }

    def upload_file_with_requests(self, file_path: str) -> str:
        """Upload file using requests library"""
        try:
            url = f"{self.valves.H2OGPTE_URL}/api/v1/uploads"
            headers = self._get_headers()
            
            filename = os.path.basename(file_path)
            
            with open(file_path, 'rb') as file:
                files = {
                    'file': (filename, file, 'application/octet-stream')
                }
                
                self.log_debug(f"Uploading file to: {url}")
                response = requests.put(url, headers=headers, files=files)
                
                if response.status_code != 200:
                    raise RuntimeError(f"Upload failed with status {response.status_code}: {response.text}")
                
                result = response.json()
                upload_id = result.get('id')
                
                if not upload_id:
                    raise RuntimeError(f"No upload ID returned: {result}")
                
                self.log_debug(f"Upload successful: {result}")
                return upload_id
                
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Upload request failed: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Upload error: {str(e)}")

    def ingest_upload_with_requests(self, upload_id: str, collection_id: str) -> str:
        """Ingest uploaded file using requests library"""
        try:
            url = f"{self.valves.H2OGPTE_URL}/api/v1/uploads/{upload_id}/ingest"
            headers = self._get_headers()
            headers['Content-Type'] = 'application/json'
            
            params = {'collection_id': collection_id}
            
            self.log_debug(f"Starting ingestion: {url}")
            response = requests.post(url, headers=headers, params=params)
            
            # Handle successful ingestion (200/201/202 with JSON or 204 no content)
            if response.status_code in [200, 201, 202]:
                try:
                    result = response.json()
                    if isinstance(result, dict):
                        ingestion_id = result.get('id') or result.get('ingestion_id') or upload_id
                    else:
                        ingestion_id = str(result)
                except:
                    # If response is not JSON, use the upload_id as ingestion_id
                    ingestion_id = upload_id
                    
            elif response.status_code == 204:
                # 204 No Content - successful ingestion started
                ingestion_id = upload_id
                self.log_debug(f"Ingestion started successfully (204): {ingestion_id}")
                
            else:
                raise RuntimeError(f"Ingestion failed with status {response.status_code}: {response.text}")
            
            self.log_debug(f"Ingestion started with ID: {ingestion_id}")
            return ingestion_id
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ingestion request failed: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Ingestion error: {str(e)}")

    def check_ingestion_status_with_requests(self, ingestion_id: str) -> Dict[str, Any]:
        """Check ingestion status using requests library"""
        try:
            url = f"{self.valves.H2OGPTE_URL}/api/v1/ingestions/{ingestion_id}"
            headers = self._get_headers()
            
            response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                # If ingestion endpoint doesn't exist, try uploads endpoint
                alt_url = f"{self.valves.H2OGPTE_URL}/api/v1/uploads/{ingestion_id}/status"
                alt_response = requests.get(alt_url, headers=headers)
                if alt_response.status_code == 200:
                    return alt_response.json()
                else:
                    raise RuntimeError(f"Status check failed: {response.status_code}: {response.text}")
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Status check request failed: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Status check error: {str(e)}")

    def upload_and_ingest(self, file_path: str, collection_name: str = None, description: str = "") -> str:
        """Upload and ingest document to H2O GPT Enterprise using requests"""
        try:
            self.init_client()
            
            if collection_name is None:
                collection_name = self.valves.DEFAULT_COLLECTION_NAME
            
            # Step 1: Create or use existing collection
            if self.current_collection_id:
                collection_id = self.current_collection_id
                self.log_debug(f"Using existing collection: {collection_id}")
            else:
                collection_id = self.client.create_collection(
                    name=collection_name,
                    description=description
                )
                self.current_collection_id = collection_id
                # Update the valves with the new collection ID
                self.valves.COLLECTION_ID = collection_id
                print(f"✅ Collection created: {collection_name} ({collection_id})")

            # Step 2: Upload document using requests
            filename = os.path.basename(file_path)
            upload_id = self.upload_file_with_requests(file_path)
            print(f"📂 File uploaded: {filename} (upload_id={upload_id})")

            # Step 3: Ingest document using requests
            ingestion_id = self.ingest_upload_with_requests(upload_id, collection_id)
            print(f"⚙️ Ingestion started (id={ingestion_id})...")

            # Step 4: Poll ingestion status until finished
            start_time = time.time()
            while True:
                if time.time() - start_time > self.valves.INGESTION_TIMEOUT:
                    raise TimeoutError(f"Ingestion timed out after {self.valves.INGESTION_TIMEOUT} seconds")
                
                try:
                    status_info = self.check_ingestion_status_with_requests(ingestion_id)
                    state = status_info.get('state') or status_info.get('status') or 'processing'
                    
                    if state.lower() in ['completed', 'success', 'done']:
                        print("🎉 Document ingested successfully!")
                        # Mark file as uploaded
                        self.uploaded_files[file_path] = collection_id
                        return collection_id
                    elif state.lower() in ['failed', 'error']:
                        error_msg = status_info.get('error') or status_info.get('message', 'Unknown ingestion error')
                        raise RuntimeError(f"❌ Ingestion failed: {error_msg}")
                    else:
                        print(f"⏳ Ingestion status: {state}... waiting")
                        time.sleep(3)
                        
                except Exception as status_error:
                    self.log_debug(f"Status check error: {status_error}")
                    # Continue trying for a while in case it's a temporary issue
                    if time.time() - start_time < 30:  # First 30 seconds, keep trying
                        print(f"⏳ Status check failed, retrying... ({status_error})")
                        time.sleep(5)
                        continue
                    else:
                        # After 30 seconds, assume success if we can't check status
                        print("⚠️ Cannot verify ingestion status, assuming success...")
                        # Mark file as uploaded
                        self.uploaded_files[file_path] = collection_id
                        return collection_id

        except Exception as e:
            error_msg = f"Upload and ingestion error: {str(e)}"
            print(error_msg)
            raise RuntimeError(error_msg)
    
    def _list_all_dirs(self, base_path="/app"):
        print(f"\n📂 Walking filesystem from {base_path} ...\n")
        for root, dirs, files in os.walk(base_path):
            level = root.replace(base_path, "").count(os.sep)
            indent = " " * (4 * level)
            print(f"{indent}{os.path.basename(root)}/")
            subindent = " " * (4 * (level + 1))
            for f in files:
                print(f"{subindent}{f}")

    async def inlet(self, body: Dict[str, Any], user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        SHARED_UPLOAD_DIR = "/app/uploads"

        print("=== Inlet triggered ===")

        if body.get("files"):
            # Handle file upload and ingestion
            file_info = body["files"][0]
            filename = file_info["file"]["filename"]
            local_path = file_info["file"]["path"]

            shared_path = local_path.replace(
                "/app/backend/data/uploads",
                SHARED_UPLOAD_DIR
            )

            print("Filename:", filename)
            print("Reported local path:", local_path)
            print("Expected shared path:", shared_path)

            if os.path.exists(shared_path):
                print(f"✅ File exists in shared storage: {shared_path}")
                
                # Check if file has already been uploaded and ingested
                if shared_path in self.uploaded_files:
                    collection_id = self.uploaded_files[shared_path]
                    print(f"📋 File already ingested to collection: {collection_id}")
                    
                    # Set status and remove files from body to prevent re-ingestion
                    body["ingestion_status"] = "already_uploaded"
                    body["collection_id"] = collection_id
                    #body["message"] = f"Document '{filename}' is already ingested and ready for queries."
                    
                    # Remove files and pipeline_file_path to prevent re-processing
                    del body["files"]
                    if "pipeline_file_path" in body:
                        del body["pipeline_file_path"]
                    
                    # Ensure we use the correct collection
                    self.current_collection_id = collection_id
                    self.valves.COLLECTION_ID = collection_id
                else:
                    # File not yet uploaded, proceed with ingestion
                    body["pipeline_file_path"] = shared_path

                    # Ingest the document to H2O GPT Enterprise
                    try:
                        if not self.valves.COLLECTION_ID and self.valves.AUTO_CREATE_COLLECTION:
                            print("📤 No collection ID set, will create new collection and ingest document...")
                            collection_id = self.upload_and_ingest(
                                file_path=shared_path,
                                collection_name=f"{self.valves.DEFAULT_COLLECTION_NAME}_{int(time.time())}",
                                description=f"Auto-created collection for {filename}"
                            )
                            body["ingestion_status"] = "success"
                            body["collection_id"] = collection_id
                            print(f"🎉 Document successfully ingested to collection: {collection_id}")
                        elif self.valves.COLLECTION_ID:
                            print(f"📤 Ingesting document to existing collection: {self.valves.COLLECTION_ID}")
                            self.current_collection_id = self.valves.COLLECTION_ID
                            collection_id = self.upload_and_ingest(
                                file_path=shared_path,
                                description=f"Document: {filename}"
                            )
                            body["ingestion_status"] = "success"
                            body["collection_id"] = collection_id
                            print(f"🎉 Document successfully ingested to collection: {collection_id}")
                        else:
                            print("⚠️ No collection ID set and auto-creation disabled. Document uploaded but not ingested.")
                            body["ingestion_status"] = "skipped"
                            body["message"] = "Document uploaded but not ingested. Please set COLLECTION_ID or enable AUTO_CREATE_COLLECTION."
                        
                        # Remove files from body after successful ingestion to prevent re-processing
                        if body.get("ingestion_status") == "success":
                            del body["files"]
                            if "pipeline_file_path" in body:
                                del body["pipeline_file_path"]
                    
                    except Exception as e:
                        error_msg = f"Failed to ingest document: {str(e)}"
                        print(f"❌ {error_msg}")
                        body["ingestion_status"] = "failed"
                        body["ingestion_error"] = error_msg

            else:
                print(f"❌ File not found in shared storage: {shared_path}")
                body["file_error"] = f"File not found: {shared_path}"

        else:
            # Handle query-only requests
            print("📄 No files in body — treating as query/message request")
            if "queries" in body:
                print("Queries:", body["queries"])

        return body

    def pipe(
        self,
        user_message: str,
        model_id: str,
        messages: List[Dict[str, Any]],
        body: Dict[str, Any],
        files: Optional[List[str]] = None,
    ) -> Union[str, Generator[str, None, None]]:
        try:
            is_streaming = body.get("stream", False)
            self.init_client()
            
            # Check if there was an ingestion process
            ingestion_status = body.get("ingestion_status")
            if ingestion_status == "success":
                collection_id = body.get("collection_id")
                if collection_id:
                    self.current_collection_id = collection_id
                    # Update valves for future queries
                    self.valves.COLLECTION_ID = collection_id
            elif ingestion_status == "already_uploaded":
                collection_id = body.get("collection_id")
                if collection_id:
                    self.current_collection_id = collection_id
                    # Update valves for future queries
                    self.valves.COLLECTION_ID = collection_id
            
            # Validate collection ID
            collection_id = self._validate_collection_id(self.current_collection_id or self.valves.COLLECTION_ID)
            self.log_debug(f"Using collection: {collection_id}")
            
            # Add ingestion status to response if applicable
            prefix = ""
            if ingestion_status == "success":
                prefix = "✅ Document successfully ingested and ready for queries!\n\n"
            # elif ingestion_status == "already_uploaded":
            #     prefix = f"📋 {body.get('message', 'Document already available for queries')}\n\n"
            elif ingestion_status == "failed":
                prefix = f"⚠️ Document ingestion failed: {body.get('ingestion_error', 'Unknown error')}\nProceeding with query using existing collection...\n\n"
            elif ingestion_status == "skipped":
                prefix = f"⚠️ {body.get('message', 'Document not ingested')}\n\n"
            
            # Check if there's an actual query message to process
            if not user_message or user_message.strip() == "":
                # Only return the status message without querying H2OGPTE
                if prefix:
                    return prefix.rstrip()  # Remove trailing newlines for cleaner output
                else:
                    return "Document processed successfully. You can now ask questions about it."
            
            # Create chat session for actual queries
            chat_session_id = self.client.create_chat_session(collection_id=collection_id)
            
            # Determine RAG type
            rag_type = "rag" if collection_id else "llm_only"
            
            if is_streaming:
                return self._stream_with_prefix(prefix, user_message, chat_session_id, rag_type)
            else:
                response = self._query_h2ogpte(user_message, chat_session_id, rag_type, is_streaming)
                return prefix + response if isinstance(response, str) else response
                
        except Exception as e:
            error_msg = f"Pipeline Error: {str(e)}"
            self.log_debug(error_msg)
            return error_msg

    def _stream_with_prefix(self, prefix: str, user_message: str, chat_session_id: str, rag_type: str) -> Generator[str, None, None]:
        """Stream response with prefix message"""
        if prefix:
            yield prefix
        
        for chunk in self._query_h2ogpte(user_message, chat_session_id, rag_type, True):
            yield chunk

    def _query_h2ogpte(self, user_message: str, chat_session_id: str, rag_type: str, is_streaming: bool) -> Union[str, Generator[str, None, None]]:
        """Unified query method for both streaming and non-streaming"""
        query_args = {
            "message": user_message,
            "llm": "auto",
            "llm_args": {
                "enable_vision": "auto",
                "visible_vision_models": ["auto"],
                "use_agent": False,
                "cost_controls": {
                    "max_cost": 0.05,
                    "willingness_to_pay": 0.2,
                    "willingness_to_wait": 10,
                    "max_cost_per_million_tokens": 75,
                    "model": None,
                },
                "client_metadata": "h2ogpte-openwebui-single-pipeline",
            },
            "self_reflection_config": None,
            "rag_config": {"rag_type": rag_type},
            "include_chat_history": "auto",
            "timeout": self.valves.STREAM_TIMEOUT,
        }

        if is_streaming:
            return self._stream_response(chat_session_id, query_args)
        else:
            return self._get_response(chat_session_id, query_args)

    def _stream_response(self, chat_session_id: str, query_args: dict) -> Generator[str, None, None]:
        try:
            response_queue = queue.Queue()
            completed = threading.Event()
            last_content = ""

            def safe_concat(last: str, delta: str) -> str:
                if last and delta:
                    # If last ends with a letter/number and delta starts with one → insert space
                    if last[-1].isalnum() and delta[0].isalnum():
                        return last + " " + delta
                return last + delta

            def streaming_callback(message):
                nonlocal last_content
                try:
                    if isinstance(message, PartialChatMessage) and message.content:
                        new_text = message.content

                        # Find the new delta safely
                        if new_text.startswith(last_content):
                            delta = new_text[len(last_content):]
                        else:
                            # fallback: find longest common prefix
                            i = 0
                            while i < len(new_text) and i < len(last_content) and new_text[i] == last_content[i]:
                                i += 1
                            delta = new_text[i:]

                        if delta:
                            fixed = safe_concat(last_content, delta)[len(last_content):]
                            response_queue.put(fixed)
                            last_content = safe_concat(last_content, delta)

                except Exception as e:
                    self.log_debug(f"Callback error: {e}")

            def query_thread():
                try:
                    with self.client.connect(chat_session_id) as session:
                        session.query(**query_args, callback=streaming_callback)
                except Exception as e:
                    response_queue.put(f"Query error: {str(e)}")
                finally:
                    completed.set()

            thread = threading.Thread(target=query_thread)
            thread.daemon = True
            thread.start()

            yielded_content = set()  # Track yielded content to prevent duplicates
            
            # Stream responses until completion
            while not completed.is_set() or not response_queue.empty():
                try:
                    content = response_queue.get(timeout=1.0)
                    # Only yield if we haven't seen this exact content before
                    if content not in yielded_content:
                        yielded_content.add(content)
                        yield content
                except queue.Empty:
                    continue
                except Exception as e:
                    self.log_debug(f"Stream error: {e}")
                    break

        except Exception as e:
            yield f"Streaming error: {str(e)}"

    def _get_response(self, chat_session_id: str, query_args: dict) -> str:
        try:
            with self.client.connect(chat_session_id) as session:
                reply = session.query(**query_args)
            return reply.content or "No response received"
        except Exception as e:
            return f"Response error: {str(e)}"