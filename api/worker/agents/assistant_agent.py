import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import LLMClient, ToolExecutor, tool_registry
from ..models import AssistantMessage, ToolCall, ToolResult
from ..tools.csv_formatter import events_to_csv
from ..tools.timeline_tools import batch_generate_embeddings
from .context_manager import (
    estimate_tokens,
    prune_chat_log,
    load_investigation_context,
    load_execution_phase_context,
    load_analysis_phase_context,
)
from .tool_categories import filter_tools_for_phase
from .memory_summarizer import generate_chat_summary, load_chat_summary, trim_messages_from_middle
from .prompts import get_system_prompt, get_tool_execution_prompt, get_analysis_prompt
from .investigation_playbooks import get_investigation_strategy_prompt

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2               # seconds: 2, 4, 8 …
MAX_TOOLS_PER_ITERATION = 3          # Limit to 3 tools per iteration for focused investigation
COMPAT_TOKEN_THRESHOLD = 0.80        # compact when >80 % of LLM context
MAX_CHAT_LOG_TOKENS = 100000         # Maximum tokens for chat log before compaction
MAX_RESULT_SIZE = 100                # Maximum events returned per query - encourage focused queries
HIGH_RESULT_THRESHOLD = 50           # Threshold for "too many results" warning

def _compact_serialize(data: Any) -> str:
    return json.dumps(data, default=str, separators=(",", ":"), ensure_ascii=False)

def _deduplicate_tool_calls(
    tool_calls: List[ToolCall],
) -> Tuple[List[ToolCall], int]:
    seen, uniq, dup = set(), [], 0
    for tc in tool_calls:
        name = tc.function.get("name", "")
        try:
            args = json.loads(tc.function.get("arguments", "{}"))
        except Exception:
            args = {}
        sig = f"{name}:{json.dumps({k: v for k, v in args.items() if k != 'description'}, sort_keys=True)}"
        if sig not in seen:
            seen.add(sig)
            uniq.append(tc)
        else:
            dup += 1
    return uniq, dup

class _ContextBuilder:
    def __init__(
        self,
        db: AsyncSession,
        investigation_id: str,
        llm_client: LLMClient,
        question: str,
        iteration: int,
        max_context: int,
    ):
        self.db = db
        self.investigation_id = investigation_id
        self.llm_client = llm_client
        self.question = question
        self.iteration = iteration
        self.max_context = max_context

    async def system_prompt(self) -> str:
        base_ctx = await load_investigation_context(
            db=self.db,
            investigation_id=self.investigation_id,
            llm_client=self.llm_client,
            llm_max_context=self.max_context,
        )
        return get_system_prompt(base_ctx)

    async def phase_context(self, phase: str) -> str:
        if phase == "tool_execution":
            ctx = await load_execution_phase_context(
                db=self.db,
                investigation_id=self.investigation_id,
                llm_client=self.llm_client,
                llm_max_context=self.max_context,
            )
            prompt = get_tool_execution_prompt(self.question, self.iteration)
        else:  # analysis
            ctx = await load_analysis_phase_context(
                db=self.db,
                investigation_id=self.investigation_id,
            )
            # a short summary of tool results is injected later by the caller
            prompt = ""  # placeholder – filled in run()
        return f"{ctx}\n{prompt}"


