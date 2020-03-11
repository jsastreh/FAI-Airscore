import pytest
from track import Track
from datetime import datetime, date
from flight_result import Flight_result
from .obj_factories import test_task


def test_track_read():
    test_track = Track.read_file('/app/tests/test_igc_1.igc', par_id=1)
    assert len(test_track.fixes) == 13856
    assert test_track.date == date(2019, 3, 9)
    assert test_track.gnss_alt_valid
    assert test_track.press_alt_valid
    assert test_track.flight.valid
    assert len(test_track.flight.fixes)
    assert test_track.flight.glider_type == 'OZONE Zeno'
    assert test_track.flight.date_timestamp == 1552089600.0


def test_track_flight_check():
    test_track = Track.read_file('/app/tests/test_igc_2.igc', par_id=1)
    test_result = Flight_result.check_flight(test_track.flight, test_task)
    assert int(test_result.distance_flown) == 64360
    assert test_result.best_waypoint_achieved == 'Goal'
    assert len(test_result.waypoints_achieved) == test_result.waypoints_made
    assert test_result.SSS_time == 41400
    assert test_result.ESS_time == 50555
    assert test_result.ESS_altitude == 880.0
    assert test_result.real_start_time == 41428
    assert test_result.flight_time == 12158.0
    assert test_result.waypoints_achieved[1] == ['TP01', 43947, 1445.0]