import numpy as np
import pandas as pd
import xarray as xr

from src.forcing import normalize_noleap_calendar


def test_normalize_noleap_calendar_removes_feb_29_and_sets_metadata() -> None:
    time = pd.date_range("2016-02-27", "2016-03-02", freq="D")
    ds = xr.Dataset({"pr": ("time", np.arange(len(time), dtype=float))}, coords={"time": time})

    fixed = normalize_noleap_calendar(ds)

    assert len(fixed.time) == 4
    assert str(fixed.time.dt.calendar) == "noleap"
    assert fixed.time.encoding.get("calendar") == "365_day"
    assert "2016-02-29" not in {str(value)[:10] for value in fixed.time.values}