"""
Benchmark & Kiểm thử toàn diện 5 bài tests theo 3 mức độ cho Voice AI Assistant.
"""

import os
import sys
import time
import json
import base64
import subprocess
from unittest.mock import patch

# Đảm bảo đường dẫn `src/` trong sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from ai_assistant.core.nlu import fast_path_nlu, clean_user_input
from ai_assistant.tools.apps import build_app_index
from ai_assistant.tools.registry import tool_registry
from ai_assistant.core.orchestrator import agent_orchestrator
from ai_assistant.tools.vision import see_screen, _check_grim_available

def run_test_level_1():
    print("\n" + "="*70)
    print("🚀 BÀI TEST 1 & 2: MỨC 1 - MỞ ỨNG DỤNG HỆ THỐNG & WEB APPS (YouTube, Gmail, Facebook)")
    print("="*70)
    
    app_index = build_app_index()
    print(f"[*] Số ứng dụng desktop được lập chỉ mục: {len(app_index)}")
    
    results = []
    
    # 1. Web Apps
    web_tests = [
        ("mở youtube", "YouTube web", True),
        ("mở gmail", "Gmail web", True),
        ("mở facebook", "Facebook web", True),
        ("mở youtube trên web", "YouTube web với từ đệm", True),
        ("mở facebook trên web", "Facebook web với từ đệm", True),
        ("mở ứng dụng youtube", "YouTube web với từ khóa 'ứng dụng'", True),
    ]
    
    print("\n--- [Bài Test 1] Ứng dụng Web (YouTube, Gmail, Facebook) ---")
    for query, desc, expect in web_tests:
        handled, reply = fast_path_nlu(query, app_index, dry_run=True)
        is_ok = handled and any(w.lower() in reply.lower() for w in ["youtube", "gmail", "facebook"])
        # Kiểm tra xem có bị lỗi 'trên web' làm từ khóa tìm kiếm không
        has_glitch = "trên web" in reply.lower()
        status = "PASSED" if is_ok and not has_glitch else ("WARNING (Lỗi phân tích)" if is_ok and has_glitch else "FAILED")
        print(f"• Query: '{query}' ({desc})")
        print(f"  -> Handled: {handled} | Reply: '{reply}'")
        print(f"  -> Trạng thái: {status}\n")
        results.append({"test": "Test 1 - Web", "query": query, "status": status, "reply": reply})

    # 2. Desktop Apps
    desktop_tests = [
        ("mở terminal", "Terminal (Kitty)"),
        ("mở vs code", "Visual Studio Code"),
        ("mở file", "Quản lý tệp (Thunar)"),
        ("mở spotify", "Spotify Music"),
        ("mở trình duyệt", "Trình duyệt (Brave)"),
    ]
    
    print("\n--- [Bài Test 2] Ứng dụng Desktop Hệ thống ---")
    for query, desc in desktop_tests:
        handled, reply = fast_path_nlu(query, app_index, dry_run=True)
        status = "PASSED" if handled and "đã mở" in reply.lower() else "FAILED"
        print(f"• Query: '{query}' ({desc})")
        print(f"  -> Handled: {handled} | Reply: '{reply}'")
        print(f"  -> Trạng thái: {status}\n")
        results.append({"test": "Test 2 - Desktop", "query": query, "status": status, "reply": reply})

    return results

