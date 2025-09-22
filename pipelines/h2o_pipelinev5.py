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
        STREAM_TIMEOUT: int = 60
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
        
    def log_debug(self, message: str) -> None:
        if self.valves.DEBUG_MODE:
            print(f"[H2OGPTE] {message}")

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
        """Enhanced final answer extraction with multiple strategies"""
        
        # Strategy 1: Look for structured content with stream turn titles
        pattern = re.compile(r"<stream_turn_title>(.*?)</stream_turn_title>(.*?)(?=<stream_turn_title>|ENDOFTURN|$)", re.DOTALL)
        matches = pattern.findall(full_text)
        
        if matches:
            # Find substantial content matches (avoiding metadata turns)
            substantial_matches = []
            for title, content in matches:
                cleaned_content = content.strip()
                # More specific filtering for actual content vs metadata
                if (len(cleaned_content) > 50 and  # Lowered threshold
                    not cleaned_content.startswith('**Completed LLM call') and
                    not cleaned_content.startswith('**Executing python') and
                    not cleaned_content.startswith('** [') and  # Added this filter
                    'No code blocks executed' not in cleaned_content and
                    'No executable code blocks found' not in cleaned_content):
                    substantial_matches.append((title.strip(), cleaned_content))
            
            self.log_debug(f"Found {len(substantial_matches)} substantial matches")
            for i, (title, content) in enumerate(substantial_matches):
                self.log_debug(f"Match {i}: Title='{title}', Content preview='{content[:100]}...'")
            
            # Use the LAST substantial match (most recent actual content)
            if substantial_matches:
                final_title, final_content = substantial_matches[-1]
                self.log_debug(f"Selected final answer from: '{final_title}'")
                return self._clean_extracted_content(final_content)
        
        # Strategy 2: Look for content blocks without stream structure
        content_blocks = self._extract_substantial_content_blocks(full_text)
        if content_blocks:
            return self._clean_extracted_content(content_blocks[-1])  # Use last block
        
        # Strategy 3: Enhanced fallback extraction
        fallback_content = self._extract_enhanced_fallback(full_text)
        if fallback_content:
            return self._clean_extracted_content(fallback_content)
        
        return None

    def _extract_substantial_content_blocks(self, full_text: str) -> List[str]:
        """Extract substantial content blocks from the full text"""
        lines = full_text.split('\n')
        content_blocks = []
        current_block = []
        
        for line in lines:
            stripped_line = line.strip()
            
            # Skip technical artifacts - expanded list
            if (stripped_line.startswith('**Completed LLM call') or 
                stripped_line.startswith('**Executing python') or
                stripped_line.startswith('** [') or  # Added this
                'ENDOFTURN' in stripped_line or
                '<stream_turn_title>' in stripped_line or
                'No executable code blocks found' in stripped_line or
                'No code blocks executed' in stripped_line):
                
                # Save current block if substantial
                if current_block:
                    block_text = '\n'.join(current_block).strip()
                    if len(block_text) > 50:  # Lowered threshold
                        content_blocks.append(block_text)
                current_block = []
                continue
            
            # Add meaningful content
            if stripped_line:
                current_block.append(line)
        
        # Add final block
        if current_block:
            block_text = '\n'.join(current_block).strip()
            if len(block_text) > 50:  # Lowered threshold
                content_blocks.append(block_text)
        
        return content_blocks

    def _clean_extracted_content(self, content: str) -> str:
        """Clean and format extracted content"""
        if not content:
            return ""
        
        # Remove technical artifacts - expanded patterns
        content = re.sub(r'\*\*Completed LLM call.*?\*\*', '', content, flags=re.DOTALL)
        content = re.sub(r'\*\*Executing python.*?\*\*', '', content, flags=re.DOTALL)
        content = re.sub(r'ENDOFTURN.*?$', '', content, flags=re.DOTALL | re.MULTILINE)
        content = re.sub(r'\*\* \[.*?\].*?\*\*\n?', '', content, flags=re.DOTALL)
        content = re.sub(r'No executable code blocks found.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r'No code blocks executed.*?$', '', content, flags=re.MULTILINE)
        
        # Remove any remaining ENDOFTURN markers
        content = re.sub(r'ENDOFTURN', '', content)
        
        # Clean up excessive whitespace while preserving structure
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
        content = content.strip()
        
        return content
    

    def _extract_enhanced_fallback(self, full_text: str) -> Optional[str]:
        """Enhanced fallback extraction for when patterns fail"""
        # Look for common final answer indicators
        indicators = [
            r"# Available Documents.*?(?=\n\n|\Z)",
            r"Based on.*?examination.*?(?=\n\n|\Z)",
            r"(?:Here's what I.*?found|Summary|Analysis).*?(?=\n\n|\Z)",
        ]
        
        for indicator_pattern in indicators:
            pattern = re.compile(indicator_pattern, re.DOTALL | re.IGNORECASE)
            match = pattern.search(full_text)
            if match and len(match.group(0).strip()) > 100:
                return match.group(0).strip()
        
        # Last resort: find the longest coherent paragraph
        paragraphs = [p.strip() for p in full_text.split('\n\n') if p.strip()]
        substantial_paragraphs = [p for p in paragraphs if len(p) > 150 and not p.startswith('**')]
        
        if substantial_paragraphs:
            return substantial_paragraphs[-1]
        
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
        """Enhanced streaming with improved display and final answer extraction"""
        print("Starting enhanced _stream_response with improved extraction")
        try:
            response_queue = queue.Queue()
            completed = threading.Event()
            full_stream_buffer = []
            full_msg ,partial_msg ,message_id = None, None, None
            def streaming_callback(message):
                nonlocal full_stream_buffer, full_msg, partial_msg , message_id
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
                        result=session.query(**query_args, callback=streaming_callback)
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

            # Phase 1: Enhanced collapsible details section
            if self.valves.USE_AGENT:
                yield "<details open>\n"
                yield "    <summary>🧠 Live Agentic Flow (Processing...)</summary>\n"
                yield "\n"
                yield "```\n"
            else:
                pass
            
            # Stream content with safe escaping
            chunk_count = 0
            while not completed.is_set() or not response_queue.empty():
                try:
                    chunk = response_queue.get(timeout=1.0)
                    chunk_count += 1
                    # Safe escaping that preserves formatting
                    safe_chunk = chunk.replace("```", "`​`​`")  # Zero-width space
                    if self.valves.USE_AGENT:
                        yield safe_chunk
                except queue.Empty:
                    continue
                except Exception as e:
                    self.log_debug(f"Live streaming error: {e}")
                    break

            # Close the streaming section
            if self.valves.USE_AGENT:
                yield "\n```\n"
                yield "    <summary>Final Response</summary>\n"
                yield "</details>\n"
                yield "\n---\n"
            else:
                pass

            # Wait for thread completion
            print("Waiting for thread completion...")
            thread.join(timeout=10)

            # After streaming finishes → download and upload reference highlighting to OpenWebUI
            reference_files = []
            print(f"Final message ID: {message_id}, current_openwebui_chat_id: {self.current_openwebui_chat_id}")
            print(f"message_id and self.current_openwebui_chat_id: {message_id and self.current_openwebui_chat_id}")
            if message_id and self.current_openwebui_chat_id:
                reference_files = self._download_and_upload_reference_highlighting(
                    message_id=message_id,
                    chat_id=self.current_openwebui_chat_id
                )
                print(f"Downloaded and uploaded {len(reference_files)} reference highlighting files")
            
            # Phase 2: Enhanced final answer extraction
            full_response_text = "".join(full_stream_buffer)
            print(f"Full response length: {len(full_response_text)} chars")
            
            final_answer = self._extract_final_answer_robust(full_response_text)
            print(f"Final answer extracted: {bool(final_answer)}")
            
            if final_answer and final_answer.strip():
                #yield "<details open>\n"
                yield "\n**✨ Final Answer:**\n\n"
                yield final_answer
                yield "\n\n"
                #yield "</details>\n"
            else:
                print("No final answer to display")
                #yield "\n**⚠️ Processing completed - see details above for full response.**\n\n"
            
            # Display reference files with proper OpenWebUI links
            if reference_files:
                yield "\n\n---\n\n"
                yield "**📚 Source References:**\n\n"
                
                for idx, ref_file in enumerate(reference_files, 1):
                    if ref_file.get('id'):  # Successfully uploaded to OpenWebUI
                        yield f"{idx}. [📄 {ref_file['name']}]({ref_file['view_url']}) *(via OpenWebUI)*\n"
                    elif ref_file.get('path'):  # Fallback to local path
                        yield f"{idx}. 📄 {ref_file['name']} *(local file: {ref_file.get('error', 'upload failed')})*\n"

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
            
            # Determine RAG type based on current collection
            rag_type = "rag" if self.current_collection_id else "llm_only"
            
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
                return self._stream_with_prefix(prefix, user_message, rag_type)
            else:
                response = self._query_h2ogpte(user_message, rag_type, is_streaming)
                return prefix + response if isinstance(response, str) else response
                
        except Exception as e:
            error_msg = f"Pipeline Error: {str(e)}"
            self.log_debug(error_msg)
            return error_msg

    def _stream_with_prefix(self, prefix: str, user_message: str, rag_type: str) -> Generator[str, None, None]:
        """Stream response with prefix message"""
        if prefix:
            yield prefix
        
        for chunk in self._query_h2ogpte(user_message, rag_type, True):
            yield chunk

    def _query_h2ogpte(self, user_message: str, rag_type: str, is_streaming: bool) -> Union[str, Generator[str, None, None]]:
        """Unified query method for both streaming and non-streaming using persistent chat session"""
        print(f"inside query_h2ogpte - streaming: {is_streaming}")
        
        query_args = {
            "message": user_message,   # dynamic user input
            "llm": "auto",
            "llm_args": {
                # Core LLM runtime configs
                "temperature": 0.2,
                "max_new_tokens": 32768,
                
                # Vision / multimodal configs
                "enable_vision": "auto",
                "visible_vision_models": ["auto"],
                
                # Agent configs (lightweight by default)
                "use_agent": self.valves.USE_AGENT,
                "agent_max_turns": 7, 
                "agent_accuracy": "basic", 
                "agent_timeout": 30,
                "agent_tools": [
                    "ask_question_about_documents.py",
                ],

                # Cost & runtime controls
                "cost_controls": {
                    "max_cost": 0.05,
                    "willingness_to_pay": 0.2,
                    "willingness_to_wait": 10,
                    "max_cost_per_million_tokens": 75,
                    "model": None,
                },

                # Metadata to identify pipeline
                "client_metadata": "h2ogpte-openwebui-single-pipeline-persistent",
            },

            # Self-reflection disabled (set None)
            "self_reflection_config": None,

            # Retrieval configuration (can switch rag_type dynamically)
            "rag_config": {
                "rag_type": rag_type,   # e.g., "agent_only" or "vector_search"
            },

            # Chat session continuity - this is key for persistent conversations
            "include_chat_history": "auto",

            # Timeout (from valves config)
            "timeout": self.valves.STREAM_TIMEOUT,
        }

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