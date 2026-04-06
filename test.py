import websocket
import ssl
import io
import json
import base64
import msgpack
import os
import re
import time
from pathlib import Path

TOKEN_ENV_VAR = "FIREANT_ACCESS_TOKEN"
TOKEN_FILE = Path("access_token.txt")
JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+")


def load_access_token() -> str:
    token = os.getenv(TOKEN_ENV_VAR, "").strip()
    if token:
        return token
    if TOKEN_FILE.exists():
        raw_text = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if raw_text:
            match = JWT_PATTERN.search(raw_text)
            if match:
                return match.group(0)
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            if len(lines) == 1:
                return lines[0]
    raise RuntimeError(
        f"Missing websocket token. Set {TOKEN_ENV_VAR} or provide {TOKEN_FILE}."
    )


WS_URL = f"wss://tradestation.fireant.vn/quote-lite?access_token={load_access_token()}"

RS = "\x1e"  # Record Separator

# Three subscribe requests, already encoded in Base64.
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
# PARSE UPDATE* PACKETS
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
# HANDSHAKE + SEND EACH REQUEST FOR 1 MINUTE PER SYMBOL
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
    log_step("Handshake completed - sending ApEG")
    log_data("ApEG raw hex", raw.hex())
    ws.send(raw, opcode=websocket.ABNF.OPCODE_BINARY)


def start_next_request(ws):
    """
    Send the next subscribe request in SUB_REQUESTS.
    Each request starts its own timer and stays active for 60 seconds.
    """
    if ws.current_req_index is None:
        ws.current_req_index = 0
    else:
        ws.current_req_index += 1

    if ws.current_req_index >= len(SUB_REQUESTS):
        log_step("All subscribe requests have been sent; continue listening only.")
        ws.current_req_started_at = None
        return

    name, b64 = SUB_REQUESTS[ws.current_req_index]
    raw = base64.b64decode(b64)

    ws.current_req_started_at = time.time()

    log_step(f"Sending subscribe request for {name} - listening for 60 seconds")
    log_data("Subscribe raw hex", raw.hex())
    ws.send(raw, opcode=websocket.ABNF.OPCODE_BINARY)


def maybe_switch_request(ws):
    """
    Switch to the next symbol once the current request has run for 60 seconds.
    This function is called whenever a binary frame is received.
    """
    if ws.current_req_started_at is None:
        return
    if ws.current_req_index is None:
        return

    elapsed = time.time() - ws.current_req_started_at
    if elapsed >= 60 and ws.current_req_index < len(SUB_REQUESTS) - 1:
        current_symbol = SUB_REQUESTS[ws.current_req_index][0]
        log_step(f"Request {current_symbol} reached 60s -> switching to the next symbol")
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

        # Handshake ACK in text form: "{}\x1e"
        if not ws.handshake_done and message.strip() == "{}" + RS:
            log_step("Handshake ACK (TEXT) from server")
            ws.handshake_done = True
            send_apeg(ws)
            start_next_request(ws)  # start sending FPT, SSI, VIC
        return

    # BINARY FRAME
    msg_bytes = message
    log_step("Binary frame received")
    # log_data("Raw hex", msg_bytes.hex())

    ascii_preview = "".join(chr(b) if 32 <= b <= 126 else "." for b in msg_bytes)
    log_data("ASCII preview", ascii_preview)

    # Handshake ACK in binary form: b'{}\x1e' (base64 = 'e30e')
    if not ws.handshake_done:
        b64 = base64.b64encode(msg_bytes).decode("ascii")
        if msg_bytes == b"{}\x1e" or b64 == "e30e":
            log_step("Handshake ACK (BINARY) from server - e30e")
            log_data("Handshake payload (hex)", msg_bytes.hex())
            ws.handshake_done = True
            send_apeg(ws)
            start_next_request(ws)
            return  # this frame is only an ACK, not an Update* payload

    # The section below keeps the existing UpdateLastPrices / UpdateRefPrices / UpdateOrderBooks handling.
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
        log_data("Command", "UNKNOWN (no Update* command found)")

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
