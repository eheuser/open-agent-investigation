import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
import aiohttp

from ..core.config import settings
from ..crud.job import enqueue_agent_job, get_active_parsing_jobs
from ..crud.llm_config import get_active_llm_config
from .llm_auth_helper import prepare_llm_auth

from ..utils.log_setup import get_logger
from ..utils.security import sanitize_path_component, validate_path_within_base, sanitize_log_message

logger = get_logger(__name__)


POLICIES_DIR = Path("/app/data/policies")

# Valid policy IDs
VALID_POLICIES = [
    "event_search",
]


def extract_policy_name(llm_response: str) -> str:
    """
    Extract a valid policy name from an LLM response.

    The language model may return explanatory text instead of a plain policy identifier.
    This function parses the raw response and returns the first recognized policy name,
    falling back to a default when no match is found.

    Args:
        llm_response (str): The raw text returned by the LLM.

    Returns:
        str: The extracted policy name if one is identified; otherwise the first
             entry from `VALID_POLICIES` or `"event_search"` as a fallback.
    """
    if not llm_response or llm_response.strip() == "":
        default_policy = VALID_POLICIES[0] if VALID_POLICIES else "event_search"
        logger.warning(
            f"[POLICY_ROUTER] Empty LLM response received. Using default '{sanitize_log_message(default_policy)}'"
        )
        return default_policy

    response_lower = llm_response.lower().strip()
    logger.debug(f"[POLICY_ROUTER] Parsing response: '{sanitize_log_message(response_lower)}'")

    # First, check if the response IS a valid policy (simple case)
    if response_lower in VALID_POLICIES:
        logger.debug(f"[POLICY_ROUTER] Exact match found: '{sanitize_log_message(response_lower)}'")
        return response_lower

    # Check if response starts with a valid policy name
    for policy in VALID_POLICIES:
        if response_lower.startswith(policy):
            logger.debug(
                f"[POLICY_ROUTER] Extracted policy '{sanitize_log_message(policy)}' from response: {sanitize_log_message(llm_response[:100])}"
            )
            return policy

    # Search for valid policy names anywhere in the response
    for policy in VALID_POLICIES:
        if policy in response_lower:
            logger.debug(
                f"[POLICY_ROUTER] Found policy '{sanitize_log_message(policy)}' in response: {sanitize_log_message(llm_response[:100])}"
            )
            return policy

    # No valid policy found - log and use default (first available policy)
    default_policy = VALID_POLICIES[0] if VALID_POLICIES else "event_search"
    logger.info(
        f"[POLICY_ROUTER] Could not extract valid policy from LLM response: '{sanitize_log_message(llm_response[:200])}'. "
        f"Using default '{sanitize_log_message(default_policy)}'"
    )
    return default_policy


def load_policy(policy_id: str) -> Dict[str, Any]:
    """
    Load a policy definition from its YAML file.

    Parameters
    ----------
    policy_id: str
        The identifier of the policy to load. This corresponds to a YAML file named `{policy_id}.yaml` located in :data:`POLICIES_DIR`.

    Returns
    -------
    Dict[str, Any]
        A dictionary representation of the parsed YAML content for the requested policy.

    Raises
    ------
    FileNotFoundError
        If no file matching `{policy_id}.yaml` exists in :data:`POLICIES_DIR`.
    """
    # Sanitize policy_id to prevent path traversal
    safe_policy_id = sanitize_path_component(policy_id)
    
    # Construct path and validate it's within POLICIES_DIR
    policy_filename = f"{safe_policy_id}.yaml"
    path = validate_path_within_base(Path(policy_filename), POLICIES_DIR)
    
    if not path.is_file():
        raise FileNotFoundError(f"Policy '{safe_policy_id}' not found at {path}")

    with open(path, "r") as f:
        return yaml.safe_load(f)


