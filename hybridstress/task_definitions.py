"""
HybridStress Task Definitions
==============================

20 audited tasks for the HybridStress benchmark.
Selection criteria:
- Switch frequency >= 3 per episode
- Deterministic replay capability
- Coverage of diverse app categories

Tasks are organized by app category and include structured postconditions
that can be verified by deterministic validators (ADB, UI XML, OCR).
"""

from __future__ import annotations

from typing import Dict, List

from .data_types import Predicate


# ---------------------------------------------------------------------------
# Task definition schema
# ---------------------------------------------------------------------------

def _task(
    task_id: str,
    app: str,
    category: str,
    description: str,
    instruction: str,
    postconditions: List[Predicate],
    expected_switches: int = 3,
    target_package: str = "",
) -> Dict:
    return {
        "task_id": task_id,
        "app": app,
        "category": category,
        "description": description,
        "instruction": instruction,
        "postconditions": postconditions,
        "expected_switches": expected_switches,
        "target_package": target_package,
    }


# ---------------------------------------------------------------------------
# 20 benchmark tasks (grouped by category)
# ---------------------------------------------------------------------------

BENCHMARK_TASKS: List[Dict] = [
    # ── Messaging (3 tasks) ──────────────────────────────────────────────
    _task(
        task_id="msg_send_001",
        app="messaging",
        category="messaging",
        description="Send text message via API, verify delivery in GUI",
        instruction="打开短信应用，发送一条测试短信给联系人Test，内容为'HybridStress测试消息'",
        postconditions=[
            Predicate("conversation", "contains", "HybridStress测试消息"),
            Predicate("notification_bar", "shows", "消息已发送"),
        ],
        expected_switches=3,
        target_package="com.android.messaging",
    ),
    _task(
        task_id="msg_read_002",
        app="messaging",
        category="messaging",
        description="Read unread messages via API, confirm read status in GUI",
        instruction="打开短信应用，查看未读消息并标记为已读",
        postconditions=[
            Predicate("message_status", "is", "read"),
            Predicate("unread_count", "value_is", "0"),
        ],
        expected_switches=3,
        target_package="com.android.messaging",
    ),
    _task(
        task_id="msg_delete_003",
        app="messaging",
        category="messaging",
        description="Delete a conversation via API, verify removal in GUI",
        instruction="打开短信应用，删除与Test的对话",
        postconditions=[
            Predicate("conversation_list", "not_contains", "Test"),
            Predicate("current_screen", "is", "conversations_main"),
        ],
        expected_switches=4,
        target_package="com.android.messaging",
    ),

    # ── Settings (3 tasks) ───────────────────────────────────────────────
    _task(
        task_id="set_wifi_004",
        app="settings",
        category="settings",
        description="Toggle WiFi via API, verify status in Settings GUI",
        instruction="打开设置，切换WiFi开关状态",
        postconditions=[
            Predicate("wifi_status", "is", "enabled"),
            Predicate("current_screen", "is", "wifi_settings"),
        ],
        expected_switches=3,
        target_package="com.android.settings",
    ),
    _task(
        task_id="set_bright_005",
        app="settings",
        category="settings",
        description="Set screen brightness via API, verify slider in GUI",
        instruction="打开设置，将屏幕亮度调到最大",
        postconditions=[
            Predicate("brightness", "value_is", "255"),
            Predicate("current_screen", "is", "display_settings"),
        ],
        expected_switches=3,
        target_package="com.android.settings",
    ),
    _task(
        task_id="set_bluetooth_006",
        app="settings",
        category="settings",
        description="Toggle Bluetooth via API, verify in GUI",
        instruction="打开设置，开启蓝牙并查看可用设备",
        postconditions=[
            Predicate("bluetooth_status", "is", "enabled"),
            Predicate("current_screen", "is", "bluetooth_settings"),
        ],
        expected_switches=3,
        target_package="com.android.settings",
    ),

    # ── Contacts (3 tasks) ───────────────────────────────────────────────
    _task(
        task_id="con_add_007",
        app="contacts",
        category="contacts",
        description="Add contact via API, verify in contacts list GUI",
        instruction="添加一个新联系人：姓名为TestUser，电话为13800138000",
        postconditions=[
            Predicate("contacts_list", "contains", "TestUser"),
            Predicate("contact_phone", "value_is", "13800138000"),
        ],
        expected_switches=4,
        target_package="com.android.contacts",
    ),
    _task(
        task_id="con_edit_008",
        app="contacts",
        category="contacts",
        description="Edit contact via API, verify changes in GUI",
        instruction="编辑联系人TestUser，将电话改为13900139000",
        postconditions=[
            Predicate("contact_phone", "value_is", "13900139000"),
            Predicate("current_screen", "is", "contact_detail"),
        ],
        expected_switches=3,
        target_package="com.android.contacts",
    ),
    _task(
        task_id="con_search_009",
        app="contacts",
        category="contacts",
        description="Search contacts via API, verify results in GUI",
        instruction="在联系人中搜索TestUser",
        postconditions=[
            Predicate("search_results", "contains", "TestUser"),
            Predicate("current_screen", "is", "contacts_search"),
        ],
        expected_switches=3,
        target_package="com.android.contacts",
    ),

    # ── Calendar (2 tasks) ───────────────────────────────────────────────
    _task(
        task_id="cal_create_010",
        app="calendar",
        category="calendar",
        description="Create calendar event via API, verify in calendar GUI",
        instruction="创建一个日历事件：标题为TeamMeeting，时间为明天上午10点",
        postconditions=[
            Predicate("calendar_event", "contains", "TeamMeeting"),
            Predicate("event_time", "value_is", "10:00"),
        ],
        expected_switches=4,
        target_package="com.android.calendar",
    ),
    _task(
        task_id="cal_delete_011",
        app="calendar",
        category="calendar",
        description="Delete calendar event via API, verify removal in GUI",
        instruction="删除日历中的TeamMeeting事件",
        postconditions=[
            Predicate("calendar_view", "is", "day_view"),
            Predicate("current_screen", "is", "calendar_main"),
        ],
        expected_switches=3,
        target_package="com.android.calendar",
    ),

    # ── File Manager (2 tasks) ───────────────────────────────────────────
    _task(
        task_id="file_create_012",
        app="files",
        category="file_management",
        description="Create folder via API, verify in file browser GUI",
        instruction="在文件管理器中创建一个名为HybridTest的文件夹",
        postconditions=[
            Predicate("file_list", "contains", "HybridTest"),
            Predicate("current_screen", "is", "file_browser"),
        ],
        expected_switches=3,
        target_package="com.android.documentsui",
    ),
    _task(
        task_id="file_rename_013",
        app="files",
        category="file_management",
        description="Rename folder via API, verify in file browser GUI",
        instruction="将HybridTest文件夹重命名为HybridTestRenamed",
        postconditions=[
            Predicate("file_list", "contains", "HybridTestRenamed"),
            Predicate("current_screen", "is", "file_browser"),
        ],
        expected_switches=3,
        target_package="com.android.documentsui",
    ),

    # ── Clock / Alarm (2 tasks) ──────────────────────────────────────────
    _task(
        task_id="alarm_set_014",
        app="clock",
        category="clock",
        description="Set alarm via API, verify in alarm list GUI",
        instruction="设置一个早上7:30的闹钟",
        postconditions=[
            Predicate("alarm_list", "contains", "7:30"),
            Predicate("alarm_status", "is", "enabled"),
        ],
        expected_switches=3,
        target_package="com.android.deskclock",
    ),
    _task(
        task_id="alarm_delete_015",
        app="clock",
        category="clock",
        description="Delete alarm via API, verify removal in GUI",
        instruction="删除7:30的闹钟",
        postconditions=[
            Predicate("current_screen", "is", "alarm_list"),
        ],
        expected_switches=3,
        target_package="com.android.deskclock",
    ),

    # ── Notes / Memo (2 tasks) ───────────────────────────────────────────
    _task(
        task_id="note_create_016",
        app="notes",
        category="notes",
        description="Create note via API, verify in notes list GUI",
        instruction="创建一个备忘录，标题为ExperimentLog，内容为'实验记录开始'",
        postconditions=[
            Predicate("notes_list", "contains", "ExperimentLog"),
            Predicate("note_content", "contains", "实验记录开始"),
        ],
        expected_switches=4,
        target_package="com.android.notes",
    ),
    _task(
        task_id="note_edit_017",
        app="notes",
        category="notes",
        description="Edit note via API, verify changes in GUI",
        instruction="编辑备忘录ExperimentLog，添加内容'第二阶段完成'",
        postconditions=[
            Predicate("note_content", "contains", "第二阶段完成"),
            Predicate("current_screen", "is", "note_editor"),
        ],
        expected_switches=3,
        target_package="com.android.notes",
    ),

    # ── Gallery / Media (2 tasks) ────────────────────────────────────────
    _task(
        task_id="gallery_view_018",
        app="gallery",
        category="media",
        description="Open gallery via API, verify image display in GUI",
        instruction="打开相册，查看最近的照片",
        postconditions=[
            Predicate("current_screen", "is", "gallery_grid"),
            Predicate("image_count", "value_is", "positive"),
        ],
        expected_switches=3,
        target_package="com.android.gallery3d",
    ),
    _task(
        task_id="gallery_share_019",
        app="gallery",
        category="media",
        description="Share image via API, verify share sheet in GUI",
        instruction="选择一张照片并分享",
        postconditions=[
            Predicate("current_screen", "is", "share_sheet"),
        ],
        expected_switches=4,
        target_package="com.android.gallery3d",
    ),

    # ── Phone / Dialer (1 task) ──────────────────────────────────────────
    _task(
        task_id="phone_call_020",
        app="phone",
        category="phone",
        description="Initiate call via API, verify call screen in GUI",
        instruction="拨打电话给TestUser",
        postconditions=[
            Predicate("call_status", "is", "dialing"),
            Predicate("current_screen", "is", "call_screen"),
        ],
        expected_switches=3,
        target_package="com.android.dialer",
    ),
]

# Quick lookup
TASK_BY_ID = {t["task_id"]: t for t in BENCHMARK_TASKS}

# 3 pilot tasks for M0 sanity check
PILOT_TASK_IDS = ["msg_send_001", "set_wifi_004", "con_add_007"]
PILOT_TASKS = [TASK_BY_ID[tid] for tid in PILOT_TASK_IDS]

# Category grouping
TASK_CATEGORIES = {}
for t in BENCHMARK_TASKS:
    TASK_CATEGORIES.setdefault(t["category"], []).append(t["task_id"])

# Held-out apps for natural trace collection (M3)
HELD_OUT_APPS = [
    "com.android.calculator2",
    "com.android.browser",
    "com.android.email",
    "com.android.music",
    "com.android.camera",
    "com.android.vending",  # Play Store
    "com.android.maps",
    "com.android.chrome",
    "com.android.youtube",
    "com.android.keep",
]
