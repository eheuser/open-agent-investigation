"""
Mock LLM service for testing.

Provides a simple HTTP server that mimics OpenAI's chat completion API
with deterministic responses for testing purposes.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn

app = FastAPI(title="Mock LLM Service")


class Message(BaseModel):
    """Chat message."""

    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """Chat completion request."""

    model: str
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000
    stream: Optional[bool] = False


class ChatCompletionResponse(BaseModel):
    """Chat completion response."""

    id: str
    object: str = "chat.completion"
    created: int = 1234567890
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]


# Predefined responses for different query patterns
MOCK_RESPONSES = {
    # Intent classification responses
    "timeline": {
        "intent": "timeline_query",
        "confidence": 0.95,
        "reasoning": "User wants to view or manage timeline entries",
    },
    "find": {
        "intent": "execute_agent_policy",
        "confidence": 0.9,
        "reasoning": "Requires event search and analysis",
    },
    "what is": {
        "intent": "general_chat",
        "confidence": 0.85,
        "reasoning": "Metadata question about investigation",
    },
    "evidence": {
        "intent": "augmented_chat",
        "confidence": 0.88,
        "reasoning": "Semantic search query",
    },
    # Query expansion responses
    "credential access": [
        "lsass.exe",
        "mimikatz",
        "SAM database",
        "NTLM hash",
        "kerberos",
        "logonpasswords",
    ],
    "lateral movement": [
        "psexec",
        "remote desktop",
        "wmi",
        "scheduled task",
        "service installation",
    ],
    "privilege escalation": [
        "UAC bypass",
        "token manipulation",
        "DLL hijacking",
        "scheduled task",
        "service creation",
    ],
}


def get_mock_response(messages: List[Message]) -> str:
    """
    Generate a deterministic mock response based on a list of chat messages.

    Args:
        messages: A list of :class:`Message` objects representing the conversation history. The function scans the list in reverse order and extracts the most recent message whose `role` is `"user"`, converting its content to lowercase for processing.

    Returns:
        A string containing the mock response:

        * If the user message contains the words `"classify"` or `"intent"`, the function looks for a matching keyword in :data:`MOCK_RESPONSES`. When a match is found and the associated value is a dictionary, that dictionary is serialized to JSON and returned.

        * If the user message contains the words `"expand"` or `"terms"`, the function searches for a matching keyword whose value is a list. It then returns a JSON-encoded object with an `"expanded_terms"` key mapping to that list.

        * If no specific pattern matches, a generic placeholder string is returned: `"This is a mock LLM response for testing purposes."`.

    Raises:
        None. The function always returns a string, falling back to the default message when necessary.
    """
    # Get last user message
    user_msg = next((m.content.lower() for m in reversed(messages) if m.role == "user"), "")

    # Check for intent classification
    if "classify" in user_msg or "intent" in user_msg:
        for keyword, response in MOCK_RESPONSES.items():
            if keyword in user_msg:
                if isinstance(response, dict):
                    import json

                    return json.dumps(response)

    # Check for query expansion
    if "expand" in user_msg or "terms" in user_msg:
        for keyword, terms in MOCK_RESPONSES.items():
            if keyword in user_msg and isinstance(terms, list):
                import json

                return json.dumps({"expanded_terms": terms})

    # Default response
    return "This is a mock LLM response for testing purposes."


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completion(request: ChatCompletionRequest):
    """
    \"""Mock chat completion endpoint.

    This coroutine emulates OpenAI's Chat Completion API for testing purposes.
    It accepts a :class:`ChatCompletionRequest` containing the model name,
    messages, and streaming flag, and returns a deterministic
    :class:`ChatCompletionResponse`.

    Parameters
    ----------
    request: ChatCompletionRequest
        The incoming request object.  `request.messages` should be an iterable
        of message objects each exposing a `content` attribute.  If
        `request.stream` is true a :class:`fastapi.HTTPException` with status
        code 400 is raised because streaming is not supported by the mock.

    Returns
    -------
    ChatCompletionResponse
        A response object mirroring the structure of OpenAI's API, including:

        * `id` - a deterministic identifier derived from the hash of the
          generated content.
        * `model` - echoed from the request.
        * `choices` - a list containing a single choice with the assistant's
          message and a `finish_reason` of `"stop"`.
        * `usage` - token usage statistics calculated as an approximate
          word-count division by four for both prompt and completion tokens.

    Raises
    ------
    fastapi.HTTPException
        If `request.stream` is true, indicating that streaming responses are
        requested, which the mock service does not implement.\"""
    """
    if request.stream:
        raise HTTPException(status_code=400, detail="Streaming not supported in mock service")

    # Generate mock response
    response_content = get_mock_response(request.messages)

    return ChatCompletionResponse(
        id=f"mock-{hash(response_content) % 10000}",
        model=request.model,
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": response_content},
                "finish_reason": "stop",
            }
        ],
        usage={
            "prompt_tokens": sum(len(m.content) for m in request.messages) // 4,
            "completion_tokens": len(response_content) // 4,
            "total_tokens": (sum(len(m.content) for m in request.messages) + len(response_content))
            // 4,
        },
    )


@app.get("/health")
async def health():
    """
    Health check endpoint that reports service status.

    Returns:
        dict: A dictionary containing the health status and service name, e.g., {"status": "healthy", "service": "mock-llm"}.
    """
    return {"status": "healthy", "service": "mock-llm"}


@app.get("/")
async def root():
    """
    Root endpoint that returns basic service metadata, including the service name, version, and a dictionary of available API endpoints.
    """
    return {
        "service": "Mock LLM Service",
        "version": "1.0.0",
        "endpoints": {"chat_completion": "/v1/chat/completions", "health": "/health"},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
