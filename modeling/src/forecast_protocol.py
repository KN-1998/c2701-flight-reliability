"""Calendar and model settings for a frozen, fixed-origin experiment."""
from __future__ import annotations

from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from numbers import Integral, Real


@dataclass(frozen=True)
class ForecastProtocol:
    """Executed dates are ISO calendar dates, with both endpoints inclusive."""

    label: str
    fit_start: str
    fit_end: str
    tune_start: str
    refit_end: str
    calibration_start: str
    calibration_end: str
    required_months: tuple[str, ...]
    tune_months: tuple[str, ...]
    calibration_months: tuple[str, ...]
    new_core_months: tuple[str, ...]
    previously_scored_months: tuple[str, ...]
    late_months: tuple[str, ...]
    holdout_months: tuple[str, ...]
    thresholds_minutes: tuple[int, ...]
    fit_cap: int
    seed: int
    C_grid: tuple[float, ...]
    baseline_strength: float


def _date(value, field):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return parsed
    except (TypeError, ValueError):
        pass
    raise ValueError(f'{field} must have YYYY-MM-DD format')


def _month_end(day):
    return day.replace(day=monthrange(day.year, day.month)[1])


def _months(mapping, field, *, contiguous=False):
    values = mapping[field]
    if not isinstance(values, (list, tuple)):
        raise ValueError(f'{field} must be a sequence of YYYY-MM months')
    result = []
    for value in values:
        if not isinstance(value, str) or len(value) != 7:
            raise ValueError(f'{field} must use YYYY-MM months')
        result.append(_date(value + '-01', field))
    if len(result) != len(set(result)):
        raise ValueError(f'{field} contains duplicate months')
    if contiguous and (not result or any(
            _month_end(a) + timedelta(days=1) != b for a, b in zip(result, result[1:]))):
        raise ValueError(f'{field} must contain consecutive months in chronological order')
    return result


def _int(value, field, minimum):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f'{field} must be an integer >= {minimum}')
    return int(value)


def _number(value, field, *, zero_allowed=False):
    if (isinstance(value, bool) or not isinstance(value, Real)
            or not isfinite(value) or value < 0 or (not zero_allowed and value == 0)):
        raise ValueError(f'{field} must be a finite {"nonnegative" if zero_allowed else "positive"} number')
    return float(value)


def parse_forecast_protocol(value):
    """Read the v5 contract and derive the windows actually used by all v6 models.

    Coverage is required from fit_start through calibration_end. The historical v5
    contract omitted fit_start, which defaults to January 1 of fit_end's year.
    Holdout months can have gaps and must follow calibration.
    """
    if isinstance(value, ForecastProtocol):
        return value
    if not isinstance(value, Mapping):
        raise ValueError('Forecast protocol must be a mapping')

    required = (
        'fit_end', 'tune_months', 'refit_end', 'calibration_months', 'new_core_months',
        'previously_scored_months', 'late_months', 'thresholds_minutes', 'fit_cap',
        'seed', 'C_grid', 'baseline_strength',
    )
    missing = [name for name in required if name not in value]
    if missing:
        raise ValueError('Missing forecast protocol fields: ' + ', '.join(missing))
    label = value.get('label', 'configured_primary')
    if not isinstance(label, str) or not label.strip():
        raise ValueError('label must be a nonempty string')
    if value.get('primary_loss', 'Brier') != 'Brier':
        raise ValueError('The configured runner supports Brier as its primary loss')

    fit_end = _date(value['fit_end'], 'fit_end')
    fit_start = _date(value.get('fit_start', date(fit_end.year, 1, 1).isoformat()), 'fit_start')
    refit_end = _date(value['refit_end'], 'refit_end')
    tune = _months(value, 'tune_months', contiguous=True)
    calibration = _months(value, 'calibration_months', contiguous=True)
    if (fit_start.day != 1 or fit_start > fit_end or fit_end != _month_end(fit_end)
            or tune[0] != fit_end + timedelta(days=1)
            or refit_end != _month_end(tune[-1])
            or calibration[0] != refit_end + timedelta(days=1)):
        raise ValueError('Fit, tuning, refit and calibration windows must be ordered, adjacent full months')
    previous_scope = _months(value, 'previously_scored_months')
    new_scope = _months(value, 'new_core_months')
    later_scope = _months(value, 'late_months')
    holdout = sorted(new_scope + previous_scope + later_scope)
    cal_end = _month_end(calibration[-1])
    if not holdout or len(holdout) != len(set(holdout)) or holdout[0] <= cal_end:
        raise ValueError('Holdout months must be unique across scopes and begin after calibration')

    thresholds = value['thresholds_minutes']
    if not isinstance(thresholds, (list, tuple)) or not thresholds:
        raise ValueError('thresholds_minutes must be a nonempty sequence')
    thresholds = tuple(_int(t, 'thresholds_minutes', 1) for t in thresholds)
    if tuple(sorted(set(thresholds))) != thresholds:
        raise ValueError('thresholds_minutes must be unique and ascending')
    grid = value['C_grid']
    if not isinstance(grid, (list, tuple)) or not grid:
        raise ValueError('C_grid must be a nonempty sequence')
    grid = tuple(_number(c, 'C_grid') for c in grid)
    if len(grid) != len(set(grid)):
        raise ValueError('C_grid contains duplicate values')

    required_months = []
    start = fit_start
    while start <= cal_end:
        required_months.append(start.isoformat()[:7])
        if _month_end(start) == cal_end:
            break
        start = _month_end(start) + timedelta(days=1)
    return ForecastProtocol(
        label=label,
        fit_start=fit_start.isoformat(),
        fit_end=fit_end.isoformat(),
        tune_start=tune[0].isoformat(),
        refit_end=refit_end.isoformat(),
        calibration_start=calibration[0].isoformat(),
        calibration_end=cal_end.isoformat(),
        required_months=tuple(required_months),
        tune_months=tuple(m.isoformat()[:7] for m in tune),
        calibration_months=tuple(m.isoformat()[:7] for m in calibration),
        new_core_months=tuple(m.isoformat()[:7] for m in new_scope),
        previously_scored_months=tuple(m.isoformat()[:7] for m in previous_scope),
        late_months=tuple(m.isoformat()[:7] for m in later_scope),
        holdout_months=tuple(m.isoformat()[:7] for m in holdout),
        thresholds_minutes=thresholds,
        fit_cap=_int(value['fit_cap'], 'fit_cap', 1),
        seed=_int(value['seed'], 'seed', 0),
        C_grid=grid,
        baseline_strength=_number(value['baseline_strength'], 'baseline_strength', zero_allowed=True),
    )
