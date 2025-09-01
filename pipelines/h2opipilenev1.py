##This pipeline can send a request to the H2OGPTE
from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import os
from h2ogpte import H2OGPTE
from h2ogpte.types import PartialChatMessage , ChatMessage



class Pipeline:
      # Ensure the H2OGPTE class is loaded
    class Valves(BaseModel):
        H2OGPTE_API_KEY: str = ""
        H2OGPTE_URL: str = "https://h2ogpte.internal.dedicated.h2o.ai"

    def __init__(self):
        self.name = "H2OGPTE Pipeline"
        self.valves = self.Valves(
            **{
                "H2OGPTE_API_KEY": os.getenv("H2OGPTE_API_KEY", ""),
                "H2OGPTE_URL": os.getenv(
                    "H2OGPTE_URL", "https://h2ogpte.internal.dedicated.h2o.ai"
                ),
            }
        )
        self.client = None  # Client will be lazily initialized

    async def on_startup(self):
        from llama_index.core import Settings, VectorStoreIndex, SimpleDirectoryReader
        global documents, index
        print(f"on_startup:{__name__}")
        self.documents = SimpleDirectoryReader("/app/backend/data").load_data()
        print(f"Loaded {len(self.documents)} documents.")
        if not self.valves.H2OGPTE_API_KEY:
            print("⚠️ WARNING: H2OGPTE_API_KEY not set in OpenWebUI.")
        pass

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        pass

    def init_client(self):
        """Lazy initialization of H2OGPTE client."""
        if not self.valves.H2OGPTE_API_KEY or not self.valves.H2OGPTE_URL:
            raise ValueError(
                "H2OGPTE_API_KEY or H2OGPTE_URL not set in OpenWebUI. Cannot create client."
            )
        if self.client is None:
            self.client = H2OGPTE(
                address=self.valves.H2OGPTE_URL,
                api_key=self.valves.H2OGPTE_API_KEY,
            )

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        """
        Main pipeline function to handle chat with H2OGPTE.
        """
        print(f"pipe:{__name__}")
        print(f"User message: {user_message}")
        print(f"Messages: {messages}")

        try:
            # Lazy-load client
            self.init_client()

            # Create chat session
            chat_session_id = self.client.create_chat_session(collection_id=None)

            # Optional prompt template
            self.client.set_chat_session_prompt_template(
                chat_session_id=chat_session_id,
                prompt_template_id=None,
            )

            # Start interactive session
            with self.client.connect(chat_session_id) as session:
                answer = session.query(
                    message=user_message,
                    llm="auto",
                    llm_args={
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
                        "client_metadata": "h2ogpte-openwebui-pipeline",
                    },
                    self_reflection_config=None,
                    rag_config={"rag_type": "llm_only"},
                    include_chat_history="auto",
                )

                if body.get("stream"):
                    # Yield content for streaming                    
                    yield answer.content
                else:
                    return {"content": answer.content}

        except Exception as e:
            return f"Error communicating with H2OGPTE: {e}"
