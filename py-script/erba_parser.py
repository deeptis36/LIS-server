#!/usr/bin/env python3
"""
ERBA EM-200 / MultiXL ASTM parser.

This file ONLY parses the completed ASTM message.
TCP communication and API communication remain in erba_listener.py.

The parser preserves all fields so that unknown ERBA/MultiXL field positions
are never silently lost.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Union


def _decode(message: Union[str, bytes, bytearray]) -> str:
    if isinstance(message, (bytes, bytearray)):
        return bytes(message).decode("ascii", errors="replace")
    if isinstance(message, str):
        return message
    raise TypeError("message must be str, bytes, or bytearray")


def _clean_transport(text: str) -> str:
    # Transport characters are removed because the listener already validates
    # ASTM frames and reconstructs the message.
    for ch in ("\x02", "\x03", "\x04", "\x05", "\x06", "\x15", "\x17"):
        text = text.replace(ch, "")

    return text.replace("\r\n", "\r").replace("\n", "")


def _remove_frame_number(record: str) -> str:
    # Protects against a listener/parser being given 1H|..., 2P|..., etc.
    if len(record) >= 2 and record[0].isdigit() and record[1].upper() in {
        "H", "P", "O", "R", "C", "L", "Q"
    }:
        return record[1:]
    return record


def _numeric(value: str) -> Any:
    value = value.strip()
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value):
        try:
            return float(value)
        except ValueError:
            pass
    return value


def _components(value: str) -> List[str]:
    return value.split("^") if value else []


def parse_astm_message(
    message: Union[str, bytes, bytearray]
) -> Dict[str, Any]:
    """
    Parse a completed ERBA ASTM message into JSON-friendly Python data.

    Output intentionally follows the structure already used by the previous
    working listener:
        raw_text
        records[]
            type
            raw
            fields

    Additional convenient sections are included:
        header
        patient
        orders
        results
        sample_id
        parsed_at

    The original raw record is always preserved.
    """

    text = _clean_transport(_decode(message))

    lines = [
        _remove_frame_number(line.strip())
        for line in text.split("\r")
        if line.strip()
    ]

    records: List[Dict[str, Any]] = []
    header: Dict[str, Any] = {}
    patient: Dict[str, Any] = {}
    orders: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    terminator: Dict[str, Any] = {}

    for raw_record in lines:
        fields = raw_record.split("|")
        record_type = fields[0].strip().upper() if fields else ""

        record: Dict[str, Any] = {
            "type": record_type,
            "raw": raw_record,
            "fields": fields,
        }

        if record_type == "H":
            header = {
                "raw_fields": fields,
                "delimiters": fields[1] if len(fields) > 1 else "",
                "sender": fields[2] if len(fields) > 2 else "",
                "sender_name": fields[3] if len(fields) > 3 else "",
            }

            for i, value in enumerate(fields[4:], start=4):
                header[f"field_{i}"] = value

            record["data"] = header

        elif record_type == "P":
            patient = {
                "raw_fields": fields,
                "sequence": fields[1] if len(fields) > 1 else "",
                "practice_assigned_patient_id": fields[2] if len(fields) > 2 else "",
                "laboratory_assigned_patient_id": fields[3] if len(fields) > 3 else "",
                "patient_id_2": fields[4] if len(fields) > 4 else "",
                "patient_name": fields[5] if len(fields) > 5 else "",
                "birth_date": fields[7] if len(fields) > 7 else "",
                "sex": fields[8] if len(fields) > 8 else "",
            }

            for i, value in enumerate(fields[9:], start=9):
                patient[f"field_{i}"] = value

            record["data"] = patient

        elif record_type == "O":
            order = {
                "raw_fields": fields,
                "sequence": fields[1] if len(fields) > 1 else "",
                "specimen_id": fields[2] if len(fields) > 2 else "",
                "instrument_specimen_id": fields[3] if len(fields) > 3 else "",
                "test_code": fields[4] if len(fields) > 4 else "",
                "priority": fields[5] if len(fields) > 5 else "",
                "requested_date_time": fields[6] if len(fields) > 6 else "",
                "specimen_collection_date_time": fields[7] if len(fields) > 7 else "",
                "specimen_received_date_time": fields[8] if len(fields) > 8 else "",
                "specimen_type": fields[9] if len(fields) > 9 else "",
            }

            test_code = order["test_code"]
            order["test_components"] = _components(test_code)
            order["test_code_clean"] = (
                next((x for x in reversed(_components(test_code)) if x), "")
            )

            for i, value in enumerate(fields[10:], start=10):
                order[f"field_{i}"] = value

            orders.append(order)
            record["data"] = order

        elif record_type == "R":
            result = {
                "raw_fields": fields,
                "sequence": fields[1] if len(fields) > 1 else "",
                "universal_test_id": fields[2] if len(fields) > 2 else "",
                "data_type": fields[3] if len(fields) > 3 else "",
                "value": fields[4] if len(fields) > 4 else "",
                "units": fields[5] if len(fields) > 5 else "",
                "reference_range": fields[6] if len(fields) > 6 else "",
                "abnormal_flags": fields[7] if len(fields) > 7 else "",
                "nature_of_abnormality": fields[8] if len(fields) > 8 else "",
                "result_status": fields[9] if len(fields) > 9 else "",
                "date_time_of_test": fields[10] if len(fields) > 10 else "",
                "operator_id": fields[11] if len(fields) > 11 else "",
                "date_time_of_result": fields[12] if len(fields) > 12 else "",
                "instrument_id": fields[13] if len(fields) > 13 else "",
                "dilution_factor": fields[14] if len(fields) > 14 else "",
                "result_comments": fields[15] if len(fields) > 15 else "",
            }

            test_id = result["universal_test_id"]
            components = _components(test_id)
            non_empty = [x for x in components if x]

            result["test_components"] = components
            result["test_code"] = non_empty[-1] if non_empty else test_id
            result["numeric_value"] = _numeric(result["value"])

            for i, value in enumerate(fields[16:], start=16):
                result[f"field_{i}"] = value

            results.append(result)
            record["data"] = result

        elif record_type == "L":
            terminator = {
                "raw_fields": fields,
                "sequence": fields[1] if len(fields) > 1 else "",
                "termination_code": fields[2] if len(fields) > 2 else "",
                "termination_text": fields[3] if len(fields) > 3 else "",
            }
            record["data"] = terminator

        records.append(record)

    sample_id = find_sample_id_from_records(records)

    return {
        "source_device": "",
        "parser": {
            "name": "ERBA EM-200 ASTM Parser",
            "version": "2.1.0",
            "parsed_at": datetime.now().isoformat(timespec="seconds"),
            "record_count": len(records),
        },
        "sample_id": sample_id,
        "header": header,
        "patient": patient,
        "orders": orders,
        "results": results,
        "terminator": terminator,
        # Kept for compatibility with the previous listener.
        "raw_text": text,
        "records": records,
    }


def find_sample_id_from_records(records: List[Dict[str, Any]]) -> str:
    """
    Sample ID priority:
      1. O.2 specimen_id
      2. O.3 instrument_specimen_id
      3. first non-empty field after O/sequence

    SAMPLE_ID_OVERRIDE remains handled by the listener/.env.
    """
    for record in records:
        if record.get("type") != "O":
            continue

        fields = record.get("fields", [])

        if len(fields) > 2 and fields[2].strip():
            return fields[2].strip()

        if len(fields) > 3 and fields[3].strip():
            return fields[3].strip()

        for value in fields[2:]:
            value = value.strip()
            if value:
                return value

    return ""


def parse_astm_json(
    message: Union[str, bytes, bytearray],
    *,
    pretty: bool = True,
) -> str:
    """Convenience wrapper returning JSON text."""
    data = parse_astm_message(message)
    return json.dumps(
        data,
        indent=2 if pretty else None,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    sample = (
        "H|\\^&|ERBA|EM200||||LIS\r"
        "P|1\r"
        "O|1|SAMP-33872||GLU^Glucose\r"
        "R|1|^^^GLU|NM|98|mg/dL|70-110|N||F\r"
        "L|1|N\r"
    )

    print(parse_astm_json(sample))
