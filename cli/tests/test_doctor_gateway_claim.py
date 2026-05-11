from unittest.mock import patch

from robot_md.doctor import check_drivers


def test_doctor_explains_ttyacm_owned_by_gateway():
    """When /dev/ttyACM0 is owned by robot-md-gateway user, surface that as
    informational warning, not a hard fail. Gateway-as-bus-owner is intended."""
    fm = {"drivers": [{"id": "serial-ttyACM0", "protocol": "serial",
                       "port": "/dev/ttyACM0"}]}

    with patch("pathlib.Path.exists", return_value=True), \
         patch("os.access", return_value=False), \
         patch("robot_md.doctor._is_owned_by_gateway", return_value=True):
        results = check_drivers(fm)

    matching = [r for r in results if "gateway" in r.detail.lower()
                and r.status == "warn"]
    assert matching, (
        f"doctor should emit warn-with-gateway-explanation; got: "
        f"{[(r.status, r.detail) for r in results]}"
    )
