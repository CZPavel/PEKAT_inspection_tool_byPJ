from __future__ import annotations

from typing import Any, Dict, Optional

from ..types import NormalizedEvaluation


def normalize_context_evaluation(
    context: Optional[Dict[str, Any]],
    fallback_ok_nok: Optional[str],
    latency_ms: int,
    oknok_source: str = "context_result",
) -> NormalizedEvaluation:
    if not isinstance(context, dict):
        return NormalizedEvaluation(
            eval_status="ERROR",
            result_bool=None,
            ok_nok=None,
            complete_time_s=None,
            complete_time_ms=None,
            detected_count=0,
        )

    result_bool = _extract_result_bool(context) if oknok_source == "context_result" else None
    if result_bool is True:
        eval_status = "OK"
        ok_nok = "OK"
    elif result_bool is False:
        eval_status = "NOK"
        ok_nok = "NOK"
    else:
        ok_nok = _normalize_ok_nok_string(fallback_ok_nok)
        if ok_nok == "OK":
            eval_status = "OK"
        elif ok_nok == "NOK":
            eval_status = "NOK"
        else:
            eval_status = "UNKNOWN"

    complete_time_s = _extract_complete_time_s(context)
    if complete_time_s is not None:
        complete_time_ms = int(round(complete_time_s * 1000.0))
    else:
        complete_time_ms = int(latency_ms)

    detected_count = 0
    rectangles = context.get("detectedRectangles")
    if isinstance(rectangles, list):
        detected_count = len(rectangles)

    return NormalizedEvaluation(
        eval_status=eval_status,
        result_bool=result_bool,
        ok_nok=ok_nok,
        complete_time_s=complete_time_s,
        complete_time_ms=complete_time_ms,
        detected_count=detected_count,
    )


def _extract_result_bool(context: Dict[str, Any]) -> Optional[bool]:
    value = context.get("result")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"ok", "true", "1"}:
            return True
        if lowered in {"nok", "ng", "false", "0"}:
            return False
    return None


def _extract_complete_time_s(context: Dict[str, Any]) -> Optional[float]:
    value = context.get("completeTime")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _normalize_ok_nok_string(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in {"ok", "true", "1"}:
        return "OK"
    if lowered in {"nok", "ng", "false", "0"}:
        return "NOK"
    return None
