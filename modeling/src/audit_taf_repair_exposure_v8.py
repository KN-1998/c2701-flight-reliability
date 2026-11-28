"""Count exact source-repair matches in the fixed fit, calibration and historical score cohorts."""
from pathlib import Path
import argparse

import pandas as pd

from run_study_v7 import (ROOT, attach, groups, identity_digest, new_directory, prepare, read_taf,
                          sample_weather_rows, save_json, sha)
from run_weather_v8 import V7_PRODUCTS, V8_PROTOCOL, protocol_for_months


CORRECTIONS = ROOT / 'data/taf_v8/exact_product_adjudication.csv'
ARCHIVE = ROOT / 'data/taf_v8/taf_prevailing_corrected.csv.gz'
KEY = ['Origin','product_id','valid_from_utc']


def impacts(matched, verified):
    indexes = pd.MultiIndex.from_frame(matched[KEY])
    features = verified.loc[verified.disposition.eq('feature_fields_repaired')]
    only_metadata = verified.loc[verified.disposition.eq('text_or_relation_repaired')]
    return {
        'matched':len(matched),
        'model_field_repair_matches':int(indexes.isin(pd.MultiIndex.from_frame(features[KEY])).sum()),
        'text_or_relation_only_matches':int(indexes.isin(pd.MultiIndex.from_frame(only_metadata[KEY])).sum()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    protocol = protocol_for_months()
    new_directory(args.out)
    train,calibrate,test = prepare(ROOT/'data',protocol,args.out)
    text = pd.read_csv(CORRECTIONS)
    text['Origin'] = text.station.str[1:]
    text['valid_from_utc'] = pd.to_datetime(text.valid_from_utc,utc=True,format='mixed').astype('datetime64[ns, UTC]')
    if text.duplicated(KEY).any():
        raise ValueError('Duplicate correction key')
    taf = read_taf(ARCHIVE,V7_PRODUCTS)
    timing = protocol['information_experiment']
    matched = attach(train,taf,timing)
    sampled = sample_weather_rows(matched,protocol['fit_scope'])
    rows = [{'role':'fit_pool','period':'all',**impacts(matched,text)},
            {'role':'fit_sample','period':'all',**impacts(sampled,text)}]
    sample_digest = identity_digest(sampled)
    del train, matched, sampled
    rows.append({'role':'calibration','period':'all',**impacts(attach(calibrate,taf,timing),text)})
    del calibrate
    for period,flight in groups(test):
        rows.append({'role':'historical_score','period':period,**impacts(attach(flight,taf,timing),text)})
    result = pd.DataFrame(rows)
    result.to_csv(args.out/'exact_taf_repair_exposure.csv',index=False)
    save_json({'protocol_sha256':sha(V8_PROTOCOL),'corrected_archive_sha256':sha(ARCHIVE),
               'segment_decisions_sha256':sha(CORRECTIONS),'fit_sample_identity_sha256':sample_digest,
               'status':'VERIFIED_SOURCE_REPAIR_EXPOSURE'},args.out/'exposure_status.json')
    print(result.to_string(index=False))


if __name__ == '__main__':
    main()
