"""
Agent Core Orchestrator (Bộ não điều phối đa nhiệm cho Local AI OS Agent).
Hiện thực hóa chu trình Plan -> Act -> Observe -> Reflect với Ollama Native Tool Calling.
"""

import os
import re
import json
import time
import requests
from typing import Optional

from ai_assistant.config import OLLAMA_URL, DEFAULT_VOICE
from ai_assistant.core.state import set_assistant_state
from ai_assistant.core.agent_state import StructuredAgentState, AgentBudget
from ai_assistant.core.evaluator import task_evaluator, retry_controller
from ai_assistant.ai.model_router import route_task, MODEL_ROLES
from ai_assistant.tools.registry import tool_registry
from ai_assistant.speech.tts import speak, sanitize_text_for_voice

AGENT_SYSTEM_PROMPT = """Bạn là Agent điều phối hệ thống trên Arch Linux / Hyprland.
Bạn thực hiện tác vụ bằng cách gọi công cụ (Tools) được cung cấp.

QUY TẮC:
- Tự mình gọi công cụ để thực hiện, tuyệt đối không bảo người dùng tự gõ lệnh.
- Chỉ sử dụng các công cụ có trong danh sách tools được cung cấp.
- Khi hoàn thành: trả lời bằng 1-2 câu tiếng Việt tự nhiên, không dùng markdown.
"""

