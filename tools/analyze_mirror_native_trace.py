"""Read-only EOSM202 v1/v2 trace analysis; never grants a RAW write lease.

Usage: python tools/analyze_mirror_native_trace.py MTR000.LOG [--probe MRAW000.LOG]
       python tools/analyze_mirror_native_trace.py --probe MRAW000.LOG
Stdout is JSON. Input logs, firmware and photos are never modified.
DMA arithmetic follows pinned src/edmac.c edmac_get_total_size; it describes
transfer counts/final displacement, not the complete set of accessed addresses.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

MASK = 0xffffffff
POINTS = {0: 0xff1707e8, 1: 0xff1686d0, 2: 0xff429210,
          3: 0xff4292b8, 4: 0xff168128, 5: 0xff429280,
          6: 0xff22dac0, 7: 0xff22da74}
DESCRIPTORS = {0x70340: 'Mem1 RAW', 0x6fce4: 'SSS RAW', 0x6fd8c: 'candidate JPEG'}
SOURCE_KINDS = {0, 1, 4}
HEADER = 'phase error core_error error_pc installed events dropped skipped max_hook_us requested_ms armed_ms last_ms starts'
EVENT = 'event ms us kind pc lr task desc source_field effective_source x y precision'
DESC = 'rd_channel rd_flags rd_offset wr_channel output_suite output2 gui lv job context_job opaque_context'
DMA = 'dma_before after address pointer flags xa ya xb yb xn yn off1a off2a off1b off2b off3'
DELIVERED = 'delivered preview_ms params'
CONTEXT = 'original_cpsr argument_job argument_source reader_valid reader_before reader_after reader_address reader_pointer reader_flags'
READER = 'reader_xa reader_ya reader_xb reader_yb reader_xn reader_yn reader_off1a reader_off2a reader_off1b reader_off2b reader_off3'
HEX = set('core_error error_pc installed pc lr task desc source_field effective_source precision rd_flags rd_offset output_suite output2 context_job opaque_context address pointer flags off1a off2a off1b off2b off3'.split())
HEX.update('original_cpsr argument_job argument_source reader_address reader_pointer reader_flags reader_off1a reader_off2a reader_off1b reader_off2b reader_off3'.split())


def fields(line, expected):
    pairs = line.split()
    result = {}
    for pair in pairs:
        key, sep, value = pair.partition('=')
        if not sep or key in result:
            raise ValueError('Malformed or duplicate field: ' + pair)
        if key == 'params':
            if not re.fullmatch(r'[0-9]+,[0-9]+,[0-9]+,[0-9]+', value):
                raise ValueError('Malformed Mirror controls')
            result[key] = [int(v) for v in value.split(',')]
        else:
            base = 16 if key in HEX else 10
            if not re.fullmatch(r'[0-9a-fA-F]+' if base == 16 else r'[0-9]+', value):
                raise ValueError('Malformed numeric field: ' + key)
            result[key] = int(value, base)
        values = result[key] if isinstance(result[key], list) else [result[key]]
        if any(v > MASK for v in values):
            raise ValueError('Field exceeds ARM32: ' + key)
    if set(result) != set(expected.split()):
        raise ValueError('Unexpected or missing fields in: ' + line[:120])
    return result


def canonical(address):
    # Only treat known EOSM RAM/cache aliases as candidates. ROM/zero are not
    # valid shared sensor evidence, even if their numeric values happen to match.
    value = address & ~0x40000000
    return value if 0x1000 <= value < 0x20000000 else None


def signed32(value):
    return value - (1 << 32) if value & (1 << 31) else value


def dma_sizes(info):
    """Count bytes and final displacement, preserving signed offset semantics.

    These equations do NOT give min/max addresses for negative/strided paths,
    validate flags or prove that a transfer has completed.
    """
    xa, ya, xb, yb, xn, yn = (info[k] for k in ('xa', 'ya', 'xb', 'yb', 'xn', 'yn'))
    if any(v > 65535 for v in (xa, ya, xb, yb, xn, yn)):
        raise ValueError('EDMAC dimensions exceed register width')
    a, b, c, d, e = (signed32(info[k]) for k in ('off1a', 'off2a', 'off1b', 'off2b', 'off3'))
    count = (xa * (ya + 1) * xn + xb * (ya + 1)) * yn + xa * (yb + 1) * xn + xb * (yb + 1)
    displacement = (((xa + a) * ya + xa + b) * xn + ((xb + c) * ya + xb + e)) * yn + ((xa + a) * yb + xa + d) * xn + (xb + c) * yb + xb + e
    address, pointer = canonical(info['address']), canonical(info['pointer'])
    comparable = address is not None and pointer is not None
    return {'transferred_bytes_arithmetic': count, 'final_displacement_arithmetic': displacement,
            'count_exceeds_uint32': count > MASK, 'displacement_outside_uint32': not 0 <= displacement <= MASK,
            'idle_at_both_samples': info['dma_before'] == info['after'] == 0,
            'canonical_address': address, 'canonical_pointer': pointer,
            'pointer_minus_address': pointer - address if comparable else None,
            'pointer_matches_computed_end': comparable and pointer == address + displacement,
            'exclusive_ownership_verified': False}


def read_log(path):
    data = path.read_bytes()
    if len(data) > 256 * 1024:
        raise ValueError('Log exceeds 256 KiB')
    return data.decode('ascii').splitlines(), {'file': path.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def analyze_trace(path):
    lines, provenance = read_log(path)
    v2 = bool(lines and lines[0] == 'Mirror native CR2 path metadata v2 / EOSM202 / ML ed3e7c0')
    expected = ['Mirror native CR2 path metadata / EOSM202 / ML ed3e7c0',
                'Read-only sensor/arguments; runtime cache hooks remain until power OFF',
                'No owned RAW lease; no mirrored CR2 saved; sensor/output pointers never dereferenced']
    if v2:
        expected[0] = lines[0]
    if lines[:3] != expected or len(lines) < 4:
        raise ValueError('Not a supported dev9 EOSM202 trace')
    header = fields(lines[3], HEADER)
    capacity, all_hooks, stride = (64, 255, 6) if v2 else (16, 63, 4)
    if header['events'] > capacity or header['installed'] & ~all_hooks or header['phase'] > 4 or header['error'] > 7:
        raise ValueError('Invalid trace status/capacity')
    if len(lines) != 4 + stride * header['events']:
        raise ValueError('Truncated trace or unexpected records')
    warnings, events, source_matches = [], [], []
    if header['phase'] != 3 or header['error']:
        warnings.append('Trace did not complete successfully; use the status/error fields.')
    if header['installed'] != all_hooks:
        warnings.append('Not all expected hooks were installed; missing paths cannot be excluded.')
    if header['dropped']:
        warnings.append('Ring tail only; earlier events were overwritten. First-observed is not first-consumer.')
    if header['skipped']:
        warnings.append('Some callback arguments were rejected; the trace is selective.')
    for i in range(header['events']):
        offset = 4 + i * stride
        record = fields(lines[offset], EVENT)
        descriptor = fields(lines[offset + 1], DESC)
        dma = fields(lines[offset + 2], DMA)
        delivered = fields(lines[offset + 3], DELIVERED)
        kind = record['kind']
        accessor = v2 and kind in (6, 7)
        pc_ok = record['pc'] == POINTS.get(kind) or (v2 and kind == 6 and record['pc'] == 0xff22dab4)
        if record['event'] != i or not pc_ok or (not v2 and kind > 5) or (record['desc'] != 0 if accessor else record['desc'] not in DESCRIPTORS):
            raise ValueError('Invalid event index, hook point or descriptor')
        fixed = {0: 0x70340, 1: 0x6fce4, 4: 0x6fd8c, 5: 0x6fd8c}
        if kind in fixed and record['desc'] != fixed[kind]:
            raise ValueError('Hook/descriptor mismatch')
        if delivered['delivered'] not in (0, 1):
            raise ValueError('Invalid delivered flag')
        p = delivered['params']
        if delivered['delivered'] and (p[0] > 179 or p[1] not in (2, 4, 6, 8, 10, 12) or max(p[2:]) > 1000):
            raise ValueError('Invalid delivered Mirror controls')
        # Source stores are observed BEFORE the original STR; source_field is
        # deliberately stale there. At prepare/start it must equal effective_source.
        if not accessor and kind not in SOURCE_KINDS and record['source_field'] != record['effective_source']:
            raise ValueError('Inconsistent prepare/start source')
        elapsed_ms = (record['ms'] - header['armed_ms']) & MASK
        if elapsed_ms > 61000:
            warnings.append(f'Event {i} is outside the expected observation window; clock/order needs inspection.')
        entry = {'record': record, 'descriptor': descriptor, 'delivered': delivered,
                 'path': ('job source getter' if kind == 6 else 'job source publication') if accessor else DESCRIPTORS[record['desc']], 'elapsed_ms_mod32': elapsed_ms,
                 'source_canonical': canonical(record['effective_source']), 'dma': dma,
                 'dma_arithmetic': dma_sizes(dma)}
        if v2:
            context = fields(lines[offset + 4], CONTEXT)
            reader = fields(lines[offset + 5], READER)
            if context['reader_valid'] not in (0, 1):
                raise ValueError('Invalid reader flag')
            if context['reader_valid'] != int(not accessor and descriptor['rd_channel'] == 10):
                raise ValueError('Reader channel/valid flag mismatch')
            if accessor:
                if (any(record[k] for k in ('desc', 'source_field', 'x', 'y', 'precision')) or
                        descriptor['context_job'] != context['argument_job'] or
                        (kind == 6 and (record['effective_source'] or context['argument_source'])) or
                        (kind == 7 and record['effective_source'] != context['argument_source'])):
                    raise ValueError('Invalid register-only source accessor record')
            elif context['argument_job'] or context['argument_source']:
                raise ValueError('Unexpected accessor arguments in descriptor record')
            snapshot = {k.removeprefix('reader_'): value for k, value in reader.items()}
            snapshot.update(dma_before=context['reader_before'], after=context['reader_after'],
                            address=context['reader_address'], pointer=context['reader_pointer'], flags=context['reader_flags'])
            # Validate geometry even when no reader was sampled.
            arithmetic = dma_sizes(snapshot)
            if not context['reader_valid'] and (any(reader.values()) or any(context[k] for k in ('reader_before', 'reader_after', 'reader_address', 'reader_pointer', 'reader_flags'))):
                raise ValueError('Unsampled reader contains data')
            entry.update(context=context, reader=snapshot, reader_arithmetic=arithmetic,
                         original_cpu_mode=context['original_cpsr'] & 31,
                         original_IRQ_masked=bool(context['original_cpsr'] & 128),
                         wait_safety_verified=False)
        for previous in events:
            if not accessor and previous['record']['desc'] and entry['source_canonical'] is not None and previous['source_canonical'] == entry['source_canonical'] and previous['record']['desc'] != record['desc']:
                source_matches.append({'earlier_event': previous['record']['event'], 'later_event': i,
                                       'canonical_source': entry['source_canonical'],
                                       'delta_ms_mod32': (record['ms'] - previous['record']['ms']) & MASK,
                                       'delta_us_mod32': (record['us'] - previous['record']['us']) & MASK})
        events.append(entry)
    retained_starts = sum(e['record']['kind'] == 3 for e in events)
    if header['starts'] < retained_starts or (not header['dropped'] and header['starts'] != retained_starts):
        raise ValueError('Start count disagrees with retained events')
    return {'provenance': provenance, 'format_version': 2 if v2 else 1, 'status': header,
            'core_cache_collision': bool(header['core_error'] & 0x10), 'events': events,
            'data_origin': 'Input log is not independently attested as on-camera execution.',
            'equal_source_addresses_across_descriptors': source_matches,
            'warnings': warnings,
            'limits': ['Equal addresses may be reused or accessed by unobserved consumers.',
                       'Candidate JPEG descriptor is not proved to feed Canon review.',
                       'EDMAC0 is photo readout; descriptor RD1 may use another channel.',
                       'DMA arithmetic and idle samples do not prove ownership or cache coherence.',
                       'Stored task ID does not establish a context that may safely wait.',
                       'Source accessor entry logs arguments before Canon tag validation; publication success is unproved.',
                       'Delivered controls are sampled at hooks, not latched at full shutter.'],
            'exclusive_RAW_handoff_verified': False, 'matching_review_verified': False,
            'mirrored_CR2_verified': False}


def analyze_probe(path):
    lines, provenance = read_log(path)
    if lines[:2] != ['Mirror shutter observation and RAW source probe / EOSM202 / ML ed3e7c0',
                     'Read-only samples; no owned RAW lease, no mirrored DNG saved']:
        raise ValueError('Not a supported dev8/dev9 EOSM202 probe')
    geometry = [line for line in lines if line.startswith('width=')]
    if len(geometry) != 1:
        raise ValueError('Missing or duplicate probe geometry')
    if len(lines) < 3:
        raise ValueError('Truncated probe status')
    status = fields(lines[2], 'stage error request request_ms preview_ms qr_ms read_ms recheck_ms polls')
    # Probe uses buffer/dma_* hex fields; keep the parser explicit so addresses
    # containing only decimal-looking digits are never read as decimal.
    raw = geometry[0].split()
    values = {}
    for item in raw:
        key, sep, value = item.partition('=')
        if not sep or key in values:
            raise ValueError('Malformed probe geometry')
        base = 16 if key in ('buffer', 'dma_address', 'dma_pointer') else 10
        if not re.fullmatch(r'[0-9a-fA-F]+' if base == 16 else r'[0-9]+', value):
            raise ValueError('Malformed probe value')
        values[key] = int(value, base)
    if set(values) != set('width height pitch bytes bits buffer dma_state dma_address dma_pointer'.split()) or any(v > MASK for v in values.values()):
        raise ValueError('Invalid probe geometry fields')
    v = values
    end = canonical(v['buffer'])
    pointer = canonical(v['dma_pointer'])
    difference = pointer - end - v['bytes'] if end is not None and pointer is not None else None
    return {'provenance': provenance, 'status': status, 'reported': v,
            'geometry_consistent': v['pitch'] * v['height'] == v['bytes'] and v['pitch'] * 8 == v['width'] * v['bits'],
            'pointer_minus_contiguous_frame_end': difference,
            'pointer_one_row_beyond': bool(v['pitch'] and difference == v['pitch']),
            'transfer_geometry_available': False,
            'possible_core_even_height_rounding': 'Pinned raw.c computes N+1, then rounds height down to even; actual EDMAC geometry is required.',
            'exclusive_RAW_handoff_verified': False}


def correlate(trace, probe):
    """Compare metadata, without asserting that two input files are one shot.

    A flat transfer can explain the QR even-height discrepancy. Descriptor
    The verified ROM path adds RD1_Offset to RD1_Address for SetEDmac. This
    address arithmetic is not proof of sensor row layout, crop or a write lease.
    """
    v = probe['reported']
    rows = []
    source_layout = []
    for e in trace['events']:
        r, d, a = e['record'], e['dma'], e['dma_arithmetic']
        same = (canonical(v['dma_address']) is not None and
                canonical(v['buffer']) == canonical(v['dma_address']) and
                canonical(v['dma_address']) == canonical(d['address']) and
                canonical(v['dma_pointer']) == canonical(d['pointer']))
        # Explicit flat-path shape; the general arithmetic alone cannot infer
        # row layout from arbitrary signed/strided transfers.
        flat = (d['xa'] == d['xb'] == v['pitch'] and v['pitch'] > 0 and
                d['ya'] == d['yb'] == d['yn'] == 0 and
                all(d[k] == 0 for k in ('off1a', 'off2a', 'off1b', 'off2b', 'off3')))
        if same and flat and a['pointer_matches_computed_end'] and probe['geometry_consistent']:
            height = d['xn'] + 1
            rows.append({'event': r['event'], 'transfer_rows': height,
                         'probe_rows': v['height'],
                         'core_even_height_matches': (height & ~1) == v['height'],
                         'extra_bytes': a['transferred_bytes_arithmetic'] - v['bytes']})
        if r['desc'] and e['source_canonical'] is not None and canonical(v['buffer']) is not None:
            configured = e['source_canonical'] + e['descriptor']['rd_offset']
            source_layout.append({'event': r['event'], 'path': e['path'],
                                  'probe_buffer_minus_descriptor_base': canonical(v['buffer']) - e['source_canonical'],
                                  'descriptor_RD1_Offset': e['descriptor']['rd_offset'],
                                  'RD1_address_arithmetic': configured,
                                  'RD1_address_outside_canonical_RAM': not 0x1000 <= configured < 0x20000000,
                                  'probe_buffer_minus_RD1_address_arithmetic': canonical(v['buffer']) - configured,
                                  'source_layout_verified': False})
    ordering = []
    for jpeg in trace['events']:
        if jpeg['path'] != 'candidate JPEG' or jpeg['record']['kind'] != 3:
            continue
        for raw in trace['events']:
            if raw['path'] == 'candidate JPEG' or raw['record']['kind'] != 3:
                continue
            if (raw['record']['event'] > jpeg['record']['event'] and
                    jpeg['source_canonical'] is not None and
                    canonical(jpeg['descriptor']['context_job']) is not None and
                    raw['source_canonical'] == jpeg['source_canonical'] and
                    raw['descriptor']['context_job'] == jpeg['descriptor']['context_job']):
                ordering.append({'JPEG_start_event': jpeg['record']['event'],
                                 'RAW_start_event': raw['record']['event'],
                                 'delta_us_mod32': (raw['record']['us'] - jpeg['record']['us']) & MASK,
                                 'same_numeric_job_and_source': True})
    return {'flat_transfer_observations': rows,
            'descriptor_and_probe_layout': source_layout,
            'recorded_JPEG_before_RAW_starts': ordering,
            'input_files_same_capture_verified': False,
            'limits': ['Matching metadata can be reused across captures; file pairing needs external provenance.',
                       'The candidate JPEG path is not proved to feed Canon review.',
                       'Probe buffer and descriptor base/offset are distinct; source layout is not established.',
                       'An earlier JPEG start rules out relying on a later RAW-only mutation for that earlier JPEG result.',
                       'Flat transfer arithmetic explains height rounding, not ownership, cache coherence or safe pixel access.'],
            'exclusive_RAW_handoff_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', nargs='?', type=Path)
    parser.add_argument('--probe', type=Path)
    args = parser.parse_args()
    if not args.trace and not args.probe:
        parser.error('Provide a trace, a probe, or both')
    try:
        result = {'kind': 'read-only-EOSM202-native-capture-log-analysis'}
        if args.trace:
            result['trace'] = analyze_trace(args.trace)
        if args.probe:
            result['probe'] = analyze_probe(args.probe)
        if args.trace and args.probe:
            result['cross_observations'] = correlate(result['trace'], result['probe'])
    except (ValueError, UnicodeError, OSError) as error:
        parser.exit(2, f'Log analysis refused: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
