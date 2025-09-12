"""
Simple H2OGPTE Summarization Pipeline
Gets the most recent message and sends it to H2OGPTE for summarization.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import os
import re
from h2ogpte import H2OGPTE
from fastapi import Request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Action:
    class Valves(BaseModel):
        """Configuration parameters for H2OGPTE connection."""

        H2OGPTE_API_KEY: str = Field(
            default_factory=lambda: os.getenv(
                "H2OGPTE_API_KEY", ""
            ),
            description="H2OGPTE API key for authentication",
        )
        H2OGPTE_URL: str = Field(
            default_factory=lambda: os.getenv(
                "H2OGPTE_URL", "https://h2ogpte.internal.dedicated.h2o.ai"
            ),
            description="H2OGPTE service URL",
        )
        max_cost: float = Field(0.02, description="Maximum cost per request")
        willingness_to_pay: float = Field(0.1, description="Maximum willing to pay")
        timeout_seconds: int = Field(60, description="Request timeout in seconds")

    class UserValves(BaseModel):
        show_status: bool = Field(
            default=True, description="Show status of the action."
        )

    def __init__(self):
        self.valves = self.Valves()
        self._client = None
        print(f"[INIT] H2OGPTE Summarizer initialized")

    @property
    def client(self) -> H2OGPTE:
        """Get or create H2OGPTE client with lazy initialization."""
        if self._client is None:
            print(f"[CLIENT] Creating new H2OGPTE client")
            if not self.valves.H2OGPTE_API_KEY:
                print(f"[ERROR] H2OGPTE_API_KEY not configured")
                raise ValueError("H2OGPTE_API_KEY not configured")

            self._client = H2OGPTE(
                address=self.valves.H2OGPTE_URL,
                api_key=self.valves.H2OGPTE_API_KEY,
            )
            print(f"[CLIENT] H2OGPTE client initialized for {self.valves.H2OGPTE_URL}")
        else:
            print(f"[CLIENT] Using existing H2OGPTE client")

        return self._client

    def extract_recent_message(self, body: dict) -> str:
        """Extract the most recent message from the conversation."""
        print(f"[EXTRACT] Starting message extraction")

        try:
            messages = body.get("messages", [])
            print(f"[EXTRACT] Found {len(messages)} messages in body")

            if not messages:
                print(f"[EXTRACT] No messages found in body")
                raise ValueError("No messages found in conversation")

            # Get the last assistant message (most recent response)
            last_message = messages[-1]
            print(f"[EXTRACT] Last message role: {last_message.get('role', 'unknown')}")
            print(
                f"[EXTRACT] Last message content length: {len(last_message.get('content', ''))}"
            )

            content = last_message.get("content", "")
            if not content or not content.strip():
                print(
                    f"[EXTRACT] Last message content is empty, checking previous messages"
                )

                # If last message is empty, try to find the last non-empty message
                for msg in reversed(messages):
                    if msg.get("content", "").strip():
                        content = msg.get("content", "")
                        print(
                            f"[EXTRACT] Found non-empty message with role: {msg.get('role', 'unknown')}"
                        )
                        break

            if not content.strip():
                print(f"[EXTRACT] No content found in any message")
                raise ValueError("No content found in messages")

            print(
                f"[EXTRACT] Successfully extracted content: {len(content)} characters"
            )
            print(f"[EXTRACT] Content preview: {content[:100]}...")

            return content.strip()

        except Exception as e:
            print(f"[EXTRACT] Error extracting message: {str(e)}")
            raise

    async def summarize_with_h2ogpte(self, content: str) -> str:
        """Send content to H2OGPTE for summarization."""
        print(f"[SUMMARIZE] Starting summarization process")
        print(f"[SUMMARIZE] Input content length: {len(content)} characters")

        try:
            # Create summarization prompt
            prompt = f"""
Please provide a clear, concise, and well-structured summary of the following text.

⚠️ Important instructions:
- Exclude any Python code, execution traces, or agent reasoning steps.
- Ignore mentions of tools, filenames, or process descriptions.
- Only focus on the actual content and meaning of the text.
- Summarize the key points, main ideas, and important takeaways in plain language.
- The response must read like a final answer, not a process log.

