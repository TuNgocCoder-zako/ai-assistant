"""
Structured Agent State, Execution Trace & Budget Management (V2.1).
Cung cấp mô hình trạng thái tường minh cho Agent Core: Goal, Plan, Steps, Observations, Stall Detection và Trace Logging.
"""

import os
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from ai_assistant.config import BASE_DIR

LOGS_AGENT_DIR = os.path.join(BASE_DIR, "logs", "agent")

@dataclass
class AgentStep:
    step_index: int
    tool_name: str
    arguments: dict
    observation: dict
    start_time: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    status: str = "success"  # success, failed, blocked

@dataclass
class AgentBudget:
    max_steps: int = 8
    max_runtime_sec: float = 60.0
    max_tool_calls: int = 12
    max_consecutive_identical_calls: int = 2  # Ngưỡng kích hoạt Stall Detection

@dataclass
class StructuredAgentState:
    goal: str
    model: str
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    plan: list[str] = field(default_factory=list)
    current_step: int = 0
    steps: list[AgentStep] = field(default_factory=list)
    budget: AgentBudget = field(default_factory=AgentBudget)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    final_status: str = "in_progress"  # in_progress, success, stalled, timeout, max_steps_exceeded, error
    final_response: str = ""
    errors: list[str] = field(default_factory=list)

    def add_step(self, tool_name: str, arguments: dict, observation: dict, duration_ms: float = 0.0, status: str = "success") -> AgentStep:
        """Ghi nhận một bước thực thi công cụ trong hành trình Agent."""
        self.current_step += 1
        step = AgentStep(
            step_index=self.current_step,
            tool_name=tool_name,
            arguments=arguments,
            observation=observation,
            duration_ms=round(duration_ms, 2),
            status=status
        )
        self.steps.append(step)
        return step

    def is_stalled(self, tool_name: str, arguments: dict) -> bool:
        """
        Stall Detection: Kiểm tra xem mô hình có đang bị kẹt lặp lại cùng một công cụ
        với cùng bộ tham số liên tục không.
        """
        threshold = self.budget.max_consecutive_identical_calls
        if len(self.steps) < threshold:
            return False

        # Kiểm tra N bước gần nhất
        recent_steps = self.steps[-threshold:]
        for prev in recent_steps:
            if prev.tool_name != tool_name or prev.arguments != arguments:
                return False
        return True

    def check_budget_exceeded(self) -> tuple[bool, str]:
        """
        Kiểm tra toàn diện các giới hạn tài nguyên của Agent:
        - Số bước (steps)
        - Thời gian thực thi (runtime timeout)
        - Tổng số lần gọi công cụ (tool calls)
        """
        elapsed_sec = time.time() - self.start_time
        if elapsed_sec > self.budget.max_runtime_sec:
            return True, f"Quá thời gian cho phép ({elapsed_sec:.1f}s > {self.budget.max_runtime_sec}s)"

        if self.current_step >= self.budget.max_steps:
            return True, f"Vượt quá số bước tối đa ({self.current_step}/{self.budget.max_steps})"

        if len(self.steps) >= self.budget.max_tool_calls:
            return True, f"Vượt quá giới hạn gọi công cụ ({len(self.steps)}/{self.budget.max_tool_calls})"

        return False, ""

    def complete(self, final_response: str, status: str = "success") -> str:
        """Đánh dấu phiên làm việc của Agent đã kết thúc và lưu Trace file."""
        self.end_time = time.time()
        self.final_response = final_response
        self.final_status = status
        return self.save_trace()

    def to_dict(self) -> dict:
        """Xuất dữ liệu có cấu trúc sang dict."""
        elapsed_ms = round((self.end_time - self.start_time) * 1000, 2) if self.end_time > 0 else round((time.time() - self.start_time) * 1000, 2)
        return {
            "session_id": self.session_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.start_time)),
            "goal": self.goal,
            "model": self.model,
            "duration_ms": elapsed_ms,
            "final_status": self.final_status,
            "plan": self.plan,
            "steps_count": len(self.steps),
            "steps": [asdict(s) for s in self.steps],
            "budget": asdict(self.budget),
            "errors": self.errors,
            "final_response": self.final_response
        }

    def save_trace(self, target_dir: str = LOGS_AGENT_DIR) -> str:
        """Lưu execution trace ra file JSON (ví dụ: logs/agent/2026-09-24_22-01-32_abc123.json)."""
        try:
            os.makedirs(target_dir, exist_ok=True)
            t_str = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(self.start_time))
            file_name = f"{t_str}_{self.session_id}_{self.final_status}.json"
            trace_path = os.path.join(target_dir, file_name)

            with open(trace_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

            return trace_path
        except Exception as e:
            print(f"⚠️ [AgentState] Không thể lưu trace file: {e}")
            return ""