class AssistantAgent:
    """
    Two-phase forensic LLM agent (Plan-then-Execute).

    Phase 1: Planner asks the model to produce a list of tool calls.
    Phase 2: Executor runs those tools, then Analyzer receives results,
              may register timeline entries or finish the investigation.

    The class streams progress events for UI consumption.
    """

    def __init__(
        self,
        db: AsyncSession,
        investigation_id: str,
        job_id: int,
        question: str,
        llm_endpoint: str,
        llm_model: str,
        llm_api_key: Optional[str] = None,
        llm_max_context: int = 32768,
        llm_temperature: float = 0.1,
        llm_top_p: Optional[float] = None,
        llm_top_k: Optional[int] = None,
        llm_min_p: Optional[float] = None,
        llm_timeout: int = 300,
        max_iterations: int = 10,
        user_id: Optional[int] = None,
    ):
        self.db = db
        self.investigation_id = investigation_id
        self.job_id = job_id
        self.question = question

        # LLM client
        self.llm_client = LLMClient(
            endpoint=llm_endpoint,
            model=llm_model,
            api_key=llm_api_key,
            max_context_length=llm_max_context,
            temperature=llm_temperature,
            top_p=llm_top_p,
            top_k=llm_top_k,
            min_p=llm_min_p,
            timeout=llm_timeout,
        )
        self.llm_max_context = llm_max_context
        self.llm_temp = llm_temperature

        # Tool executor & stats
        self.stats = {
            "events_analyzed": 0,
            "tools_called": {},
            "timeline_entries_created": 0,
            "tags_applied": set(),
        }
        self.tool_executor = ToolExecutor(
            db, investigation_id, self.stats, user_id=user_id
        )
        self.user_id = user_id

        # Iteration control
        self.iteration = 0
        self.max_iterations = max_iterations
        self.hard_ceiling = 30
        self.turn_extensions = 0
        self.cancelled = False
        self.total_tools_executed = 0
        self.tool_execution_log: List[Dict[str, Any]] = []
        self.query_signatures: set[str] = set()  # Track unique query signatures to prevent repetition

        # Compaction trigger (80 % of model context)
        self.compact_threshold = int(llm_max_context * COMPAT_TOKEN_THRESHOLD)

    async def check_cancel_signal(self) -> bool:
        try:
            result = await self.db.execute(
                text(
                    """
                    SELECT metadata->>'stop_requested' AS stop_requested
                    FROM jobs_agents
                    WHERE job_id = :job_id
                    """
                ),
                {"job_id": self.job_id},
            )
            row = result.fetchone()
            if row and row[0] == "true":
                self.cancelled = True
                logger.info(f"Job {self.job_id} cancelled by user")
                return True
        except Exception as e:
            logger.warning(f"Cancel check failed: {e}")
        return False

    async def _llm_stream(
        self,
        chat_log: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream LLM response with retry / back-off.
        Emits:
          - llm_retry
          - llm_error
          - llm_response (AssistantMessage | None)
          - agent_cancelled
        """
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # token estimate for logging
                inp_toks = sum(
                    estimate_tokens(json.dumps(m, default=str)) for m in chat_log
                )
                logger.info(f"LLM call (attempt {attempt}) – ~{inp_toks} input tokens")

                stream = self.llm_client.stream_chat(
                    messages=chat_log,
                    tools=tools,
                    tool_choice=tool_choice,
                    temperature=self.llm_temp,
                    max_tokens=min(16384, self.llm_max_context // 4),
                    top_p=self.llm_client._service.config.top_p,
                    top_k=self.llm_client._service.config.top_k,
                    min_p=self.llm_client._service.config.min_p,
                    timeout=self.llm_client._service.config.timeout,
                )

                content, tool_calls = "", []
                i = 0
                async for chunk in stream:
                    if i % 10 == 0 and await self.check_cancel_signal():
                        yield {"type": "agent_cancelled", "message": "Investigation stopped"}
                        raise asyncio.CancelledError()
                    i += 1

                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta:
                        content += delta["content"] or ""
                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            while len(tool_calls) <= idx:
                                tool_calls.append(
                                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                                )
                            if "id" in tc:
                                tool_calls[idx]["id"] = tc["id"]
                            if "function" in tc:
                                f = tc["function"]
                                if "name" in f:
                                    tool_calls[idx]["function"]["name"] += f["name"]
                                if "arguments" in f:
                                    tool_calls[idx]["function"]["arguments"] += f["arguments"]

                # Build AssistantMessage
                msg_dict: Dict[str, Any] = {"role": "assistant", "content": content or None}
                if tool_calls:
                    parsed = [
                        ToolCall(id=tc.get("id"), type="function", function=tc["function"])
                        for tc in tool_calls
                    ]
                    msg_dict["tool_calls"] = parsed
                assistant_msg = AssistantMessage(**msg_dict)

                yield {"type": "llm_response", "message": assistant_msg, "success": True}
                return

            except asyncio.CancelledError:
                yield {"type": "agent_cancelled", "message": "Investigation stopped"}
                raise
            except Exception as e:
                last_err = e
                logger.error(f"LLM error (attempt {attempt}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_BASE ** attempt
                    yield {"type": "llm_retry", "message": f"Retrying in {wait}s...", "retry_count": attempt}
                    await asyncio.sleep(wait)
                else:
                    yield {"type": "llm_error", "error": str(e)}
                    yield {"type": "llm_response", "message": None, "success": False, "error": str(e)}
                    return

    async def _plan_tools(
        self,
        chat_log: List[Dict[str, Any]],
        available_tools: List[Dict[str, Any]],
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Planner – ask LLM to produce tool calls (tool_choice=required).
        Yields events and returns assistant message and a deduplicated list of ToolCall objects.
        """
        planner_msg: Optional[AssistantMessage] = None
        planned_calls: List[ToolCall] = []
        
        async for ev in self._llm_stream(chat_log, available_tools, tool_choice="required"):
            if ev["type"] == "llm_response":
                msg: Optional[AssistantMessage] = ev["message"]
                if not ev["success"] or msg is None:
                    yield {"type": "_internal_plan_result", "message": None, "tool_calls": []}
                    return
                calls = msg.tool_calls or []
                uniq, dup = _deduplicate_tool_calls(calls)
                
                # Log and notify about duplicates
                if dup:
                    logger.info(f"Removed {dup} duplicate tool calls")
                    yield {
                        "type": "tool_limit_enforced",
                        "message": f"Removed {dup} duplicate tool calls",
                        "requested": len(calls),
                        "executed": len(uniq),
                    }
                
                # enforce per-iteration limit
                if len(uniq) > MAX_TOOLS_PER_ITERATION:
                    logger.warning(
                        f"Agent requested {len(uniq)} tools, limiting to {MAX_TOOLS_PER_ITERATION} "
                        f"(iteration {self.iteration}/{self.max_iterations})"
                    )
                    yield {
                        "type": "tool_limit_enforced",
                        "message": f"Tool limit enforced: {len(uniq)} requested, executing {MAX_TOOLS_PER_ITERATION}",
                        "requested": len(uniq),
                        "executed": MAX_TOOLS_PER_ITERATION,
                    }
                    uniq = uniq[:MAX_TOOLS_PER_ITERATION]
                
                planner_msg = msg
                planned_calls = uniq
                logger.info(f"Planning complete: {len(planned_calls)} tools to execute")
                # Internal message for workflow
                yield {"type": "_internal_plan_result", "message": planner_msg, "tool_calls": planned_calls}
                return
            else:
                yield ev

        yield {"type": "_internal_plan_result", "message": None, "tool_calls": []}

    async def _execute_tools(
        self,
        tool_calls: List[ToolCall],
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute each ToolCall via ToolExecutor with retry.
        Yields UI-friendly events and internal `_internal_tool_result`.
        Updates statistics.
        """
        for tc in tool_calls:
            if await self.check_cancel_signal():
                yield {"type": "agent_cancelled", "message": "Investigation stopped"}
                raise asyncio.CancelledError()

            name = tc.function.get("name", "")
            try:
                args = json.loads(tc.function.get("arguments", "{}"))
            except Exception:
                args = {}

            # UI start event
            yield {
                "type": "tool_executing",
                "tool": name,
                "arguments": args,
                "turn_number": self.iteration,
                "max_turns": self.max_iterations,
            }

            last_err = None
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    result: ToolResult = await self.tool_executor.execute(name, args)
                    # UI result event
                    summary = ""
                    if result.status == "ok" and result.result:
                        cnt = result.result.get("count", 0)
                        summary = f"Found {cnt} events"
                    elif result.status == "error":
                        summary = f"Error: {result.error_msg}"
                    yield {
                        "type": "tool_result",
                        "tool": name,
                        "display_name": args.get("description", name),
                        "result": {
                            "status": result.status,
                            "result": result.result,
                            "error_msg": result.error_msg,
                        },
                        "result_summary": summary,
                        "success": result.status == "ok",
                        "tool_call_id": tc.id or f"tc_{self.total_tools_executed}",
                    }
                    # internal event for downstream logic
                    yield {"type": "_internal_tool_result", "tool_result_obj": result}
                    self.total_tools_executed += 1

                    # record query-tool usage (for history)
                    if name in {
                        "query_jsonb_field",
                        "aggregate_jsonb_field",
                        "search_events_by_content",
                        "get_event_by_id",
                        "hybrid_search",
                        "execute_sql",
                    } and result.status == "ok":
                        result_count = result.result.get("count", 0) if result.result else 0
                        
                        # Extract sample fields from first event to show LLM what data exists
                        sample_fields = {}
                        if result.result and "events" in result.result and result.result["events"]:
                            first_event = result.result["events"][0]
                            payload = first_event.get("payload", {})
                            if isinstance(payload, dict):
                                # Extract key fields that are useful for investigation
                                for key in ["event_data", "system", "EventData", "System"]:
                                    if key in payload and isinstance(payload[key], dict):
                                        # Get first few fields from nested object
                                        nested = payload[key]
                                        sample_fields[key] = {k: v for i, (k, v) in enumerate(nested.items()) if i < 5}
                        
                        # Provide feedback for overly broad queries
                        feedback = ""
                        if result_count > HIGH_RESULT_THRESHOLD:
                            feedback = f" (HIGH: Consider narrowing with additional filters)"
                        elif result_count == 0:
                            feedback = " (EMPTY: Consider broadening search or trying different fields)"
                        
                        self.tool_execution_log.append(
                            {
                                "iteration": self.iteration,
                                "tool_name": name,
                                "arguments": {k: v for k, v in args.items() if k != "description"},
                                "summary": summary + feedback,
                                "status": result.status,
                                "result_count": result_count,
                                "result_data": {"sample_fields": sample_fields} if sample_fields else None,
                            }
                        )
                    
                    # Check if investigation completed
                    if name == "complete_investigation" and result.status == "ok":
                        completion_summary = result.result.get("summary", "Investigation completed")
                        logger.info(f"Investigation completed: {completion_summary[:100]}...")
                        yield {
                            "type": "_investigation_completed",
                            "summary": completion_summary,
                        }
                    
                    break
                except asyncio.CancelledError:
                    logger.info(f"Tool {name} cancelled by user")
                    raise
                except Exception as e:
                    last_err = e
                    logger.error(f"Tool {name} error (attempt {attempt}/{MAX_RETRIES}): {e}")
                    if attempt < MAX_RETRIES:
                        wait = RETRY_BACKOFF_BASE ** attempt
                        yield {
                            "type": "tool_retry",
                            "tool": name,
                            "message": f"Retrying in {wait}s...",
                            "retry_count": attempt,
                        }
                        await asyncio.sleep(wait)
                    else:
                        err_res = ToolResult(status="error", error_msg=str(e), result=None)
                        yield {
                            "type": "tool_result",
                            "tool": name,
                            "display_name": args.get("description", name),
                            "result": {"status": "error", "result": None, "error_msg": str(e)},
                            "result_summary": f"Error: {e}",
                            "success": False,
                            "tool_call_id": tc.id or f"tc_err_{self.total_tools_executed}",
                        }
                        yield {"type": "_internal_tool_result", "tool_result_obj": err_res}
                        break

    async def _analyze_results(
        self,
        chat_log: List[Dict[str, Any]],
        analysis_tools: List[Dict[str, Any]],
        tool_summary: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Analyzer – feed LLM with tool results and optional analysis tools.
        Returns final assistant message (analysis) plus any timeline/completion actions.
        """
        # Append short tool-result summary for the model
        chat_log.append(
            {"role": "system", "content": f"## Tool Execution Summary\n{tool_summary}"}
        )
        async for ev in self._llm_stream(chat_log, analysis_tools, tool_choice="auto"):
            if ev["type"] == "llm_response":
                msg: Optional[AssistantMessage] = ev["message"]
                if not ev["success"] or msg is None:
                    yield {"type": "phase_error", "phase": "analysis", "error": ev.get("error")}
                    return
                # Run any analysis-phase tool calls (e.g., register_timeline_entry)
                if msg.tool_calls:
                    uniq, dup = _deduplicate_tool_calls(msg.tool_calls)
                    if dup:
                        yield {
                            "type": "tool_limit_enforced",
                            "message": f"Removed {dup} duplicate analysis tools",
                        }
                    for tc in uniq:
                        if await self.check_cancel_signal():
                            yield {"type": "agent_cancelled", "message": "Investigation stopped"}
                            raise asyncio.CancelledError()
                        name = tc.function.get("name", "")
                        try:
                            args = json.loads(tc.function.get("arguments", "{}"))
                        except Exception:
                            args = {}
                        async for tool_ev in self._execute_tools([tc]):
                            if tool_ev["type"] != "_internal_tool_result":
                                yield tool_ev
                yield {"type": "analysis_complete", "summary": msg.content or ""}
                return
            else:
                yield ev

    async def _maybe_compact(self, chat_log: List[Dict[str, Any]]) -> AsyncIterator[Dict[str, Any]]:
        """
        Compact the log if token budget exceeded.
        Emits `context_compacted` and final `_compacted_chat_log`.
        """
        cur = sum(estimate_tokens(json.dumps(m, default=str)) for m in chat_log)
        if cur > self.compact_threshold:
            logger.info(f"Compacting chat ({cur} tokens > {self.compact_threshold})")
            async for ev in self._compact_chat_log(chat_log):
                if ev["type"] == "_compacted_chat_log":
                    chat_log[:] = ev["chat_log"]
                else:
                    yield ev
        else:
            # simple prune to stay under hard limit
            chat_log[:] = prune_chat_log(chat_log, max_tokens=MAX_CHAT_LOG_TOKENS)

    async def _compact_chat_log(
        self,
        chat_log: List[Dict[str, Any]],
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Summarise older messages via LLM or fall back to middle-trimming.
        """
        if len(chat_log) <= 7:
            yield {"type": "_compacted_chat_log", "chat_log": chat_log}
            return

        # try cached summary
        summary_text, meta = await load_chat_summary(
            db=self.db,
            investigation_id=self.investigation_id,
            job_id=self.job_id,
            iteration_number=self.iteration,
        )
        if not summary_text:
            try:
                summary_text, meta = await generate_chat_summary(
                    db=self.db,
                    investigation_id=self.investigation_id,
                    job_id=self.job_id,
                    iteration_number=self.iteration,
                    messages_to_summarize=chat_log[2:-5],
                    start_idx=2,
                    end_idx=len(chat_log) - 5,
                    llm_client=self.llm_client,
                )
            except Exception as e:
                logger.warning(f"LLM summary failed: {e}")
                trimmed = trim_messages_from_middle(chat_log, max_tokens=4000)
                yield {"type": "context_compacted", "message": "Trimmed from middle"}
                yield {"type": "_compacted_chat_log", "chat_log": trimmed}
                return

        compacted = [
            chat_log[0],
            chat_log[1],
            {
                "role": "system",
                "content": f"## Investigation History (Compacted)\n{summary_text}",
            },
        ] + chat_log[-5:]

        yield {"type": "context_compacted", "message": "LLM summary applied"}
        yield {"type": "_compacted_chat_log", "chat_log": compacted}

    def _stats_snapshot(self) -> Dict[str, Any]:
        return {
            "turns_executed": self.iteration,
            "tool_executions": self.total_tools_executed,
            "events_analyzed": self.stats.get("events_analyzed", 0),
            "timeline_entries_created": self.stats.get("timeline_entries_created", 0),
            "tools_called": dict(self.stats.get("tools_called", {})),
        }

    async def _batch_generate_embeddings(self) -> None:
        try:
            count = await batch_generate_embeddings(
                db=self.db,
                investigation_id=self.investigation_id,
                user_id=self.user_id or 1,
            )
            if count:
                logger.info(f"Generated {count} timeline embeddings")
        except Exception as e:
            logger.warning(f"Embedding batch failed: {e}")

    async def run(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Main loop – yields progress events for UI.
        """
        # Build initial context
        ctx = _ContextBuilder(
            db=self.db,
            investigation_id=self.investigation_id,
            llm_client=self.llm_client,
            question=self.question,
            iteration=0,
            max_context=self.llm_max_context,
        )
        system_msg = await ctx.system_prompt()
        
        # Initialize chat log that will be maintained across iterations
        chat_log: List[Dict[str, Any]] = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": self.question},
        ]
        
        # Get playbook for this investigation (if applicable)
        selected_playbook = None
        playbook_metadata = None
        try:
            from .playbooks import select_playbook_for_query
            selected_playbook = await select_playbook_for_query(self.question, self.llm_client)
            if selected_playbook:
                playbook_metadata = {
                    "playbook_name": selected_playbook.name,
                    "playbook_display_name": selected_playbook.display_name,
                    "playbook_description": selected_playbook.description,
                }
                logger.info(f"Selected playbook: {selected_playbook.display_name}")
        except Exception as e:
            logger.warning(f"Playbook selection failed: {e}")
        
        try:
            yield {
                "type": "agent_started",
                "question": self.question,
                "playbook_metadata": playbook_metadata,
            }
            while not self.cancelled and self.iteration < self.max_iterations:
                self.iteration += 1
                logger.info(f"--- Iteration {self.iteration}/{self.max_iterations} ---")

                if await self.check_cancel_signal():
                    yield {"type": "agent_cancelled", "message": "Investigation stopped"}
                    break

                # ---------- Phase 1 – Planning ----------
                # Inject investigation strategy guidance
                strategy_guidance = await get_investigation_strategy_prompt(
                    user_question=self.question,
                    iteration=self.iteration,
                    max_iterations=self.max_iterations,
                    tool_execution_log=self.tool_execution_log,
                    llm_client=self.llm_client,
                )
                
                # Add strategy as a system message before planning
                chat_log.append({
                    "role": "system",
                    "content": strategy_guidance
                })
                
                exec_tools_def = filter_tools_for_phase(
                    tool_registry.get_openai_format(), "tool_execution"
                )
                
                # Remove disabled broad-search tools to encourage focused queries
                exec_tools_def = [
                    t for t in exec_tools_def
                    if t.get("function", {}).get("name") not in {
                        "search_events_by_type",
                        "search_events_by_timerange"
                    }
                ]
                
                # allow completion after a few turns
                if self.iteration >= 4:
                    comp_tool = [
                        t for t in tool_registry.get_openai_format()
                        if t.get("function", {}).get("name") == "complete_investigation"
                    ]
                    exec_tools_def.extend(comp_tool)

                planner_msg = None
                planned_calls: List[ToolCall] = []
                async for ev in self._plan_tools(chat_log, exec_tools_def):
                    if ev["type"] == "_internal_plan_result":
                        planner_msg, planned_calls = ev["message"], ev.get("tool_calls", [])
                        logger.info(f"Received plan with {len(planned_calls)} tools")
                    elif ev["type"] != "_internal_plan_result":
                        # Only yield non-internal events to WebSocket
                        yield ev
                
                # Remove strategy guidance from chat log (it was just for planning context)
                if chat_log and chat_log[-1].get("role") == "system" and "INVESTIGATION STRATEGY" in chat_log[-1].get("content", ""):
                    chat_log.pop()
                
                # Filter out duplicate queries
                filtered_calls: List[ToolCall] = []
                duplicates_removed = 0
                for tc in planned_calls:
                    name = tc.function.get("name", "")
                    try:
                        args = json.loads(tc.function.get("arguments", "{}"))
                    except Exception:
                        args = {}
                    
                    # Create signature (exclude description as it varies)
                    sig_args = {k: v for k, v in args.items() if k != 'description'}
                    signature = f"{name}:{json.dumps(sig_args, sort_keys=True)}"
                    
                    if signature in self.query_signatures:
                        duplicates_removed += 1
                        logger.warning(f"Blocking duplicate query: {signature}")
                    else:
                        self.query_signatures.add(signature)
                        filtered_calls.append(tc)
                
                if duplicates_removed > 0:
                    logger.warning(f"Removed {duplicates_removed} duplicate queries from iteration {self.iteration}")
                    yield {
                        "type": "tool_limit_enforced",
                        "message": f"Blocked {duplicates_removed} duplicate queries - you already ran those!",
                        "requested": len(planned_calls),
                        "executed": len(filtered_calls),
                    }
                
                planned_calls = filtered_calls
                
                # Sanity check - ensure we never execute more than the limit
                if len(planned_calls) > MAX_TOOLS_PER_ITERATION:
                    logger.error(
                        f"CRITICAL: planned_calls has {len(planned_calls)} tools after limit should have been enforced! "
                        f"Forcing limit now."
                    )
                    planned_calls = planned_calls[:MAX_TOOLS_PER_ITERATION]

                # ---------- Phase 1 – Execution ----------
                investigation_completed_in_execution = False
                completion_summary_execution = None
                tool_results_for_llm: List[Dict[str, Any]] = []  # Collect tool results for LLM
                
                async for ev in self._execute_tools(planned_calls):
                    if ev["type"] == "_investigation_completed":
                        investigation_completed_in_execution = True
                        completion_summary_execution = ev["summary"]
                    elif ev["type"] == "_internal_tool_result":
                        # Collect tool result for LLM context
                        tool_res: ToolResult = ev["tool_result_obj"]
                        # Find the corresponding tool call ID
                        tc_id = planned_calls[len(tool_results_for_llm)].id if len(tool_results_for_llm) < len(planned_calls) else f"tc_{len(tool_results_for_llm)}"
                        tool_name = planned_calls[len(tool_results_for_llm)].function.get("name", "unknown") if len(tool_results_for_llm) < len(planned_calls) else "unknown"
                        
                        # Format result for LLM - include actual data
                        if tool_res.status == "ok" and tool_res.result:
                            content = json.dumps(tool_res.result, default=str, indent=2)
                        else:
                            content = json.dumps({"error": tool_res.error_msg}, default=str)
                        
                        tool_results_for_llm.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": tool_name,
                            "content": content
                        })
                    elif ev["type"] != "_internal_tool_result":
                        # Only yield non-internal events to WebSocket
                        yield ev
                
                # Add assistant's tool calls and tool results to chat log
                if planner_msg and planner_msg.tool_calls:
                    chat_log.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": tc.id,
                            "type": "function",
                            "function": tc.function
                        } for tc in planned_calls]
                    })
                
                # Add tool results to chat log so LLM can see the actual data
                chat_log.extend(tool_results_for_llm)
                
                # Check if investigation completed in execution phase
                if investigation_completed_in_execution and completion_summary_execution:
                    logger.info(f"Investigation completed in execution phase: {completion_summary_execution[:100]}...")
                    yield {
                        "type": "agent_completed",
                        "summary": completion_summary_execution,
                        "stats": self._stats_snapshot(),
                    }
                    return

                # Collect tool-result summary for analysis phase with investigative guidance
                tool_summary_parts = []
                for entry in self.tool_execution_log[-MAX_TOOLS_PER_ITERATION:]:
                    summary = f"- {entry['tool_name']} – {entry['summary']}"
                    
                    # Add sample data if available to show LLM what fields exist
                    if 'result_data' in entry and entry['result_data']:
                        sample_fields = entry['result_data'].get('sample_fields', {})
                        if sample_fields:
                            summary += f"\n  Sample fields: {json.dumps(sample_fields, indent=2)}"
                    
                    tool_summary_parts.append(summary)
                
                # Add investigative guidance based on results
                guidance_parts = []
                recent_results = self.tool_execution_log[-MAX_TOOLS_PER_ITERATION:]
                
                # Check for patterns that need correction
                high_count = sum(1 for e in recent_results if e.get('result_count', 0) > HIGH_RESULT_THRESHOLD)
                empty_count = sum(1 for e in recent_results if e.get('result_count', 0) == 0)
                
                if high_count > 0:
                    guidance_parts.append(
                        "⚠️ Some queries returned large result sets. Refine with more specific filters using JSONB field queries."
                    )
                if empty_count > 0:
                    guidance_parts.append(
                        "⚠️ Some queries returned no results. Consider alternative field names or broader search terms."
                    )
                
                tool_summary = "\n".join(tool_summary_parts) or "No tools executed."
                if guidance_parts:
                    tool_summary += "\n\n" + "\n".join(guidance_parts)

                # ---------- Phase 2 – Analysis ----------
                analysis_tools_def = filter_tools_for_phase(
                    tool_registry.get_openai_format(), "analysis"
                )
                if self.iteration < 4:
                    analysis_tools_def = [
                        t
                        for t in analysis_tools_def
                        if t.get("function", {}).get("name") != "complete_investigation"
                    ]

                analysis_summary = None
                investigation_completed = False
                completion_summary = None
                
                async for ev in self._analyze_results(chat_log, analysis_tools_def, tool_summary):
                    if ev["type"] == "analysis_complete":
                        analysis_summary = ev["summary"]
                    elif ev["type"] == "_investigation_completed":
                        investigation_completed = True
                        completion_summary = ev["summary"]
                    if ev["type"] not in ("_internal_tool_result", "_investigation_completed"):
                        # Only yield non-internal events to WebSocket
                        yield ev
                
                # Check if investigation completed
                if investigation_completed and completion_summary:
                    logger.info(f"Investigation completed! Summary: {completion_summary[:100]}...")
                    yield {
                        "type": "agent_completed",
                        "summary": completion_summary,
                        "stats": self._stats_snapshot(),
                    }
                    return
                
                # Add analysis summary to chat log for next iteration
                if analysis_summary:
                    chat_log.append({"role": "assistant", "content": analysis_summary})

                await self._batch_generate_embeddings()
                async for ev in self._maybe_compact(chat_log):
                    yield ev

                yield {
                    "type": "iteration_complete",
                    "iteration": self.iteration,
                    "stats": self._stats_snapshot(),
                }

            # max-iterations reached without explicit completion
            if not self.cancelled:
                yield {
                    "type": "agent_completed",
                    "summary": (
                        f"Reached max iterations ({self.max_iterations}) "
                        f"without final `complete_investigation`. "
                        f"{self.total_tools_executed} tools run, "
                        f"{self.stats.get('timeline_entries_created', 0)} timeline entries."
                    ),
                    "stats": self._stats_snapshot(),
                    "incomplete": True,  # Signal that investigation is incomplete
                }

        except asyncio.CancelledError:
            yield {
                "type": "agent_cancelled",
                "message": "Investigation stopped by user",
                "stats": self._stats_snapshot(),
            }
            raise
        except Exception as exc:
            logger.error(f"Unexpected agent error: {exc}", exc_info=True)
            yield {"type": "agent_error", "error": str(exc)}

__all__ = ["AssistantAgent"]