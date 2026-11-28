"""Post-v7 text/parsed-field consistency diagnostic, without repairing archived data.

These narrow token checks flag records for original-product review. They cannot
adjudicate a historical parser/version mismatch or prove all other fields correct.
"""
from pathlib import Path
import argparse
import json
import re

import pandas as pd

from predeparture_v7 import ORIGIN_STATION, read_taf
from run_study_v7 import PROTOCOL, ROOT, attach, groups, new_directory, prepare

CLOUD = re.compile(r'\b(?:BKN|OVC|VV)(\d{3})(?:CB|TCU)?\b')


def raw_text_flags(segments):
    source = segments.source_forecast_text.fillna('').astype(str)
    fields = segments.weather_codes.fillna('').astype(str)
    text_ceiling = source.map(lambda text: min([int(n)*100 for n in CLOUD.findall(text)],default=float('nan')))
    parsed_ceiling = pd.to_numeric(segments.ceiling_ft_agl,errors='raise')
    mismatch = (text_ceiling.notna() & parsed_ceiling.notna() & text_ceiling.ne(parsed_ceiling)) | (text_ceiling.isna() & parsed_ceiling.notna())
    unsupported_adverse = fields.str.contains(r'TS|FZRA') & ~source.str.contains(r'TS|FZRA')
    result = segments.loc[mismatch | unsupported_adverse].copy()
    result['visible_text_ceiling_ft'] = text_ceiling.loc[result.index]
    result['ceiling_text_mismatch'] = mismatch.loc[result.index]
    result['adverse_code_absent_in_visible_text'] = unsupported_adverse.loc[result.index]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--data',type=Path,default=ROOT/'data')
    parser.add_argument('--protocol',type=Path,default=PROTOCOL)
    parser.add_argument('--taf',type=Path,default=ROOT/'data/taf_v7/taf_prevailing_normalized.csv.gz')
    parser.add_argument('--taf-products',type=Path,default=ROOT/'data/taf_v7/taf_products_normalized.csv.gz')
    args=parser.parse_args();new_directory(args.out)
    segments=pd.read_csv(args.taf)
    flagged=raw_text_flags(segments)
    flagged.to_csv(args.out/'taf_text_flagged_segments.csv',index=False)
    # Product-wide exposure is conservative: a flag in one segment does not mean
    # every flight matched to any segment of the product has an incorrect input.
    flag_products=set(zip(flagged.station,flagged.product_id))
    flag_segments=set(zip(flagged.station,flagged.product_id,pd.to_datetime(flagged.valid_from_utc,utc=True)))
    protocol=json.loads(args.protocol.read_text(encoding='utf-8-sig'))
    train,cal,test=prepare(args.data,protocol,args.out)
    taf=read_taf(args.taf,args.taf_products)
    rows=[]
    for role,frame in [('fit',train),('calibration',cal),('score',test)]:
        for period,flight in groups(frame):
            data=attach(flight,taf,protocol['information_experiment'])
            stations=data.Origin.map(ORIGIN_STATION)
            product_exposed=pd.Series([(s,p) in flag_products for s,p in zip(stations,data.product_id)],index=data.index)
            segment_exposed=pd.Series([(s,p,t) in flag_segments for s,p,t in zip(stations,data.product_id,data.valid_from_utc)],index=data.index)
            rows.append({'role':role,'period':period,'n':len(data),
                         'flagged_product_matched_flights':int(product_exposed.sum()),
                         'flagged_segment_matched_flights':int(segment_exposed.sum()),
                         'scope':'frozen_followup' if role=='score' and period in protocol['holdout_months'] else ('previously_reviewed' if role=='score' else role)})
    pd.DataFrame(rows).to_csv(args.out/'taf_text_flag_exposure.csv',index=False)
    status={'status':'SOURCE_TEXT_DISCREPANCIES_REQUIRE_RAW_PRODUCT_REVIEW',
            'segments_checked':len(segments),'flagged_segments':len(flagged),
            'flagged_products':len(flag_products),
            'ceiling_discrepancies':int(flagged.ceiling_text_mismatch.sum()),
            'adverse_codes_absent_in_visible_text':int(flagged.adverse_code_absent_in_visible_text.sum()),
            'correction_applied':False,'new_holdout':False,
            'interpretation':'Candidate source discrepancies, not all adjudicated errors. Original NWS bulletin and historic parser/version review pending. No performance improvement or live use authorized.'}
    (args.out/'TAF_TEXT_AUDIT_STATUS.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(status,indent=2));print(pd.DataFrame(rows).groupby(['role','scope'])[['n','flagged_product_matched_flights','flagged_segment_matched_flights']].sum().to_string())


if __name__=='__main__':main()
