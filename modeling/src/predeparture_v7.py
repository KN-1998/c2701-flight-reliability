"""Flight-time-safe matching of archived terminal forecasts to BTS schedule proxies."""
from pathlib import Path

import numpy as np
import pandas as pd

ORIGIN_ZONE = {
    'ATL': 'America/New_York', 'DEN': 'America/Denver', 'DFW': 'America/Chicago',
    'EWR': 'America/New_York', 'HNL': 'Pacific/Honolulu', 'LGA': 'America/New_York',
    'MCO': 'America/New_York', 'ORD': 'America/Chicago', 'SEA': 'America/Los_Angeles',
    'SFO': 'America/Los_Angeles',
}
ORIGIN_STATION = {origin: ('P' if origin == 'HNL' else 'K')+origin for origin in ORIGIN_ZONE}
TAF_NUMBERS = ['visibility_sm', 'ceiling_ft_agl', 'wind_speed_kt', 'gust_kt']
TAF_FEATURES = TAF_NUMBERS + ['clear_ceiling', 'adverse_forecast']
TAF_DATES = ['issued_utc', 'available_utc', 'valid_from_utc', 'valid_to_utc']
PRODUCT = ['station','product_id','issued_utc','available_utc']
UTC_DTYPE = 'datetime64[ns, UTC]'


def read_taf(path, products_path=None):
    """Read prevailing segments while retaining every known issuance for supersession."""
    segments = pd.read_csv(Path(path),low_memory=False)
    fields = ['station','product_id','valid_from_utc','valid_to_utc','weather_codes','ceiling_status',*TAF_NUMBERS]
    if products_path is None:
        # Allows compact contract fixtures. The real-data CLI requires a product inventory.
        taf = segments.assign(available_utc=segments.issued_utc)
        if 'wind_speed_kt' not in taf.columns:
            taf['wind_speed_kt'] = np.nan
        if 'ceiling_status' not in taf.columns:
            taf['ceiling_status'] = 'unknown'
    else:
        products = pd.read_csv(products_path,low_memory=False)
        if products.duplicated(['station','product_id']).any():
            raise ValueError('Duplicate TAF product in the complete issuance inventory')
        usable = products.loc[products.product_status.eq('usable'),['station','product_id']]
        timed = segments[fields].merge(usable,on=['station','product_id'],how='inner',validate='many_to_one')
        taf = products[PRODUCT].merge(timed,on=['station','product_id'],how='left',validate='one_to_many')
    required = set(fields+PRODUCT)
    if missing := required.difference(taf.columns):
        raise ValueError(f'Missing archived TAF fields: {sorted(missing)}')
    taf = taf[list(sorted(required))].drop_duplicates()
    for name in TAF_DATES:
        taf[name] = pd.to_datetime(taf[name],utc=True,errors='raise',format='mixed').astype(UTC_DTYPE)
    for name in TAF_NUMBERS:
        taf[name] = pd.to_numeric(taf[name],errors='raise')
    if (not taf.available_utc.ge(taf.issued_utc).all() or taf.station.isna().any() or taf.product_id.isna().any()
            or not taf.station.isin(ORIGIN_STATION.values()).all()):
        raise ValueError('Invalid TAF station, product or issuance; require original timestamps')
    if taf.groupby(['station','product_id'])[['issued_utc','available_utc']].nunique().gt(1).any().any():
        raise ValueError('A TAF product cannot have multiple issuance times')
    has_segment = taf.valid_from_utc.notna()
    if (has_segment.ne(taf.valid_to_utc.notna()).any()
            or not taf.loc[has_segment,'valid_to_utc'].gt(taf.loc[has_segment,'valid_from_utc']).all()
            or taf.loc[has_segment].duplicated(['station','product_id','valid_from_utc']).any()):
        raise ValueError('Malformed or ambiguous prevailing forecast segments')
    for col in TAF_NUMBERS:
        known = taf[col].dropna()
        if not np.isfinite(known).all() or known.lt(0).any():
            raise ValueError(f'Invalid TAF forecast number in {col}')
    return taf


