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


class RetryController:
    """
    Bộ điều khiển thử lại độc lập (Dedicated Retry Controller - V2.3).
    Quản lý chính sách thử lại (Retry Policy), giới hạn số lần retry theo từng công cụ,
    tính toán backoff và đề xuất công cụ thay thế.
    """
    def __init__(self, max_retries_per_tool: int = 2, max_total_retries: int = 4):
        self.max_retries_per_tool = max_retries_per_tool
        self.max_total_retries = max_total_retries
        self.tool_retry_counts: dict[str, int] = {}
        self.total_retries: int = 0

    def reset(self):
        """Khởi tạo lại trạng thái cho phiên làm việc mới."""
        self.tool_retry_counts.clear()
        self.total_retries = 0

    def can_retry(self, tool_name: str, error_message: str = "") -> Tuple[bool, str]:
        """
        Xác định xem công cụ có được phép thử lại không.
        """
        # Kiểm tra nếu lỗi do phân quyền hoặc vi phạm an toàn -> tuyệt đối không retry
        if any(w in error_message for w in ["CHÍNH SÁCH BẢO MẬT", "Từ chối quyền", "bị từ chối", "DANGEROUS_BLOCKED"]):
            return False, "Hành động bị chặn bởi chính sách bảo mật, không cho phép thử lại."

        tool_count = self.tool_retry_counts.get(tool_name, 0)
        if tool_count >= self.max_retries_per_tool:
            return False, f"Công cụ '{tool_name}' đã vượt quá giới hạn thử lại ({tool_count}/{self.max_retries_per_tool})."

        if self.total_retries >= self.max_total_retries:
            return False, f"Đã đạt giới hạn thử lại tổng cộng của phiên ({self.total_retries}/{self.max_total_retries})."

        return True, ""

    def record_retry(self, tool_name: str) -> int:
        """Ghi nhận một lượt thử lại cho công cụ cụ thể."""
        self.tool_retry_counts[tool_name] = self.tool_retry_counts.get(tool_name, 0) + 1
        self.total_retries += 1
        return self.tool_retry_counts[tool_name]

    def get_alternative_suggestion(self, tool_name: str) -> Optional[str]:
        """Gợi ý công cụ thay thế phù hợp khi công cụ hiện tại thất bại nhiều lần."""
        alternatives = {
            "see_screen": "capture_screen hoặc get_hyprland_active_window",
            "check_and_manage_port": "run_terminal_command (fuser / ss / netstat)",
            "find_files_or_projects": "run_terminal_command (find / fd)",
            "launch_application": "run_terminal_command (nohup <app> &)",
            "watch_camera": "see_screen hoặc kiểm tra thiết bị /dev/video0"
        }
        return alternatives.get(tool_name)


# Instance toàn cục RetryController
retry_controller = RetryController()

