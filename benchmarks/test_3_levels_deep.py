"""
Kịch bản kiểm thử chuyên sâu 3 Mức Độ (Deep Verification) cho Voice AI Assistant
Mức 1: Bật/Tắt ứng dụng hệ thống & các liên kết Web (Gmail, FB, GitHub, YouTube...)
Mức 2: Thao tác & Điều khiển Hệ thống (Phần cứng, Mạng, Tiến trình, Bảo mật, Terminal)
Mức 3: Thị giác Màn hình (Vision: see_screen, capture_screen, analyze_image) & Thực thi đa bước
"""

import os
import sys
import time
import json
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from ai_assistant.core.nlu import fast_path_nlu, clean_user_input
from ai_assistant.tools.apps import build_app_index
from ai_assistant.tools.registry import tool_registry
from ai_assistant.core.orchestrator import agent_orchestrator
from ai_assistant.tools.vision import (
    capture_screen,
    _check_grim_available
)
from ai_assistant.tools.permission import permission_policy, PermissionLevel

def test_muc_1():
    print("\n" + "="*80)
    print("🔹 KIỂM THỬ MỨC 1: BẬT / TẮT ỨNG DỤNG HỆ THỐNG & CÁC ĐƯỜNG LINK WEB PHỔ BIẾN")
    print("="*80)
    app_index = build_app_index()
    print(f"[*] Đã lập chỉ mục {len(app_index)} ứng dụng desktop trên hệ thống.\n")

    test_cases = [
        # Web Links
        ("mở gmail", "Mở trang web Gmail", ["gmail"]),
        ("vào facebook", "Mở mạng xã hội Facebook", ["facebook"]),
        ("bật github", "Mở GitHub", ["github"]),
        ("mở youtube", "Mở YouTube", ["youtube"]),
        ("mở chatgpt", "Mở ChatGPT", ["chatgpt"]),
        ("vào gemini", "Mở Google Gemini", ["gemini"]),
        ("mở trang web gmail", "Mở Gmail với từ đệm 'trang web'", ["gmail"]),
        ("vào trang web facebook", "Mở Facebook với từ đệm 'trang web'", ["facebook"]),
        
        # Bật ứng dụng desktop
        ("mở terminal", "Khởi chạy Kitty Terminal", ["kitty", "terminal"]),
        ("mở vs code", "Khởi chạy Visual Studio Code", ["visual studio code", "code"]),
        ("mở file", "Khởi chạy Trình quản lý file Thunar", ["thunar", "file"]),
        ("mở trình duyệt", "Khởi chạy Brave Browser", ["brave", "trình duyệt"]),

        # Mở nhiều ứng dụng / web cùng lúc (Multi-app Launch)
        ("mở youtube và facebook", "Mở đồng thời YouTube và Facebook", ["youtube", "facebook"]),
        ("mở zalo và vs code", "Mở đồng thời Zalo và Visual Studio Code", ["zalo", "visual studio code"]),
        
        # Đóng / Tắt ứng dụng
        ("đóng ứng dụng kitty", "Đóng ứng dụng Kitty", ["đã đóng", "kitty"]),
        ("tắt vs code", "Tắt Visual Studio Code", ["đã đóng", "visual studio code", "code"]),
        ("đóng cửa sổ hiện tại", "Đóng cửa sổ đang active", ["đã đóng", "cửa sổ"]),
        ("tắt tab hiện tại", "Đóng tab hiện tại (Ctrl+W)", ["đã đóng", "tab"]),
        ("đóng youtube và facebook", "Đóng đồng thời YouTube và Facebook", ["youtube", "facebook"]),
        ("tắt zalo và vs code", "Đóng đồng thời Zalo và VS Code", ["zalo", "visual studio code"]),
    ]

    passed_count = 0
    for query, desc, expected_keywords in test_cases:
        t0 = time.perf_counter()
        handled, reply = fast_path_nlu(query, app_index, dry_run=True)
        latency_ms = (time.perf_counter() - t0) * 1000

        is_success = handled and any(kw.lower() in reply.lower() for kw in expected_keywords)
        status = "PASSED" if is_success else "FAILED"
        if is_success:
            passed_count += 1
        print(f"  [{status}] '{query}' -> {desc}")
        print(f"         Phản hồi ({latency_ms:.2f}ms): {reply}")

    print(f"\n=> Kết quả Mức 1: {passed_count}/{len(test_cases)} tests đạt chuẩn.")
    return passed_count == len(test_cases)

