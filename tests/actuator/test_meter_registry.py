"""The meter registry counts and times, and writes what it measured in Prometheus's text format."""

import pytest

from snakeboot.actuator import InvalidMeterError, MeterRegistry


def test_a_counter_counts_and_prometheus_sees_it_as_total() -> None:
    meters = MeterRegistry()
    meters.counter("games_started", "Games started", tags={"game": "tictactoe"}).increment()
    meters.counter("games_started", "Games started", tags={"game": "tictactoe"}).increment(2)

    assert meters.scrape() == (
        "# HELP games_started_total Games started\n"
        "# TYPE games_started_total counter\n"
        'games_started_total{game="tictactoe"} 3.0\n'
    )


def test_a_timer_is_a_cumulative_histogram_with_a_count_and_a_sum() -> None:
    meters = MeterRegistry()
    timer = meters.timer("ai_move_seconds", "How long the AI thinks")
    timer.record(0.003)
    timer.record(0.3)

    scraped = meters.scrape().splitlines()

    assert scraped[:3] == [
        "# HELP ai_move_seconds How long the AI thinks",
        "# TYPE ai_move_seconds histogram",
        'ai_move_seconds_bucket{le="0.005"} 1.0',
    ]
    assert 'ai_move_seconds_bucket{le="0.25"} 1.0' in scraped
    assert 'ai_move_seconds_bucket{le="0.5"} 2.0' in scraped
    assert 'ai_move_seconds_bucket{le="+Inf"} 2.0' in scraped
    assert "ai_move_seconds_count 2.0" in scraped
    assert "ai_move_seconds_sum 0.303" in scraped


def test_a_timer_times_a_block_even_when_it_raises() -> None:
    timer = MeterRegistry().timer("work_seconds", "Work")

    with pytest.raises(RuntimeError), timer.time():
        raise RuntimeError

    assert timer.count == 1


def test_a_gauge_is_read_whenever_prometheus_asks() -> None:
    meters, queue = MeterRegistry(), [1, 2]
    meters.gauge("queue_length", "Waiting messages", lambda: len(queue))
    queue.append(3)

    assert "queue_length 3.0" in meters.scrape()


def test_a_gauge_that_cannot_be_read_is_left_out() -> None:
    meters = MeterRegistry()
    meters.gauge("broken", "Cannot be read", lambda: 1 / 0)

    assert meters.scrape() == "# HELP broken Cannot be read\n# TYPE broken gauge\n"


def test_tag_values_are_escaped() -> None:
    meters = MeterRegistry()
    meters.counter("calls", "Calls", tags={"uri": 'say "hi"\\'}).increment()

    assert 'calls_total{uri="say \\"hi\\"\\\\"} 1.0' in meters.scrape()


def test_names_prometheus_refuses_are_refused() -> None:
    meters = MeterRegistry()

    with pytest.raises(InvalidMeterError, match="no metric name"):
        meters.counter("games-started", "Games")
    with pytest.raises(InvalidMeterError, match="no tag name"):
        meters.counter("games", "Games", tags={"le": "1"})


def test_one_name_is_one_kind_of_meter() -> None:
    meters = MeterRegistry()
    meters.counter("games", "Games")

    with pytest.raises(InvalidMeterError, match="games is a counter already"):
        meters.timer("games", "Games")


def test_a_counter_never_goes_down() -> None:
    with pytest.raises(InvalidMeterError, match="only goes up"):
        MeterRegistry().counter("games", "Games").increment(-1)