def run_test_level_2():
    print("\n" + "="*70)
    print("🚀 BÀI TEST 3 & 4: MỨC 2 - KIỂM TRA THÔNG SỐ HỆ THỐNG & CÔNG CỤ DÒNG LỆNH / MẠNG")
    print("="*70)
    
    app_index = build_app_index()
    results = []

    # 3. System Hardware
    hardware_tests = [
        ("kiểm tra thông số máy", "Thông số toàn bộ máy tính (RAM, Uptime)"),
        ("kiểm tra cpu", "Thông số vi xử lý CPU, tải và nhiệt độ"),
        ("pin còn bao nhiêu", "Tình trạng pin và nguồn sạc"),
    ]
    
    print("\n--- [Bài Test 3] Thông số Máy tính & Phần cứng ---")
    for query, desc in hardware_tests:
        t0 = time.time()
        handled, reply = fast_path_nlu(query, app_index, dry_run=False)
        duration = round((time.time() - t0) * 1000, 2)
        status = "PASSED" if handled and len(reply) > 20 else "FAILED"
        print(f"• Query: '{query}' ({desc})")
        print(f"  -> Handled: {handled} | Thời gian: {duration}ms")
        print(f"  -> Dữ liệu thực tế: '{reply}'")
        print(f"  -> Trạng thái: {status}\n")
        results.append({"test": "Test 3 - Hardware", "query": query, "status": status, "reply": reply, "latency_ms": duration})

    # 4. System Dev Tools & Network Speed
    dev_and_net_tests = [
        ("kiểm tra cổng 8080", "Kiểm tra cổng mạng TCP 8080"),
        ("kiểm tra docker", "Kiểm tra danh sách Docker container"),
        ("kiểm tra git", "Kiểm tra git repository status"),
        ("kiểm tra tốc độ mạng", "Đo/Kiểm tra tốc độ mạng Internet"),
        ("đo tốc độ mạng", "Đo băng thông mạng"),
    ]
    
    print("\n--- [Bài Test 4] Lệnh / Công cụ Hệ thống & Mạng ---")
    for query, desc in dev_and_net_tests:
        t0 = time.time()
        handled, reply = fast_path_nlu(query, app_index, dry_run=False)
        is_complex = agent_orchestrator.is_complex_request(query)
        schemas = tool_registry.get_relevant_schemas(query)
        tool_names = [s["function"]["name"] for s in schemas]
        duration = round((time.time() - t0) * 1000, 2)
        
        has_speed_tool = any("network" in tn or "speed" in tn or "ping" in tn for tn in tool_names)
        
        if handled:
            status = "PASSED"
        elif is_complex or has_speed_tool:
            status = "PARTIAL (Cần Agent loop)"
        else:
            status = "FAILED (Chưa hỗ trợ công cụ/intent)"
            
        print(f"• Query: '{query}' ({desc})")
        print(f"  -> Fast-Path: {handled} | Reply: '{reply}'")
        print(f"  -> Is Complex: {is_complex} | Relevant Tools: {tool_names}")
        print(f"  -> Trạng thái: {status}\n")
        results.append({"test": "Test 4 - Tools & Net", "query": query, "status": status, "reply": reply, "is_complex": is_complex})

    return results

def run_test_level_3():
    print("\n" + "="*70)
    print("🚀 BÀI TEST 5: MỨC 3 (CAO NHẤT) - THỊ GIÁC AI (VISION) & QUAN SÁT MÀN HÌNH / ĐỌC CODE")
    print("="*70)
    
    results = []
    
    # 5.1 Kiểm tra công cụ chụp ảnh Wayland (grim)
    grim_ok = _check_grim_available()
    print(f"1. Kiểm tra công cụ grim (Wayland Screen Capture): {'SẴN SÀNG (/usr/bin/grim)' if grim_ok else 'THIẾU'}")
    
    # 5.2 Kiểm tra nhận diện Intent & Tool Selection
    vision_queries = [
        "mô tả màn hình đang có gì",
        "nhìn màn hình kiểm tra code",
        "trên màn hình đang có gì",
    ]
    print("\n2. Kiểm tra nhận diện Intent Vision & Lựa chọn Tool:")
    for q in vision_queries:
        is_complex = agent_orchestrator.is_complex_request(q)
        schemas = tool_registry.get_relevant_schemas(q)
        tool_names = [s["function"]["name"] for s in schemas]
        has_see_screen = "see_screen" in tool_names
        status = "PASSED" if is_complex and has_see_screen else "FAILED"
        print(f"• Query: '{q}' -> Trigger Agent: {is_complex} | Có tool 'see_screen': {has_see_screen} => {status}")
        results.append({"test": "Test 5.1 - Vision Intent", "query": q, "status": status})

    # 5.3 Kiểm tra Chụp màn hình thực tế & Phân tích qua Vision Model
    print("\n3. Kiểm tra Chụp màn hình và Phân tích Vision Model:")
    print("   [*] Đang thử nghiệm công cụ `see_screen` trực tiếp...")
    t0 = time.time()
    try:
        # Chụp màn hình
        res = see_screen(query="Mô tả nội dung trên màn hình")
        duration = round(time.time() - t0, 2)
        print(f"   -> Kết quả see_screen: success={res.get('success')}, error={res.get('error')}")
        print(f"   -> Nội dung trả về: '{res.get('result')}'")
        print(f"   -> Thời gian thực thi: {duration}s")
        print(f"   -> Metadata: {res.get('metadata')}")
        
        if res.get("success") and res.get("result"):
            v_status = "PASSED"
        else:
            v_status = f"FAILED (Mô hình trả về rỗng hoặc lỗi: {res.get('error')})"
    except Exception as e:
        v_status = f"FAILED (Ngoại lệ: {e})"
        duration = 0

    print(f"   => Trạng thái see_screen: {v_status}")
    results.append({"test": "Test 5.2 - See Screen Direct", "status": v_status, "duration_s": duration})

    return results

if __name__ == "__main__":
    r1 = run_test_level_1()
    r2 = run_test_level_2()
    r3 = run_test_level_3()
    print("\n" + "="*70)
    print("✅ HOÀN THÀNH 5 BÀI TESTS CHO CẢ 3 MỨC ĐỘ!")
    print("="*70)
