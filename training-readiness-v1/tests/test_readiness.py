from dvizh_training_test.readiness import ReadinessInputs, evaluate_readiness


def test_green_day():
    result = evaluate_readiness(ReadinessInputs(
        sleep_hours=8,
        sleep_quality=3,
        energy=3,
        soreness=0,
        pain=0,
        stress=0,
    ))
    assert result.status == "green"
    assert result.score >= 75
    assert result.rpe_cap == 8


def test_yellow_day_from_sleep_and_soreness():
    result = evaluate_readiness(ReadinessInputs(
        sleep_hours=5.5,
        sleep_quality=1,
        energy=2,
        soreness=2,
        pain=0,
        stress=1,
        volleyball_today=True,
        lower_load_36h=300,
    ))
    assert result.status in {"yellow", "red"}
    assert result.score < 75
    assert result.rpe_cap <= 6


def test_red_day_for_systemic_illness():
    result = evaluate_readiness(ReadinessInputs(
        sleep_hours=8,
        sleep_quality=3,
        energy=3,
        soreness=0,
        pain=0,
        stress=0,
        illness="systemic",
    ))
    assert result.status == "red"
    assert result.strength_level == "recovery"
    assert result.volleyball_level == "stop"


def test_red_flag_is_urgent():
    result = evaluate_readiness(ReadinessInputs(
        sleep_hours=8,
        sleep_quality=3,
        energy=3,
        soreness=0,
        pain=0,
        stress=0,
        red_flag=True,
    ))
    assert result.status == "red"
    assert result.urgent is True


def test_invalid_scale_rejected():
    try:
        evaluate_readiness(ReadinessInputs(
            sleep_hours=8,
            sleep_quality=4,
            energy=3,
            soreness=0,
            pain=0,
            stress=0,
        ))
    except ValueError:
        pass
    else:
        raise AssertionError("invalid scale accepted")
