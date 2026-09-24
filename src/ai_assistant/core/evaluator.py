"""
Task Completion Evaluator & Retry/Abort Decision Engine (V2.2).
Đánh giá mức độ hoàn thành mục tiêu, phát hiện điều kiện rẽ nhánh và hướng dẫn Agent tự sửa lỗi.
"""

from typing import Optional, Tuple
from dataclasses import dataclass

@dataclass
class EvaluationResult:
    is_goal_met: bool
    should_continue: bool
    should_retry: bool
    reason: str
    suggested_feedback: Optional[str] = None

class TaskCompletionEvaluator:
    """
    Đánh giá kết quả của chu trình ReAct theo mục tiêu người dùng:
    - Nhận biết nhánh điều kiện ('nếu lỗi thì...', 'nếu thành công thì...')
    - Phát hiện lỗi công cụ có thể tự sửa (recoverable error) để kích hoạt retry
    - Quyết định khi nào nên kết thúc hoặc chuyển hướng điều tra
    """

    @staticmethod
    def evaluate_step(goal: str, tool_name: str, args: dict, observation: dict, step_index: int, max_steps: int) -> EvaluationResult:
        g_lower = goal.lower()
        success = observation.get("success", False)

        # 1. Trường hợp công cụ thất bại (lỗi phân quyền hoặc lỗi cú pháp)
        if not success:
            err = str(observation.get("error") or observation.get("stderr") or "Thất bại không rõ nguyên nhân")

            # Nếu bị Permission Policy từ chối
            if "CHÍNH SÁCH BẢO MẬT" in err or "Từ chối quyền" in err:
                return EvaluationResult(
                    is_goal_met=False,
                    should_continue=False,
                    should_retry=False,
                    reason="Hành động bị chính sách bảo mật hệ thống từ chối.",
                    suggested_feedback=f"Công cụ '{tool_name}' bị chặn vì lý do bảo mật: {err}. Hãy giải thích điều này cho người dùng và dừng lại."
                )

            # Nếu lỗi tham số có thể thử lại
            if "tham số" in err.lower() or "not found" in err.lower():
                return EvaluationResult(
                    is_goal_met=False,
                    should_continue=True,
                    should_retry=True,
                    reason=f"Công cụ '{tool_name}' gặp lỗi tham số hoặc tài nguyên: {err}",
                    suggested_feedback=f"Công cụ '{tool_name}' gặp lỗi: {err}. Hãy thử điều chỉnh lại tham số hoặc dùng công cụ thay thế."
                )

            # Lỗi trong lệnh build / compile / test (ví dụ Spring Boot, maven, gradle, cargo)
            if any(k in g_lower for k in ["build", "compile", "chạy thử", "test"]):
                # Người dùng có yêu cầu: "nếu build lỗi thì tìm nguyên nhân"
                if any(cond in g_lower for cond in ["nếu lỗi", "tìm nguyên nhân", "sửa lỗi", "báo lỗi"]):
                    return EvaluationResult(
                        is_goal_met=False,
                        should_continue=True,
                        should_retry=False,
                        reason="Build thất bại. Cần kích hoạt bước tìm nguyên nhân theo yêu cầu.",
                        suggested_feedback=f"Lệnh build thất bại với stderr: {err[:200]}. Hãy phân tích log hoặc đọc file lỗi để tìm nguyên nhân."
                    )

        # 2. Trường hợp công cụ thành công
        # Nếu mục tiêu là kiểm tra build và build đã thành công (không có lỗi)
        if any(k in g_lower for k in ["build", "compile"]) and ("nếu" in g_lower and "lỗi" in g_lower):
            cmd = str(args.get("command", "")).lower()
            if any(b in cmd for b in ["mvn", "gradle", "cargo", "npm run build", "make", "javac"]):
                return EvaluationResult(
                    is_goal_met=True,
                    should_continue=False,
                    should_retry=False,
                    reason="Build thành công, không phát sinh lỗi.",
                    suggested_feedback="Build hoàn toàn thành công, không có lỗi nào phát sinh."
                )

        # 3. Đạt giới hạn bước
        if step_index >= max_steps:
            return EvaluationResult(
                is_goal_met=False,
                should_continue=False,
                should_retry=False,
                reason="Đã đạt số bước tối đa cho phép.",
                suggested_feedback="Đã đạt giới hạn bước. Hãy tóm tắt lại kết quả hiện có."
            )

        # Mặc định tiếp tục chu trình suy luận
        return EvaluationResult(
            is_goal_met=False,
            should_continue=True,
            should_retry=False,
            reason="Bước hoàn thành bình thường, tiếp tục suy luận.",
            suggested_feedback=None
        )

# Instance toàn cục
task_evaluator = TaskCompletionEvaluator()