Content to summarize:
{content}
"""

            print(f"[SUMMARIZE] Created prompt with length: {len(prompt)} characters")

            # Create chat session
            print(f"[SUMMARIZE] Creating chat session...")
            chat_session_id = self.client.create_chat_session(collection_id=None)
            print(f"[SUMMARIZE] Created chat session: {chat_session_id}")

            # Generate summary with timeout
            print(f"[SUMMARIZE] Sending request to H2OGPTE...")
            with self.client.connect(chat_session_id) as session:
                summary_response = await asyncio.wait_for(
                    asyncio.to_thread(
                        session.query,
                        message=prompt,
                        llm="auto",
                        llm_args={
                            "cost_controls": {
                                "max_cost": self.valves.max_cost,
                                "willingness_to_pay": self.valves.willingness_to_pay,
                                "willingness_to_wait": 30,
                                "max_cost_per_million_tokens": 75,
                                "model": None,
                            },
                            "client_metadata": "h2ogpte-openwebui-simple-summarize",
                        },
                        rag_config={"rag_type": "llm_only"},
                    ),
                    timeout=self.valves.timeout_seconds,
                )

                print(f"[SUMMARIZE] Received response from H2OGPTE")
                print(
                    f"[SUMMARIZE] Summary length: {len(summary_response.content)} characters"
                )
                print(
                    f"[SUMMARIZE] Summary preview: {summary_response.content[:100]}..."
                )

                return summary_response.content

        except asyncio.TimeoutError:
            print(
                f"[SUMMARIZE] Request timed out after {self.valves.timeout_seconds} seconds"
            )
            raise Exception(
                f"Summarization timed out after {self.valves.timeout_seconds} seconds"
            )
        except Exception as e:
            print(f"[SUMMARIZE] Error during summarization: {str(e)}")
            raise Exception(f"Failed to generate summary: {str(e)}")

    async def action(
        self,
        body: dict,
        __request__: Request,
        __user__=None,
        __event_emitter__=None,
        __event_call__=None,
    ) -> Optional[dict]:
        """Main action method for summarization."""
        print(f"[ACTION] Starting action: {__name__}")
        print(f"[ACTION] User ID: {__user__.get('id') if __user__ else 'None'}")

        try:
            # Get user valves
            user_valves = __user__.get("valves") if __user__ else None
            if not user_valves:
                user_valves = self.UserValves()
                print(f"[ACTION] Using default user valves")
            else:
                print(f"[ACTION] Using user-specific valves")

            # Send initial status if enabled
            if __event_emitter__ and user_valves.show_status:
                print(f"[STATUS] Sending initial status...")
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": "Starting H2OGPTE summarization..."},
                    }
                )

            # Extract the recent message
            print(f"[ACTION] Extracting recent message...")
            message_content = self.extract_recent_message(body)

            # Send processing status
            if __event_emitter__ and user_valves.show_status:
                print(f"[STATUS] Sending processing status...")
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": "Processing message with H2OGPTE..."},
                    }
                )

            # Initialize client and generate summary
            print(f"[ACTION] Initializing H2OGPTE client...")
            _ = self.client  # Initialize client

            print(f"[ACTION] Generating summary...")
            summary = await self.summarize_with_h2ogpte(message_content)

            formatted_response = f"""        
           
            {summary} 
            ---
            *Summary generated using H2OGPTE*
            """

            # Send success notification
            print(f"formated response {formatted_response}")
            if __event_emitter__:
                word_count = len(summary.split())
                print(
                    f"[NOTIFICATION] Sending success notification (word count: {word_count})"
                )
                await __event_emitter__(
                    {
                        "type": "notification",
                        "data": {
                            "type": "success",
                            "content": f"✅ Summary generated successfully ({word_count} words)",
                        },
                    }
                )
                await __event_emitter__(
                    {"type": "message", "data": {"content": formatted_response}}
                )

            print(f"[ACTION] Successfully completed summarization")
            return {"content": formatted_response}

        except ValueError as ve:
            error_msg = f"❌ Input validation error: {str(ve)}"
            print(f"[ERROR] Validation error: {str(ve)}")
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "notification",
                        "data": {"type": "error", "content": error_msg},
                    }
                )
                # Also send error as message
                await __event_emitter__(
                    {
                        "type": "message",
                        "data": {"content": error_msg},
                    }
                )
            return {"content": error_msg, "type": "error"}

        except Exception as e:
            error_msg = f"❌ Summarization failed: {str(e)}"
            print(f"[ERROR] Action failed: {str(e)}")
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "notification",
                        "data": {"type": "error", "content": error_msg},
                    }
                )
                # Also send error as message
                await __event_emitter__(
                    {
                        "type": "message",
                        "data": {"content": error_msg},
                    }
                )
            return {"content": error_msg, "type": "error"}


# Action registration
actions = [
    {
        "id": "h2ogpte_simple_summarize",
        "name": "📄 Simple H2OGPTE Summarize",
        "description": "Generate AI-powered summary of the most recent message",
        "icon_url": "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0xNCAySDZhMiAyIDAgMCAwLTIgMnYxNmEyIDIgMCAwIDAgMiAyaDEyYTIgMiAwIDAgMCAyLTJWOHoiLz48cG9seWxpbmUgcG9pbnRzPSIxNCAyIDE0IDggMjAgOCIvPjxsaW5lIHgxPSIxNiIgeTE9IjEzIiB4Mj0iOCIgeTI9IjEzIi8+PGxpbmUgeDE9IjE2IiB5MT0iMTciIHgyPSI4IiB5Mj0iMTciLz48Y2lyY2xlIGN4PSIxMiIgY3k9IjEwIiByPSIyIi8+PC9zdmc+",
    }
]
