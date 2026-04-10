"""
Cockpit IVI Task Definitions
==============================

20 IVI-domain benchmark tasks for the virtual car cockpit.
Organized across 7 subsystems: navigation, media, climate, phone, messages, settings, vehicle.

Each task defines:
- API endpoint sequence (for API-only mode)
- GUI interaction sequence (for GUI-only mode, via Playwright)
- Deterministic postconditions (verifiable via /state API)
"""

from __future__ import annotations

from typing import Dict, List

from hybridstress.data_types import Predicate


def _task(
    task_id: str,
    app: str,
    category: str,
    description: str,
    instruction: str,
    postconditions: List[Predicate],
    api_actions: List[Dict],
    expected_switches: int = 3,
) -> Dict:
    return {
        "task_id": task_id,
        "app": app,
        "category": category,
        "description": description,
        "instruction": instruction,
        "postconditions": postconditions,
        "api_actions": api_actions,
        "expected_switches": expected_switches,
        "target_package": f"cockpit.{app}",
    }


# ---------------------------------------------------------------------------
# 20 IVI Benchmark Tasks
# ---------------------------------------------------------------------------

COCKPIT_TASKS: List[Dict] = [
    # ── Navigation (3 tasks) ────────────────────────────────────────────
    _task(
        task_id="nav_set_dest_001",
        app="navigation",
        category="navigation",
        description="Set navigation destination to airport via API, verify route in GUI",
        instruction="设置导航目的地为机场，查看路线预览",
        postconditions=[
            Predicate("navigation", "contains", "机场"),
            Predicate("current_screen", "is", "navigation_route_preview"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/navigation/set_destination",
             "body": {"name": "机场", "address": "北京首都国际机场T3航站楼"}},
        ],
    ),
    _task(
        task_id="nav_start_002",
        app="navigation",
        category="navigation",
        description="Start navigation to pre-set destination, verify active navigation",
        instruction="设置目的地为公司，开始导航",
        postconditions=[
            Predicate("is_navigating", "value_is", "true"),
            Predicate("current_screen", "is", "navigation_active"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/navigation/set_destination",
             "body": {"name": "公司", "address": "北京市海淀区中关村大街1号"}},
            {"method": "POST", "path": "/api/navigation/start", "body": {}},
        ],
    ),
    _task(
        task_id="nav_stop_003",
        app="navigation",
        category="navigation",
        description="Stop active navigation, verify return to home screen",
        instruction="停止当前导航，返回导航主页",
        postconditions=[
            Predicate("is_navigating", "value_is", "false"),
            Predicate("current_screen", "is", "navigation_home"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/navigation/set_destination",
             "body": {"name": "机场"}},
            {"method": "POST", "path": "/api/navigation/start", "body": {}},
            {"method": "POST", "path": "/api/navigation/stop", "body": {}},
        ],
    ),

    # ── Media (3 tasks) ─────────────────────────────────────────────────
    _task(
        task_id="media_play_004",
        app="media",
        category="media",
        description="Play music from playlist via API, verify playback in GUI",
        instruction="播放音乐，开始播放第一首歌曲",
        postconditions=[
            Predicate("playing", "value_is", "true"),
            Predicate("current_track", "contains", "夜曲"),
            Predicate("current_screen", "is", "media_playing"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/media/play", "body": {}},
        ],
    ),
    _task(
        task_id="media_next_005",
        app="media",
        category="media",
        description="Skip to next track, verify track change in GUI",
        instruction="播放音乐，然后切换到下一首",
        postconditions=[
            Predicate("current_track", "contains", "晴天"),
            Predicate("playing", "value_is", "true"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/media/play", "body": {}},
            {"method": "POST", "path": "/api/media/next", "body": {}},
        ],
    ),
    _task(
        task_id="media_volume_006",
        app="media",
        category="media",
        description="Set volume to maximum via API, verify slider in GUI",
        instruction="将媒体音量调到最大（100）",
        postconditions=[
            Predicate("volume", "value_is", "100"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/media/volume", "body": {"volume": 100}},
        ],
    ),

    # ── Climate (3 tasks) ───────────────────────────────────────────────
    _task(
        task_id="climate_temp_007",
        app="climate",
        category="climate",
        description="Set driver temperature to 20°C, verify in GUI",
        instruction="将驾驶员侧空调温度设置为20度",
        postconditions=[
            Predicate("temperature_driver", "value_is", "20.0"),
            Predicate("current_screen", "is", "climate_home"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/climate/temperature",
             "body": {"zone": "driver", "temperature": 20.0}},
        ],
    ),
    _task(
        task_id="climate_ac_off_008",
        app="climate",
        category="climate",
        description="Toggle AC off, verify status change in GUI",
        instruction="关闭空调",
        postconditions=[
            Predicate("ac_on", "value_is", "false"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/climate/toggle_ac", "body": {}},
        ],
    ),
    _task(
        task_id="climate_seat_heat_009",
        app="climate",
        category="climate",
        description="Turn on driver seat heating to high, verify in GUI",
        instruction="打开驾驶员座椅加热至最高档",
        postconditions=[
            Predicate("seat_heating_driver", "value_is", "3"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/climate/seat_heating",
             "body": {"zone": "driver", "level": 3}},
        ],
    ),

    # ── Phone (3 tasks) ─────────────────────────────────────────────────
    _task(
        task_id="phone_dial_010",
        app="phone",
        category="phone",
        description="Dial a contact by name, verify call screen in GUI",
        instruction="拨打电话给张三",
        postconditions=[
            Predicate("in_call", "value_is", "true"),
            Predicate("call_contact", "contains", "张三"),
            Predicate("current_screen", "is", "phone_calling"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/phone/dial",
             "body": {"contact": "张三"}},
        ],
    ),
    _task(
        task_id="phone_hangup_011",
        app="phone",
        category="phone",
        description="End an active call, verify return to phone home",
        instruction="拨打电话给李四，然后挂断",
        postconditions=[
            Predicate("in_call", "value_is", "false"),
            Predicate("current_screen", "is", "phone_home"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/phone/dial", "body": {"contact": "李四"}},
            {"method": "POST", "path": "/api/phone/hangup", "body": {}},
        ],
    ),
    _task(
        task_id="phone_add_contact_012",
        app="phone",
        category="phone",
        description="Add a new contact, verify in contacts list",
        instruction="添加新联系人：姓名为赵六，电话为13700137000",
        postconditions=[
            Predicate("contacts", "contains", "赵六"),
            Predicate("contacts", "contains", "13700137000"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/phone/contacts/add",
             "body": {"name": "赵六", "number": "13700137000"}},
        ],
    ),

    # ── Messages (3 tasks) ──────────────────────────────────────────────
    _task(
        task_id="msg_send_013",
        app="messages",
        category="messages",
        description="Send a message via API, verify in conversation GUI",
        instruction="发送一条短信给张三，内容为'会议改到下午3点'",
        postconditions=[
            Predicate("conversations", "contains", "会议改到下午3点"),
            Predicate("current_screen", "is", "messages_conversation"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/messages/send",
             "body": {"contact": "张三", "text": "会议改到下午3点"}},
        ],
    ),
    _task(
        task_id="msg_read_014",
        app="messages",
        category="messages",
        description="Read a conversation and mark as read, verify status",
        instruction="打开与张三的对话，标记为已读",
        postconditions=[
            Predicate("message_status", "value_is", "read"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/messages/read",
             "body": {"contact": "张三"}},
        ],
    ),
    _task(
        task_id="msg_delete_015",
        app="messages",
        category="messages",
        description="Delete a conversation, verify removal from list",
        instruction="删除与Test的对话",
        postconditions=[
            Predicate("conversation_list", "not_contains", "Test"),
            Predicate("current_screen", "is", "messages_home"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/messages/delete",
             "body": {"contact": "Test"}},
        ],
    ),

    # ── Settings (3 tasks) ──────────────────────────────────────────────
    _task(
        task_id="set_brightness_016",
        app="settings",
        category="settings",
        description="Set screen brightness to maximum, verify in GUI",
        instruction="将屏幕亮度调到最大（100）",
        postconditions=[
            Predicate("brightness", "value_is", "100"),
            Predicate("current_screen", "is", "settings_display"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/settings/brightness",
             "body": {"brightness": 100}},
        ],
    ),
    _task(
        task_id="set_wifi_017",
        app="settings",
        category="settings",
        description="Toggle WiFi off, verify status in GUI",
        instruction="关闭WiFi",
        postconditions=[
            Predicate("wifi_on", "value_is", "false"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/settings/toggle_wifi", "body": {}},
        ],
    ),
    _task(
        task_id="set_bluetooth_018",
        app="settings",
        category="settings",
        description="Toggle Bluetooth off, verify in GUI and phone status",
        instruction="关闭蓝牙",
        postconditions=[
            Predicate("bluetooth_on", "value_is", "false"),
            Predicate("bluetooth_status", "value_is", "disabled"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/settings/toggle_bluetooth", "body": {}},
        ],
    ),

    # ── Vehicle (2 tasks) ───────────────────────────────────────────────
    _task(
        task_id="veh_sport_mode_019",
        app="vehicle",
        category="vehicle",
        description="Switch to sport drive mode, verify in GUI",
        instruction="切换驾驶模式为运动模式",
        postconditions=[
            Predicate("drive_mode", "value_is", "sport"),
            Predicate("current_screen", "is", "vehicle_drive_mode"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/vehicle/drive_mode",
             "body": {"mode": "sport"}},
        ],
    ),
    _task(
        task_id="veh_unlock_020",
        app="vehicle",
        category="vehicle",
        description="Unlock doors via API, verify in GUI",
        instruction="解锁车门",
        postconditions=[
            Predicate("doors_locked", "value_is", "false"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/vehicle/unlock_doors", "body": {}},
        ],
    ),
]

# Quick lookup
COCKPIT_TASK_BY_ID = {t["task_id"]: t for t in COCKPIT_TASKS}

# Pilot tasks for M0 sanity
COCKPIT_PILOT_IDS = ["nav_set_dest_001", "media_play_004", "msg_send_013"]
COCKPIT_PILOT_TASKS = [COCKPIT_TASK_BY_ID[tid] for tid in COCKPIT_PILOT_IDS]

# Category grouping
COCKPIT_TASK_CATEGORIES = {}
for t in COCKPIT_TASKS:
    COCKPIT_TASK_CATEGORIES.setdefault(t["category"], []).append(t["task_id"])


# ---------------------------------------------------------------------------
# Held-out tasks for M3 (natural trace transfer evaluation)
# These tasks test the same subsystems but with DIFFERENT operations
# not seen during M1 training, providing transfer evaluation data.
# ---------------------------------------------------------------------------

COCKPIT_HELD_OUT_TASKS: List[Dict] = [
    _task(
        task_id="ho_nav_recent_001",
        app="navigation",
        category="navigation",
        description="Navigate to a recent destination from history",
        instruction="从最近目的地列表选择'家'开始导航",
        postconditions=[
            Predicate("destination", "contains", "家"),
            Predicate("is_navigating", "value_is", "true"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/navigation/set_destination",
             "body": {"name": "家", "address": "北京市朝阳区建国路88号"}},
            {"method": "POST", "path": "/api/navigation/start", "body": {}},
        ],
    ),
    _task(
        task_id="ho_media_radio_002",
        app="media",
        category="media",
        description="Switch to FM radio and tune to 103.9",
        instruction="切换到收音机，调至FM 103.9",
        postconditions=[
            Predicate("source", "value_is", "radio"),
            Predicate("radio_frequency", "value_is", "103.9"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/media/radio",
             "body": {"frequency": 103.9}},
        ],
    ),
    _task(
        task_id="ho_climate_dual_003",
        app="climate",
        category="climate",
        description="Set dual-zone temperatures: driver 22, passenger 26",
        instruction="设置双区空调：驾驶员22度，副驾驶26度",
        postconditions=[
            Predicate("temperature_driver", "value_is", "22.0"),
            Predicate("temperature_passenger", "value_is", "26.0"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/climate/temperature",
             "body": {"zone": "driver", "temperature": 22.0}},
            {"method": "POST", "path": "/api/climate/temperature",
             "body": {"zone": "passenger", "temperature": 26.0}},
        ],
    ),
    _task(
        task_id="ho_phone_edit_004",
        app="phone",
        category="phone",
        description="Edit an existing contact's phone number",
        instruction="修改联系人张三的电话为13900139999",
        postconditions=[
            Predicate("contacts", "contains", "13900139999"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/phone/contacts/edit",
             "body": {"name": "张三", "new_number": "13900139999"}},
        ],
    ),
    _task(
        task_id="ho_msg_multi_005",
        app="messages",
        category="messages",
        description="Send messages to two different contacts",
        instruction="分别给李四和王五发消息",
        postconditions=[
            Predicate("conversations", "contains", "李四"),
            Predicate("conversations", "contains", "测试消息"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/messages/send",
             "body": {"contact": "李四", "text": "测试消息一"}},
            {"method": "POST", "path": "/api/messages/send",
             "body": {"contact": "王五", "text": "测试消息二"}},
        ],
    ),
    _task(
        task_id="ho_set_night_006",
        app="settings",
        category="settings",
        description="Switch display to night mode and lower brightness",
        instruction="切换到夜间模式，降低亮度到30",
        postconditions=[
            Predicate("display_mode", "value_is", "night"),
            Predicate("brightness", "value_is", "30"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/settings/display_mode",
             "body": {"mode": "night"}},
            {"method": "POST", "path": "/api/settings/brightness",
             "body": {"brightness": 30}},
        ],
    ),
    _task(
        task_id="ho_veh_eco_007",
        app="vehicle",
        category="vehicle",
        description="Switch to eco mode and turn on headlights",
        instruction="切换ECO模式并开启近光灯",
        postconditions=[
            Predicate("drive_mode", "value_is", "eco"),
            Predicate("headlights", "value_is", "low"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/vehicle/drive_mode",
             "body": {"mode": "eco"}},
            {"method": "POST", "path": "/api/vehicle/headlights",
             "body": {"mode": "low"}},
        ],
    ),
    _task(
        task_id="ho_climate_defrost_008",
        app="climate",
        category="climate",
        description="Turn on rear defrost and set fan to max",
        instruction="开启后挡风除霜，风速调到最大",
        postconditions=[
            Predicate("rear_defrost", "value_is", "true"),
            Predicate("fan_speed", "value_is", "7"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/climate/rear_defrost", "body": {}},
            {"method": "POST", "path": "/api/climate/fan_speed",
             "body": {"speed": 7}},
        ],
    ),
    _task(
        task_id="ho_veh_window_009",
        app="vehicle",
        category="vehicle",
        description="Open driver window halfway and unlock trunk",
        instruction="打开驾驶员车窗到一半，开启后备箱",
        postconditions=[
            Predicate("trunk_open", "value_is", "true"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/vehicle/window",
             "body": {"window": "fl", "position": 50}},
            {"method": "POST", "path": "/api/vehicle/trunk", "body": {}},
        ],
    ),
    _task(
        task_id="ho_media_prev_010",
        app="media",
        category="media",
        description="Play music then skip back to previous track",
        instruction="播放音乐，然后切回上一首",
        postconditions=[
            Predicate("playing", "value_is", "true"),
            Predicate("current_track", "contains", "青花瓷"),
        ],
        api_actions=[
            {"method": "POST", "path": "/api/media/play", "body": {}},
            {"method": "POST", "path": "/api/media/previous", "body": {}},
        ],
    ),
]

COCKPIT_HELD_OUT_BY_ID = {t["task_id"]: t for t in COCKPIT_HELD_OUT_TASKS}
