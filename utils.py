import json


def decode_itu_01h(data):
    """decode 8901/9901 temperature and humidity"""
    if len(data) < 7:
        return None
    th, tl = data[3], data[4]
    hh, hl = data[5], data[6]

    # temperature
    if th == 0xFF and tl == 0xFF:
        temp = "Fault"
    else:
        is_neg = bool(th & 0x08)
        val = ((th & 0x07) * 256 + tl) * 0.0625
        temp = -val if is_neg else val

    # humidity
    if hh == 0xFF and hl == 0xFF:
        humi = "Fault"
    else:
        humi = ((hh & 0x03) * 256 + hl) / 10.0

    return {"type": "temperature_and_humidity", "temperature_c": temp, "humidity_rh": humi}


def process_data_area(hex_str):
    """partition"""
    raw_bytes = bytes.fromhex(hex_str.replace(" ", ""))
    results = []
    i = 0

    while i < len(raw_bytes):
        length = raw_bytes[i]
        segment = raw_bytes[i: i + length + 1]

        itu_type = segment[1]
        itu_addr = segment[2]

        info = {"address": f"{itu_addr:02X}H", "raw": segment.hex().upper()}

        if itu_type == 0x01:
            info.update(decode_itu_01h(segment))
            results.append(info)

        i += (length + 1)

    return results


if __name__ == "__main__":
    hex_data = "060102017600A30A0B054000410042364300060102017600A3"

    decoded_list = process_data_area(hex_data)
    print(json.dumps(decoded_list, indent=4, ensure_ascii=False))