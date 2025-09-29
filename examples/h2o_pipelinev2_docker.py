##This pipeline will connect user to a H2OGPTE Collection
import os
import subprocess
import sys
import threading
import queue
from typing import List, Optional, Union, Generator, Dict, Any
from pydantic import BaseModel

# Auto-install required packages
def install_package(package):
    """Install a package using pip"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"Successfully installed {package}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install {package}: {e}")
        return False

# Install h2ogpte if not available
H2OGPTE = None
PartialChatMessage = None
ChatMessage = None

try:
    from h2ogpte import H2OGPTE
    from h2ogpte.types import PartialChatMessage, ChatMessage
    print("h2ogpte package imported successfully")
except ImportError:
    print("h2ogpte package not found. Installing...")
    if install_package("h2ogpte"):
        print("h2ogpte installed successfully. Please restart the pipeline container to complete the setup.")
        print("Run: docker restart pipelines")
        # Try importing again after installation
        try:
            import importlib
            import h2ogpte
            importlib.reload(h2ogpte)
            from h2ogpte import H2OGPTE
            from h2ogpte.types import PartialChatMessage, ChatMessage
            print("h2ogpte package successfully imported after installation")
        except ImportError:
            print("h2ogpte installation completed but requires container restart to function properly")
            print("Please restart your pipeline container: docker restart pipelines")
    else:
        print("Failed to install h2ogpte package")


class Pipeline:
    """Streamlined H2OGPTE Pipeline with optional collection connection"""
    
    class Valves(BaseModel):
        """Configuration parameters"""
        H2OGPTE_API_KEY: str = ""
        H2OGPTE_URL: str = ""
        COLLECTION_ID: Optional[str] = None  # Default to None so collection is not required
        DEBUG_MODE: bool = False
        STREAM_TIMEOUT: int = 60

    def __init__(self):
        self.type = "manifold"
        self.id = "h2ogpte_single"
        self.name = ""
        
        self.valves = self.Valves(
            **{
                "H2OGPTE_API_KEY": os.getenv("H2OGPTE_API_KEY", ""),
                "H2OGPTE_URL": os.getenv("H2OGPTE_URL", "https://h2ogpte.genai.h2o.ai"),
                "COLLECTION_ID": os.getenv("COLLECTION_ID", None),  # Default to None
                "DEBUG_MODE": os.getenv("DEBUG_MODE", "false").lower() == "true",
                "STREAM_TIMEOUT": int(os.getenv("STREAM_TIMEOUT", "60")),
            }
        )
        self.client: Optional[H2OGPTE] = None

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

    def pipelines(self) -> List[Dict[str, str]]:
        """Return available pipeline models - called during startup"""
        try:
            return [{"id": "h2ogpte", "name": "H2OGPTe"}]
        except Exception as e:
            print(f"Error in pipelines method: {e}")
            return [{"id": "h2ogpte", "name": "H2OGPTe"}]

    def init_client(self) -> None:
        if H2OGPTE is None:
            raise ValueError("h2ogpte package not available - please restart the pipeline container")
        
        if not self.valves.H2OGPTE_API_KEY:
            raise ValueError("H2OGPTE_API_KEY is required but not set")
            
        if not self.valves.H2OGPTE_URL:
            raise ValueError("H2OGPTE_URL is required but not set")
        
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
            
            # Validate collection ID
            collection_id = self._validate_collection_id(self.valves.COLLECTION_ID)
            self.log_debug(f"Using collection: {collection_id}")
            
            # Create chat session
            chat_session_id = self.client.create_chat_session(collection_id=collection_id)
            
            # Determine RAG type
            rag_type = "rag" if collection_id else "llm_only"
            
            return self._query_h2ogpte(user_message, chat_session_id, rag_type, is_streaming)
                
        except Exception as e:
            error_msg = f"Pipeline Error: {str(e)}"
            self.log_debug(error_msg)
            return error_msg

    def _query_h2ogpte(self, user_message: str, chat_session_id: str, rag_type: str, is_streaming: bool) -> Union[str, Generator[str, None, None]]:
        print(f"_query_h2ogpte:user_message={user_message}, chat_session_id={chat_session_id}, rag_type={rag_type}, is_streaming={is_streaming}")
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

                    # elif isinstance(message, ChatMessage) and message.content:
                    #     final_text = message.content
                    #     if final_text.startswith(last_content):
                    #         final_delta = final_text[len(last_content):]
                    #     else:
                    #         final_delta = final_text
                    #     if final_delta:
                    #         response_queue.put(final_delta)
                    #     last_content = final_text
                except Exception as e:
                    self.log_debug(f"Callback error: {e}")


            # def streaming_callback(message):
            #     nonlocal last_content
            #     try:
            #         if isinstance(message, PartialChatMessage) and message.content:
            #             # Yield only the delta, not full repetition
            #             delta = message.content[len(last_content):]
            #             if delta:
            #                 response_queue.put(delta)
            #                 last_content = message.content

            #         elif isinstance(message, ChatMessage) and message.content:
            #             # Final message – ensure we don't repeat all previous text
            #             final_delta = message.content[len(last_content):]
            #             if final_delta:
            #                 response_queue.put(final_delta)
            #             last_content = message.content
            #     except Exception as e:
            #         self.log_debug(f"Callback error: {e}")

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