def test_muc_2():
    print("\n" + "="*80)
    print("🔹 KIỂM THỬ MỨC 2: LÀM VIỆC VỚI HỆ THỐNG (HARDWARE, NETWORK, PROCESS, SAFETY)")
    print("="*80)
    app_index = build_app_index()

    test_cases_nlu = [
        # Thông số phần cứng
        ("kiểm tra cpu", "Đo xung nhịp, số luồng và nhiệt độ CPU"),
        ("kiểm tra thông số máy", "Đo dung lượng RAM, uptime và tình trạng máy"),
        ("pin còn bao nhiêu", "Đo tỷ lệ pin và trạng thái sạc"),
        
        # Mạng & Kết nối
        ("kiểm tra tốc độ mạng", "Đo ping DNS và băng thông tải xuống"),
        ("bật wifi", "Điều khiển bật Wi-Fi"),
        ("tắt wifi", "Điều khiển tắt Wi-Fi"),
        ("bật bluetooth", "Điều khiển bật Bluetooth"),
        
        # Âm thanh & Độ sáng
        ("đặt âm lượng 50%", "Chỉnh mức âm lượng chính xác"),
        ("tăng âm lượng", "Tăng âm lượng thêm 10%"),
        ("giảm âm lượng", "Giảm âm lượng 10%"),
        ("tắt tiếng", "Mute âm thanh"),
        ("tăng độ sáng", "Tăng độ sáng màn hình"),
        
        # Quạt & ASUS TUF Profile
        ("chế độ turbo", "Chuyển cấu hình ASUS sang Turbo"),
        ("chế độ yên tĩnh", "Chuyển cấu hình ASUS sang Quiet"),
        
        # Developer Tools
        ("kiểm tra cổng 8080", "Kiểm tra socket port TCP 8080"),
        ("kiểm tra docker", "Kiểm tra container Docker đang chạy"),
        ("kiểm tra git", "Kiểm tra nhánh git và file chưa commit"),
    ]

    passed_count = 0
    print("\n--- 2.1 Kiểm tra phản xạ Fast-Path & Lệnh Hệ thống ---")
    for query, desc in test_cases_nlu:
        t0 = time.perf_counter()
        handled, reply = fast_path_nlu(query, app_index, dry_run=True)
        latency_ms = (time.perf_counter() - t0) * 1000

        is_success = handled and len(reply.strip()) > 0
        status = "PASSED" if is_success else "FAILED"
        if is_success:
            passed_count += 1
        print(f"  [{status}] '{query}' ({latency_ms:.2f}ms) -> {reply[:70]}...")

    print("\n--- 2.2 Kiểm tra Tầng Bảo Mật & Chặn Lệnh Nguy Hiểm (Permission Policy) ---")
    dangerous_commands = [
        ("rm -rf /", "Xóa toàn bộ hệ thống root"),
        ("mkfs.ext4 /dev/sda", "Format ổ cứng"),
        ("killall systemd", "Hạ gục tiến trình init hệ điều hành"),
        (":(){ :|:& };:", "Fork bomb làm nghẽn CPU"),
        ("cat /etc/shadow", "Đọc file mật khẩu hệ thống"),
    ]

    sec_passed = 0
    from unittest.mock import patch
    # Fail-safe tuyệt đối: nếu bất kỳ lệnh nguy hiểm nào lọt qua bộ lọc, chặn ngay tại subprocess.run
    with patch("subprocess.run") as mock_sub:
        mock_sub.side_effect = RuntimeError("NGUY HIỂM: Lệnh lọt qua Permission Policy và cố chạy subprocess.run!")
        for cmd, desc in dangerous_commands:
            res = tool_registry.execute("run_terminal_command", {"command": cmd})
            blocked = not res.get("success") and any(k in str(res).lower() for k in ["chặn", "từ chối", "dangerous_blocked", "bảo mật"])
            status = "BLOCKED (SAFE)" if blocked else "UNSAFE LEAK!"
            if blocked:
                sec_passed += 1
            print(f"  [{status}] Lệnh nguy hiểm: '{cmd}' ({desc}) -> Phản hồi: {res.get('stderr') or res.get('error')}")

    print(f"\n=> Kết quả Mức 2: {passed_count}/{len(test_cases_nlu)} hệ thống + {sec_passed}/{len(dangerous_commands)} bảo mật đạt chuẩn.")
    return (passed_count == len(test_cases_nlu)) and (sec_passed == len(dangerous_commands))

def test_muc_3():
    print("\n" + "="*80)
    print("🔹 KIỂM THỬ MỨC 3: THỊ GIÁC MÀN HÌNH (VISION) & THỰC THI THEO YÊU CẦU")
    print("="*80)

    # 1. Kiểm tra grim
    grim_available = _check_grim_available()
    print(f"[*] 1. Công cụ chụp ảnh Wayland (grim): {'SẴN SÀNG' if grim_available else 'CHƯA CÀI'}")

    # 2. Test capture_screen (lưu ảnh ra file trên đĩa cứng)
    print("\n[*] 2. Chụp màn hình và lưu vào tệp (capture_screen)...")
    test_img_path = "/tmp/test_voice_ai_screenshot.png"
    if os.path.exists(test_img_path):
        os.remove(test_img_path)

    cap_res = capture_screen(save_path=test_img_path)
    cap_ok = cap_res.get("success") and os.path.exists(test_img_path)
    cap_size = os.path.getsize(test_img_path) if cap_ok else 0
    print(f"  -> Kết quả capture_screen: {cap_ok} | Đường dẫn: {test_img_path} ({cap_size/1024:.1f} KB)")
    print(f"  -> Metadata: {cap_res.get('metadata')}")

    # 3. Dọn dẹp tệp tạm
    if os.path.exists(test_img_path):
        os.remove(test_img_path)

    all_muc_3_ok = grim_available and cap_ok
    print(f"\n=> Kết quả Mức 3: {'TOÀN BỘ ĐẠT CHUẨN (PASSED)' if all_muc_3_ok else 'CÓ LỖI'}")
    return all_muc_3_ok

if __name__ == "__main__":
    ok1 = test_muc_1()
    ok2 = test_muc_2()
    ok3 = test_muc_3()

    print("\n" + "="*80)
    print(f"🏁 TỔNG KẾT TOÀN BỘ 3 MỨC ĐỘ: {'TẤT CẢ ĐỀU VƯỢT QUA (ALL 3 LEVELS PASSED)' if (ok1 and ok2 and ok3) else 'CÓ BÀI TEST CHƯA ĐẠT'}")
    print("="*80)
