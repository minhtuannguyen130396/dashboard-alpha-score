import websocket
import ssl
import io
import json
import base64
import msgpack
import time

WS_URL = "wss://tradestation.fireant.vn/quote-lite?access_token=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSIsImtpZCI6IkdYdExONzViZlZQakdvNERWdjV4QkRITHpnSSJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4iLCJhdWQiOiJodHRwczovL2FjY291bnRzLmZpcmVhbnQudm4vcmVzb3VyY2VzIiwiZXhwIjoxODg5NjIyNTMwLCJuYmYiOjE1ODk2MjI1MzAsImNsaWVudF9pZCI6ImZpcmVhbnQudHJhZGVzdGF0aW9uIiwic2NvcGUiOlsiYWNhZGVteS1yZWFkIiwiYWNhZGVteS13cml0ZSIsImFjY291bnRzLXJlYWQiLCJhY2NvdW50cy13cml0ZSIsImJsb2ctcmVhZCIsImNvbXBhbmllcy1yZWFkIiwiZmluYW5jZS1yZWFkIiwiaW5kaXZpZHVhbHMtcmVhZCIsImludmVzdG9wZWRpYS1yZWFkIiwib3JkZXJzLXJlYWQiLCJvcmRlcnMtd3JpdGUiLCJwb3N0cy1yZWFkIiwicG9zdHMtd3JpdGUiLCJzZWFyY2giLCJzeW1ib2xzLXJlYWQiLCJ1c2VyLWRhdGEtcmVhZCIsInVzZXItZGF0YS13cml0ZSIsInVzZXJzLXJlYWQiXSwianRpIjoiMjYxYTZhYWQ2MTQ5Njk1ZmJiYzcwODM5MjM0Njc1NWQifQ.dA5-HVzWv-BRfEiAd24uNBiBxASO-PAyWeWESovZm_hj4aXMAZA1-bWNZeXt88dqogo18AwpDQ-h6gefLPdZSFrG5umC1dVWaeYvUnGm62g4XS29fj6p01dhKNNqrsu5KrhnhdnKYVv9VdmbmqDfWR8wDgglk5cJFqalzq6dJWJInFQEPmUs9BW_Zs8tQDn-i5r4tYq2U8vCdqptXoM7YgPllXaPVDeccC9QNu2Xlp9WUvoROzoQXg25lFub1IYkTrM66gJ6t9fJRZToewCt495WNEOQFa_rwLCZ1QwzvL0iYkONHS_jZ0BOhBCdW9dWSawD6iF1SIQaFROvMDH1rg"  # giữ giống code cũ của bạn

RS = "\x1e"  # Record Separator

# 3 request subscribe (đã cho sẵn dạng Base64)
SUB_REQUESTS = [
    ("FPT", "MpUBgKEwr1N1YnNjcmliZVF1b3Rlc5G7RlBULEJCQyxEUE0sQUNCLENNRyxGT1gsQ1REHpUBgKExr1N1YnNjcmliZVF1b3Rlc5GnRlBULEJCQyqVAYChMq9TdWJzY3JpYmVRdW90ZXORs0RQTSxBQ0IsQ01HLEZPWCxDVEQ="),
    ("SSI", "T5UBgKEwr1N1YnNjcmliZVF1b3Rlc5HZN1NTSSxCTVAsRlBULENUUixBTlQsQUNCLEFWQyxNV0csTUJTLEFOVixIUEcsQVBHLEJTUixETTcelQGAoTGvU3Vic2NyaWJlUXVvdGVzkadTU0ksQk1QR5UBgKEyr1N1YnNjcmliZVF1b3Rlc5HZL0ZQVCxDVFIsQU5ULEFDQixBVkMsTVdHLE1CUyxBTlYsSFBHLEFQRyxCU1IsRE03"),
    ("VIC", "RZUBgKEwr1N1YnNjcmliZVF1b3Rlc5HZLVZJQyxITlhJTkRFWCxIUEcsSElELFZITSxVUy5WRlMsSE5YMzAsQ1RSLFBPTRqVAYChMa9TdWJzY3JpYmVRdW90ZXORo1ZJQ0GVAYChMq9TdWJzY3JpYmVRdW90ZXOR2SlITlhJTkRFWCxIUEcsSElELFZITSxVUy5WRlMsSE5YMzAsQ1RSLFBPTQ=="),
]

###############################################################################
# LOG
###############################################################################

def log_step(step):
    print(f"\n===== [STEP] {step} =====")


def log_data(title, data):
    print(f"[{title}] {data}")


###############################################################################
# PARSE CÁC GÓI UPDATE*
###############################################################################

def try_decode_msgpack(payload: bytes):
    try:
        unpacker = msgpack.Unpacker(io.BytesIO(payload), raw=False)
        objs = list(unpacker)
        log_data("MessagePack decoded", objs)
        return objs
    except Exception as e:
        log_data("MsgPack decode error", str(e))
        log_data("Payload HEX", payload.hex())
        return None


def handle_update_last_prices(payload: bytes):
    log_step("Handle UpdateLastPrices")
    try_decode_msgpack(payload)


def handle_update_ref_prices(payload: bytes):
    log_step("Handle UpdateRefPrices")
    try_decode_msgpack(payload)


def handle_update_orderbooks(payload: bytes):
    log_step("Handle UpdateOrderBooks")
    try_decode_msgpack(payload)


###############################################################################
# HANDSHAKE + GỬI REQUEST 1 PHÚT / MÃ
###############################################################################

