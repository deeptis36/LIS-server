#!/usr/bin/env python3
"""
ERBA / MultiXL ASTM TCP Host Listener
-------------------------------------

This is the NETWORK LISTENER.

Responsibilities:
    1. Listen on TCP/IP 0.0.0.0:5002 (from .env).
    2. Perform ASTM ENQ/ACK and frame ACK/NAK handshake.
    3. Reconstruct a complete ASTM message.
    4. Pass the message to erba_parser.py.
    5. Save the exact raw message.
    6. Save the parsed JSON.
    7. Send the existing working API payload to Coco Hospitals.

The parser is intentionally kept in a separate file:
    erba_parser.py

The API endpoint/configuration comes from .env.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from erba_parser import parse_astm_message


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

load_dotenv()

LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "5002"))

API_ENABLED = os.getenv(
    "API_ENABLED", "true"
).strip().lower() in ("1", "true", "yes", "y")

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "https://rims.admin.cocohospitals.com",
).rstrip("/")

API_PATH_TEMPLATE = os.getenv(
    "API_PATH_TEMPLATE",
    "/api/v1/hospital/rims/analyzer-webhook",
)

API_TOKEN = os.getenv("API_TOKEN", "").strip()
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "20"))

SAMPLE_ID_OVERRIDE = os.getenv(
    "SAMPLE_ID_OVERRIDE", ""
).strip()

CONFIGURED_SOURCE_DEVICE = os.getenv(
    "SOURCE_DEVICE", ""
).strip()

LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# ASTM control characters
# ---------------------------------------------------------------------------

STX = 0x02
ETX = 0x03
EOT = 0x04
ENQ = 0x05
ACK = 0x06
NAK = 0x15
ETB = 0x17
CR = 0x0D
LF = 0x0A


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(
            LOG_DIR / "erba_listener.log",
            encoding="utf-8",
        ),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("erba-listener")


# ---------------------------------------------------------------------------
# ASTM frame handling
# ---------------------------------------------------------------------------

def calculate_checksum(frame_number_and_text: bytes, terminator: int) -> str:
    """Calculate the two-character ASTM checksum."""
    total = sum(frame_number_and_text + bytes([terminator]))
    return f"{total & 0xFF:02X}"


def validate_frame(frame: bytes):
    """
    Expected frame:

        STX + frame_number + text + ETX/ETB + checksum(2) + CR + LF

    Returns:
        (True, frame_number, payload, terminator)
    or:
        (False, reason, None, None)
    """
    if len(frame) < 7:
        return False, "Frame too short", None, None

    if frame[0] != STX:
        return False, "Missing STX", None, None

    if frame[-2:] != bytes([CR, LF]):
        return False, "Missing CR/LF", None, None

    terminator_index = len(frame) - 5
    terminator = frame[terminator_index]

    if terminator not in (ETX, ETB):
        return False, "Missing ETX/ETB", None, None

    frame_number = frame[1:2]

    if len(frame_number) != 1 or not chr(frame_number[0]).isdigit():
        return False, "Invalid frame number", None, None

    received_checksum = frame[
        terminator_index + 1:terminator_index + 3
    ]

    try:
        received_checksum_text = received_checksum.decode(
            "ascii"
        ).upper()
    except UnicodeDecodeError:
        return False, "Checksum is not ASCII", None, None

    checksum_input = frame[1:terminator_index]
    expected_checksum = calculate_checksum(
        checksum_input,
        terminator,
    )

    if received_checksum_text != expected_checksum:
        return (
            False,
            f"Checksum mismatch: received={received_checksum_text}, "
            f"expected={expected_checksum}",
            None,
            None,
        )

    payload = frame[2:terminator_index]

    return (
        True,
        chr(frame_number[0]),
        payload,
        terminator,
    )


def extract_frames(buffer: bytearray):
    """Extract complete ASTM frames ending in CR LF."""
    frames = []

    while True:
        try:
            start = buffer.index(STX)
        except ValueError:
            return frames, bytearray()

        if start > 0:
            del buffer[:start]

        end = buffer.find(bytes([CR, LF]), 1)

        if end == -1:
            return frames, buffer

        frame_end = end + 2
        frame = bytes(buffer[:frame_end])
        del buffer[:frame_end]
        frames.append(frame)


# ---------------------------------------------------------------------------
# Sample extraction
# ---------------------------------------------------------------------------

def find_sample_id(parsed: dict) -> str:
    if SAMPLE_ID_OVERRIDE:
        return SAMPLE_ID_OVERRIDE

    sample_id = str(parsed.get("sample_id") or "").strip()

    if sample_id:
        return sample_id

    # Extra compatibility fallback.
    for order in parsed.get("orders", []):
        for key in ("specimen_id", "instrument_specimen_id"):
            value = str(order.get(key) or "").strip()
            if value:
                return value

    return ""


def find_source_device(parsed: dict) -> str:
    header = parsed.get("header") or {}
    sender = str(header.get("sender") or "").strip()
    sender_name = str(header.get("sender_name") or "").strip()

    if sender and sender_name:
        return f"{sender}_{sender_name}"

    if sender:
        return sender

    return CONFIGURED_SOURCE_DEVICE


# ---------------------------------------------------------------------------
# Raw / JSON persistence
# ---------------------------------------------------------------------------

def save_message_files(
    raw_message: bytes,
    parsed: dict,
) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    messages_dir = LOG_DIR / "messages"
    json_dir = LOG_DIR / "json"

    messages_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    raw_file = messages_dir / f"erba_{timestamp}.txt"
    json_file = json_dir / f"erba_{timestamp}.json"

    # Exact reconstructed ASTM payload.
    raw_file.write_bytes(raw_message)

    # Parsed JSON.
    json_file.write_text(
        json.dumps(
            parsed,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    logger.info("RAW FILE  : %s", raw_file)
    logger.info("JSON FILE : %s", json_file)

    return raw_file, json_file


# ---------------------------------------------------------------------------
# Coco Hospitals API
# ---------------------------------------------------------------------------

def build_api_payload(
    raw_message: bytes,
    parsed: dict,
) -> dict:
    """
    Mirror the working MAGLUMI approach: send the parsed system/analyzer
    data to the analyzer-webhook. No appointment_id is required here.
    """
    return parsed


def send_to_api(
    raw_message: bytes,
    parsed: dict,
):
    if not API_ENABLED:
        logger.info("API_ENABLED=false -> API call skipped.")
        return None

    payload = build_api_payload(
        raw_message=raw_message,
        parsed=parsed,
    )

    url = API_BASE_URL + API_PATH_TEMPLATE

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    logger.info("API URL: %s", url)
    logger.info(
        "API PAYLOAD: %s",
        json.dumps(payload, ensure_ascii=False),
    )

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=API_TIMEOUT,
        )

        logger.info(
            "API RESPONSE: HTTP %s | %s",
            response.status_code,
            response.text[:2000],
        )

        response.raise_for_status()

        logger.info(
            "API SUCCESS: source_device=%s sample_id=%s",
            parsed.get("source_device"),
            parsed.get("sample_id"),
        )

        return response

    except requests.RequestException as exc:
        logger.exception(
            "API REQUEST FAILED: %s",
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Complete message processing
# ---------------------------------------------------------------------------

def process_complete_message(
    message_buffer: bytearray,
    frame_count: int,
):
    raw_message = bytes(message_buffer)

    logger.info("=" * 80)
    logger.info("COMPLETE ERBA ASTM MESSAGE")
    logger.info("Frames: %s", frame_count)
    logger.info(
        "RAW HEX: %s",
        raw_message.hex(" "),
    )
    logger.info(
        "RAW TEXT:\n%s",
        raw_message.decode("ascii", errors="replace"),
    )

    # Parse in the separate parser file.
    parsed = parse_astm_message(raw_message)
    parsed["source_device"] = find_source_device(parsed)

    sample_id = find_sample_id(parsed)

    raw_file, json_file = save_message_files(
        raw_message,
        parsed,
    )

    logger.info("Source Device : %s", parsed.get("source_device", ""))
    logger.info("Sample ID     : %s", sample_id or "<not detected>")
    logger.info(
        "Orders        : %s",
        len(parsed.get("orders", [])),
    )
    logger.info(
        "Results       : %s",
        len(parsed.get("results", [])),
    )

    for record in parsed.get("records", []):
        logger.info(
            "RECORD %s: %s",
            record.get("type"),
            record.get("raw"),
        )

    # API is called AFTER raw + JSON are safely saved.
    send_to_api(
        raw_message=raw_message,
        parsed=parsed,
    )

    logger.info("=" * 80)


# ---------------------------------------------------------------------------
# TCP connection
# ---------------------------------------------------------------------------

def handle_connection(conn: socket.socket, addr):
    logger.info(
        "TCP CONNECTION: %s:%s",
        addr[0],
        addr[1],
    )

    conn.settimeout(60)

    buffer = bytearray()
    message_buffer = bytearray()
    frame_count = 0
    total_bytes = 0

    try:
        while True:
            data = conn.recv(4096)

            if not data:
                logger.info(
                    "Connection closed by client. total_bytes=%s",
                    total_bytes,
                )
                break

            total_bytes += len(data)

            logger.info(
                "RX %s bytes | HEX=%s",
                len(data),
                data.hex(" "),
            )

            # ---------------------------------------------------------------
            # ENQ -> ACK
            # ---------------------------------------------------------------
            if ENQ in data:
                logger.info("ENQ received -> ACK")
                conn.sendall(bytes([ACK]))
                data = data.replace(bytes([ENQ]), b"")

            # ---------------------------------------------------------------
            # EOT
            # ---------------------------------------------------------------
            if EOT in data:
                eot_index = data.find(bytes([EOT]))

                if eot_index >= 0:
                    before_eot = data[:eot_index]

                    if before_eot:
                        buffer.extend(before_eot)

                    logger.info("EOT received.")

                    if message_buffer:
                        process_complete_message(
                            message_buffer,
                            frame_count,
                        )

                    message_buffer.clear()
                    frame_count = 0
                    data = data[eot_index + 1:]

            # ---------------------------------------------------------------
            # Frames
            # ---------------------------------------------------------------
            if data:
                buffer.extend(data)

            frames, buffer = extract_frames(buffer)

            for frame in frames:
                valid, info, payload, terminator = validate_frame(frame)

                if not valid:
                    logger.error(
                        "INVALID ASTM FRAME: %s | HEX=%s",
                        info,
                        frame.hex(" "),
                    )
                    conn.sendall(bytes([NAK]))
                    continue

                frame_number = info
                frame_count += 1

                logger.info(
                    "VALID FRAME #%s | %s | PAYLOAD=%r",
                    frame_number,
                    "ETX" if terminator == ETX else "ETB",
                    payload,
                )

                message_buffer.extend(payload)

                # ACK every valid frame.
                conn.sendall(bytes([ACK]))
                logger.info(
                    "ACK sent for frame #%s",
                    frame_number,
                )

                # ETX marks final ASTM frame.
                if terminator == ETX:
                    process_complete_message(
                        message_buffer,
                        frame_count,
                    )

                    message_buffer.clear()
                    frame_count = 0

    except socket.timeout:
        logger.warning("Socket timeout. Closing connection.")

    except ConnectionResetError:
        logger.warning("Client reset the connection.")

    except Exception:
        logger.exception(
            "Unexpected connection error."
        )

    finally:
        try:
            conn.close()
        except Exception:
            pass

        logger.info("TCP connection closed.\n")


# ---------------------------------------------------------------------------
# Main server
# ---------------------------------------------------------------------------

def main():
    logger.info("=" * 80)
    logger.info("ERBA / MultiXL ASTM TCP HOST LISTENER")
    logger.info("=" * 80)
    logger.info(
        "Listening on %s:%s",
        LISTEN_HOST,
        LISTEN_PORT,
    )
    logger.info(
        "API enabled: %s",
        API_ENABLED,
    )
    logger.info(
        "API base: %s",
        API_BASE_URL,
    )
    logger.info(
        "API path: %s",
        API_PATH_TEMPLATE,
    )
    logger.info(
        "LOG DIR: %s",
        LOG_DIR.resolve(),
    )
    logger.info("Press Ctrl+C to stop.")
    logger.info("=" * 80)

    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )

    try:
        server.bind(
            (LISTEN_HOST, LISTEN_PORT)
        )

        server.listen(5)

        logger.info(
            "LISTENING SUCCESSFULLY on TCP %s",
            LISTEN_PORT,
        )

        while True:
            conn, addr = server.accept()
            handle_connection(
                conn,
                addr,
            )

    except KeyboardInterrupt:
        logger.info("Stopped by user.")

    except OSError as exc:
        logger.exception(
            "Could not bind to %s:%s. "
            "Check: netstat -ano | findstr :%s",
            LISTEN_HOST,
            LISTEN_PORT,
            LISTEN_PORT,
        )
        raise exc

    finally:
        server.close()


if __name__ == "__main__":
    main()
