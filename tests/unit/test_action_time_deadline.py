from src.domain.action_time_deadline import ActionTimeDeadline


def test_global_deadline_uses_the_shortest_source_and_monotonic_budget():
    deadline = ActionTimeDeadline.start(
        opened_wall_ms=1_000,
        opened_monotonic_ms=50_000,
        expiry_candidates_ms=(8_000, 1_500, 9_000),
        system_budget_ms=30_000,
    )

    assert deadline.global_deadline_ms == 1_500
    assert deadline.remaining_ms(monotonic_now_ms=50_499) == 1
    assert deadline.remaining_ms(monotonic_now_ms=50_500) == 0


def test_later_fact_can_only_shorten_an_action_time_deadline():
    deadline = ActionTimeDeadline.start(
        opened_wall_ms=1_000,
        opened_monotonic_ms=20_000,
        expiry_candidates_ms=(20_000,),
        system_budget_ms=30_000,
    )

    assert deadline.shorten(expiry_candidates_ms=(40_000,)).global_deadline_ms == 20_000
    assert deadline.shorten(expiry_candidates_ms=(1_250,)).global_deadline_ms == 1_250
