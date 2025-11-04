##This pipeline will connect user to a H2OGPTE Collection with document ingestion support
import os
import time
import threading
import queue
from typing import List, Optional, Union, Generator, Dict, Any
#from oracledb import message
from pydantic import BaseModel
import requests
import json
import re
import shutil
import concurrent.futures
import tempfile
try:
    from h2ogpte import H2OGPTE
    from h2ogpte.types import PartialChatMessage, ChatMessage
except ImportError:
    print("h2ogpte package not installed. Install with: pip install h2ogpte")
    H2OGPTE = None
    PartialChatMessage = None
    ChatMessage = None


class Pipeline:
    """Enhanced H2OGPTE Pipeline with improved streaming display and final answer extraction"""
    
    class Valves(BaseModel):
        """Configuration parameters"""
        H2OGPTE_API_KEY: str = ""
        H2OGPTE_URL: str = ""
        COLLECTION_ID: str = ""  # Optional collection ID
        AUTO_CREATE_COLLECTION: bool = True  # Auto-create collection if not set
        DEFAULT_COLLECTION_NAME: str = "AutoDocs"
        DEBUG_MODE: bool = False
        USE_AGENT: bool = False  # Use agentic capabilities
        STREAM_TIMEOUT: int = 600
        INGESTION_TIMEOUT: int = 300  # 5 minutes timeout for ingestion
        OPENWEBUI_API_KEY: str = ""  # OpenWebUI API key for file uploads
        OPENWEBUI_BASE_URL: str = "http://localhost:3000"  # OpenWebUI base URL

    def __init__(self):
        self.type = "manifold"
        self.id = "h2ogpte_single"
        self.name = ""
        self.session_id_n_files_map = {}
        
        self.valves = self.Valves(
            **{
                "H2OGPTE_API_KEY": os.getenv("H2OGPTE_API_KEY", ""),
                "H2OGPTE_URL": os.getenv("H2OGPTE_URL", "https://h2ogpte.genai.h2o.ai"),
                "COLLECTION_ID": os.getenv("COLLECTION_ID", ""),
                "AUTO_CREATE_COLLECTION": os.getenv("AUTO_CREATE_COLLECTION", "true").lower() == "true",
                "DEFAULT_COLLECTION_NAME": os.getenv("DEFAULT_COLLECTION_NAME", "OpenWebUI Documents"),
                "DEBUG_MODE": os.getenv("DEBUG_MODE", "false").lower() == "true",
                "USE_AGENT": os.getenv("USE_AGENT", "false").lower() == "true",
                "STREAM_TIMEOUT": int(os.getenv("STREAM_TIMEOUT", "60")),
                "INGESTION_TIMEOUT": int(os.getenv("INGESTION_TIMEOUT", "300")),
                "OPENWEBUI_API_KEY": os.getenv("OPENWEBUI_API_KEY", ""),
                "OPENWEBUI_BASE_URL": os.getenv("OPENWEBUI_BASE_URL", "http://localhost:3000"),
            }
        )
        
        # Persistent connection attributes
        self.client: Optional[H2OGPTE] = None
        self.current_collection_id: Optional[str] = None
        self.chat_session_id: Optional[str] = None
        self.current_openwebui_chat_id: Optional[str] = None  # Track OpenWebUI chat ID
        self.current_file_path: Optional[str] = None

    def params(self) -> List[Dict[str, Any]]:
        """
        Define chat-level parameters exposed in OpenWebUI's advanced settings.
        These parameters can be configured per-chat by end users.
        """
        return [
            {
                "id": "collection_id",
                "label": "Collection ID",
                "type": "str",
                "value": "",
                "placeholder": "Enter H2OGPTE collection ID (leave empty for auto-create)",
                "description": "Specify which H2OGPTE collection to use for RAG. Leave empty to auto-create a new collection when uploading documents."
            },
            {
                "id": "use_agent",
                "label": "Enable Agent Mode",
                "type": "bool",
                "value": False,
                "description": "Enable agentic capabilities with tool use (web search, document analysis, etc.). Shows detailed agent workflow when enabled."
            },
            {
                "id": "temperature",
                "label": "Temperature",
                "type": "float",
                "value": 0.2,
                "min": 0.0,
                "max": 2.0,
                "step": 0.1,
                "description": "Controls randomness in responses. Lower values (0.0-0.3) are more focused and deterministic, higher values (0.7-2.0) are more creative."
            },
            {
                "id": "max_tokens",
                "label": "Max Tokens",
                "type": "int",
                "value": 32768,
                "min": 512,
                "max": 131072,
                "step": 512,
                "description": "Maximum number of tokens in the response. Higher values allow longer responses but may increase cost."
            },
            {
                "id": "agent_max_turns",
                "label": "Agent Max Turns",
                "type": "int",
                "value": 7,
                "min": 1,
                "max": 20,
                "step": 1,
                "description": "Maximum number of agent iterations when agent mode is enabled. Higher values allow more complex multi-step reasoning."
            },
            {
                "id": "agent_accuracy",
                "label": "Agent Accuracy",
                "type": "str",
                "value": "basic",
                "choices": ["basic", "medium", "high", "maximum"],
                "description": "Agent accuracy level. Higher accuracy uses more resources but provides better results."
            },
            {
                "id": "rag_type",
                "label": "RAG Type",
                "type": "str",
                "value": "auto",
                "choices": ["auto", "llm_only", "rag", "hyde"],
                "description": "Retrieval strategy: 'auto' decides based on collection, 'llm_only' uses no documents, 'rag' uses vector search, 'hyde' uses hypothetical document embeddings."
            },
            {
                "id": "debug_mode",
                "label": "Debug Mode",
                "type": "bool",
                "value": False,
                "description": "Enable detailed debug logging for troubleshooting."
            },
            {
                "id": "stream_timeout",
                "label": "Stream Timeout (seconds)",
                "type": "int",
                "value": 60,
                "min": 10,
                "max": 300,
                "step": 10,
                "description": "Timeout for streaming responses in seconds."
            },
            {
                "id": "auto_create_collection",
                "label": "Auto-Create Collection",
                "type": "bool",
                "value": True,
                "description": "Automatically create a new collection when uploading documents if no collection ID is specified."
            },
            {
                "id": "enable_vision",
                "label": "Enable Vision",
                "type": "str",
                "value": "auto",
                "choices": ["auto", "on", "off"],
                "description": "Enable vision/multimodal capabilities for image understanding."
            },
            {
                "id": "include_chat_history",
                "label": "Include Chat History",
                "type": "str",
                "value": "auto",
                "choices": ["auto", "on", "off"],
                "description": "Include previous conversation context in queries."
            }
        ]

    def _resolve_param(self, body: Dict[str, Any], param_name: str, default: Any) -> Any:
        """Resolve parameter with precedence: body > valves > default"""
        if param_name in body:
            value = body[param_name]
            if value is not None and value != "":
                return value
        
        valves_param_name = param_name.upper()
        if hasattr(self.valves, valves_param_name):
            valve_value = getattr(self.valves, valves_param_name)
            if valve_value is not None and valve_value != "":
                return valve_value
        
        default_valve_name = f"DEFAULT_{param_name.upper()}"
        if hasattr(self.valves, default_valve_name):
            valve_value = getattr(self.valves, default_valve_name)
            if valve_value is not None and valve_value != "":
                return valve_value
        
        return default
    
    def _build_query_args(self, user_message: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build query arguments using resolved parameters from chat-level and pipeline-level configs.
        This implements the precedence hierarchy: chat params > pipeline valves > hardcoded defaults
        """
        # Resolve all parameters using the precedence hierarchy
        use_agent = self._resolve_param(body, "use_agent", False)
        temperature = self._resolve_param(body, "temperature", 0.2)
        max_tokens = self._resolve_param(body, "max_tokens", 32768)
        agent_max_turns = self._resolve_param(body, "agent_max_turns", 7)
        agent_accuracy = self._resolve_param(body, "agent_accuracy", "basic")
        rag_type = self._resolve_param(body, "rag_type", "auto")
        stream_timeout = self._resolve_param(body, "stream_timeout", 60)
        enable_vision = self._resolve_param(body, "enable_vision", "auto")
        include_chat_history = self._resolve_param(body, "include_chat_history", "auto")
        
        # Determine actual rag_type based on collection
        if rag_type == "auto":
            rag_type = "rag" if self.current_collection_id else "llm_only"
        
        self.log_debug(f"Resolved parameters: use_agent={use_agent}, temp={temperature}, "
                      f"max_tokens={max_tokens}, rag_type={rag_type}", body)
        
        query_args = {
            "message": user_message,
            "llm": "auto",
            "llm_args": {
                "temperature": float(temperature),
                "max_new_tokens": int(max_tokens),
                "enable_vision": enable_vision,
                "visible_vision_models": ["auto"],
                "use_agent": use_agent,
                "agent_max_turns": int(agent_max_turns),
                "agent_accuracy": agent_accuracy,
                "agent_timeout": 30,
                "agent_tools": [
                    "ask_question_about_documents.py",
                ],
                "cost_controls": {
                    "max_cost": 0.05,
                    "willingness_to_pay": 0.2,
                    "willingness_to_wait": 10,
                    "max_cost_per_million_tokens": 75,
                    "model": None,
                },
                "client_metadata": "h2ogpte-openwebui-improved-pipeline",
            },
            "self_reflection_config": None,
            "rag_config": {
                "rag_type": rag_type,
            },
            "include_chat_history": include_chat_history,
            "timeout": int(stream_timeout),
        }
        
        return query_args
    
    def log_debug(self, message: str, body: Optional[Dict[str, Any]] = None) -> None:
        """Log debug messages when DEBUG_MODE is enabled"""
        if not self.valves.DEBUG_MODE:
            return
        
        debug_message = f"[H2OGPTE] {message}"
        
        if body:
            debug_info = []
            if "use_agent" in body:
                debug_info.append(f"body.use_agent={body['use_agent']}")
            if "temperature" in body:
                debug_info.append(f"body.temperature={body['temperature']}")
            if "chat_id" in body.get("metadata", {}):
                debug_info.append(f"chat_id={body['metadata']['chat_id']}")
            
            if debug_info:
                debug_message += f" | {', '.join(debug_info)}"
        
        print(debug_message)
    

    async def on_startup(self) -> None:
        """Initialize client and chat session on startup"""
        if not self.valves.H2OGPTE_API_KEY:
            print("H2OGPTE_API_KEY not set")
            return
        if H2OGPTE is None:
            print("h2ogpte package not available")
            return
            
        try:
            self.init_client()
            self.init_chat_session()
            print("✅ H2OGPTE client and chat session initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize H2OGPTE: {e}")

    async def on_shutdown(self) -> None:
        """Clean up connections on shutdown"""
        self.chat_session_id = None
        self.client = None
        self.current_collection_id = None
        self.current_openwebui_chat_id = None
        self.current_file_path = None

    async def on_valves_updated(self) -> None:
        """Reinitialize when configuration changes"""
        print("🔄 Configuration updated, reinitializing connections...")
        self.chat_session_id = None
        self.client = None
        self.current_collection_id = None
        self.current_openwebui_chat_id = None
        self.current_file_path = None
        
        # Reinitialize if we have valid config
        if self.valves.H2OGPTE_API_KEY and self.valves.H2OGPTE_URL and H2OGPTE is not None:
            try:
                self.init_client()
                self.init_chat_session()
                print("✅ Reinitialization complete")
            except Exception as e:
                print(f"❌ Reinitialization failed: {e}")

    def pipelines(self) -> List[Dict[str, str]]:
        """Return available pipeline models - called during startup"""
        try:
            return [{"id": "h2ogpte", "name": "H2OGPTe"}]
        except Exception as e:
            print(f"Error in pipelines method: {e}")
            return [{"id": "h2ogpte", "name": "H2OGPTe"}]

    def init_client(self) -> None:
        """Initialize H2OGPTE client if not already initialized"""
        if not self.valves.H2OGPTE_API_KEY or not self.valves.H2OGPTE_URL or H2OGPTE is None:
            raise ValueError("Missing configuration or h2ogpte package")
        
        if self.client is None:
            self.client = H2OGPTE(
                address=self.valves.H2OGPTE_URL,
                api_key=self.valves.H2OGPTE_API_KEY,
            )
            self.log_debug("Client initialized")

    def init_chat_session(self) -> None:
        """Initialize chat session if not already initialized"""
        if self.chat_session_id is None and self.client is not None:
            # Validate and set collection ID
            collection_id = self._validate_collection_id(self.valves.COLLECTION_ID)
            if collection_id:
                self.current_collection_id = collection_id
            
            # Create chat session
            self.chat_session_id = self.client.create_chat_session(collection_id=self.current_collection_id)
            self.session_id_n_files_map[self.chat_session_id] = 0
            self.log_debug(f"Chat session created: {self.chat_session_id} (collection: {self.current_collection_id})")

    def reset_chat_session(self, collection_id: Optional[str] = None, reason: str = "reset requested") -> None:
        """Reset chat session with new collection if needed"""
        print(f"Resetting chat session - {reason}")
        if collection_id != self.current_collection_id:
            self.current_collection_id = collection_id
            
        self.chat_session_id = None
        if self.client:
            self.chat_session_id = self.client.create_chat_session(collection_id=collection_id)
            self.log_debug(f"Chat session reset with collection: {collection_id}")

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
    
    def _download_and_upload_agent_files(self, message_id: str, chat_id: str) -> list:
        """Download agent-generated files and upload to OpenWebUI"""
        print(f"Downloading and uploading agent files for message ID: {message_id}, chat ID: {chat_id}")
        
        try:
            if not self.client:
                self.log_debug("Client not initialized, cannot download agent files")
                return []
            
            # Step 1: Get agent_files metadata
            try:
                agent_files_meta = self.client.list_chat_message_meta_part(message_id, "agent_files")
                
                if not agent_files_meta or not agent_files_meta.content:
                    self.log_debug("No agent files metadata found")
                    return []
                
                # Parse the JSON list of files
                agent_files = json.loads(agent_files_meta.content)
                
                if not agent_files or len(agent_files) == 0:
                    self.log_debug("Agent files list is empty")
                    return []
                
                print(f"Found {len(agent_files)} agent-generated files")
                
            except Exception as e:
                self.log_debug(f"Error retrieving agent files metadata: {str(e)}")
                return []
            
            # Step 2: Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix=f"h2ogpte_agent_{chat_id}_")
            
            try:
                result = []
                
                # Step 3: Download each agent file
                for file_entry in agent_files:
                    # Extract document_id and filename: {"document_id": "filename.ext"}
                    doc_id = list(file_entry.keys())[0]
                    doc_name = file_entry[doc_id]
                    
                    print(f"Processing agent file: {doc_name} (ID: {doc_id})")
                    
                    try:
                        # Download to temp directory
                        self.client.download_document(temp_dir, doc_name, doc_id)
                        file_path = os.path.join(temp_dir, doc_name)
                        
                        if not os.path.exists(file_path):
                            print(f"❌ Downloaded file not found: {file_path}")
                            continue
                        
                        print(f"✅ Downloaded agent file: {doc_name}")
                        
                        # Step 4: Upload to OpenWebUI
                        upload_result = self.upload_file_to_openwebui(file_path)
                        
                        if upload_result:
                            file_id = upload_result.get('id')
                            
                            # Determine file type
                            file_ext = os.path.splitext(doc_name)[1].lower()
                            file_type_map = {
                                '.png': 'image',
                                '.jpg': 'image',
                                '.jpeg': 'image',
                                '.gif': 'image',
                                '.pdf': 'pdf',
                                '.txt': 'text',
                                '.json': 'json',
                                '.csv': 'csv'
                            }
                            file_type = file_type_map.get(file_ext, 'file')
                            
                            result.append({
                                "id": file_id,
                                "name": doc_name,
                                "upload_url": f"{self.valves.OPENWEBUI_BASE_URL}/api/v1/files/{file_id}/content",
                                "view_url": f"{self.valves.OPENWEBUI_BASE_URL}/api/v1/files/{file_id}/content",
                                "type": file_type,
                                "source": "h2ogpte_agent",
                                "document_id": doc_id
                            })
                            
                            self.log_debug(f"Successfully uploaded agent file {doc_name} to OpenWebUI with ID: {file_id}")
                        else:
                            result.append({
                                "name": doc_name,
                                "path": file_path,
                                "type": "file",
                                "source": "h2ogpte_agent",
                                "document_id": doc_id,
                                "error": "Failed to upload to OpenWebUI"
                            })
                            self.log_debug(f"Failed to upload agent file {doc_name} to OpenWebUI")
                    
                    except Exception as file_error:
                        print(f"❌ Error processing agent file {doc_name}: {str(file_error)}")
                        result.append({
                            "name": doc_name,
                            "document_id": doc_id,
                            "error": str(file_error),
                            "source": "h2ogpte_agent"
                        })
                
                self.log_debug(f"Processed {len(result)} agent files")
                return result
            
            finally:
                # Clean up temp directory
                try:
                    shutil.rmtree(temp_dir)
                    self.log_debug(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as cleanup_error:
                    self.log_debug(f"Failed to clean up temp directory: {cleanup_error}")
        
        except Exception as e:
            self.log_debug(f"Error downloading and uploading agent files: {str(e)}")
            return []


    def upload_file_to_openwebui(self, file_path: str) -> Optional[Dict[str, Any]]:
        print(f"Uploading file to OpenWebUI: {file_path}")
        """Upload file to OpenWebUI and return file info"""
        if not self.valves.OPENWEBUI_API_KEY:
            self.log_debug("OpenWebUI API key not configured, skipping upload")
            return None
            
        try:
            url = f"{self.valves.OPENWEBUI_BASE_URL}/api/v1/files/"
            headers = {
                'Authorization': f'Bearer {self.valves.OPENWEBUI_API_KEY}',
                'Accept': 'application/json'
            }
            
            filename = os.path.basename(file_path)
            
            with open(file_path, 'rb') as file:
                files = {'file': (filename, file, 'application/pdf')}
                
                self.log_debug(f"Uploading file to OpenWebUI: {url}")
                response = requests.post(url, headers=headers, files=files)
                
                if response.status_code in [200, 201]:
                    result = response.json()
                    self.log_debug(f"OpenWebUI upload successful: {result}")
                    return result
                else:
                    self.log_debug(f"OpenWebUI upload failed with status {response.status_code}: {response.text}")
                    return None
                    
        except requests.exceptions.RequestException as e:
            self.log_debug(f"OpenWebUI upload request failed: {str(e)}")
            return None
        except Exception as e:
            self.log_debug(f"OpenWebUI upload error: {str(e)}")
            return None
   
    def _extract_final_answer_robust(self, full_text: str) -> Optional[str]:
        """
        Enhanced final answer extraction with improved filtering for agentic responses.
        Handles complex agentic workflows with multiple metadata blocks.
        """
        
        # Strategy 1: Look for content with stream_turn_title tags
        pattern = re.compile(
            r"<stream_turn_title>(.*?)</stream_turn_title>(.*?)(?=<stream_turn_title>|ENDOFTURN|$)", 
            re.DOTALL
        )
        matches = pattern.findall(full_text)
        
        if matches:
            substantial_matches = []
            
            for title, content in matches:
                cleaned_content = content.strip()
                
                # More comprehensive filtering for metadata and technical artifacts
                is_metadata = (
                    cleaned_content.startswith('**Completed LLM call') or
                    cleaned_content.startswith('**Executing python') or
                    cleaned_content.startswith('**Process using') or
                    cleaned_content.startswith('** [') or
                    cleaned_content.startswith('**LLM Call Info:') or
                    'No code blocks executed' in cleaned_content or
                    'No executable code blocks found' in cleaned_content or
                    'Max turns' in cleaned_content and 'reached' in cleaned_content or
                    'Turn Time:' in cleaned_content or
                    'Cost:' in cleaned_content or
                    len(cleaned_content) < 100  # Too short to be substantial
                )
                
                if not is_metadata:
                    substantial_matches.append((title.strip(), cleaned_content))
            
            self.log_debug(f"Found {len(substantial_matches)} substantial content matches")
            
            # Use the LAST substantial match as the final answer
            if substantial_matches:
                final_title, final_content = substantial_matches[-1]
                self.log_debug(f"Selected final answer from section: '{final_title}'")
                return self._clean_extracted_content(final_content)
        
        # Strategy 2: Look for large content blocks without stream structure
        content_blocks = self._extract_substantial_content_blocks(full_text)
        if content_blocks:
            # Return the last substantial block
            return self._clean_extracted_content(content_blocks[-1])
        
        # Strategy 3: Enhanced fallback - look for markdown headers and structured content
        fallback_content = self._extract_enhanced_fallback(full_text)
        if fallback_content:
            return self._clean_extracted_content(fallback_content)
        
        # Strategy 4: Last resort - extract everything after last ENDOFTURN
        last_endofturn_pos = full_text.rfind('ENDOFTURN')
        if last_endofturn_pos != -1:
            remaining_text = full_text[last_endofturn_pos + len('ENDOFTURN'):].strip()
            # Only use if it's substantial
            if len(remaining_text) > 200 and not remaining_text.startswith('**'):
                return self._clean_extracted_content(remaining_text)
        
        return None


    def _extract_substantial_content_blocks(self, full_text: str) -> List[str]:
        """
        Extract substantial content blocks, filtering out all technical metadata.
        """
        lines = full_text.split('\n')
        content_blocks = []
        current_block = []
        in_metadata_section = False
        
        for line in lines:
            stripped_line = line.strip()
            
            # Detect start of metadata sections
            if (stripped_line.startswith('**Completed LLM call') or 
                stripped_line.startswith('**Executing python') or
                stripped_line.startswith('**Process using') or
                stripped_line.startswith('** [') or
                stripped_line.startswith('**LLM Call Info:')):
                in_metadata_section = True
                
                # Save current block if substantial before entering metadata
                if current_block:
                    block_text = '\n'.join(current_block).strip()
                    if len(block_text) > 200:  # Substantial threshold
                        content_blocks.append(block_text)
                current_block = []
                continue
            
            # Detect end of metadata sections
            if in_metadata_section and stripped_line == '':
                in_metadata_section = False
                continue
            
            # Skip lines that are clearly metadata
            if (stripped_line.startswith('ENDOFTURN') or
                '<stream_turn_title>' in stripped_line or
                '</stream_turn_title>' in stripped_line or
                'No executable code blocks found' in stripped_line or
                'No code blocks executed' in stripped_line or
                'Max turns' in stripped_line and 'reached' in stripped_line):
                continue
            
            # Skip if we're in a metadata section
            if in_metadata_section:
                continue
            
            # Add meaningful content lines
            if stripped_line or current_block:  # Include empty lines within blocks
                current_block.append(line)
        
        # Add final block if substantial
        if current_block:
            block_text = '\n'.join(current_block).strip()
            if len(block_text) > 200:
                content_blocks.append(block_text)
        
        return content_blocks


    def _clean_extracted_content(self, content: str) -> str:
        """
        Thoroughly clean extracted content, removing all technical artifacts.
        """
        if not content:
            return ""
        
        # Remove technical metadata blocks
        content = re.sub(r'\*\*Completed LLM call.*?\*\*', '', content, flags=re.DOTALL)
        content = re.sub(r'\*\*Executing python.*?\*\*', '', content, flags=re.DOTALL)
        content = re.sub(r'\*\*Process using.*?\*\*', '', content, flags=re.DOTALL)
        content = re.sub(r'\*\* \[.*?\].*?\*\*', '', content, flags=re.DOTALL)
        content = re.sub(r'\*\*LLM Call Info:.*?\*\*', '', content, flags=re.DOTALL)
        
        # Remove metadata lines
        content = re.sub(r'ENDOFTURN.*?$', '', content, flags=re.DOTALL | re.MULTILINE)
        content = re.sub(r'No executable code blocks found.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r'No code blocks executed.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r'Max turns.*?reached.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r'Turn Time:.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r'Cost:.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r'Turns:.*?out of.*?$', '', content, flags=re.MULTILINE)
        
        # Remove any remaining ENDOFTURN markers
        content = re.sub(r'ENDOFTURN', '', content)
        
        # Remove stream turn title tags if any leaked through
        content = re.sub(r'</?stream_turn_title>', '', content)
        
        # Clean up excessive whitespace while preserving paragraph structure
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
        content = content.strip()
        
        return content


    def _extract_enhanced_fallback(self, full_text: str) -> Optional[str]:
        """
        Enhanced fallback extraction looking for common patterns in final answers.
        """
        # Pattern 1: Look for markdown headers followed by substantial content
        header_pattern = re.compile(r'#{1,3}\s+[A-Z].*?\n\n(.*?)(?=\n#{1,3}\s+[A-Z]|\Z)', re.DOTALL)
        header_matches = header_pattern.findall(full_text)
        
        if header_matches:
            # Find the longest match (likely the most substantive)
            longest_match = max(header_matches, key=len, default=None)
            if longest_match and len(longest_match.strip()) > 300:
                return longest_match.strip()
        
        # Pattern 2: Look for structured lists or tables
        structured_pattern = re.compile(
            r'(?:Understanding|Strategy|Plan|Recommendations?|Approach).*?\n\n((?:[-*•]|\d+\.|\|).*?)(?=\n\n#{1,3}|\Z)',
            re.DOTALL | re.IGNORECASE
        )
        structured_matches = structured_pattern.findall(full_text)
        
        if structured_matches:
            combined_content = '\n\n'.join(structured_matches)
            if len(combined_content.strip()) > 300:
                return combined_content.strip()
        
        # Pattern 3: Look for content after "Based on" or similar analytical phrases
        analysis_pattern = re.compile(
            r'(?:Based on|According to|From (?:our|the) analysis).*?(?:\n\n)(.*?)(?=\n\n\*\*|ENDOFTURN|\Z)',
            re.DOTALL | re.IGNORECASE
        )
        analysis_match = analysis_pattern.search(full_text)
        
        if analysis_match and len(analysis_match.group(1).strip()) > 300:
            return analysis_match.group(1).strip()
        
        # Pattern 4: Find the longest coherent section with multiple paragraphs
        paragraphs = [p.strip() for p in full_text.split('\n\n') if p.strip()]
        
        # Filter out metadata paragraphs
        substantive_paragraphs = [
            p for p in paragraphs 
            if (len(p) > 150 and 
                not p.startswith('**') and
                'ENDOFTURN' not in p and
                'LLM Call Info' not in p and
                'Turn Time:' not in p)
        ]
        
        if substantive_paragraphs:
            # Return the last substantial section (likely the conclusion)
            return substantive_paragraphs[-1]
        
        return None


    def _download_and_upload_reference_highlighting(self, message_id: str, chat_id: str) -> list:
        print(f"Downloading and uploading reference highlighting for message ID: {message_id}, chat ID: {chat_id}")
        """Download PDFs with reference highlighting and upload to OpenWebUI."""
        try:
            if not self.client:
                self.log_debug("Client not initialized, cannot download reference highlighting")
                return []
                
            # Create temporary directory for downloads
            import tempfile
            temp_dir = tempfile.mkdtemp(prefix=f"h2ogpte_refs_{chat_id}_")
            
            try:
                print(f"inside try block of download and upload function")
                # Download reference highlighting using H2OGPTE client
                highlighted_files = self.client.download_reference_highlighting(
                    message_id=message_id,
                    destination_directory=temp_dir,
                    output_type="combined",  # Use combined for better user experience
                    limit=None  # Get all references
                )
                print(f"Downloaded {len(highlighted_files)} highlighted files to {temp_dir}")
                
                # Upload each file to OpenWebUI and collect results
                result = []
                for file_path in highlighted_files:
                    file_name = os.path.basename(file_path)
                    
                    # Upload to OpenWebUI
                    upload_result = self.upload_file_to_openwebui(str(file_path))
                    
                    if upload_result:
                        # Use OpenWebUI file ID and URL
                        file_id = upload_result.get('id')
                        result.append({
                            "id": file_id,
                            "name": file_name,
                            "upload_url": f"{self.valves.OPENWEBUI_BASE_URL}/api/v1/files/{file_id}/content",
                            "view_url":f"http://localhost:3000/api/v1/files/{file_id}/content",
                            "type": "pdf",
                            "source": "h2ogpte_reference"
                        })
                        self.log_debug(f"Successfully uploaded {file_name} to OpenWebUI with ID: {file_id}")
                    else:
                        # Fallback: provide direct file path info
                        result.append({
                            "name": file_name,
                            "path": str(file_path),
                            "type": "pdf",
                            "source": "h2ogpte_reference",
                            "error": "Failed to upload to OpenWebUI"
                        })
                        self.log_debug(f"Failed to upload {file_name} to OpenWebUI")
                
                self.log_debug(f"Processed {len(result)} reference highlighting files")
                return result
                
            finally:
                # Clean up temporary directory
                import shutil
                try:
                    shutil.rmtree(temp_dir)
                    self.log_debug(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as cleanup_error:
                    self.log_debug(f"Failed to clean up temp directory: {cleanup_error}")
                    
        except Exception as e:
            self.log_debug(f"Error downloading and uploading reference highlighting: {str(e)}")
            return []         

    def _stream_response(self, query_args: dict) -> Generator[str, None, None]:
        """Enhanced streaming with prioritized user experience and progressive reference handling"""
        print("Starting enhanced _stream_response with progressive reference processing")

        # Extract the resolved use_agent value from query_args
        use_agent = query_args.get("llm_args", {}).get("use_agent", False)
        
        try:
            response_queue = queue.Queue()
            completed = threading.Event()
            full_stream_buffer = []
            full_msg, partial_msg, message_id = None, None, None
            
            def streaming_callback(message):
                nonlocal full_stream_buffer, full_msg, partial_msg, message_id
                try:
                    if isinstance(message, ChatMessage):
                        # Final message (complete response)
                        full_msg = message.content
                        if hasattr(message, "id") and message.id:
                            message_id = message.id
                            print(f"✅ Captured final ChatMessage ID: {message_id}")
                            
                    if isinstance(message, PartialChatMessage) and message.content:
                        print(f"message is :{message}")
                        new_text = message.content
                        full_stream_buffer.append(new_text)
                        response_queue.put(new_text)
                        print(f"Streaming callback received: {len(new_text)} chars")

                except Exception as e:
                    self.log_debug(f"Streaming callback error: {e}")
                    response_queue.put(f"Callback error: {str(e)}")

            def query_thread():
                try:
                    print("Query thread starting...")
                    with self.client.connect(self.chat_session_id) as session:
                        result = session.query(**query_args, callback=streaming_callback)
                        print(f"Query result: {result}")
                    print("Query thread completed successfully")
                except Exception as e:
                    error_msg = f"Streaming error: {str(e)}"
                    print(f"Query thread error: {error_msg}")
                    response_queue.put(error_msg)
                finally:
                    completed.set()

            # Start streaming thread
            thread = threading.Thread(target=query_thread)
            thread.daemon = True
            thread.start()
            print("Streaming thread started")

            # PHASE 1: PRIORITY STREAMING - Stream content immediately to user
            print("PHASE 1: Starting priority content streaming")
            
            # Use the resolved use_agent value instead of self.valves.USE_AGENT
            if use_agent:
                yield "<details open>\n"
                yield "    <summary>🧠 Live Agentic Flow (Processing...)</summary>\n"
                yield "\n"
                yield "```\n"
            
            # Stream content with safe escaping - prioritize user experience
            chunk_count = 0
            yielded_content = set()
            
            while not completed.is_set() or not response_queue.empty():
                try:
                    chunk = response_queue.get(timeout=1.0)
                    chunk_count += 1
                    
                    # Safe escaping that preserves formatting
                    safe_chunk = chunk.replace("```", "`​`​`")  # Zero-width space
                    
                    if use_agent:
                        yield safe_chunk
                    else:
                        if safe_chunk not in yielded_content:
                            yielded_content.add(safe_chunk)
                            yield safe_chunk
                            
                except queue.Empty:
                    continue
                except Exception as e:
                    self.log_debug(f"Live streaming error: {e}")
                    break

            # Close the streaming section and show final answer
            if use_agent:
                yield "\n```\n"
                yield "    <summary>Final Response</summary>\n"
                yield "</details>\n"
                yield "\n---\n"

            # Wait for thread completion
            print("Waiting for thread completion...")
            thread.join(timeout=10)

            # Extract and display final answer (only in agent mode)
            full_response_text = "".join(full_stream_buffer)
            print(f"Full response length: {len(full_response_text)} chars")
            
            if use_agent:
                final_answer = self._extract_final_answer_robust(full_response_text)
                print(f"Final answer extracted: {bool(final_answer)}")
                print(f"Final answer extracted: {final_answer}")
                
                if final_answer and final_answer.strip():
                    yield "\n✨ Final Answer:\n\n"
                    yield final_answer
                    yield "\n\n"

            print("PHASE 1 COMPLETE: Content streaming finished")

            # PHASE 2: PROGRESSIVE REFERENCE HANDLING
            print("PHASE 2: Starting progressive reference processing")
            
            if not (message_id and self.current_openwebui_chat_id):
                print("No message ID or chat ID available for reference processing")
                return

            # Start reference processing indicator
            yield "\n---\n\n"
            yield "📚 Processing Source References...\n\n"

            try:
                # Download reference highlighting files
                temp_dir = tempfile.mkdtemp(prefix=f"h2ogpte_refs_{self.current_openwebui_chat_id}_")
                print(f"Created temp directory: {temp_dir}")
                
                try:
                    # Download all reference files first
                    print("Downloading reference highlighting files...")
                    highlighted_files = self.client.download_reference_highlighting(
                        message_id=message_id,
                        destination_directory=temp_dir,
                        output_type="combined",
                        limit=None
                    )
                    
                    if not highlighted_files:
                        yield "No source references available for this response.\n\n"
                        return

                    print(f"Downloaded {len(highlighted_files)} highlighted files")
                    yield f"Found {len(highlighted_files)} source reference(s) - uploading...\n\n"

                    # PHASE 3: PARALLEL UPLOAD WITH PROGRESSIVE RESULTS
                    print("PHASE 3: Starting parallel uploads with progressive results")
                    
                    def upload_single_file(file_path: str) -> Dict[str, Any]:
                        """Upload a single file and return result info"""
                        file_name = os.path.basename(file_path)
                        try:
                            print(f"Uploading {file_name}...")
                            upload_result = self.upload_file_to_openwebui(str(file_path))
                            
                            if upload_result:
                                file_id = upload_result.get('id')
                                return {
                                    "success": True,
                                    "id": file_id,
                                    "name": file_name,
                                    "upload_url": f"{self.valves.OPENWEBUI_BASE_URL}/api/v1/files/{file_id}/content",
                                    "view_url": f"{self.valves.OPENWEBUI_BASE_URL}/api/v1/files/{file_id}/content",
                                    "type": "pdf",
                                    "source": "h2ogpte_reference"
                                }
                            else:
                                return {
                                    "success": False,
                                    "name": file_name,
                                    "path": str(file_path),
                                    "error": "Failed to upload to OpenWebUI"
                                }
                                
                        except Exception as e:
                            print(f"Upload error for {file_name}: {str(e)}")
                            return {
                                "success": False,
                                "name": file_name,
                                "error": str(e)
                            }

                    # Use ThreadPoolExecutor for parallel uploads
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        # Submit all upload tasks
                        future_to_file = {
                            executor.submit(upload_single_file, file_path): file_path 
                            for file_path in highlighted_files
                        }
                        
                        reference_count = 0
                        
                        # Process completed uploads as they finish
                        for future in concurrent.futures.as_completed(future_to_file):
                            file_path = future_to_file[future]
                            
                            try:
                                result = future.result()
                                reference_count += 1
                                
                                if result["success"]:
                                    # Yield successful upload without bold formatting
                                    yield f"{reference_count}. 📄 [{result['name']}]({result['view_url']}) (ID: {result['id']})\n"
                                    print(f"Successfully uploaded and yielded: {result['name']}")
                                else:
                                    # Yield failed upload info without bold formatting
                                    yield f"{reference_count}. 📄 {result['name']} (Upload failed: {result.get('error', 'Unknown error')})\n"
                                    print(f"Failed upload yielded: {result['name']}")
                                    
                            except Exception as e:
                                reference_count += 1
                                file_name = os.path.basename(file_path)
                                yield f"{reference_count}. 📄 {file_name} (Processing error: {str(e)})\n"
                                print(f"Exception during upload processing: {str(e)}")

                    print("PHASE 3 COMPLETE: All reference uploads processed")
                    
                finally:
                    # Clean up temporary directory
                    try:
                        shutil.rmtree(temp_dir)
                        self.log_debug(f"Cleaned up temporary directory: {temp_dir}")
                    except Exception as cleanup_error:
                        self.log_debug(f"Failed to clean up temp directory: {cleanup_error}")

            except Exception as e:
                error_msg = f"Reference processing error: {str(e)}"
                print(f"PHASE 2/3 ERROR: {error_msg}")
                yield f"\nError processing references: {error_msg}\n"
            
            # PHASE 3: AGENT-GENERATED FILES (NEW)
            if use_agent:
                print("PHASE 3: Starting agent files processing")
                yield "\n---\n\n"
                yield "🤖 Processing Agent-Generated Files...\n\n"

                try:
                    agent_files = self._download_and_upload_agent_files(
                        message_id=message_id,
                        chat_id=self.current_openwebui_chat_id
                    )
                    
                    if not agent_files:
                        yield "No agent-generated files available.\n\n"
                    else:
                        yield f"Found {len(agent_files)} agent-generated file(s):\n\n"
                        
                        for idx, file_info in enumerate(agent_files, 1):
                            if file_info.get("error"):
                                yield f"{idx}. ⚠️ {file_info['name']} (Error: {file_info['error']})\n"
                            else:
                                file_type_emoji = {
                                    'image': '🖼️',
                                    'pdf': '📄',
                                    'text': '📝',
                                    'json': '📊',
                                    'csv': '📈',
                                    'file': '📎'
                                }
                                emoji = file_type_emoji.get(file_info.get('type', 'file'), '📎')
                                
                                yield f"{idx}. {emoji} [{file_info['name']}]({file_info['view_url']}) (ID: {file_info['id']})\n"
                        
                        yield "\n"
                    
                    print("PHASE 3 COMPLETE: Agent files processing finished")
                    
                except Exception as e:
                    error_msg = f"Agent files processing error: {str(e)}"
                    print(f"PHASE 3 ERROR: {error_msg}")
                    yield f"\nError processing agent files: {error_msg}\n"

            print("PHASE 2 & 3 COMPLETE: Reference processing finished")
        
        except Exception as e:
            error_msg = f"Enhanced streaming error: {str(e)}"
            print(f"_stream_response error: {error_msg}")
            yield error_msg

    def upload_and_ingest(self, file_path: str, collection_name: str = None, description: str = "") -> str:
        """Upload and ingest document to H2O GPT Enterprise using requests"""
        try:
            # Ensure client is initialized
            if not self.client:
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
                # Reset chat session to use new collection
                self.reset_chat_session(collection_id, "new collection created")
                print(f"✅ Collection created: {collection_name} ({collection_id})")

            # Step 2: Upload document using requests
            filename = os.path.basename(file_path)
            upload_id = self.upload_file_with_requests(file_path)
            print(f"📂 File uploaded: {filename} (upload_id={upload_id})")

            # Step 3: Ingest document using requests
            ingestion_id = self.ingest_upload_with_requests(upload_id, collection_id)
            print(f"⚙️ Ingestion started (id={ingestion_id})...")


        except Exception as e:
            error_msg = f"Upload and ingestion error: {str(e)}"
            print(error_msg)
            raise RuntimeError(error_msg)
        
    
    def has_new_files_to_upload(self, body: Dict[str, Any]) -> bool:
        """
        Analyze files in body and determine if there are new files to upload.
        Returns True if there are new files, False otherwise.
        """
        try:
            # Get files from body
            current_files = body.get("files", [])
            
            # If no files in body, nothing to upload
            if not current_files:
                print("📄 No files in request body")
                return False
            
            # Initialize processed_file_ids if not exists
            if not hasattr(self, 'processed_file_ids'):
                self.processed_file_ids = set()
                
            # Extract current file IDs from body
            current_file_ids = set()
            for file_info in current_files:
                file_id = file_info.get("id") or file_info.get("file", {}).get("id")
                if file_id:
                    current_file_ids.add(file_id)
            
            print(f"Current file IDs: {current_file_ids}")
            print(f"Previously processed IDs: {self.processed_file_ids}")
            
            # Check for new file IDs
            new_file_ids = current_file_ids - self.processed_file_ids
            
            if new_file_ids:
                print(f"🆕 New file IDs detected: {new_file_ids}")
                # Store the new file information in body for later use
                body["new_file_ids"] = list(new_file_ids)
                body["new_files"] = [
                    file_info for file_info in current_files 
                    if (file_info.get("id") or file_info.get("file", {}).get("id")) in new_file_ids
                ]
                return True
            else:
                print("📋 No new files detected - all files already processed")
                body["new_file_ids"] = []
                body["new_files"] = []
                return False
                
        except Exception as e:
            print(f"❌ Error checking for new files: {str(e)}")
            # On error, assume no new files to be safe
            return False

    def mark_files_as_processed(self, file_ids: List[str]) -> None:
        """
        Mark given file IDs as processed to avoid re-uploading.
        """
        if not hasattr(self, 'processed_file_ids'):
            self.processed_file_ids = set()
        
        for file_id in file_ids:
            self.processed_file_ids.add(file_id)
        
        print(f"✅ Marked files as processed: {file_ids}")
        print(f"Total processed files: {len(self.processed_file_ids)}")

    def reset_processed_files(self) -> None:
        """
        Reset the processed files tracking (useful when chat session changes).
        """
        if hasattr(self, 'processed_file_ids'):
            print(f"🧹 Clearing {len(self.processed_file_ids)} processed file IDs")
            self.processed_file_ids.clear()
        else:
            self.processed_file_ids = set()
        print("✨ Processed files tracking reset")

    def get_file_details_for_upload(self, body: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get detailed information about new files that need to be uploaded.
        Returns list of file details with paths and metadata.
        """
        SHARED_UPLOAD_DIR = "/app/uploads"
        
        if not self.has_new_files_to_upload(body):
            return []
        
        upload_files = []
        
        for file_info in body.get("new_files", []):
            try:
                file_data = file_info.get("file", file_info)
                file_id = file_info.get("id") or file_data.get("id")
                filename = file_data.get("filename")
                local_path = file_data.get("path")
                
                if not all([file_id, filename, local_path]):
                    print(f"⚠️ Incomplete file info: {file_info}")
                    continue
                
                # Convert to shared path
                shared_path = local_path.replace(
                    "/app/backend/data/uploads",
                    SHARED_UPLOAD_DIR
                )
                
                # Verify file exists
                if not os.path.exists(shared_path):
                    print(f"❌ File not found: {shared_path}")
                    continue
                
                upload_files.append({
                    "file_id": file_id,
                    "filename": filename,
                    "local_path": local_path,
                    "shared_path": shared_path,
                    "size": file_data.get("size", 0),
                    "content_type": file_data.get("meta", {}).get("content_type", "application/octet-stream")
                })
                
                print(f"📁 Prepared for upload: {filename} ({file_id})")
                
            except Exception as e:
                print(f"❌ Error processing file info: {str(e)}")
                continue
        
        return upload_files

    def is_meaningful_chat_change(self, previous_chat_id: Optional[str], current_chat_id: Optional[str]) -> bool:
        """
        Determine if a chat ID change is meaningful and should trigger session reset.
        Ignores temporary None values from follow-up generation or internal processes.
        """
        # If both are None, no change
        if previous_chat_id is None and current_chat_id is None:
            return False
        
        # If previous was None and current has a value, it's a new session start
        if previous_chat_id is None and current_chat_id is not None:
            return True
        
        # If current is None but previous had a value, it's likely temporary (follow-ups)
        # Don't treat this as a meaningful change
        if previous_chat_id is not None and current_chat_id is None:
            print("🔍 Detected temporary None chat ID (likely follow-up generation), ignoring...")
            return False
        
        # If both have values and they're different, it's a real chat change
        if previous_chat_id != current_chat_id:
            return True
        
        # No meaningful change
        return False

    async def inlet(self, body: Dict[str, Any], user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process incoming requests - handle file uploads and chat ID management"""
        print("=== Inlet triggered ===")

        # Handle chat ID comparison and tracking
        current_openwebui_chat_id = None
        if "metadata" in body and "chat_id" in body["metadata"]:
            current_openwebui_chat_id = body["metadata"]["chat_id"]
        
        # Store previous chat ID in body for comparison in pipe()
        body["previous_openwebui_chat_id"] = self.current_openwebui_chat_id
        body["current_openwebui_chat_id"] = current_openwebui_chat_id
        
        print(f"Previous chat ID: {body['previous_openwebui_chat_id']}")
        print(f"Current chat ID: {body['current_openwebui_chat_id']}")
        
        # Use improved chat change detection
        meaningful_chat_change = self.is_meaningful_chat_change(
            self.current_openwebui_chat_id, 
            current_openwebui_chat_id
        )
        
        if meaningful_chat_change:
            print("🔄 Meaningful OpenWebUI chat ID change detected, will reset H2OGPTE session in pipe()")
            body["chat_id_changed"] = True
            # Only reset processed files tracking on meaningful chat changes
            self.reset_processed_files()
            print("🗂️ Reset file tracking due to meaningful chat change")
        else:
            body["chat_id_changed"] = False
            if current_openwebui_chat_id is None:
                print("📝 Temporary chat ID change (follow-up generation), maintaining session state")

        # Check for new files to upload using the new function
        has_new_files = self.has_new_files_to_upload(body)
        body["has_new_files"] = has_new_files
        
        if has_new_files:
            print("🆕 New files detected for upload/ingestion")
            
            # Get detailed file information for upload
            upload_files = self.get_file_details_for_upload(body)
            body["upload_files"] = upload_files
            
            if upload_files:
                print(f"📤 Processing {len(upload_files)} new files...")
                
                # Process each new file
                for file_details in upload_files:
                    file_id = file_details["file_id"]
                    filename = file_details["filename"]
                    shared_path = file_details["shared_path"]
                    
                    try:
                        print(f"Processing file: {filename} (ID: {file_id})")
                        
                        # Determine collection strategy
                        if not self.valves.COLLECTION_ID and self.valves.AUTO_CREATE_COLLECTION:
                            print("📤 No collection ID set, will create new collection...")
                            collection_id = self.upload_and_ingest(
                                file_path=shared_path,
                                collection_name=f"{self.valves.DEFAULT_COLLECTION_NAME}_{int(time.time())}",
                                description=f"Auto-created collection for {filename}"
                            )
                            body["collection_id"] = collection_id
                            print(f"🎉 Document successfully ingested to new collection: {collection_id}")
                            
                        elif self.valves.COLLECTION_ID:
                            print(f"📤 Ingesting document to existing collection: {self.valves.COLLECTION_ID}")
                            collection_id = self.upload_and_ingest(
                                file_path=shared_path,
                                description=f"Document: {filename}"
                            )
                            body["collection_id"] = collection_id
                            print(f"🎉 Document successfully ingested to collection: {collection_id}")
                            
                        else:
                            print("⚠️ No collection ID set and auto-creation disabled.")
                            body["ingestion_status"] = "skipped"
                            body["message"] = "Document uploaded but not ingested. Please set COLLECTION_ID or enable AUTO_CREATE_COLLECTION."
                            continue
                        
                        # Mark this file as processed
                        self.mark_files_as_processed([file_id])
                        body["ingestion_status"] = "success"
                        
                    except Exception as e:
                        error_msg = f"Failed to ingest document {filename}: {str(e)}"
                        print(f"❌ {error_msg}")
                        body["ingestion_status"] = "failed"
                        body["ingestion_error"] = error_msg
                        # Don't mark as processed if it failed
                        
            else:
                print("❌ No valid files found for upload")
                body["ingestion_status"] = "no_valid_files"
                
        else:
            print("📄 No new files detected - treating as query/message request")
            body["ingestion_status"] = "no_new_files"

        return body

    def pipe(
        self,
        user_message: str,
        model_id: str,
        messages: List[Dict[str, Any]],
        body: Dict[str, Any],
        files: Optional[List[str]] = None,
    ) -> Union[str, Generator[str, None, None]]:
        """Main pipeline processing"""
        try:
            is_streaming = body.get("stream", False)
            
            # Extract chat ID information from body (processed in inlet)
            current_openwebui_chat_id = body.get("current_openwebui_chat_id")
            previous_openwebui_chat_id = body.get("previous_openwebui_chat_id")
            chat_id_changed = body.get("chat_id_changed", False)
            
            print(f"Processing request - Meaningful chat ID change: {chat_id_changed}")
            
            # Ensure client is initialized
            if not self.client:
                self.init_client()
            
            # Handle chat session management
            if not self.chat_session_id:
                # First time - create new session
                self.init_chat_session()
                # Only update current chat ID if it's not None (avoid storing temporary states)
                if current_openwebui_chat_id is not None:
                    self.current_openwebui_chat_id = current_openwebui_chat_id
                print("🆕 Created new H2OGPTE chat session")
            elif chat_id_changed:
                # Meaningful OpenWebUI chat change - reset H2OGPTE session
                print("🔄 Resetting H2OGPTE session due to meaningful OpenWebUI chat change")
                self.reset_chat_session(self.current_collection_id, "meaningful OpenWebUI chat change")
                # Only update current chat ID if it's not None
                if current_openwebui_chat_id is not None:
                    self.current_openwebui_chat_id = current_openwebui_chat_id
            else:
                # No meaningful change - keep existing session
                # Only update chat ID if current is not None (preserve existing for temporary None states)
                if current_openwebui_chat_id is not None and current_openwebui_chat_id != self.current_openwebui_chat_id:
                    print("🔄 Updating stored chat ID without session reset")
                    self.current_openwebui_chat_id = current_openwebui_chat_id
            
            # Handle collection changes from document ingestion
            ingestion_status = body.get("ingestion_status")
            if ingestion_status == "success":
                collection_id = body.get("collection_id")
                if collection_id and collection_id != self.current_collection_id:
                    print("🔄 Resetting H2OGPTE session due to new document collection")
                    self.reset_chat_session(collection_id, "new document ingested")
                    # Update valves for future queries
                    self.valves.COLLECTION_ID = collection_id
            
            self.log_debug(f"Using H2OGPTE session: {self.chat_session_id} (OpenWebUI: {self.current_openwebui_chat_id}, collection: {self.current_collection_id})")
            
            # Prepare response prefix based on ingestion status
            prefix = ""
            if ingestion_status == "success":
                prefix = "✅ Document successfully ingested and ready for queries!\n\n"
            elif ingestion_status == "already_uploaded":
                prefix = f"📋 {body.get('message', 'Document already available for queries')}\n\n"
            elif ingestion_status == "failed":
                prefix = f"⚠️ Document ingestion failed: {body.get('ingestion_error', 'Unknown error')}\nProceeding with query using existing collection...\n\n"
            elif ingestion_status == "skipped":
                prefix = f"⚠️ {body.get('message', 'Document not ingested')}\n\n"
            
            if is_streaming:
                return self._stream_with_prefix(prefix, user_message, body)
            else:
                response = self._query_h2ogpte(user_message, body, is_streaming)
                return prefix + response if isinstance(response, str) else response
                
        except Exception as e:
            error_msg = f"Pipeline Error: {str(e)}"
            self.log_debug(error_msg)
            return error_msg

    def _stream_with_prefix(self, prefix: str, user_message: str, body: Dict[str, Any]) -> Generator[str, None, None]:
        """Stream response with prefix message"""
        if prefix:
            yield prefix
        
        for chunk in self._query_h2ogpte(user_message, body, True):
            yield chunk

    def _query_h2ogpte(self, user_message: str, body: Dict[str, Any], is_streaming: bool) -> Union[str, Generator[str, None, None]]:
        """Unified query method for both streaming and non-streaming using persistent chat session"""
        print(f"inside query_h2ogpte - streaming: {is_streaming}")
        
        # Build query arguments using the precedence hierarchy (chat-level > pipeline-level > defaults)
        query_args = self._build_query_args(user_message, body)      
        if is_streaming:
            print("Calling _stream_response")
            return self._stream_response(query_args)
        else:
            print("Calling _get_response")
            return self._get_response(query_args)
     
    def _get_response(self, query_args: dict) -> str:
        """Get non-streaming response using persistent chat session"""
        print("Getting non-streaming response")
        try:
            with self.client.connect(self.chat_session_id) as session:
                reply = session.query(**query_args)
            result = reply.content or "No response received"
            print(f"Non-streaming response: {len(result)} chars")
            return result
        except Exception as e:
            error_msg = f"Response error: {str(e)}"
            print(f"Non-streaming error: {error_msg}")
            return error_msg