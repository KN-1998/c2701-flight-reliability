"""Source traceability and algebra checks; NOT evidence that assumptions hold."""
from pathlib import Path
import csv,hashlib,json,sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from prediction import combine

ROOT=Path(__file__).resolve().parents[1]

class ProvenanceTests(unittest.TestCase):
    def test_original_sources_and_exact_versions(self):
        manifest=json.loads((ROOT/'literature'/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
        sources={r['id']:r for r in manifest['sources']}
        for sid in ['P1','P2','T0','CAL2005','SCORE2007']:
            item=sources[sid];data=(ROOT/'literature'/item['file']).read_bytes()
            self.assertTrue(data.startswith(b'%PDF'))
            self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256'])
            if sid in ['P1','P2']:
                self.assertEqual(item['status'],'PRIMARY_RESEARCH_PREPRINT_READ')
                self.assertIn('including references',item['full_text_read_scope'])
            else:
                # Selected-page inspection cannot satisfy this project's full-reading gate.
                self.assertEqual(item['status'],'BIBLIOGRAPHY_VERIFIED_FULL_READING_GATE_PENDING')
        gate=json.loads((ROOT/'docs/PROVENANCE_GATE.json').read_text(encoding='utf-8'))
        self.assertEqual(set(gate['auxiliary_full_reading_gate_pending']),{'T0','CAL2005','SCORE2007'})
        self.assertEqual(sources['K_META']['status'],'METADATA_ONLY_NOT_FULLTEXT')

    def test_registry_keeps_evidence_gaps_visible(self):
        with (ROOT/'docs'/'ASSUMPTION_REGISTER.csv').open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        self.assertGreaterEqual(len(rows),54)
        self.assertEqual(len(rows),json.loads((ROOT/'docs'/'PROVENANCE_GATE.json').read_text(encoding='utf-8'))['assumptions_registered'])
        self.assertEqual(len({r['id'] for r in rows}),len(rows))
        self.assertTrue(all(all(r.values()) for r in rows))
        gate=json.loads((ROOT/'docs'/'PROVENANCE_GATE.json').read_text(encoding='utf-8'))
        self.assertFalse(gate['all_substantive_assumptions_justified'])
        self.assertFalse(gate['default_2027_multiplier_scenarios_allowed'])

    def test_unknown_bounds_and_reference_mixture(self):
        q=np.array([[.1,.2,.3],[.2,.3,.4],[.05,.1,.2]])
        leaf=combine(q);u=np.array([.0,.1,.4]);w=np.array([.2,.3,.5])
        lower=np.dot(w,(1-u)*leaf[:,3]);upper=lower+np.dot(w,u)
        for theta in [np.zeros(3),np.ones(3),np.array([.1,.5,.7])]:
            reliability=np.dot(w,(1-u)*leaf[:,3]+u*theta)
            self.assertGreaterEqual(reliability,lower-1e-12)
            self.assertLessEqual(reliability,upper+1e-12)
        self.assertAlmostEqual(upper-lower,float(np.dot(w,u)))
        np.testing.assert_allclose(leaf.sum(axis=1),1)

    def test_support_and_mix_are_not_the_same_component(self):
        # Only two strata shared; excluded records differ by airport.
        rates=np.array([[.9,.7],[.6,.8]])
        mixes=np.array([[.8,.2],[.3,.7]])
        w=np.array([.5,.5])
        std=rates@w
        shared=(rates*mixes).sum(axis=1)
        full=np.array([.4,.9])
        gap=full[0]-full[1];adjusted=std[0]-std[1]
        common_gap=shared[0]-shared[1]
        composition=common_gap-adjusted
        restriction=gap-common_gap
        self.assertAlmostEqual(gap,adjusted+composition+restriction)
        self.assertNotAlmostEqual(gap-adjusted,composition)

if __name__=='__main__':unittest.main(verbosity=2)