def send_handshake(ws):
    handshake = {"protocol": "messagepack", "version": 1}
    text = json.dumps(handshake) + RS
    log_step("Send handshake JSON")
    log_data("Handshake", text.encode("utf-8"))
    print("send handshake ok")
    ws.send(text)


def send_apeg(ws):
    raw = base64.b64decode("ApEG")
    log_step("Bắt tay thành công – gửi ApEG")
    log_data("ApEG raw hex", raw.hex())
    ws.send(raw, opcode=websocket.ABNF.OPCODE_BINARY)


def start_next_request(ws):
    """
    Gửi subscribe cho mã tiếp theo trong SUB_REQUESTS.
    Mỗi request: set thời gian bắt đầu, giữ 60s để nghe dữ liệu.
    """
    if ws.current_req_index is None:
        ws.current_req_index = 0
    else:
        ws.current_req_index += 1

    if ws.current_req_index >= len(SUB_REQUESTS):
        log_step("Đã gửi hết subscribe cho tất cả mã, tiếp tục chỉ nghe dữ liệu.")
        ws.current_req_started_at = None
        return

    name, b64 = SUB_REQUESTS[ws.current_req_index]
    raw = base64.b64decode(b64)

    ws.current_req_started_at = time.time()

    log_step(f"Gửi subscribe cho {name} – sẽ nghe dữ liệu trong 60s")
    log_data("Subscribe raw hex", raw.hex())
    ws.send(raw, opcode=websocket.ABNF.OPCODE_BINARY)


def maybe_switch_request(ws):
    """
    Kiểm tra nếu đã quá 60s cho request hiện tại thì chuyển sang mã tiếp theo.
    Hàm này được gọi mỗi khi nhận 1 binary frame.
    """
    if ws.current_req_started_at is None:
        return
    if ws.current_req_index is None:
        return

    elapsed = time.time() - ws.current_req_started_at
    if elapsed >= 60 and ws.current_req_index < len(SUB_REQUESTS) - 1:
        log_step(f"Hết 60s cho request {SUB_REQUESTS[ws.current_req_index][0]} → chuyển sang mã tiếp theo")
        start_next_request(ws)


###############################################################################
# CALLBACKS
###############################################################################

def on_open(ws):
    log_step("WebSocket Connected")
    log_data("URL", WS_URL)

    ws.handshake_done = False
    ws.current_req_index = None
    ws.current_req_started_at = None

    send_handshake(ws)



def on_message(ws, message):
    # TEXT FRAME
    if isinstance(message, str):
        log_step("Text frame received")
        log_data("Text", repr(message))

        # Handshake ACK dạng text: "{}\x1e"
        if not ws.handshake_done and message.strip() == "{}" + RS:
            log_step("Handshake ACK (TEXT) từ server")
            ws.handshake_done = True
            send_apeg(ws)
            start_next_request(ws)   # bắt đầu gửi FPT, SSI, VIC
        return

    # BINARY FRAME
    msg_bytes = message
    log_step("Binary frame received")
    #log_data("Raw hex", msg_bytes.hex())

    ascii_preview = "".join(chr(b) if 32 <= b <= 126 else "." for b in msg_bytes)
    log_data("ASCII preview", ascii_preview)

    # 🔹 Handshake ACK dạng BINARY: b'{}\x1e' (base64 = 'e30e')
    if not ws.handshake_done:
        b64 = base64.b64encode(msg_bytes).decode("ascii")
        if msg_bytes == b'{}\x1e' or b64 == "e30e":
            log_step("Handshake ACK (BINARY) từ server – e30e")
            log_data("Handshake payload (hex)", msg_bytes.hex())
            ws.handshake_done = True
            send_apeg(ws)
            start_next_request(ws)
            return  # frame này chỉ là ACK, không phải Update*

    # ↓↓↓ Phần dưới giữ nguyên: xử lý UpdateLastPrices / UpdateRefPrices / UpdateOrderBooks

    COMMAND_HANDLERS = {
        b"UpdateLastPrices": handle_update_last_prices,
        b"UpdateRefPrices": handle_update_ref_prices,
        b"UpdateOrderBooks": handle_update_orderbooks,
    }

    found_cmd = None
    for cmd in COMMAND_HANDLERS:
        idx = msg_bytes.find(cmd)
        if idx != -1:
            found_cmd = cmd
            break

    if found_cmd:
        cmd_name = found_cmd.decode("ascii")
        log_data("Command detected", cmd_name)

        payload_start = msg_bytes.index(found_cmd) + len(found_cmd)
        header = msg_bytes[:payload_start]
        payload = msg_bytes[payload_start:]

        log_data("Header hex", header.hex())
        log_data("Payload hex", payload.hex())

        handler = COMMAND_HANDLERS[found_cmd]
        handler(payload)
    else:
        log_data("Command", "UNKNOWN (không thấy Update*)")

    maybe_switch_request(ws)


def on_error(ws, error):
    log_step("Error")
    log_data("Error detail", error)


def on_close(ws, code, reason):
    log_step("WebSocket Closed")
    log_data("Close code", code)
    log_data("Reason", reason)


###############################################################################
# MAIN
###############################################################################

if __name__ == "__main__":
    websocket.enableTrace(False)

    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    ws.run_forever(
        sslopt={"cert_reqs": ssl.CERT_NONE},
        ping_interval=30,
        ping_timeout=10,
    )
