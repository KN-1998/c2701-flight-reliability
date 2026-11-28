"""Rebuild a targeted v8 TAF correction from exact archived NWS bulletins."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timedelta
from fractions import Fraction
import gzip
import hashlib
import io
from itertools import groupby
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "data/taf_v7/taf_prevailing_normalized.csv.gz"
FLAGS = ROOT / "results/v7_review_20261128/taf_text_audit/taf_text_flagged_segments.csv"
RAW = ROOT / "data/taf_v8/original_products"
KEY = ("station", "product_id", "valid_from_utc")
ID = re.compile(r"(\d{12})-([A-Z]{4})-([A-Z]{4}\d{2})-(TAF[A-Z]{3})(?:-([A-Z]{3}))?")
GROUP = re.compile(r"(?<!\S)(FM\d{6}|TEMPO|PROB[34]0|BECMG)\b")
WIND = re.compile(r"(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT")
VISIBILITY = re.compile(r"(\d+ )?([PM])?(\d+(?:/\d+)?)SM\b")
CLOUD = re.compile(r"(FEW|SCT|BKN|OVC|VV)(\d{3}|///)(?:CB|TCU)?")
WX = re.compile(
    r"(?:(?:[+-]|VC)?(?:MI|PR|BC|DR|BL|SH|TS|FZ)?"
    r"(?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS){1,3}"
    r"|TS|VCTS|VCSH)"
)
NON_CEILING = {"SKC", "CLR", "NSC", "NCD"}
NUMBERS = {"visibility_sm", "ceiling_ft_agl", "wind_speed_kt", "gust_kt"}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def row_key(row):
    return tuple(row[name] for name in KEY)


def fail(message):
    raise ValueError(message)


def read_source(raw_directory, expected):
    manifest = json.loads((raw_directory / "manifest.json").read_text(encoding="utf-8"))
    records = {item["product_id"]: item for item in manifest}
    if len(records) != len(manifest) or set(records) != expected:
        fail("Raw product receipt identities differ from the frozen diagnostic inventory")
    result = {}
    for product_id, item in records.items():
        if not ID.fullmatch(product_id):
            fail(f"Unexpected archive product ID: {product_id}")
        path = raw_directory / (product_id + ".txt")
        if (
            item["url"] != f"https://mesonet.agron.iastate.edu/api/1/nwstext/{product_id}"
            or item["status"] != 200
            or not item["content_type"].startswith("text/plain")
            or path.stat().st_size != item["bytes"]
            or sha256(path) != item["sha256"]
        ):
            fail(f"Invalid archive receipt or bytes for {product_id}")
        result[product_id] = path.read_bytes()
    return result


def raw_groups(product_id, row, raw):
    stamp, office, wmo, awips, revision = ID.fullmatch(product_id).groups()
    lines = raw.decode("ascii").strip().splitlines()
    header = " ".join(filter(None, (wmo, office, stamp[-6:], revision)))
    if [" ".join(line.split()) for line in lines].count(header) != 1 or awips not in [line.strip() for line in lines]:
        fail(f"Wrong WMO/AWIPS archive response for {product_id}")
    text = " ".join(" ".join(lines).split())
    issuance = datetime.fromisoformat(row["issued_utc"]).strftime("%d%H%MZ")
    head = re.compile(rf"\b{re.escape(row['station'])} {issuance} (\d{{4}})/(\d{{4}}) ")
    match = head.search(text)
    if not match or not text.endswith("=") or text.count("=") != 1:
        fail(f"Missing or ambiguous forecast body for {product_id}")
    for value, column in zip(match.groups(), ("product_valid_from_utc", "product_valid_to_utc")):
        moment = datetime.fromisoformat(row[column])
        standard = moment.strftime("%d%H")
        midnight_as_24 = (moment - timedelta(days=1)).strftime("%d") + "24"
        if value != standard and not (standard.endswith("00") and value == midnight_as_24):
            fail(f"NWS and archived product bounds differ for {product_id}: {column}")
    body = text[match.end():-1].strip()
    boundaries = list(GROUP.finditer(body))
    prevailing = {"initial": body[:boundaries[0].start()].strip() if boundaries else body}
    for index, start in enumerate(boundaries):
        label = start.group(1)
        if not label.startswith("FM"):
            continue
        if label in prevailing:
            fail(f"Ambiguous original {label} in {product_id}")
        stop = boundaries[index + 1].start() if index + 1 < len(boundaries) else len(body)
        prevailing[label] = body[start.start():stop].strip()
    return prevailing


def parse_values(text):
    """Decode prevailing fields, preserving the v7 P6SM numerical encoding."""
    tokens = text.split()
    if tokens[-3:] == ["AMD", "NOT", "SKED"]:
        tokens = tokens[:-3]
    if not tokens:
        fail("Empty forecast group")
    if re.fullmatch(r"FM\d{6}", tokens[0]):
        tokens = tokens[1:]
    wind = WIND.fullmatch(tokens[0]) if tokens else None
    if not wind:
        fail(f"Unsupported prevailing wind: {text}")
    conditions = " ".join(tokens[1:])
    visibility = VISIBILITY.match(conditions)
    if not visibility:
        fail(f"Unsupported prevailing visibility: {text}")
    whole, comparator, amount = visibility.groups()
    value = (int(whole) if whole else 0) + Fraction(amount)
    if comparator == "P":
        value += Fraction(1, 100)
    elif comparator == "M":
        value -= Fraction(1, 100)
    if value < 0:
        fail(f"Invalid visibility: {text}")
    cloud_layers, weather = [], []
    for token in conditions[visibility.end():].split():
        cloud = CLOUD.fullmatch(token)
        if cloud:
            cloud_layers.append(cloud.groups())
        elif token in NON_CEILING:
            cloud_layers.append((token, None))
        elif WX.fullmatch(token):
            weather.append(token)
        elif token == "NSW" or re.fullmatch(r"WS\d{3}/\d{5,6}KT", token):
            continue
        else:
            fail(f"Unsupported prevailing token {token}: {text}")
    layers = [level for cover, level in cloud_layers if cover in {"BKN", "OVC", "VV"}]
    if layers and "///" not in layers:
        ceiling, ceiling_status = str(100 * min(map(int, layers))), "present"
    else:
        ceiling = ""
        ceiling_status = "none" if cloud_layers and not layers else "unknown"
    return {
        "visibility_sm": str(float(value)),
        "visibility_relation": {"P": "greater_than", "M": "less_than", None: "encoded_value"}[comparator],
        "ceiling_ft_agl": ceiling,
        "ceiling_status": ceiling_status,
        "wind_speed_kt": wind.group(2).lstrip("0") or "0",
        "gust_kt": str(int(wind.group(3) or 0)),
        "weather_codes": " ".join(weather),
        "source_forecast_text": text,
    }


def differs(field, before, after):
    if field in NUMBERS and before and after:
        return float(before) != float(after)
    return before != after


def write_group(writer, row, replacements, evidence, flagged):
    changes = [field for field, after in replacements.items() if differs(field, row[field], after)]
    writer.writerow({**row, **{field: replacements[field] for field in changes}})
    disposition = "unchanged"
    if any(field not in ("source_forecast_text", "visibility_relation") for field in changes):
        disposition = "feature_fields_repaired"
    elif changes:
        disposition = "text_or_relation_repaired"
    evidence.writerow({
        **dict(zip(KEY, row_key(row))), "valid_to_utc": row["valid_to_utc"],
        "initial_or_fm": row["segment_kind"], "diagnostic_flag": str(flagged).lower(),
        "disposition": disposition, "changed_fields": " ".join(changes),
        "old_values": json.dumps({field: row[field] for field in changes}, sort_keys=True),
        "new_values": json.dumps({field: replacements[field] for field in changes}, sort_keys=True),
        "original_group": replacements["source_forecast_text"],
    })
    return disposition, changes


def write_exact(segments, sources, flags, output, evidence):
    stats = Counter()
    field_counts = Counter()
    seen_products = set()
    all_keys = set()
    with gzip.open(segments, "rt", encoding="utf-8", newline="") as source, output.open("wb") as base:
        with gzip.GzipFile(filename="", mode="wb", fileobj=base, mtime=0) as archive, \
                io.TextIOWrapper(archive, encoding="utf-8", newline="") as destination:
            reader = csv.DictReader(source)
            writer = csv.DictWriter(destination, fieldnames=reader.fieldnames, lineterminator="\n")
            writer.writeheader()
            evidence_fields = [
                *KEY, "valid_to_utc", "initial_or_fm", "diagnostic_flag", "disposition",
                "changed_fields", "old_values", "new_values", "original_group",
            ]
            with evidence.open("w", encoding="utf-8", newline="") as data:
                evidence_writer = csv.DictWriter(data, evidence_fields, lineterminator="\n")
                evidence_writer.writeheader()
                for (station, product_id), product in groupby(reader, lambda r: (r["station"], r["product_id"])):
                    if product_id not in sources:
                        for row in product:
                            writer.writerow(row)
                            stats["all_segments"] += 1
                        continue
                    if product_id in seen_products:
                        fail(f"Repeated targeted product {product_id}")
                    seen_products.add(product_id)
                    rows = list(product)
                    groups = raw_groups(product_id, rows[0], sources[product_id])
                    for index, row in enumerate(rows):
                        moment = datetime.fromisoformat(row["valid_from_utc"])
                        label = "initial" if row["segment_kind"] == "initial" else "FM" + moment.strftime("%d%H%M")
                        if label not in groups or (index == 0) != (label == "initial"):
                            fail(f"Cannot pair {product_id} to original segment {label}")
                        next_start = rows[index + 1]["valid_from_utc"] if index + 1 < len(rows) else row["product_valid_to_utc"]
                        if row["valid_to_utc"] != next_start:
                            fail(f"Archived segment bounds differ from next prevailing group for {product_id}")
                        if label == "initial" and row["valid_from_utc"] != row["product_valid_from_utc"]:
                            fail(f"Initial segment does not start at product validity for {product_id}")
                        raw_group = groups.pop(label)
                        replacements = parse_values(raw_group)
                        key = row_key(row)
                        all_keys.add(key)
                        disposition, fields = write_group(writer, row, replacements, evidence_writer, key in flags)
                        field_counts.update(fields)
                        stats.update(("all_segments", "exact_groups_checked", disposition))
                        if key in flags:
                            stats["v7_diagnostic_flags_rechecked"] += 1
                    if groups:
                        fail(f"Unmatched original prevailing groups in {product_id}: {sorted(groups)}")
                    if station not in {item[0] for item in flags if item[1] == product_id}:
                        fail(f"Unexpected station for {product_id}")
    if seen_products != set(sources) or not flags.issubset(all_keys):
        fail("An original bulletin or diagnostic segment did not join to the normalized table")
    return dict(stats), dict(sorted(field_counts.items()))



def vrb_candidate(row, text_is_unique):
    """Use the attached group only if its identity and non-wind fields agree."""
    text = " ".join(row["source_forecast_text"].split())
    first = text.split()[:2]
    if len(first) == 0:
        return None, "no_text"
    wind = first[-1] if first[0].startswith("FM") else first[0]
    if row["wind_speed_kt"] or not wind.startswith("VRB"):
        return None, "not_missing_vrb"
    if not text_is_unique:
        return None, "repeated_group_text"
    if row["segment_kind"] == "FM":
        moment = datetime.fromisoformat(row["valid_from_utc"])
        if first[0] != "FM" + moment.strftime("%d%H%M"):
            return None, "unverified_group_identity"
    elif row["segment_kind"] != "initial" or first[0] != wind:
        return None, "unverified_group_identity"
    try:
        values = parse_values(text)
    except ValueError:
        return None, "unsupported_group_text"
    for field in ("visibility_sm", "visibility_relation", "ceiling_ft_agl", "ceiling_status", "weather_codes"):
        if differs(field, row[field], values[field]):
            return None, "nonwind_field_disagrees"
    if row["gust_kt"] and differs("gust_kt", row["gust_kt"], values["gust_kt"]):
        return None, "known_gust_disagrees"
    replacements = {"wind_speed_kt": values["wind_speed_kt"]}
    if not row["gust_kt"]:
        replacements["gust_kt"] = values["gust_kt"]
    return replacements, "text_supported_vrb_repair"


def build_vrb_sensitivity(corrected, verified_products, output, ledger):
    stats = Counter()
    per_month_station = Counter()
    sample_limit = 2
    challenges = {}
    with gzip.open(corrected, "rt", encoding="utf-8", newline="") as source, output.open("wb") as base:
        with gzip.GzipFile(filename="", mode="wb", fileobj=base, mtime=0) as archive, \
                io.TextIOWrapper(archive, encoding="utf-8", newline="") as destination:
            reader = csv.DictReader(source)
            writer = csv.DictWriter(destination, fieldnames=reader.fieldnames, lineterminator="\n")
            writer.writeheader()
            seen = set()
            for (station, product_id), product in groupby(reader, lambda row: (row["station"], row["product_id"])):
                identity = station, product_id
                if identity in seen:
                    fail(f"Noncontiguous rows for bulletin {identity}")
                seen.add(identity)
                rows = list(product)
                if product_id in verified_products:
                    writer.writerows(rows)
                    stats["exact_products_excluded_segments"] += len(rows)
                    continue
                texts = Counter(" ".join(row["source_forecast_text"].split()) for row in rows)
                for row in rows:
                    unique = texts[" ".join(row["source_forecast_text"].split())] == 1
                    replacements, disposition = vrb_candidate(row, unique)
                    stats[disposition] += 1
                    if replacements:
                        month = row["valid_from_utc"][:7]
                        per_month_station[(station, month)] += 1
                        sample = challenges.setdefault(station, [])
                        digest = hashlib.sha256("/".join(row_key(row)).encode("ascii")).hexdigest()
                        entry = {"sha256_selection": digest, **{field: row[field] for field in (*KEY, "source_forecast_text")},
                                 **replacements}
                        sample.append(entry)
                        sample.sort(key=lambda item: item["sha256_selection"])
                        del sample[sample_limit:]
                    writer.writerow({**row, **(replacements or {})})
    with ledger.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("station", "segment_start_utc_month", "text_supported_vrb_segments"))
        for (station, month), count in sorted(per_month_station.items()):
            writer.writerow((station, month, count))
    return dict(stats), [entry for candidates in challenges.values() for entry in candidates]


def run_vrb_sensitivity(directory, raw_directory, corrected, manifest):
    if not corrected.is_file() or not manifest.is_file():
        fail("Build the exact source repair before the VRB sensitivity")
    receipt = json.loads(manifest.read_text(encoding="utf-8"))
    if sha256(corrected) != receipt["outputs_sha256"][corrected.name]:
        fail("The exact corrected input differs from its recorded digest")
    sources = json.loads((raw_directory / "manifest.json").read_text(encoding="utf-8"))
    verified = {item["product_id"] for item in sources}
    output = directory / "taf_prevailing_vrb_sensitivity.csv.gz"
    ledger = directory / "vrb_sensitivity_by_station_month.csv"
    manifest_path = directory / "taf_vrb_sensitivity_manifest.json"
    artifacts = (output, ledger, manifest_path)
    if any(path.exists() for path in artifacts):
        fail("Use a directory without prior VRB sensitivity artifacts")
    staging = [path.with_suffix(path.suffix + ".part") for path in artifacts]
    stats, challenge = build_vrb_sensitivity(corrected, verified, *staging[:2])
    result = {
        "status": "GUARDED_VRB_TEXT_SENSITIVITY",
        "scope": "Separate sensitivity, using normalized attached text outside the exact archived-product adjudication.",
        "eligibility": {
            "candidate": "Missing structured wind speed and a VRB group wind token.",
            "group": "Initial text starts with VRB or FM token agrees with normalized UTC start. Repeated product text excluded.",
            "checks": "Decoded visibility and qualifier, ceiling and state, weather codes, and any known gust agree.",
            "write": "Recover only missing speed/gust fields, with 0 gust when no G token. Keep original source text and all timing.",
        },
        "input_sha256": sha256(corrected),
        "counts": stats,
        "outputs_sha256": {path.name: sha256(part) for path, part in zip(artifacts[:2], staging[:2])},
        "raw_challenge_samples": challenge,
        "raw_challenge_design": "Two lexicographically smallest SHA-256 digests of station/product/segment per station among corrected records, for later exact-bulletin challenge.",
    }
    staging[2].write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for path, part in zip(artifacts, staging):
        part.replace(path)
    print(json.dumps({key: value for key, value in result.items() if key != "raw_challenge_samples"}, indent=2))


def screen_attached_groups(segments, inventory):
    """Flag non-wind-missing differences for exact original-product review."""
    if inventory.exists():
        fail("Use an output directory without a prior diagnostic inventory")
    with gzip.open(segments, "rt", encoding="utf-8", newline="") as source, \
            inventory.open("x", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, [*KEY, "reasons"], lineterminator="\n")
        writer.writeheader()
        for row in csv.DictReader(source):
            text = row["source_forecast_text"]
            start = datetime.fromisoformat(row["valid_from_utc"]).strftime("%d%H%M")
            reasons = []
            if row["segment_kind"] == "FM" and not text.startswith("FM" + start + " "):
                reasons.append("fm_group_text_identity_missing")
            try:
                decoded = parse_values(text)
            except ValueError:
                decoded = {}
                reasons.append("attached_group_not_decoded")
            for field, expected in decoded.items():
                if field == "source_forecast_text" or not differs(field, row[field], expected):
                    continue
                if field in ("wind_speed_kt", "gust_kt") and not row[field] and "VRB" in text:
                    continue  # Missing VRB speed/gust have a separate sensitivity.
                reasons.append(field + "_comparison")
            if reasons:
                writer.writerow({**dict(zip(KEY, row_key(row))), "reasons": " ".join(reasons)})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=Path, default=ORIGINAL)
    parser.add_argument("--flags", type=Path, default=FLAGS)
    parser.add_argument("--raw", type=Path, default=RAW)
    parser.add_argument("--out", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--screen", action="store_true",
                      help="Write the extra attached-field screening inventory without changing inputs")
    mode.add_argument("--vrb-sensitivity", action="store_true",
                        help="Build only the separate text-supported wind sensitivity from an existing exact repair")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.screen:
        screen_attached_groups(args.segments, args.out / "diagnostic_inventory.csv")
        return
    corrected = args.out / "taf_prevailing_corrected.csv.gz"
    adjudication = args.out / "exact_product_adjudication.csv"
    manifest = args.out / "taf_correction_manifest.json"
    artifacts = (corrected, adjudication, manifest)
    if args.vrb_sensitivity:
        run_vrb_sensitivity(args.out, args.raw, corrected, manifest)
        return
    if any(path.exists() for path in artifacts):
        fail("Use an output directory without prior correction artifacts")
    with args.flags.open(encoding="utf-8-sig", newline="") as source:
        flags = {row_key(row) for row in csv.DictReader(source)}
    sources = read_source(args.raw, {key[1] for key in flags})
    staging = [path.with_suffix(path.suffix + ".part") for path in artifacts]
    stats, fields = write_exact(args.segments, sources, flags, *staging[:2])
    original_flags = args.flags.resolve() == FLAGS.resolve()
    scope = "Every prevailing group in the products flagged by the v7 text diagnostic. Other structured records remain unchanged."
    if not original_flags:
        stats["additional_diagnostic_flags_rechecked"] = stats.pop("v7_diagnostic_flags_rechecked")
        scope = "Every prevailing group in the additionally screened original products. Other input records remain unchanged."
    result = {
        "status": "TARGETED_EXACT_NWS_GROUPS_REPAIRED",
        "source": "NWS issuance bytes retrieved from the IEM NWS Text Archive via exact WMO/AWIPS/BBB IDs",
        "source_documentation": "https://mesonet.agron.iastate.edu/nws/text.php",
        "product_guide": "https://www.weather.gov/media/directives/010_pdfs/pd01008013curr.pdf",
        "scope": scope,
        "exact_products": len(sources),
        "counts": stats,
        "changed_field_counts": fields,
        "inputs_sha256": {
            args.segments.name: sha256(args.segments), args.flags.name: sha256(args.flags),
            "original_products/manifest.json": sha256(args.raw / "manifest.json"),
        },
        "outputs_sha256": {path.name: sha256(part) for path, part in zip(artifacts[:2], staging[:2])},
        "source_text_note": "The archived group text is repaired only after the exact raw bulletin is matched.",
        "timing": "The v7 product inventory, segment keys, timing, fit scope, and matching rules are reused.",
    }
    staging[2].write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for path, part in zip(artifacts, staging):
        part.replace(path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