def scheduled_utc(flights, origin):
    """Local schedule proxy; retain unresolved daylight-saving and 2400 cases as missing."""
    minutes = flights.dep_minutes.where(flights.CRSDepTime.ne(2400))
    local = flights.date.dt.normalize() + pd.to_timedelta(minutes,unit='m')
    return local.dt.tz_localize(ORIGIN_ZONE[origin],ambiguous='NaT',nonexistent='NaT').dt.tz_convert('UTC').astype(UTC_DTYPE)


def match_origin_taf(flights, taf, *, lead_minutes, availability_lag_minutes):
    """Choose the latest legally timed issuance, then its segment valid at departure.

    A newer bulletin can supersede an earlier one even when the newer product
    does not cover departure. Missing coverage is deliberately left unmatched.
    """
    if lead_minutes < 0 or availability_lag_minutes < 0:
        raise ValueError('Lead and issuance buffer must be nonnegative')
    issued_limit = pd.Timedelta(minutes=lead_minutes+availability_lag_minutes)
    output = []
    for origin, group in flights.groupby('Origin',observed=True):
        departures = scheduled_utc(group,origin).rename('scheduled_utc')
        rows = departures.dropna().rename_axis('flight_index').reset_index()
        bulletin = taf.loc[taf.station.eq(ORIGIN_STATION[origin])]
        publications = bulletin[PRODUCT[1:]].drop_duplicates().sort_values(['available_utc','issued_utc'])
        # A delayed older bulletin never replaces a newer issuance already available.
        publications = publications.loc[publications.issued_utc.eq(publications.issued_utc.cummax())].copy()
        # A later duplicate only makes the issuance ambiguous once that duplicate is available.
        publications['ambiguous_product'] = publications.duplicated('issued_utc',keep='first')
        publications = publications.drop_duplicates('available_utc',keep='last')
        if rows.empty or publications.empty:
            continue
        rows['issue_cutoff'] = rows.scheduled_utc-issued_limit
        matched = pd.merge_asof(rows.sort_values('issue_cutoff'), publications,
                                left_on='issue_cutoff',right_on='available_utc',direction='backward')
        matched = matched.loc[matched.product_id.notna() & matched.ambiguous_product.eq(False)]
        segments = bulletin.loc[bulletin.valid_from_utc.notna(),
                                ['product_id','valid_from_utc','valid_to_utc','weather_codes','ceiling_status',*TAF_NUMBERS]]
        if matched.empty or segments.empty:
            continue
        timed = pd.merge_asof(matched.sort_values('scheduled_utc'),segments.sort_values('valid_from_utc'),
                              by='product_id',left_on='scheduled_utc',right_on='valid_from_utc',
                              direction='backward')
        timed = timed.loc[timed.scheduled_utc.lt(timed.valid_to_utc)].set_index('flight_index')
        timed['clear_ceiling'] = timed.ceiling_status.eq('none').astype(int)
        timed['adverse_forecast'] = (
            timed.visibility_sm.lt(3) | timed.ceiling_ft_agl.lt(1000)
            | timed.weather_codes.astype('string').str.contains(r'TS|FZRA',na=False)
        ).astype(int)
        if not timed.available_utc.le(timed.issue_cutoff).all():
            raise ValueError('After-cutoff TAF selected')
        output.append(timed[[*TAF_FEATURES,'issued_utc','available_utc','scheduled_utc','valid_from_utc','valid_to_utc','product_id']])
    if not output:
        return pd.DataFrame(index=flights.index[:0],columns=TAF_FEATURES)
    result = pd.concat(output).sort_index()
    if not result.index.is_unique:
        raise ValueError('Duplicate TAF matches for a single flight')
    return result

