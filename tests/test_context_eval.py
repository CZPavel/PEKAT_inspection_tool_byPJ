from pektool.core.context_eval import normalize_context_evaluation


def test_context_result_ok_and_complete_time():
    context = {
        "result": True,
        "completeTime": 0.125,
        "detectedRectangles": [{"id": 1}, {"id": 2}],
    }
    evaluation = normalize_context_evaluation(
        context=context,
        fallback_ok_nok=None,
        latency_ms=200,
        oknok_source="context_result",
    )
    assert evaluation.eval_status == "OK"
    assert evaluation.result_bool is True
    assert evaluation.ok_nok == "OK"
    assert evaluation.complete_time_s == 0.125
    assert evaluation.complete_time_ms == 125
    assert evaluation.detected_count == 2


def test_fallback_to_result_field_value():
    context = {"completeTime": 0.2}
    evaluation = normalize_context_evaluation(
        context=context,
        fallback_ok_nok="NOK",
        latency_ms=180,
        oknok_source="context_result",
    )
    assert evaluation.eval_status == "NOK"
    assert evaluation.result_bool is None
    assert evaluation.ok_nok == "NOK"
    assert evaluation.complete_time_ms == 200


def test_result_field_mode_ignores_context_result():
    context = {"result": True}
    evaluation = normalize_context_evaluation(
        context=context,
        fallback_ok_nok="NOK",
        latency_ms=99,
        oknok_source="result_field",
    )
    assert evaluation.eval_status == "NOK"
    assert evaluation.result_bool is None
    assert evaluation.ok_nok == "NOK"
    assert evaluation.complete_time_ms == 99