class AgentOrchestrator:
    def __init__(self):
        self.registry = tool_registry

    def _parse_tool_calls_from_text(self, text: str) -> list:
        """Trích xuất tool calls đa dạng (XML, JSON, CLI, Python call) nếu LLM sinh trong content."""
        results = []
        if not text:
            return results

        # 1. Thẻ chuẩn <tool_call> ... </tool_call>
        blocks = re.findall(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL)
        for b in blocks:
            try:
                data = json.loads(b.strip())
                name = data.get("name") or data.get("function") or data.get("tool")
                args = data.get("arguments") or data.get("parameters") or {}
                if name:
                    results.append({"function": {"name": name, "arguments": args}})
            except Exception:
                pass
        if results:
            return results

        # 2. Markdown json code block
        code_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        for b in code_blocks:
            try:
                data = json.loads(b.strip())
                name = data.get("name") or data.get("function") or data.get("tool") or data.get("action")
                args = data.get("arguments") or data.get("parameters")
                if not isinstance(args, dict):
                    args = {k: v for k, v in data.items() if k not in ["tool", "name", "function", "action", "arguments", "parameters"]}
                if name:
                    results.append({"function": {"name": name, "arguments": args}})
            except Exception:
                pass
        if results:
            return results

        # 3. JSON object thuần
        text_clean = text.strip()
        if text_clean.startswith("{") and text_clean.endswith("}"):
            try:
                data = json.loads(text_clean)
                name = data.get("name") or data.get("function") or data.get("tool") or data.get("action")
                args = data.get("arguments") or data.get("parameters")
                if not isinstance(args, dict):
                    args = {k: v for k, v in data.items() if k not in ["tool", "name", "function", "action", "arguments", "parameters"]}
                if name:
                    results.append({"function": {"name": name, "arguments": args}})
            except Exception:
                pass
        if results:
            return results

        # 4. Tìm kiếm lệnh gọi dạng CLI (--arg val) hoặc python-call dạng func(arg=val)
        for t_name in self.registry._tools:
            # CLI format: check_and_manage_port --action check --port 8080
            m_cli = re.search(rf"\b{t_name}\b\s+((?:--[a-zA-Z_]+\s+[^\s\n]+(?:\s+)?)+)", text)
            if m_cli:
                raw_args = m_cli.group(1)
                parsed_args = {}
                for k, v in re.findall(r"--([a-zA-Z_]+)\s+([^\s\n]+)", raw_args):
                    parsed_args[k] = int(v) if v.isdigit() else v
                results.append({"function": {"name": t_name, "arguments": parsed_args}})
                return results

            # Python format: check_and_manage_port(port=8080, action='check')
            m_py = re.search(rf"\b{t_name}\b\s*\((.*?)\)", text, re.DOTALL)
            if m_py:
                arg_str = m_py.group(1)
                parsed_args = {}
                for k, v in re.findall(r"([a-zA-Z_]+)\s*=\s*['\"]?([^,'\"\)]+)['\"]?", arg_str):
                    parsed_args[k] = int(v) if v.isdigit() else v.strip()
                results.append({"function": {"name": t_name, "arguments": parsed_args}})
                return results

        # 5. Regex trích xuất dự phòng khi JSON bị lỗi dấu ngoặc kép (vd tool:"name")
        tool_name_match = re.search(r'["\']?(?:tool|name|function|action)["\']?\s*:\s*["\']([a-zA-Z0-9_-]+)["\']', text)
        if tool_name_match:
            t_name = tool_name_match.group(1)
            args = {}
            arg_block = re.search(r'["\']?(?:arguments|parameters)[a-zA-Z]*["\']?\s*:\s*(\{.*?\})', text, re.DOTALL)
            if arg_block:
                try:
                    args = json.loads(arg_block.group(1))
                except Exception:
                    for k, v in re.findall(r'["\']([a-zA-Z0-9_]+)["\']\s*:\s*([^,\}\n]+)', arg_block.group(1)):
                        val = v.strip().strip('"').strip("'")
                        args[k] = int(val) if val.isdigit() else val
            else:
                for k, v in re.findall(r'["\']([a-zA-Z0-9_]+)["\']\s*:\s*([^,\}\n]+)', text):
                    if k not in ["tool", "name", "function", "action"]:
                        val = v.strip().strip('"').strip("'")
                        args[k] = int(val) if val.isdigit() else val

            results.append({"function": {"name": t_name, "arguments": args}})
            return results

        return results

    def _extract_plan_from_llm(self, content: str, tool_calls: list) -> list[str]:
        """Trích xuất danh sách các bước kế hoạch từ phản hồi của LLM (Structured Planner)."""
        plan_steps = []
        if not content and not tool_calls:
            return plan_steps

        # 1. Trích xuất từ plan/steps lồng trong arguments hoặc tool call data
        for call in tool_calls:
            fn = call.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if isinstance(args, dict):
                p = args.get("plan") or args.get("steps")
                if isinstance(p, list) and len(p) > 0:
                    return [str(s).strip() for s in p if str(s).strip()]

        # 2. Thẻ XML <plan> ... </plan>
        plan_tag_match = re.search(r"<plan>(.*?)</plan>", content, re.DOTALL | re.IGNORECASE)
        if plan_tag_match:
            lines = [l.strip() for l in plan_tag_match.group(1).splitlines() if l.strip()]
            cleaned = [re.sub(r"^(?:\d+[\.\)]\s*|-\s*)", "", l).strip() for l in lines]
            return [c for c in cleaned if c]

        # 3. JSON block có chứa trường "plan" hoặc "steps"
        json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        for b in json_blocks:
            try:
                data = json.loads(b.strip())
                p = data.get("plan") or data.get("steps")
                if isinstance(p, list) and len(p) > 0:
                    return [str(s).strip() for s in p if str(s).strip()]
            except Exception:
                pass

        # 4. Numbered list trong suy luận (1. ... 2. ...)
        numbered = re.findall(r"(?:^|\n)\s*(\d+[\.\)]\s*[^\n]+)", content)
        if len(numbered) >= 2:
            cleaned = [re.sub(r"^\d+[\.\)]\s*", "", l).strip() for l in numbered]
            return [c for c in cleaned if c]

        return plan_steps

    def is_complex_request(self, text: str) -> bool:
        """
        Nhận diện xem câu lệnh có phải là tác vụ phức tạp/đa bước cần kích hoạt Agent Loop không:
        - Chứa mệnh đề điều kiện: 'nếu', 'thì', 'xem có ... không', 'nếu lỗi'.
        - Chứa chuỗi hành động tuần tự: 'và sau đó', 'sau đó', 'tiếp theo hãy'.
        - Chứa các yêu cầu kiểm tra + phân tích: 'kiểm tra ... và báo', 'build ... tìm nguyên nhân', 'tại sao lại lỗi'.
        """
        t = text.lower().strip().rstrip(".!?")

        # Bỏ qua các lệnh điều khiển media ngắn gọn (tránh nhầm "bài tiếp theo", "bài sau" thành lệnh đa bước)
        if re.search(r"\b(?:bài|nhạc|trang)\s+(?:tiếp(?:\s*theo)?|trước|sau)\b", t) or \
           re.search(r"\b(?:bye|bai|bay|chuyển)\s*,?\s*tiếp\s*(?:theo)?\b", t):
            return False

        # Nếu câu quá ngắn (<= 3 từ): không thể là tác vụ đa bước
        words = t.split()
        if len(words) <= 3:
            return False

        # Từ khóa điều kiện và rẽ nhánh đa bước
        conditional_keywords = [
            "và sau đó", "sau đó", "tiếp theo hãy", "tiếp theo làm", "tiếp theo thì",
            "tìm nguyên nhân", "sửa lỗi", "xem có lỗi không", "nếu lỗi",
            "nếu không", "kiểm tra và", "kiểm tra xem"
        ]
        if any(k in t for k in conditional_keywords):
            return True

        # Điều kiện 'nếu... thì...'
        if "nếu " in t and " thì " in t:
            return True

        # Đếm số lượng động từ hành động chính trong câu
        action_verbs = [
            "mở", "bật", "chạy", "tắt", "đóng", "kiểm tra", "xem", "build",
            "compile", "tìm", "lấy", "tải", "giải phóng", "kill", "commit", "push"
        ]
        matched_actions = sum(1 for v in action_verbs if re.search(rf"\b{v}\b", t))
        if matched_actions >= 3:
            return True

        return False

    def run_agent_loop(self, prompt: str, voice: str = DEFAULT_VOICE, max_steps: int = 8, budget: Optional[AgentBudget] = None, force_deep: bool = False) -> str:
        """
        Thực thi vòng lặp Agent ReAct: Plan -> Act -> Observe -> Reflect.
        Tự động điều phối công cụ, quản lý Budget, phát hiện Stall (lặp vô tận) và lưu Trace.
        """
        print(f"\n🧠 [Agent Core] Kích hoạt Bộ não điều phối cho tác vụ: '{prompt}' (Deep: {force_deep})")
        set_assistant_state("thinking", "Đang lập kế hoạch tác vụ...")

        # Chọn model phù hợp cho tác vụ:
        target_model, role_name, _ = route_task(prompt, force_deep=force_deep)
        active_model = target_model if force_deep else MODEL_ROLES.get("fast", target_model)

        print(f"🎯 [Agent Core] Sử dụng mô hình: {active_model} ({role_name})")

        # Khởi tạo Structured Agent State & Budget
        actual_budget = budget or AgentBudget(max_steps=max_steps)
        if "qwen3" in active_model.lower():
            actual_budget.max_runtime_sec = max(actual_budget.max_runtime_sec, 90.0)
        state = StructuredAgentState(goal=prompt, model=active_model, budget=actual_budget)

        schemas = self.registry.get_relevant_schemas(prompt)
        tools_desc = ""
        for s in schemas:
            fn = s["function"]
            params = ", ".join(list(fn["parameters"]["properties"].keys()))
            tools_desc += f"- {fn['name']}({params}): {fn['description']}\n"

        print(f"🛠️ [Agent Core] Nạp {len(schemas)} công cụ phù hợp với tác vụ: {[s['function']['name'] for s in schemas]}")

        dynamic_system_prompt = f"""{AGENT_SYSTEM_PROMPT}

CÁC CÔNG CỤ KHẢ DỤNG CHO TÁC VỤ NÀY:
{tools_desc}
VÍ DỤ GỌI CÔNG CỤ:
```json
{{"tool": "run_terminal_command", "arguments": {{"command": "git status"}}}}
```
"""

        messages = [
            {"role": "system", "content": dynamic_system_prompt},
            {"role": "user", "content": prompt}
        ]

        step = 0
        final_answer = ""
        retry_controller.reset()

        while step < actual_budget.max_steps:
            # Kiểm tra Agent Budget (timeout, steps, tool calls)
            is_budget_exceeded, reason = state.check_budget_exceeded()
            if is_budget_exceeded:
                print(f"⚠️ [Agent Core] {reason}. Dừng vòng lặp an toàn.")
                state.final_status = "budget_exceeded"
                state.errors.append(reason)
                break

            step += 1
            print(f"\n🔄 [Agent Loop - Bước {step}/{actual_budget.max_steps}] Đang suy luận bước đi tiếp theo...")

            # Hard Deadline Cascade: Tính toán thời gian timeout thực tế còn lại cho LLM
            elapsed_sec = time.time() - state.start_time
            remaining_time = max(3.0, actual_budget.max_runtime_sec - elapsed_sec)
            llm_timeout = min(remaining_time, 90.0 if "qwen3" in active_model.lower() else 60.0)

            payload = {
                "model": active_model,
                "messages": messages,
                "tools": schemas,  # Native Ollama tool calling schemas
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "num_gpu": 99,
                    "num_ctx": 2048,
                }
            }

            try:
                resp = requests.post(OLLAMA_URL, json=payload, timeout=llm_timeout)
                if resp.status_code != 200:
                    err = f"Lỗi gọi Ollama: HTTP {resp.status_code}"
                    print(f"⚠️ {err}")
                    state.errors.append(err)
                    final_answer = "Xin lỗi, tôi gặp trục trặc khi kết nối với bộ não xử lý."
                    state.final_status = "error"
                    break

                res_json = resp.json()
                msg = res_json.get("message", {})
                content = msg.get("content", "").strip()

                # Hybrid Tool Calling Pipeline:
                # 1. Kiểm tra structured tool_calls trả về từ native Ollama API
                native_calls = msg.get("tool_calls")
                if native_calls and isinstance(native_calls, list) and len(native_calls) > 0:
                    tool_calls = native_calls
                else:
                    # 2. Dự phòng: trích xuất tool calls từ nội dung văn bản (Compatibility Parser)
                    tool_calls = self._parse_tool_calls_from_text(content)

                # 1. Nếu mô hình yêu cầu gọi công cụ (ACT)
                if tool_calls:
                    # Trích xuất và cập nhật kế hoạch từ LLM nếu chưa có (Structured Planner)
                    if not state.plan:
                        extracted_plan = self._extract_plan_from_llm(content, tool_calls)
                        if extracted_plan:
                            state.set_plan(extracted_plan)
                            print(f"🗺️ [Structured Planner] Đã thiết lập kế hoạch {len(extracted_plan)} bước:")
                            for p_i, p_s in enumerate(extracted_plan, 1):
                                print(f"    {p_i}. {p_s}")

                    # Lưu assistant message vào lịch sử hội thoại (giữ tool_calls nếu có)
                    if native_calls and len(native_calls) > 0:
                        messages.append({"role": "assistant", "content": content, "tool_calls": native_calls})
                    else:
                        messages.append({"role": "assistant", "content": content})

                    # Trích xuất phần giải thích / suy luận của mô hình trước khi gọi tool
                    decision_thought = ""
                    if content:
                        clean_thought = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
                        clean_thought = re.sub(r"<tool_call>.*?</tool_call>", "", clean_thought, flags=re.DOTALL).strip()
                        if clean_thought:
                            decision_thought = clean_thought[:120] + "..." if len(clean_thought) > 120 else clean_thought

                    stalled = False
                    for call in tool_calls:
                        fn = call.get("function", {})
                        t_name = fn.get("name", "")
                        t_args = fn.get("arguments", {})
                        if isinstance(t_args, str):
                            try:
                                t_args = json.loads(t_args)
                            except Exception:
                                t_args = {}

                        # Mở bọc nếu arguments bị lồng dạng {"arguments": {...}}
                        if isinstance(t_args, dict) and "arguments" in t_args and isinstance(t_args["arguments"], dict):
                            t_args = t_args["arguments"]

                        # Stall Detection: Chống lặp vô tận cùng 1 tool call
                        if state.is_stalled(t_name, t_args):
                            print(f"🛑 [Stall Detection] Phát hiện gọi lặp công cụ '{t_name}' liên tiếp. Tự động ngắt vòng lặp.")
                            state.final_status = "stalled"
                            state.errors.append(f"Stall detected on tool '{t_name}'")
                            final_answer = f"Tôi nhận thấy việc gọi công cụ {t_name} đang bị lặp lại mà không có kết quả mới. Tôi tạm dừng để bạn kiểm tra lại nhé."
                            stalled = True
                            break

                        print(f"🔧 [Act] Gọi công cụ: {t_name}({t_args})")
                        set_assistant_state("thinking", f"Đang thực hiện: {t_name}...")

                        # Thực thi công cụ qua ToolRegistry (có phân tầng Permission & Validator)
                        t_start = time.time()
                        exec_result = self.registry.execute(t_name, t_args)
                        t_dur = (time.time() - t_start) * 1000

                        # Ghi nhận trạng thái thị giác vào State nếu là vision tool (Visual State V2.3)
                        if t_name in ["see_screen", "capture_screen", "analyze_image", "watch_camera"]:
                            state.record_visual_observation(exec_result)

                        # Đánh giá hoàn thành mục tiêu & phân tích lỗi qua TaskCompletionEvaluator
                        eval_res = task_evaluator.evaluate_step(
                            goal=prompt,
                            tool_name=t_name,
                            args=t_args,
                            observation=exec_result,
                            step_index=state.current_step + 1,
                            max_steps=actual_budget.max_steps
                        )

                        is_retry_step = False
                        if eval_res.should_retry:
                            can_retry, retry_reason = retry_controller.can_retry(t_name, str(exec_result.get("error", "")))
                            if can_retry:
                                retry_controller.record_retry(t_name)
                                state.record_retry(t_name, eval_res.reason)
                                is_retry_step = True
                            else:
                                print(f"⚠️ [Retry Controller] {retry_reason}")
                                state.errors.append(retry_reason)

                        # Ghi nhận vào StructuredAgentState
                        state.add_step(
                            tool_name=t_name,
                            arguments=t_args,
                            observation=exec_result,
                            model_decision=decision_thought,
                            duration_ms=t_dur,
                            status="success" if exec_result.get("success") else "failed",
                            error=exec_result.get("error") if not exec_result.get("success") else None,
                            is_retry=is_retry_step
                        )

                        obs_str = json.dumps(exec_result, ensure_ascii=False)
                        obs_preview = obs_str[:160] + "..." if len(obs_str) > 160 else obs_str
                        print(f"👁️ [Observe] Kết quả ({t_dur:.1f}ms): {obs_preview}")

                        # Gửi phản hồi quan sát (OBSERVE) cùng gợi ý điều phối (nếu có)
                        obs_feedback = f"[Kết quả quan sát công cụ {t_name}]: {obs_str}"
                        if eval_res.suggested_feedback:
                            obs_feedback += f"\n[Gợi ý điều phối]: {eval_res.suggested_feedback}"

                        # Gợi ý công cụ thay thế nếu có lỗi từ RetryController
                        alt_tool = retry_controller.get_alternative_suggestion(t_name)
                        if not exec_result.get("success") and alt_tool:
                            obs_feedback += f"\n[Công cụ thay thế đề xuất]: Bạn có thể cân nhắc dùng '{alt_tool}'."

                        # Gửi kết quả tool quan sát với vai trò 'tool' chuẩn API function calling
                        messages.append({
                            "role": "tool",
                            "name": t_name,
                            "content": obs_feedback
                        })

                        # Nếu mục tiêu điều kiện đã thỏa mãn hoàn toàn
                        if eval_res.is_goal_met and not eval_res.should_continue:
                            print(f"🎯 [Evaluator] Mục tiêu đã được thỏa mãn: {eval_res.reason}")
                            break

                    if stalled:
                        break
                    continue

                # 2. Nếu mô hình đã hoàn thành và trả lời bằng ngôn ngữ tự nhiên (REFLECT / DONE)
                if content:
                    print(f"💡 [Reflect / Hoàn thành] {content}")
                    final_answer = sanitize_text_for_voice(content)
                    state.final_status = "success"
                    break

            except Exception as e:
                err_msg = f"Ngoại lệ trong vòng lặp: {e}"
                print(f"❌ [Agent Core] {err_msg}")
                state.errors.append(err_msg)
                state.final_status = "error"
                final_answer = f"Đã xảy ra sự cố khi điều phối tác vụ: {e}"
                break

        # Nếu đạt giới hạn mà chưa có câu trả lời cuối cùng, yêu cầu LLM tóm tắt lại toàn bộ quan sát
        if not final_answer:
            print("\n⏳ [Agent Core] Đang tổng hợp kết quả cuối cùng từ các quan sát...")
            set_assistant_state("thinking", "Đang tổng hợp kết quả...")
            messages.append({
                "role": "user",
                "content": "Hãy tóm tắt ngắn gọn kết quả của toàn bộ các bước vừa thực hiện trong 1 đến 2 câu tiếng Việt để nói cho tôi biết."
            })
            try:
                elapsed_sec = time.time() - state.start_time
                remaining_time = max(3.0, actual_budget.max_runtime_sec - elapsed_sec)
                final_timeout = min(remaining_time, 30.0)

                final_req = requests.post(
                    OLLAMA_URL,
                    json={
                        "model": MODEL_ROLES["coder"] if "code" in prompt.lower() or "build" in prompt.lower() else MODEL_ROLES["fast"],
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 100,
                            "num_gpu": 99,
                            "num_ctx": 2048,
                        }
                    },
                    timeout=final_timeout
                )
                if final_req.status_code == 200:
                    ans = final_req.json().get("message", {}).get("content", "").strip()
                    final_answer = sanitize_text_for_voice(ans)
            except Exception:
                final_answer = "Tôi đã hoàn tất kiểm tra và xử lý các bước cho bạn rồi nhé."

        if not final_answer:
            final_answer = "Tôi đã hoàn thành toàn bộ tác vụ cho bạn rồi nhé."

        # Lưu Execution Trace ra file JSON
        if state.final_status == "in_progress":
            state.final_status = "success"
        trace_file = state.complete(final_response=final_answer, status=state.final_status)
        if trace_file:
            print(f"📊 [Agent Trace] Đã lưu execution trace: {trace_file}")

        # In cây vết thực thi Agent Trace trực quan ra terminal
        print("\n" + "=" * 60)
        print(state.render_tree())
        print("=" * 60 + "\n")

        # Hiển thị lên Quickshell Overlay và phát ra loa
        is_action = any(final_answer.strip().lower().startswith(p) for p in ["đã mở", "đã đóng", "đã tắt", "đã bật", "đã đặt"])
        is_long = (len(final_answer) > 100 or "\n" in final_answer) and not is_action
        set_assistant_state("speaking", text=final_answer, query=prompt, is_long_text=is_long, long_answer=final_answer if is_long else "")
        speak(final_answer, voice=voice)
        set_assistant_state("idle")
        return final_answer

# Instance đơn lẻ toàn cục
agent_orchestrator = AgentOrchestrator()
