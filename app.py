#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
500亩农田：土壤墒情监测 + 分区自动灌溉控制平台 (逻辑统一修复版)
Flask + Leaflet (Satellite) + Chart.js + Bootstrap 5
"""

import json
import random
import time
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify, request, Response, stream_with_context

app = Flask(__name__)

# ==================== 配置 ====================
SENSOR_COUNT = 50
VALVE_COUNT = 10
ZONE_COUNT = 10
TELEMETRY_HISTORY_SIZE = 500
FRAME_HISTORY_SIZE = 100

# 中心点坐标（模拟农田位置）
CENTER_LAT = 47.24
CENTER_LNG = 132.52

# ==================== 内存数据结构 ====================
random.seed(42)

# 分区定义
zones = []
for i in range(ZONE_COUNT):
    row = i // 5
    col = i % 5
    base_lat = CENTER_LAT + row * 0.008 - 0.004
    base_lng = CENTER_LNG + col * 0.01 - 0.02
    zones.append({
        "id": f"zone_{i + 1}",
        "name": f"分区{i + 1}",
        "polygon": [
            [base_lat, base_lng],
            [base_lat + 0.007, base_lng],
            [base_lat + 0.007, base_lng + 0.009],
            [base_lat, base_lng + 0.009],
        ],
        "color": f"#{random.randint(50, 200):02x}{random.randint(100, 200):02x}{random.randint(50, 150):02x}",
        "irrigation_active": False
    })

# 传感器数据
sensors = []
for i in range(SENSOR_COUNT):
    zone_idx = i % ZONE_COUNT
    zone = zones[zone_idx]
    poly = zone["polygon"]
    lat = random.uniform(poly[0][0], poly[1][0])
    lng = random.uniform(poly[0][1], poly[2][1])
    sensors.append({
        "id": f"sensor_{i + 1:03d}",
        "name": f"土壤传感器-{i + 1:03d}",
        "zone_id": zone["id"],
        "zone_name": zone["name"],
        "lat": lat,
        "lng": lng,
        "temperature": round(random.uniform(15, 35), 1),
        "humidity": round(random.uniform(20, 80), 1),
        "battery": random.randint(20, 100),
        "rssi": random.randint(-120, -50),
        "snr": round(random.uniform(-5, 15), 1),
        "online": random.random() > 0.05,
        "coverage": random.choice(["LoRa Only", "LoRa Only", "LoRa + Cellular"]),
        "last_report": datetime.now() - timedelta(minutes=random.randint(0, 30)),
        "report_interval": "30分钟"
    })

# 阀门数据
valves = []
for i in range(VALVE_COUNT):
    zone = zones[i]
    poly = zone["polygon"]
    lat = (poly[0][0] + poly[1][0]) / 2
    lng = (poly[0][1] + poly[2][1]) / 2
    valves.append({
        "id": f"valve_{i + 1:02d}",
        "name": f"电磁阀-{i + 1:02d}",
        "zone_id": zone["id"],
        "zone_name": zone["name"],
        "lat": lat,
        "lng": lng,
        "state": random.choice([True, False]),
        "last_operation": datetime.now() - timedelta(hours=random.randint(1, 48)),
        "timer_enabled": random.choice([True, False]),
        "timer_start": f"{random.randint(6, 10):02d}:00",
        "timer_duration": random.randint(15, 60),
        "online": random.random() > 0.03
    })

# 初始化时同步分区灌溉状态与阀门状态 (保持一致性)
for v in valves:
    if v["state"]:
        for z in zones:
            if z["id"] == v["zone_id"]:
                z["irrigation_active"] = True

# 遥测历史数据
telemetry_history = []
for i in range(TELEMETRY_HISTORY_SIZE):
    ts = datetime.now() - timedelta(minutes=30 * (TELEMETRY_HISTORY_SIZE - i))
    for sensor in sensors[:5]:  # 只为前5个传感器存历史
        telemetry_history.append({
            "device_id": sensor["id"],
            "timestamp": ts.isoformat(),
            "temperature": round(20 + 10 * (0.5 + 0.5 * (i % 48) / 48) + random.uniform(-2, 2), 1),
            "humidity": round(50 + 20 * (0.5 - 0.5 * (i % 48) / 48) + random.uniform(-5, 5), 1),
            "battery": max(20, 100 - i // 50),
            "rssi": random.randint(-110, -60),
            "snr": round(random.uniform(-3, 12), 1)
        })

# 原始码流数据
raw_frames = []
for i in range(FRAME_HISTORY_SIZE):
    frame_type = random.choice(["LoRaWAN", "RS485"])
    if frame_type == "LoRaWAN":
        payload = ''.join(random.choices('0123456789ABCDEF', k=random.randint(20, 40)))
        raw_frames.append({
            "id": i + 1,
            "type": frame_type,
            "timestamp": (datetime.now() - timedelta(minutes=random.randint(0, 1440))).isoformat(),
            "device_id": random.choice(sensors)["id"],
            "raw_payload": payload,
            "parsed": {
                "temperature": round(random.uniform(15, 35), 2),
                "humidity": round(random.uniform(20, 80), 2),
                "battery_mv": random.randint(2800, 3600),
                "rssi": random.randint(-120, -50),
                "snr": round(random.uniform(-5, 15), 1),
                "fcnt": random.randint(1, 65535),
                "port": random.randint(1, 10)
            }
        })
    else:
        frame = f"01{random.randint(1, 50):02X}0400{random.randint(0, 255):02X}{random.randint(0, 255):02X}{random.randint(0, 255):02X}{random.randint(0, 255):02X}"
        crc = sum(int(frame[j:j + 2], 16) for j in range(0, len(frame), 2)) & 0xFFFF
        frame += f"{crc:04X}"
        raw_frames.append({
            "id": i + 1,
            "type": frame_type,
            "timestamp": (datetime.now() - timedelta(minutes=random.randint(0, 1440))).isoformat(),
            "device_id": random.choice(sensors)["id"],
            "raw_payload": frame,
            "parsed": {
                "address": f"{random.randint(1, 50):02X}H",
                "function": "04 (Read Input Registers)",
                "temperature": round(random.uniform(15, 35), 2),
                "humidity": round(random.uniform(20, 80), 2),
                "crc_valid": True
            }
        })

# 告警数据
alerts = []
alert_id_counter = 1

# 阈值配置
thresholds = {
    "humidity_low": 25,
    "humidity_high": 75,
    "temperature_low": 10,
    "temperature_high": 40,
    "battery_low": 20,
    "rssi_low": -110
}

# 灌溉记录
irrigation_logs = []
irrigation_count_today = random.randint(3, 12)


def generate_alert(sensor, alert_type, value, threshold):
    global alert_id_counter
    alerts.insert(0, {
        "id": alert_id_counter,
        "device_id": sensor["id"],
        "device_name": sensor["name"],
        "zone": sensor["zone_name"],
        "type": alert_type,
        "value": value,
        "threshold": threshold,
        "timestamp": datetime.now().isoformat(),
        "acknowledged": False
    })
    alert_id_counter += 1
    if len(alerts) > 100:
        alerts.pop()


def check_thresholds(sensor):
    if sensor["humidity"] < thresholds["humidity_low"]:
        generate_alert(sensor, "湿度过低", sensor["humidity"], thresholds["humidity_low"])
    if sensor["humidity"] > thresholds["humidity_high"]:
        generate_alert(sensor, "湿度过高", sensor["humidity"], thresholds["humidity_high"])
    if sensor["temperature"] < thresholds["temperature_low"]:
        generate_alert(sensor, "温度过低", sensor["temperature"], thresholds["temperature_low"])
    if sensor["temperature"] > thresholds["temperature_high"]:
        generate_alert(sensor, "温度过高", sensor["temperature"], thresholds["temperature_high"])
    if sensor["battery"] < thresholds["battery_low"]:
        generate_alert(sensor, "电量过低", sensor["battery"], thresholds["battery_low"])
    if sensor["rssi"] < thresholds["rssi_low"]:
        generate_alert(sensor, "信号弱", sensor["rssi"], thresholds["rssi_low"])


def update_sensor_data():
    for sensor in sensors:
        sensor["temperature"] = round(sensor["temperature"] + random.uniform(-0.5, 0.5), 1)
        sensor["temperature"] = max(5, min(45, sensor["temperature"]))
        sensor["humidity"] = round(sensor["humidity"] + random.uniform(-1, 1), 1)
        sensor["humidity"] = max(10, min(95, sensor["humidity"]))
        sensor["battery"] = max(0, sensor["battery"] - random.randint(0, 1) if random.random() < 0.1 else sensor[
            "battery"])
        sensor["rssi"] = random.randint(-120, -50)
        sensor["snr"] = round(random.uniform(-5, 15), 1)
        sensor["last_report"] = datetime.now()
        if random.random() < 0.02:
            check_thresholds(sensor)


# ==================== API 路由 ====================

@app.route('/api/overview')
def api_overview():
    online_sensors = sum(1 for s in sensors if s["online"])
    online_valves = sum(1 for v in valves if v["online"])
    active_valves = sum(1 for v in valves if v["state"])
    avg_humidity = round(sum(s["humidity"] for s in sensors) / len(sensors), 1)
    avg_temperature = round(sum(s["temperature"] for s in sensors) / len(sensors), 1)
    unack_alerts = sum(1 for a in alerts if not a["acknowledged"])

    return jsonify({
        "online_sensors": online_sensors,
        "total_sensors": SENSOR_COUNT,
        "online_valves": online_valves,
        "total_valves": VALVE_COUNT,
        "active_valves": active_valves,
        "avg_humidity": avg_humidity,
        "avg_temperature": avg_temperature,
        "alert_count": unack_alerts,
        "irrigation_today": irrigation_count_today,
        "gateway_status": "在线" if random.random() > 0.05 else "离线",
        "last_update": datetime.now().isoformat()
    })


@app.route('/api/sensors')
def api_sensors():
    update_sensor_data()
    return jsonify([{
        **s,
        "last_report": s["last_report"].isoformat() if isinstance(s["last_report"], datetime) else s["last_report"]
    } for s in sensors])


@app.route('/api/valves')
def api_valves():
    return jsonify([{
        **v,
        "last_operation": v["last_operation"].isoformat() if isinstance(v["last_operation"], datetime) else v[
            "last_operation"]
    } for v in valves])


@app.route('/api/valves/<valve_id>/toggle', methods=['POST'])
def api_toggle_valve(valve_id):
    """
    修改点：统一逻辑。
    切换阀门状态时，自动同步对应分区的 'irrigation_active' 状态。
    并记录灌溉日志，确保手动控制阀门也被视为灌溉行为。
    """
    time.sleep(0.5)  # 模拟延迟

    global irrigation_count_today
    target_valve = None

    # 1. 找到阀门并切换状态
    for v in valves:
        if v["id"] == valve_id:
            v["state"] = not v["state"]
            v["last_operation"] = datetime.now()
            target_valve = v
            break

    if not target_valve:
        return jsonify({"success": False, "message": "阀门未找到"}), 404

    # 2. 同步分区状态 (阀门即灌溉)
    current_zone = None
    for z in zones:
        if z["id"] == target_valve["zone_id"]:
            z["irrigation_active"] = target_valve["state"]
            current_zone = z
            break

    # 3. 记录日志和统计 (如果是开启操作)
    action_msg = ""
    if target_valve["state"]:
        irrigation_count_today += 1
        irrigation_logs.append({
            "zone": target_valve["zone_name"],
            "timestamp": datetime.now().isoformat(),
            "action": f"阀门手动开启 (开始灌溉)"
        })
        action_msg = f"{target_valve['name']} 已开启，开始灌溉"
    else:
        action_msg = f"{target_valve['name']} 已关闭，停止灌溉"

    return jsonify({
        "success": True,
        "new_state": target_valve["state"],
        "message": action_msg
    })


@app.route('/api/zones')
def api_zones():
    zone_data = []
    for z in zones:
        zone_sensors = [s for s in sensors if s["zone_id"] == z["id"]]
        # 确保阀门状态是实时的
        zone_valve = next((v for v in valves if v["zone_id"] == z["id"]), None)

        # 再次确认同步 (防止异常状态)
        if zone_valve:
            z["irrigation_active"] = zone_valve["state"]

        avg_hum = round(sum(s["humidity"] for s in zone_sensors) / len(zone_sensors), 1) if zone_sensors else 0
        avg_temp = round(sum(s["temperature"] for s in zone_sensors) / len(zone_sensors), 1) if zone_sensors else 0
        zone_data.append({
            **z,
            "sensor_count": len(zone_sensors),
            "avg_humidity": avg_hum,
            "avg_temperature": avg_temp,
            "valve_state": zone_valve["state"] if zone_valve else None,
            "valve_id": zone_valve["id"] if zone_valve else None
        })
    return jsonify(zone_data)


@app.route('/api/zones/<zone_id>/irrigate', methods=['POST'])
def api_zone_irrigate(zone_id):
    """
    修改点：统一逻辑。
    分区灌溉本质上就是打开该分区的阀门。
    """
    time.sleep(0.8)

    global irrigation_count_today
    target_zone = None

    # 1. 找到分区
    for z in zones:
        if z["id"] == zone_id:
            target_zone = z
            break

    if not target_zone:
        return jsonify({"success": False, "message": "分区未找到"}), 404

    # 2. 找到对应阀门并开启
    valve_operated = False
    for v in valves:
        if v["zone_id"] == zone_id:
            if not v["state"]:  # 如果本来就是开的，就不重复计数了，但也返回成功
                v["state"] = True
                v["last_operation"] = datetime.now()
                irrigation_count_today += 1
                irrigation_logs.append({
                    "zone": target_zone["name"],
                    "timestamp": datetime.now().isoformat(),
                    "action": "分区定时灌溉启动"
                })
            target_zone["irrigation_active"] = True
            valve_operated = True

    if valve_operated:
        return jsonify({"success": True, "message": f"指令下发成功：{target_zone['name']} 阀门已开启 (灌溉中)"})
    else:
        return jsonify({"success": False, "message": "该分区未配置阀门"}), 404


@app.route('/api/telemetry')
def api_telemetry():
    device_id = request.args.get('device_id', sensors[0]["id"])
    hours = int(request.args.get('hours', 24))
    cutoff = datetime.now() - timedelta(hours=hours)

    data = [t for t in telemetry_history
            if t["device_id"] == device_id and datetime.fromisoformat(t["timestamp"]) > cutoff]

    if not data:
        # 生成模拟数据
        data = []
        for i in range(hours * 2):
            ts = cutoff + timedelta(minutes=30 * i)
            data.append({
                "device_id": device_id,
                "timestamp": ts.isoformat(),
                "temperature": round(20 + 8 * (0.5 + 0.5 * ((i * 30) % 1440) / 1440) + random.uniform(-1, 1), 1),
                "humidity": round(50 + 15 * (0.5 - 0.3 * ((i * 30) % 1440) / 1440) + random.uniform(-3, 3), 1),
                "battery": 85,
                "rssi": random.randint(-100, -60),
                "snr": round(random.uniform(0, 10), 1)
            })

    return jsonify(data)


@app.route('/api/frames')
def api_frames():
    limit = int(request.args.get('limit', 50))
    return jsonify(raw_frames[:limit])


@app.route('/api/alerts')
def api_alerts():
    return jsonify(alerts[:50])


@app.route('/api/alerts/<int:alert_id>/acknowledge', methods=['POST'])
def api_acknowledge_alert(alert_id):
    for a in alerts:
        if a["id"] == alert_id:
            a["acknowledged"] = True
            return jsonify({"success": True})
    return jsonify({"success": False}), 404


@app.route('/api/thresholds', methods=['GET', 'POST'])
def api_thresholds():
    global thresholds
    if request.method == 'POST':
        data = request.json
        thresholds.update(data)
        return jsonify({"success": True, "thresholds": thresholds})
    return jsonify(thresholds)


@app.route('/api/decode', methods=['POST'])
def api_decode():
    try:
        data = request.json
        hex_data = data.get('hex_data', '')
        decoded = internal_decode(hex_data)
        return jsonify({"success": True, "decoded": decoded, "source": "internal"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def internal_decode(hex_data):
    """内置解码函数"""
    results = []
    hex_data = hex_data.replace(" ", "").upper()
    i = 0
    while i < len(hex_data) - 12:
        try:
            addr = int(hex_data[i:i + 2], 16)
            func = int(hex_data[i + 2:i + 4], 16)
            if func == 1 or func == 2:
                byte_count = int(hex_data[i + 4:i + 6], 16)
                frame_len = 6 + byte_count * 2 + 4
                if i + frame_len <= len(hex_data):
                    raw = hex_data[i:i + frame_len]
                    results.append({
                        "address": f"{addr:02X}H",
                        "raw": raw,
                        "type": "coil_status",
                        "function": f"0{func}",
                        "byte_count": byte_count,
                        "data": hex_data[i + 6:i + 6 + byte_count * 2]
                    })
                    i += frame_len
                    continue
            elif func == 3 or func == 4:
                byte_count = int(hex_data[i + 4:i + 6], 16)
                frame_len = 6 + byte_count * 2 + 4
                if i + frame_len <= len(hex_data):
                    raw = hex_data[i:i + frame_len]
                    data_bytes = hex_data[i + 6:i + 6 + byte_count * 2]
                    temp_c = None
                    humidity_rh = None
                    if byte_count >= 4:
                        try:
                            temp_raw = int(data_bytes[0:4], 16)
                            temp_c = round(temp_raw / 10.0, 2) if temp_raw < 1000 else round((temp_raw - 65536) / 10.0,
                                                                                             2)
                            hum_raw = int(data_bytes[4:8], 16) if len(data_bytes) >= 8 else 0
                            humidity_rh = round(hum_raw / 10.0, 2)
                        except:
                            pass
                    result = {
                        "address": f"{addr:02X}H",
                        "raw": raw,
                        "type": "temp_humidity" if temp_c is not None else "register",
                        "function": f"0{func}",
                        "data": data_bytes
                    }
                    if temp_c is not None:
                        result["temperature_c"] = temp_c
                        result["humidity_rh"] = humidity_rh
                    results.append(result)
                    i += frame_len
                    continue
            i += 2
        except (ValueError, IndexError):
            i += 2
    if not results and len(hex_data) >= 14:
        results.append({"raw": hex_data, "message": "无法自动解析"})
    return results


@app.route('/stream')
def stream():
    def event_stream():
        while True:
            time.sleep(3)
            update_sensor_data()
            sensor = random.choice(sensors)
            data = {
                "type": "sensor_update",
                "data": {
                    "id": sensor["id"],
                    "temperature": sensor["temperature"],
                    "humidity": sensor["humidity"],
                    "battery": sensor["battery"],
                    "rssi": sensor["rssi"],
                    "last_report": datetime.now().isoformat()
                }
            }
            yield f"data: {json.dumps(data)}\n\n"
            if alerts and random.random() < 0.3:
                yield f"data: {json.dumps({'type': 'alert', 'data': alerts[0]})}\n\n"

    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')


@app.route('/export.csv')
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['设备ID', '时间戳', '温度(°C)', '湿度(%)', '电量(%)', 'RSSI(dBm)', 'SNR(dB)'])
    for t in telemetry_history[-200:]:
        writer.writerow(
            [t["device_id"], t["timestamp"], t["temperature"], t["humidity"], t["battery"], t["rssi"], t["snr"]])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=telemetry_export.csv"})


# ==================== HTML 模板 (统一修复后) ====================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>500亩农田智慧灌溉平台</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
    <style>
        :root {
            --primary-color: #2e7d32;
            --secondary-color: #558b2f;
            --bg-color: #f5f7f5;
            --text-primary: #1a1a1a;
            --text-secondary: #666;
            --border-color: #e0e0e0;
            --success-color: #4caf50;
            --warning-color: #ff9800;
            --danger-color: #f44336;
        }

        body {
            background: var(--bg-color);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: var(--text-primary);
        }

        .toast-container {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
        }
        .custom-toast {
            background: rgba(33, 33, 33, 0.95);
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            margin-bottom: 10px;
            animation: slideIn 0.3s, fadeOut 0.3s 2.7s forwards;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            display: flex;
            align-items: center;
            font-size: 14px;
            min-width: 250px;
        }
        .custom-toast.success { border-left: 4px solid var(--success-color); }
        .custom-toast.error { border-left: 4px solid var(--danger-color); }

        @keyframes slideIn { from { opacity: 0; transform: translateX(50px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes fadeOut { from { opacity: 1; } to { opacity: 0; } }

        .navbar {
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color)) !important;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .card {
            border: none;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            transition: all 0.3s ease;
        }

        .card:hover {
            box-shadow: 0 4px 16px rgba(0,0,0,0.1);
        }

        .stat-card { padding: 1.25rem; }
        .stat-card .stat-icon {
            width: 48px; height: 48px; border-radius: 12px;
            display: flex; align-items: center; justify-content: center; font-size: 1.5rem;
        }
        .stat-card .stat-value { font-size: 1.75rem; font-weight: 700; line-height: 1.2; }
        .stat-card .stat-label { color: var(--text-secondary); font-size: 0.875rem; }

        #map {
            height: 450px;
            border-radius: 12px;
            z-index: 1;
            background: #e0e0e0;
        }

        .device-list { max-height: 400px; overflow-y: auto; }
        .device-item {
            padding: 0.75rem; border-bottom: 1px solid var(--border-color);
            cursor: pointer; transition: background 0.2s;
        }
        .device-item:hover { background: #f8f9fa; }
        .device-item.active { background: #e8f5e9; border-left: 3px solid var(--primary-color); }

        .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
        .status-online { background: var(--success-color); }
        .status-offline { background: var(--danger-color); }

        .chart-container { height: 300px; position: relative; }

        .zone-info {
            padding: 1rem; background: #f8f9fa; border-radius: 8px; margin-top: 1rem;
        }

        .search-box {
            border-radius: 20px; padding-left: 2.5rem; background: #f8f9fa; border: 1px solid var(--border-color);
        }
        .search-icon {
            position: absolute; left: 1rem; top: 50%; transform: translateY(-50%); color: var(--text-secondary);
        }

        .leaflet-popup-content-wrapper { border-radius: 8px; padding: 0; }
        .leaflet-popup-content { margin: 10px 14px; }
        .popup-title { font-weight: 600; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #eee; }
        .popup-row { display: flex; justify-content: space-between; margin: 4px 0; font-size: 0.875rem; }

        .alert-item {
            padding: 0.75rem; border-left: 3px solid var(--warning-color);
            margin-bottom: 0.5rem; background: #fff8e1; border-radius: 0 8px 8px 0;
        }
        .alert-item.danger { border-left-color: var(--danger-color); background: #ffebee; }

        .frame-item {
            font-family: 'Courier New', monospace; font-size: 0.8rem;
            background: #f5f5f5; padding: 0.5rem; margin-bottom: 0.5rem; border-radius: 6px; word-break: break-all;
        }

        .decode-result { background: #f8f9fa; border-radius: 8px; padding: 1rem; font-family: 'Courier New', monospace; font-size: 0.85rem; max-height: 400px; overflow-y: auto; }
        .json-key { color: #0d47a1; }
        .json-string { color: #2e7d32; }
        .json-number { color: #e65100; }
    </style>
</head>
<body>
    <div id="toast-container" class="toast-container"></div>

    <nav class="navbar navbar-dark py-2 mb-4">
        <div class="container-fluid">
            <span class="navbar-brand mb-0 h4">
                <i class="bi bi-droplet-fill me-2"></i>500亩农田智慧灌溉平台
            </span>
            <div class="d-flex align-items-center text-white">
                <span class="me-3" id="current-time"></span>
                <span class="badge bg-light text-dark" id="connection-status">
                    <span class="status-dot status-online me-1"></span>实时连接
                </span>
            </div>
        </div>
    </nav>

    <div class="container-fluid px-4">
        <div class="row g-3 mb-4">
            <div class="col-6 col-md-4 col-xl-2">
                <div class="card stat-card">
                    <div class="d-flex align-items-center">
                        <div class="stat-icon bg-success bg-opacity-10 text-success me-3"><i class="bi bi-thermometer-half"></i></div>
                        <div><div class="stat-value" id="stat-sensors">0/50</div><div class="stat-label">在线传感器</div></div>
                    </div>
                </div>
            </div>
            <div class="col-6 col-md-4 col-xl-2">
                <div class="card stat-card">
                    <div class="d-flex align-items-center">
                        <div class="stat-icon bg-primary bg-opacity-10 text-primary me-3"><i class="bi bi-toggles"></i></div>
                        <div><div class="stat-value" id="stat-valves">0/10</div><div class="stat-label">阀门开启</div></div>
                    </div>
                </div>
            </div>
            <div class="col-6 col-md-4 col-xl-2">
                <div class="card stat-card">
                    <div class="d-flex align-items-center">
                        <div class="stat-icon bg-info bg-opacity-10 text-info me-3"><i class="bi bi-moisture"></i></div>
                        <div><div class="stat-value" id="stat-humidity">---%</div><div class="stat-label">平均湿度</div></div>
                    </div>
                </div>
            </div>
            <div class="col-6 col-md-4 col-xl-2">
                <div class="card stat-card">
                    <div class="d-flex align-items-center">
                        <div class="stat-icon bg-warning bg-opacity-10 text-warning me-3"><i class="bi bi-thermometer-sun"></i></div>
                        <div><div class="stat-value" id="stat-temp">---°C</div><div class="stat-label">平均温度</div></div>
                    </div>
                </div>
            </div>
            <div class="col-6 col-md-4 col-xl-2">
                <div class="card stat-card">
                    <div class="d-flex align-items-center">
                        <div class="stat-icon bg-danger bg-opacity-10 text-danger me-3"><i class="bi bi-exclamation-triangle"></i></div>
                        <div><div class="stat-value" id="stat-alerts">0</div><div class="stat-label">待处理告警</div></div>
                    </div>
                </div>
            </div>
            <div class="col-6 col-md-4 col-xl-2">
                <div class="card stat-card">
                    <div class="d-flex align-items-center">
                        <div class="stat-icon bg-secondary bg-opacity-10 text-secondary me-3"><i class="bi bi-droplet"></i></div>
                        <div><div class="stat-value" id="stat-irrigation">0次</div><div class="stat-label">今日灌溉</div></div>
                    </div>
                </div>
            </div>
        </div>

        <div class="row g-4">
            <div class="col-lg-8">
                <div class="card mb-4">
                    <div class="card-header bg-white d-flex justify-content-between align-items-center">
                        <h6 class="mb-0"><i class="bi bi-map me-2"></i>农田分区地图 (卫星视图)</h6>
                        <div>
                            <span class="badge bg-success me-2">● 传感器</span>
                            <span class="badge bg-primary">● 阀门/灌溉点</span>
                        </div>
                    </div>
                    <div class="card-body p-2">
                        <div id="map"></div>
                        <div class="zone-info" id="zone-info" style="display:none;">
                            <h6 id="zone-info-title">分区信息</h6>
                            <div class="row">
                                <div class="col-6"><small class="text-muted">平均湿度</small><div class="fw-bold" id="zone-humidity">--%</div></div>
                                <div class="col-6"><small class="text-muted">平均温度</small><div class="fw-bold" id="zone-temp">--°C</div></div>
                                <div class="col-6 mt-2"><small class="text-muted">传感器数</small><div class="fw-bold" id="zone-sensors">--</div></div>
                                <div class="col-6 mt-2"><small class="text-muted">阀门(灌溉)状态</small><div class="fw-bold" id="zone-valve">--</div></div>
                            </div>
                            <button class="btn btn-sm btn-success mt-2 w-100" id="zone-irrigate-btn">
                                <i class="bi bi-droplet-fill me-1"></i>开启阀门 (开始灌溉)
                            </button>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header bg-white">
                        <ul class="nav nav-tabs card-header-tabs" role="tablist">
                            <li class="nav-item">
                                <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#sensors-tab">
                                    <i class="bi bi-thermometer-half me-1"></i>传感器 (50)
                                </button>
                            </li>
                            <li class="nav-item">
                                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#valves-tab">
                                    <i class="bi bi-toggles me-1"></i>阀门控制 (10)
                                </button>
                            </li>
                        </ul>
                    </div>
                    <div class="card-body">
                        <div class="position-relative mb-3">
                            <i class="bi bi-search search-icon"></i>
                            <input type="text" class="form-control search-box" id="device-search" placeholder="搜索设备...">
                        </div>
                        <div class="tab-content">
                            <div class="tab-pane fade show active" id="sensors-tab">
                                <div class="device-list" id="sensor-list"></div>
                            </div>
                            <div class="tab-pane fade" id="valves-tab">
                                <div class="device-list" id="valve-list"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-lg-4">
                <div class="card mb-4">
                    <div class="card-header bg-white d-flex justify-content-between align-items-center">
                        <h6 class="mb-0"><i class="bi bi-graph-up me-2"></i>趋势曲线</h6>
                        <select class="form-select form-select-sm" style="width:auto" id="chart-device-select"></select>
                    </div>
                    <div class="card-body">
                        <div class="chart-container">
                            <canvas id="trend-chart"></canvas>
                        </div>
                    </div>
                </div>

                <div class="card mb-4">
                    <div class="card-header bg-white d-flex justify-content-between align-items-center">
                        <h6 class="mb-0"><i class="bi bi-exclamation-triangle me-2"></i>告警列表</h6>
                        <button class="btn btn-sm btn-outline-secondary" data-bs-toggle="modal" data-bs-target="#thresholdModal">
                            <i class="bi bi-gear"></i>
                        </button>
                    </div>
                    <div class="card-body p-2">
                        <div id="alert-list" style="max-height:250px;overflow-y:auto;"></div>
                    </div>
                </div>

                <div class="card mb-4">
                    <div class="card-header bg-white">
                        <h6 class="mb-0"><i class="bi bi-sliders me-2"></i>灌溉(阀门)控制</h6>
                    </div>
                    <div class="card-body">
                        <div class="mb-3">
                            <label class="form-label small">选择灌溉分区</label>
                            <select class="form-select" id="irrigation-zone">
                                <option value="">选择分区...</option>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label small">定时设置 (可选)</label>
                            <div class="row g-2">
                                <div class="col-6"><input type="time" class="form-control form-control-sm" id="timer-start" value="06:00"></div>
                                <div class="col-6"><input type="number" class="form-control form-control-sm" id="timer-duration" placeholder="时长(分)" value="30"></div>
                            </div>
                        </div>
                        <button class="btn btn-success w-100" id="start-irrigation">
                            <i class="bi bi-play-fill me-1"></i>开启阀门 (开始灌溉)
                        </button>
                    </div>
                </div>

                <div class="card">
                    <div class="card-body">
                        <a href="/export.csv" class="btn btn-outline-primary w-100">
                            <i class="bi bi-download me-2"></i>导出遥测数据 (CSV)
                        </a>
                    </div>
                </div>
            </div>
        </div>

        <div class="row mt-4">
             <div class="col-lg-6">
                <div class="card">
                    <div class="card-header bg-white"><h6 class="mb-0"><i class="bi bi-code-square me-2"></i>原始码流 (LoRaWAN / RS485)</h6></div>
                    <div class="card-body"><div id="frame-list" style="max-height:300px;overflow-y:auto;"></div></div>
                </div>
            </div>
            <div class="col-lg-6">
                 <div class="card">
                    <div class="card-header bg-white"><h6 class="mb-0"><i class="bi bi-braces me-2"></i>HEX 数据解码</h6></div>
                    <div class="card-body">
                        <textarea class="form-control mb-3" id="hex-input" rows="3" placeholder="输入 HEX 数据"></textarea>
                        <button class="btn btn-primary w-100 mb-3" id="decode-btn"><i class="bi bi-cpu me-1"></i>解码数据</button>
                        <div class="decode-result" id="decode-result"><span class="text-muted">解码结果...</span></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="modal fade" id="thresholdModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header"><h5 class="modal-title">告警阈值配置</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
                <div class="modal-body">
                    <div class="row g-3">
                        <div class="col-6"><label class="form-label small">湿度下限</label><input type="number" class="form-control" id="th-humidity-low" value="25"></div>
                        <div class="col-6"><label class="form-label small">湿度上限</label><input type="number" class="form-control" id="th-humidity-high" value="75"></div>
                        <div class="col-6"><label class="form-label small">温度下限</label><input type="number" class="form-control" id="th-temp-low" value="10"></div>
                        <div class="col-6"><label class="form-label small">温度上限</label><input type="number" class="form-control" id="th-temp-high" value="40"></div>
                        <div class="col-6"><label class="form-label small">电量下限</label><input type="number" class="form-control" id="th-battery-low" value="20"></div>
                        <div class="col-6"><label class="form-label small">RSSI下限</label><input type="number" class="form-control" id="th-rssi-low" value="-110"></div>
                    </div>
                </div>
                <div class="modal-footer"><button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button><button type="button" class="btn btn-primary" id="save-thresholds">保存</button></div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        let map, chart;
        let sensors = [], valves = [], zones = [];
        let sensorMarkers = {}, valveMarkers = {}, zonePolygons = {};
        let selectedZoneId = null;
        let selectedDeviceId = null;

        function showToast(message, type='success') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `custom-toast ${type}`;
            const icon = type === 'success' ? 'bi-check-circle-fill' : 'bi-exclamation-circle-fill';
            const color = type === 'success' ? '#4caf50' : '#f44336';
            toast.innerHTML = `<i class="bi ${icon} me-2" style="color:${color};font-size:1.2rem;"></i> <span>${message}</span>`;
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }

        function initMap() {
            map = L.map('map').setView([47.24, 132.52], 14);
            L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
                attribution: 'Tiles &copy; Esri'
            }).addTo(map);
        }

        async function loadZones() {
            const res = await fetch('/api/zones');
            zones = await res.json();
            const select = document.getElementById('irrigation-zone');

            // 保持当前选中的值，不被刷新重置
            const currentVal = select.value;
            select.innerHTML = '<option value="">选择分区...</option>';

            zones.forEach(zone => {
                // 地图逻辑
                if (!zonePolygons[zone.id]) {
                    const polygon = L.polygon(zone.polygon, {
                        color: zone.color, fillColor: zone.color, fillOpacity: 0.3, weight: 2
                    }).addTo(map);
                    polygon.on('click', () => selectZone(zone));
                    zonePolygons[zone.id] = polygon;
                }

                // 视觉同步：如果灌溉中(阀门开)，高亮显示分区
                if (zone.valve_state) {
                     zonePolygons[zone.id].setStyle({color: '#2196f3', fillColor: '#2196f3', fillOpacity: 0.4});
                } else {
                     zonePolygons[zone.id].setStyle({color: zone.color, fillColor: zone.color, fillOpacity: 0.3});
                }

                // 下拉框
                const option = document.createElement('option');
                option.value = zone.id; 
                // 下拉框显示状态
                option.textContent = `${zone.name} (${zone.valve_state ? '灌溉中' : '空闲'})`;
                select.appendChild(option);
            });
            select.value = currentVal;

            if (selectedZoneId) {
                const z = zones.find(z => z.id === selectedZoneId);
                if(z) updateZoneInfoPanel(z);
            }
        }

        function updateZoneInfoPanel(zone) {
            document.getElementById('zone-info').style.display = 'block';
            document.getElementById('zone-info-title').textContent = zone.name;
            document.getElementById('zone-humidity').textContent = zone.avg_humidity + '%';
            document.getElementById('zone-temp').textContent = zone.avg_temperature + '°C';
            document.getElementById('zone-sensors').textContent = zone.sensor_count;

            // 状态显示同步
            const statusText = zone.valve_state ? '<span class="text-primary">灌溉进行中</span>' : '<span class="text-muted">停止</span>';
            document.getElementById('zone-valve').innerHTML = statusText;

            // 按钮文字同步
            const btn = document.getElementById('zone-irrigate-btn');
            if (zone.valve_state) {
                btn.className = 'btn btn-sm btn-danger mt-2 w-100';
                btn.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i>关闭阀门 (停止灌溉)';
                btn.onclick = () => toggleValve(zone.valve_id); // 复用 toggleValve
            } else {
                btn.className = 'btn btn-sm btn-success mt-2 w-100';
                btn.innerHTML = '<i class="bi bi-droplet-fill me-1"></i>开启阀门 (开始灌溉)';
                btn.onclick = () => startIrrigation(zone.id); // 使用 startIrrigation
            }

            // 同步下拉框
            document.getElementById('irrigation-zone').value = zone.id;
        }

        function selectZone(zone) {
            selectedZoneId = zone.id;
            updateZoneInfoPanel(zone);
        }

        async function loadSensors() {
            const res = await fetch('/api/sensors');
            sensors = await res.json();
            const list = document.getElementById('sensor-list');
            list.innerHTML = '';
            const chartSelect = document.getElementById('chart-device-select');
            if (chartSelect.options.length === 0) {
                 sensors.forEach(s => {
                    const opt = document.createElement('option'); opt.value = s.id; opt.textContent = s.name;
                    chartSelect.appendChild(opt);
                 });
            }

            sensors.forEach(s => {
                if (!sensorMarkers[s.id]) {
                    const marker = L.circleMarker([s.lat, s.lng], {
                        radius: 6, fillColor: s.online ? '#4caf50' : '#f44336', color: '#fff', weight: 1, fillOpacity: 1
                    }).addTo(map);
                    marker.on('click', () => selectDevice(s.id, 'sensor'));
                    sensorMarkers[s.id] = marker;
                }
                sensorMarkers[s.id].bindPopup(`
                    <div class="popup-title">${s.name}</div>
                    <div class="popup-row"><span>T/H:</span><span>${s.temperature}°C / ${s.humidity}%</span></div>
                    <div class="popup-row"><span>电量:</span><span>${s.battery}%</span></div>
                `);

                const div = document.createElement('div');
                div.className = 'device-item' + (s.id === selectedDeviceId ? ' active' : '');
                div.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div><span class="status-dot ${s.online ? 'status-online' : 'status-offline'} me-2"></span><strong>${s.name}</strong></div>
                        <small class="text-muted">${s.zone_name}</small>
                    </div>
                    <div class="d-flex justify-content-between mt-1 small">
                        <span><i class="bi bi-thermometer"></i> ${s.temperature}°C</span>
                        <span><i class="bi bi-droplet"></i> ${s.humidity}%</span>
                        <span><i class="bi bi-battery-half"></i> ${s.battery}%</span>
                    </div>`;
                div.onclick = () => selectDevice(s.id, 'sensor');
                list.appendChild(div);
            });
        }

        async function loadValves() {
            const res = await fetch('/api/valves');
            valves = await res.json();
            const list = document.getElementById('valve-list');
            list.innerHTML = '';

            valves.forEach(v => {
                const iconHtml = `<div style="background:${v.state ? '#2196f3' : '#757575'};width:24px;height:24px;border-radius:50%;border:2px solid #fff;box-shadow:0 2px 4px rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px;font-weight:bold;">V</div>`;

                if (!valveMarkers[v.id]) {
                    const marker = L.marker([v.lat, v.lng], {
                        icon: L.divIcon({ className: 'valve-marker', html: iconHtml, iconSize: [24, 24] })
                    }).addTo(map);
                    valveMarkers[v.id] = marker;
                } else {
                    valveMarkers[v.id].setIcon(L.divIcon({ className: 'valve-marker', html: iconHtml, iconSize: [24, 24] }));
                }

                valveMarkers[v.id].bindPopup(`
                    <div class="popup-title">${v.name}</div>
                    <div class="popup-row"><span>状态:</span><span class="badge ${v.state ? 'bg-primary' : 'bg-secondary'}">${v.state ? '灌溉中' : '关闭'}</span></div>
                    <button class="btn btn-sm btn-${v.state ? 'danger' : 'success'} w-100 mt-2" onclick="toggleValve('${v.id}')">${v.state ? '关闭阀门 (停止)' : '开启阀门 (灌溉)'}</button>
                `);

                const div = document.createElement('div');
                div.className = 'device-item';
                div.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div><span class="status-dot ${v.online ? 'status-online' : 'status-offline'} me-2"></span><strong>${v.name}</strong></div>
                        <button class="btn btn-sm valve-btn ${v.state ? 'btn-outline-danger' : 'btn-outline-success'}" onclick="toggleValve('${v.id}')">${v.state ? '关闭' : '开启'}</button>
                    </div>
                    <div class="small text-muted mt-1"><span>${v.zone_name}</span> · <span>${v.state ? '灌溉进行中' : '空闲'}</span></div>`;
                list.appendChild(div);
            });
        }

        async function toggleValve(valveId) {
            showToast('正在发送控制指令...', 'success');
            try {
                const res = await fetch(`/api/valves/${valveId}/toggle`, {method: 'POST'});
                const result = await res.json();
                if (result.success) {
                    showToast(result.message, 'success');
                    await Promise.all([loadValves(), loadZones(), loadOverview()]);
                    updateControlPanelButton(); // 刷新控制面板按钮状态
                } else {
                    showToast(result.message, 'error');
                }
            } catch (e) {
                showToast('网络请求失败', 'error');
            }
        }

        async function startIrrigation(specificZoneId = null) {
            // 支持从UI获取ID或直接传入ID
            const zoneId = specificZoneId || document.getElementById('irrigation-zone').value;
            const btn = document.getElementById('start-irrigation');

            if (!zoneId) {
                showToast('请先选择灌溉分区', 'error');
                return;
            }

            // 检查该分区阀门是否已经开了，如果开了，这个按钮变成“关闭”功能 (简单的反转逻辑)
            // 为了简化，这里统一调用 irrigate 接口开启，如果要关闭，逻辑上应该引导去点"关闭阀门"
            // 但既然是“统一逻辑”，这里我们做个判断：
            const zone = zones.find(z => z.id === zoneId);
            if(zone && zone.valve_state) {
                 // 如果已经是开的，且用户点了按钮，可能是想关闭？
                 // 在这里为了逻辑清晰，我们把 startIrrigation 仅作为开启。
                 // 关闭操作通过 toggleValve (在UI上表现为 "关闭阀门")
                 toggleValve(zone.valve_id); 
                 return; 
            }

            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>指令下发中...';

            try {
                const res = await fetch(`/api/zones/${zoneId}/irrigate`, {method: 'POST'});
                const result = await res.json();
                if (result.success) {
                    showToast(result.message, 'success');
                    await Promise.all([loadValves(), loadZones(), loadOverview()]);
                } else {
                    showToast(result.message, 'error');
                }
            } catch (e) {
                showToast('网络请求异常', 'error');
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }

        // 监听下拉框变化，更新按钮状态
        document.getElementById('irrigation-zone').addEventListener('change', updateControlPanelButton);

        function updateControlPanelButton() {
            const zoneId = document.getElementById('irrigation-zone').value;
            const btn = document.getElementById('start-irrigation');
            const zone = zones.find(z => z.id === zoneId);

            if (zone) {
                if (zone.valve_state) {
                    btn.className = 'btn btn-danger w-100';
                    btn.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i>关闭阀门 (停止灌溉)';
                } else {
                    btn.className = 'btn btn-success w-100';
                    btn.innerHTML = '<i class="bi bi-play-fill me-1"></i>开启阀门 (开始灌溉)';
                }
            } else {
                btn.className = 'btn btn-success w-100';
                btn.innerHTML = '<i class="bi bi-play-fill me-1"></i>开启阀门 (开始灌溉)';
            }
        }

        function selectDevice(deviceId, type) {
            selectedDeviceId = deviceId;
            document.querySelectorAll('.device-item').forEach(el => el.classList.remove('active'));
            if (type === 'sensor' && sensorMarkers[deviceId]) {
                sensorMarkers[deviceId].openPopup();
            }
            document.getElementById('chart-device-select').value = deviceId;
            loadChartData(deviceId);
            loadSensors();
        }

        function initChart() {
            const ctx = document.getElementById('trend-chart').getContext('2d');
            chart = new Chart(ctx, {
                type: 'line',
                data: { labels: [], datasets: [
                    { label: '温度', data: [], borderColor: '#ff9800', backgroundColor: 'rgba(255, 152, 0, 0.1)', tension: 0.4, fill: true },
                    { label: '湿度', data: [], borderColor: '#2196f3', backgroundColor: 'rgba(33, 150, 243, 0.1)', tension: 0.4, fill: true }
                ]},
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } }, interaction: { intersect: false, mode: 'index' } }
            });
        }

        async function loadChartData(deviceId) {
            const res = await fetch(`/api/telemetry?device_id=${deviceId || sensors[0]?.id}&hours=24`);
            const data = await res.json();
            chart.data.labels = data.map(d => new Date(d.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
            chart.data.datasets[0].data = data.map(d => d.temperature);
            chart.data.datasets[1].data = data.map(d => d.humidity);
            chart.update();
        }

        async function loadOverview() {
            const res = await fetch('/api/overview');
            const data = await res.json();
            document.getElementById('stat-sensors').textContent = `${data.online_sensors}/${data.total_sensors}`;
            document.getElementById('stat-valves').textContent = `${data.active_valves}开`; // 简化显示
            document.getElementById('stat-humidity').textContent = `${data.avg_humidity}%`;
            document.getElementById('stat-temp').textContent = `${data.avg_temperature}°C`;
            document.getElementById('stat-alerts').textContent = data.alert_count;
            document.getElementById('stat-irrigation').textContent = `${data.irrigation_today}次`;
        }

        async function loadAlerts() {
            const res = await fetch('/api/alerts');
            const alerts = await res.json();
            const list = document.getElementById('alert-list');
            list.innerHTML = alerts.length ? '' : '<div class="text-muted text-center py-3">暂无告警</div>';
            alerts.slice(0, 20).forEach(a => {
                const div = document.createElement('div');
                div.className = 'alert-item' + (a.type.includes('过低') || a.type.includes('异常') ? ' danger' : '');
                div.innerHTML = `<div class="d-flex justify-content-between"><strong>${a.type}</strong><small class="text-muted">${new Date(a.timestamp).toLocaleTimeString()}</small></div><div class="small">${a.device_name} · ${a.zone} · 值: ${a.value}</div>`;
                list.appendChild(div);
            });
        }

        async function loadFrames() {
            const res = await fetch('/api/frames?limit=20');
            const frames = await res.json();
            const list = document.getElementById('frame-list');
            list.innerHTML = '';
            frames.forEach(f => {
                const div = document.createElement('div');
                div.className = 'frame-item';
                div.innerHTML = `<div class="d-flex justify-content-between mb-1"><span class="badge ${f.type === 'LoRaWAN' ? 'bg-info' : 'bg-warning'}">${f.type}</span><small class="text-muted">${new Date(f.timestamp).toLocaleTimeString()}</small></div><div class="text-break text-truncate">${f.raw_payload}</div>`;
                list.appendChild(div);
            });
        }

        async function decodeHex() {
            const hex = document.getElementById('hex-input').value.trim();
            if(!hex) return;
            const res = await fetch('/api/decode', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({hex_data:hex})});
            const result = await res.json();
            document.getElementById('decode-result').innerHTML = result.success ? `<pre>${JSON.stringify(result.decoded, null, 2)}</pre>` : `<span class="text-danger">${result.error}</span>`;
        }

        async function saveThresholds() {
            bootstrap.Modal.getInstance(document.getElementById('thresholdModal')).hide();
            showToast('阈值配置已保存', 'success');
        }

        // Search
        document.getElementById('device-search').addEventListener('input', e => {
            const q = e.target.value.toLowerCase();
            document.querySelectorAll('.device-item').forEach(el => el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none');
        });

        // Listeners
        document.getElementById('chart-device-select').addEventListener('change', e => loadChartData(e.target.value));
        document.getElementById('decode-btn').addEventListener('click', decodeHex);
        document.getElementById('start-irrigation').addEventListener('click', () => startIrrigation());
        document.getElementById('save-thresholds').addEventListener('click', saveThresholds);

        // Init
        document.addEventListener('DOMContentLoaded', async () => {
            initMap(); initChart();
            await Promise.all([loadZones(), loadSensors(), loadValves(), loadOverview(), loadAlerts(), loadFrames(), loadChartData()]);

            // 初始检查控制面板按钮状态
            updateControlPanelButton();

            setInterval(() => { loadOverview(); loadSensors(); }, 10000);
            setInterval(loadAlerts, 15000);

            // SSE
            const evtSource = new EventSource('/stream');
            evtSource.onmessage = e => {
                const d = JSON.parse(e.data);
                if(d.type === 'sensor_update') {
                    const s = sensors.find(x => x.id === d.data.id);
                    if(s) Object.assign(s, d.data);
                } else if(d.type === 'alert') { loadAlerts(); loadOverview(); }
            };

            // Time
            setInterval(() => document.getElementById('current-time').textContent = new Date().toLocaleString(), 1000);
        });
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)