async def call_llm_backend(db: AsyncSession, user_id: int, prompt: str) -> Dict[str, Any]:
    """
    Call the LLM backend using the active configuration for a given user and retrieve a policy name.

    The function fetches the user's currently active LLM settings from the database, builds an OpenAI-compatible request payload (including optional sampling parameters if they are configured), sends it to the specified endpoint, and parses the response to extract a single policy identifier.

    If no configuration is found, or if any step fails (e.g., network error, unexpected response format, empty content), the function falls back to a predefined default policy.

    Args:
        db: An asynchronous SQLAlchemy session used to query the user's LLM configuration.
        user_id: The unique identifier of the user whose LLM settings should be applied.
        prompt: The text prompt that will be sent to the language model; it should ask the model to select a policy.

    Returns:
        A dictionary containing at least the key `policy` with the selected policy name as a string.
        If the call succeeds, the dictionary also includes `raw_response` holding the raw content returned by the LLM.
        In fallback scenarios, only `policy` is present and `raw_response` may be omitted or contain an explanatory placeholder.

    Raises:
        No exceptions are propagated; all errors are caught internally and result in a default policy being returned.
    """
    # Get user's active LLM configuration
    llm_config = await get_active_llm_config(db, user_id)

    if not llm_config:
        # Fallback: return a default policy for demo purposes
        default_policy = VALID_POLICIES[0] if VALID_POLICIES else "event_search"
        logger.warning(
            f"No active LLM config for user {user_id}, using default policy '{default_policy}'"
        )
        return {"policy": default_policy}

    # Extract values from SQLAlchemy model
    # Access attributes directly - SQLAlchemy will return the actual values
    api_endpoint: str = llm_config.api_endpoint  # type: ignore
    api_key: Optional[str] = llm_config.api_key  # type: ignore
    model_name: str = llm_config.model_name  # type: ignore

    # Extract numeric parameters with proper type conversion
    # Note: SQLAlchemy Numeric columns return Decimal objects, need str() conversion
    temperature = 0.0  # Default for policy selection (deterministic)
    if llm_config.temperature is not None:
        temperature = float(str(llm_config.temperature))

    # Optional parameters (only add if configured)
    top_p = None
    if llm_config.top_p is not None:
        top_p = float(str(llm_config.top_p))

    top_k = None
    if llm_config.top_k is not None:
        top_k = int(str(llm_config.top_k))

    min_p = None
    if llm_config.min_p is not None:
        min_p = float(str(llm_config.min_p))

    # Prepare authentication (supports both Bearer token and cookies)
    headers, cookies = prepare_llm_auth(api_key)

    async with aiohttp.ClientSession(cookies=cookies) as session:
        # Use OpenAI-compatible format (works with LM Studio)
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "You select policies. Respond with ONLY the policy name, no explanation.",
                },
                {"role": "user", "content": prompt},
            ],
            "model": model_name,
            "max_tokens": 100,  # Fixed for policy selection (short response needed)
            "temperature": temperature,  # Use configured temperature (or 0.0 for deterministic)
        }

        # Add optional sampling parameters if configured
        if top_p is not None:
            payload["top_p"] = top_p
        if top_k is not None:
            payload["top_k"] = top_k
        if min_p is not None:
            payload["min_p"] = min_p

        # Log payload (truncate if too large)
        payload_str = json.dumps(payload, indent=2)
        if len(payload_str) > 1000:
            logger.debug(f"[POLICY_ROUTER] Sending payload (truncated): {sanitize_log_message(payload_str[:1000])}...")
        else:
            logger.debug(f"[POLICY_ROUTER] Sending payload: {sanitize_log_message(payload_str)}")

        try:
            logger.debug(f"[POLICY_ROUTER] Calling LLM at {api_endpoint} with model {model_name}")
            async with session.post(
                api_endpoint, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(
                        f"[POLICY_ROUTER] LLM endpoint returned {resp.status}: {sanitize_log_message(error_text)}"
                    )
                    raise Exception(f"LLM endpoint returned {resp.status}: {sanitize_log_message(error_text)}")

                data = await resp.json()
                # Log response structure (truncate if too large)
                response_str = json.dumps(data, indent=2)
                if len(response_str) > 2000:
                    logger.debug(
                        f"[POLICY_ROUTER] LLM raw response (truncated): {sanitize_log_message(response_str[:2000])}..."
                    )
                else:
                    logger.debug(f"[POLICY_ROUTER] LLM raw response: {sanitize_log_message(response_str)}")

                # Extract content from response - try multiple formats
                content = None

                # Format 1: OpenAI format - {"choices": [{"message": {"content": "..."}}]}
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    logger.debug(f"[POLICY_ROUTER] First choice keys: {sanitize_log_message(str(list(choice.keys())))}")

                    if "message" in choice:
                        message = choice["message"]
                        logger.debug(f"[POLICY_ROUTER] Message keys: {sanitize_log_message(str(list(message.keys())))}")
                        content = message.get("content")
                        content_type = type(content).__name__ if content is not None else "None"
                        logger.debug(
                            f"[POLICY_ROUTER] Content from message.content: {sanitize_log_message(repr(content))} (type: {content_type})"
                        )
                    elif "text" in choice:
                        content = choice["text"]
                        content_type = type(content).__name__ if content is not None else "None"
                        logger.debug(
                            f"[POLICY_ROUTER] Content from choice.text: {sanitize_log_message(repr(content))} (type: {content_type})"
                        )
                    else:
                        logger.warning(
                            f"[POLICY_ROUTER] Choice has neither 'message' nor 'text': {sanitize_log_message(str(list(choice.keys())))}"
                        )

                # Format 2: Direct response field (some providers)
                if content is None and "response" in data:
                    content = data["response"]
                    logger.debug(f"[POLICY_ROUTER] Extracted from response field: '{sanitize_log_message(str(content))}'")

                # Format 3: Direct content field (some providers)
                if content is None and "content" in data:
                    content = data["content"]
                    logger.debug(f"[POLICY_ROUTER] Extracted from content field: '{sanitize_log_message(str(content))}'")

                # Format 4: Text field (some providers)
                if content is None and "text" in data:
                    content = data["text"]
                    logger.debug(f"[POLICY_ROUTER] Extracted from text field: '{sanitize_log_message(str(content))}'")

                # Check if we got valid content
                if content is None:
                    default_policy = VALID_POLICIES[0] if VALID_POLICIES else "event_search"
                    response_str = json.dumps(data, indent=2)
                    if len(response_str) > 1000:
                        response_str = response_str[:1000] + "..."
                    logger.error(
                        f"[POLICY_ROUTER] LLM returned no content field. "
                        f"Response structure: {sanitize_log_message(str(list(data.keys())))}. "
                        f"Full response: {sanitize_log_message(response_str)}. "
                        f"Using default policy '{sanitize_log_message(default_policy)}'"
                    )
                    return {"policy": default_policy, "raw_response": "(no content field)"}

                # Convert to string and check if empty
                content_str = str(content).strip()

                if content_str == "":
                    default_policy = VALID_POLICIES[0] if VALID_POLICIES else "event_search"
                    response_str = json.dumps(data, indent=2)
                    if len(response_str) > 1000:
                        response_str = response_str[:1000] + "..."
                    logger.error(
                        f"[POLICY_ROUTER] LLM returned empty content. "
                        f"Content value: {sanitize_log_message(repr(content))}. "
                        f"Full response: {sanitize_log_message(response_str)}. "
                        f"Using default policy '{sanitize_log_message(default_policy)}'"
                    )
                    return {"policy": default_policy, "raw_response": "(empty string)"}

                # Extract valid policy name from response
                logger.debug(f"[POLICY_ROUTER] Final content to parse: '{sanitize_log_message(content_str)}'")
                policy_name = extract_policy_name(content_str)
                return {"policy": policy_name, "raw_response": content_str}

        except Exception as e:
            # Fallback on error
            default_policy = VALID_POLICIES[0] if VALID_POLICIES else "event_search"
            logger.error(
                f"[POLICY_ROUTER] LLM call failed: {sanitize_log_message(str(e))}, using default policy '{sanitize_log_message(default_policy)}'"
            )
            return {"policy": default_policy}


async def route_question(
    db: AsyncSession,
    investigation_id: UUID,
    question: str,
    user_id: int,
    policy_id: Optional[str] = None,
    rule_values: Optional[Dict[str, Any]] = None,
    effort: str = "medium",
) -> Dict[str, Any]:
    """
    Route a question to the appropriate policy and enqueue an analysis job.

    If a `policy_id` is not supplied the function queries an LLM to select one from the
    available policies.  Missing rule values trigger a clarification request that
    describes which required parameters are needed.  When all required information is
    present, the function renders the policy’s seed-instruction template, creates an
    agent job and returns details about the queued job.

    Args:
        db: An asynchronous SQLAlchemy session used for database operations.
        investigation_id: The UUID of the investigation to which the question belongs.
        question: The user-provided natural-language question that should be answered.
        user_id: Identifier of the user who submitted the question.
        policy_id: Optional identifier of a pre-selected policy.  If omitted, an LLM
            selects a suitable policy from `VALID_POLICIES`.
        rule_values: Optional mapping of rule names to values supplied by the user or
            a previous clarification step.  Missing required rules will cause a
            clarification response.
        effort: Desired effort level for the analysis (e.g., `"low"`, `"medium"`,
            `"high"`).  This value is always added to the resolved rule set.

    Returns:
        dict: One of three possible response structures:

        * Clarification request - when required rules are missing.  Contains
          `type="clarification_request"`, the selected policy identifier, a title,
          and a list of `missing_rules` each describing name, description, type,
          and options.

        * Error - when the selected policy cannot be loaded or a template rendering
          error occurs.  Includes `type="error"`, an explanatory message and, where
          appropriate, a suggestion listing available policies.

        * Job queued - when all inputs are valid and a job has been created.  Contains
          `type="job_queued"`, the new `job_id`, policy information, a success
          message and an estimated duration if provided by the policy configuration.
    """
    # Step 1: Select policy if not provided
    selected_policy_id = policy_id
    if not selected_policy_id:
        # Build LLM prompt for policy selection
        # Build policy list dynamically from VALID_POLICIES
        policy_list = "\n".join([f"{i+1}. {p}" for i, p in enumerate(VALID_POLICIES)])
        selector_prompt = f"""Select the best policy for this question.

Available Policies:
{policy_list}

Question: {question}

Answer with ONLY ONE policy name from the list above:"""

        llm_resp = await call_llm_backend(db, user_id, selector_prompt)
        default_policy = VALID_POLICIES[0] if VALID_POLICIES else "event_search"
        selected_policy_id = llm_resp.get("policy", default_policy)

        # Validate the selected policy
        if selected_policy_id not in VALID_POLICIES:
            logger.warning(
                f"LLM selected invalid policy '{sanitize_log_message(selected_policy_id)}', using {sanitize_log_message(default_policy)}. "
                f"Raw response: {sanitize_log_message(llm_resp.get('raw_response', '')[:200])}"
            )
            selected_policy_id = default_policy

    # Step 2: Load the policy
    try:
        policy = load_policy(selected_policy_id)
    except FileNotFoundError as e:
        logger.error(
            f"Policy not found for investigation {investigation_id}: "
            f"policy_id={sanitize_log_message(selected_policy_id)}, error={sanitize_log_message(str(e))}"
        )
        return {
            "type": "error",
            "message": f"Policy '{sanitize_log_message(selected_policy_id)}' not found. Please select a valid policy.",
            "suggestion": f"Available policies: {', '.join(VALID_POLICIES)}",
        }

    # Step 3: Resolve rule values
    rules_def = policy.get("rules", {})
    resolved = rule_values or {}
    # Always include effort level
    resolved["effort"] = effort
    missing = []

    for rule_name, rule_spec in rules_def.items():
        if rule_name not in resolved:
            default = rule_spec.get("default")
            if default is not None:
                resolved[rule_name] = default
            else:
                # Required rule with no default
                missing.append(
                    {
                        "name": rule_name,
                        "description": rule_spec.get("description", ""),
                        "type": rule_spec.get("type", "string"),
                        "options": rule_spec.get("options", []),
                    }
                )

    # Step 4: Check if clarification is needed
    if missing:
        return {
            "type": "clarification_request",
            "policy_id": selected_policy_id,
            "policy_title": policy.get("title", selected_policy_id),
            "missing_rules": missing,
            "message": f"The policy '{selected_policy_id}' requires additional information.",
        }

    # Step 5: Render seed instructions
    seed_template = policy.get("seed_instructions", "")
    try:
        seed_instructions = seed_template.format(question=question, **resolved)
    except KeyError as e:
        logger.error(
            f"Template error for policy {sanitize_log_message(selected_policy_id)} in investigation {investigation_id}: "
            f"missing variable {sanitize_log_message(str(e))}"
        )
        return {"type": "error", "message": "Policy configuration error. Please contact support."}

    # Step 6: Check for active parsing jobs before creating agent job
    active_parsing_jobs = await get_active_parsing_jobs(db, investigation_id)

    if active_parsing_jobs:
        job_count = len(active_parsing_jobs)
        logger.debug(
            f"[POLICY_ROUTER] Delaying agent job creation for investigation {investigation_id}: "
            f"{job_count} parsing job(s) still active (IDs: {[j.job_id for j in active_parsing_jobs]})"
        )
        return {
            "type": "parsing_in_progress",
            "message": f"Waiting for {job_count} parsing job{'s' if job_count > 1 else ''} to complete before starting analysis. "
            f"Please wait a moment and try again.",
            "active_jobs": job_count,
            "suggestion": "The system will automatically retry once parsing is complete.",
        }

    # Step 7: Create agent job (only if no parsing jobs are active)
    logger.debug(
        f"[POLICY_ROUTER] No active parsing jobs, creating agent job for investigation {investigation_id}"
    )
    job = await enqueue_agent_job(
        db,
        investigation_id=investigation_id,
        user_id=user_id,
        policy_id=selected_policy_id,
        rule_values=resolved,
        seed_instructions=seed_instructions,
    )

    # Calculate max turns based on effort level
    effort_to_turns = {
        "low": 3,
        "medium": 6,
        "high": 9,
    }
    max_turns = effort_to_turns.get(effort, 6)

    return {
        "type": "job_queued",
        "job_id": job.job_id,
        "policy_id": selected_policy_id,
        "policy_title": policy.get("title", selected_policy_id),
        "message": "Analysis job created and queued for processing.",
        "estimated_duration": policy.get("estimated_duration", "unknown"),
        "routing_metadata": {
            "handler_type": "agent",
            "handler_display_name": "AI Agent Investigation",
            "effort_level": effort,
            "max_turns": max_turns,
            "job_id": job.job_id,
        },
    }
