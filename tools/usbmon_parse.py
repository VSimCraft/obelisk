#!/usr/bin/env python3
"""Parse usbmon text or USBPcap .pcapng captures; print vendor report transfers and diff captures."""
import argparse
import struct
import sys
from collections import defaultdict


def parse_text(path, dev, ids):
    """Return list of dicts: t, dir, ep, len, data (bytes), id."""
    out = []
    pending = {}  # urb -> (setup tuple or None) from submissions
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            tok = line.split()
            if len(tok) < 5:
                continue
            urb, usec, ev, addr = tok[0], tok[1], tok[2], tok[3]
            parts = addr.split(":")
            if len(parts) != 4 or ev not in "SCE":
                continue
            kind = parts[0]
            if kind not in ("Ci", "Co", "Ii", "Io"):
                continue
            if dev is not None and int(parts[2]) != int(dev):
                continue
            try:
                t = int(usec) / 1e6
            except ValueError:
                continue
            rest = tok[4:]
            setup = None
            if rest[0] == "s":  # setup packet: s bmRT bReq wValue wIndex wLen len
                if len(rest) < 6:
                    continue
                setup = tuple(rest[1:6])
                rest = rest[6:]
            else:
                rest = rest[1:]  # status
            n = 0
            if rest:
                try:
                    n = int(rest[0])
                except ValueError:
                    pass
                rest = rest[1:]
            data = b""
            if rest and rest[0] == "=":
                try:
                    data = bytes.fromhex("".join(rest[1:]))
                except ValueError:
                    continue
            if setup:
                pending[urb] = setup
            elif kind.startswith("C") and urb in pending and ev == "C":
                setup = pending.get(urb)
            if ev == "C":
                pending.pop(urb, None)
            is_ctl = kind[0] == "C"
            if is_ctl:
                # Co: data in submission; Ci: data in completion
                if not data:
                    continue
                if kind == "Co" and ev != "S":
                    continue
                if kind == "Ci" and ev != "C":
                    continue
                if setup is not None:
                    try:
                        req = int(setup[1], 16)
                    except ValueError:
                        req = None
                    if req not in (0x09, 0x01):  # SET_REPORT / GET_REPORT
                        continue
            else:
                if not data:
                    continue
                # Io: submission carries data; Ii: completion carries data
                if kind == "Io" and ev != "S":
                    continue
                if kind == "Ii" and ev != "C":
                    continue
            rid = data[0]
            if ids is not None and rid not in ids:
                continue
            out.append({"t": t, "dir": "OUT" if kind.endswith("o") else "IN",
                        "ep": parts[3], "kind": kind, "len": n or len(data),
                        "data": data, "id": rid})
    return out


PCAPNG_MAGIC = b"\x0a\x0d\x0d\x0a"
DLT_USBPCAP = 249


def pcapng_packets(path):
    """Yield (t_abs, linktype, packet bytes) for every EPB; t in seconds."""
    with open(path, "rb") as f:
        buf = f.read()
    pos, end = 0, len(buf)
    e = "<"
    ifaces = []  # (linktype, seconds per tick)
    while pos + 12 <= end:
        if buf[pos:pos + 4] == PCAPNG_MAGIC:
            bom = buf[pos + 8:pos + 12]
            if bom == b"\x4d\x3c\x2b\x1a":
                e = "<"
            elif bom == b"\x1a\x2b\x3c\x4d":
                e = ">"
            else:
                raise SystemExit(f"{path}: bad pcapng byte-order magic")
            ifaces = []
        btype, blen = struct.unpack_from(e + "II", buf, pos)
        if blen < 12 or pos + blen > end:
            raise SystemExit(f"{path}: truncated/corrupt pcapng block at offset {pos}")
        body = buf[pos + 8:pos + blen - 4]
        if btype == 1 and len(body) >= 8:  # IDB
            link = struct.unpack_from(e + "H", body, 0)[0]
            res = 1e-6
            o = 8
            while o + 4 <= len(body):
                code, ln = struct.unpack_from(e + "HH", body, o)
                if code == 0:
                    break
                if code == 9 and ln >= 1:
                    v = body[o + 4]
                    res = 2.0 ** -(v & 0x7F) if v & 0x80 else 10.0 ** -v
                o += 4 + ((ln + 3) & ~3)
            ifaces.append((link, res))
        elif btype == 6 and len(body) >= 20:  # EPB
            ifid, hi, lo, cap, _orig = struct.unpack_from(e + "IIIII", body, 0)
            if ifid < len(ifaces):
                link, res = ifaces[ifid]
                yield ((hi << 32 | lo) * res, link, body[20:20 + cap])
        pos += blen


def usbpcap_records(path):
    """Yield dicts for each USBPcap packet (all link-type-249 packets)."""
    t0 = None
    warned = set()
    for t, link, pkt in pcapng_packets(path):
        if link != DLT_USBPCAP:
            if link not in warned:
                warned.add(link)
                print(f"{path}: skipping packets with unsupported link type {link} "
                      f"(only {DLT_USBPCAP}/USBPcap is supported)", file=sys.stderr)
            continue
        if len(pkt) < 27:
            continue
        hlen, irp, _st, _fn, info, bus, dev, ep, tr, _dlen = struct.unpack_from("<HQIHBHHBBI", pkt, 0)
        stage = pkt[27] if tr == 2 and len(pkt) > 27 else None
        if t0 is None:
            t0 = t
        yield {"t": t - t0, "irp": irp, "in_dir": bool(info & 1), "bus": bus, "dev": dev,
               "ep": ep & 0x7F, "ep_in": bool(ep & 0x80), "tr": tr, "stage": stage,
               "payload": pkt[hlen:]}


def parse_pcapng(path, dev, ids):
    out = []
    setups = {}  # (bus, dev) -> 8-byte setup of the last setup stage
    for r in usbpcap_records(path):
        if dev is not None and r["dev"] != int(dev):
            continue
        pl, tr, devkey = r["payload"], r["tr"], (r["bus"], r["dev"])
        if tr == 1:
            if not pl:
                continue
            # host->device submission (OUT) or device->host completion (IN)
            if r["ep_in"] != r["in_dir"]:
                continue
            data, direction, kind = pl, "IN" if r["ep_in"] else "OUT", "Ii" if r["ep_in"] else "Io"
        elif tr == 2:
            if r["stage"] == 0 and len(pl) >= 8:
                setups[devkey] = pl[:8]
                if r["in_dir"] or len(pl) == 8:
                    continue
                pl = pl[8:]  # setup + OUT data in one packet
            elif r["stage"] != 1:
                continue
            setup = setups.get(devkey)
            if not pl or setup is None or setup[1] not in (0x09, 0x01):
                continue
            # data stage: OUT data is host->device, IN data is a completion
            if r["in_dir"] != bool(setup[0] & 0x80):
                continue
            data, direction = pl, "IN" if setup[0] & 0x80 else "OUT"
            kind = "Ci" if direction == "IN" else "Co"
        else:
            continue
        if ids is not None and data[0] not in ids:
            continue
        out.append({"t": r["t"], "dir": direction, "ep": str(r["ep"]) if tr == 2 else f"{r['ep'] | (0x80 if r['ep_in'] else 0):02x}",
                    "kind": kind, "len": len(data), "data": data, "id": data[0]})
    return out


def list_devices(path):
    if not is_pcapng(path):
        raise SystemExit("--list-devices requires a .pcapng (USBPcap) capture")
    counts = defaultdict(int)
    ids = {}
    setups = {}
    for r in usbpcap_records(path):
        k = (r["bus"], r["dev"])
        counts[k] += 1
        if r["tr"] != 2:
            continue
        pl = r["payload"]
        if r["stage"] == 0 and len(pl) >= 8:
            setups[k] = pl[:8]
        elif r["stage"] == 1 and r["in_dir"] and len(pl) >= 12:
            s = setups.get(k)
            if s and s[1] == 6 and s[3] == 1:  # GET_DESCRIPTOR, DEVICE
                ids[k] = struct.unpack_from("<HH", pl, 8)
    for k in sorted(counts):
        vp = f" vid:pid={ids[k][0]:04x}:{ids[k][1]:04x}" if k in ids else ""
        print(f"bus={k[0]} device={k[1]} packets={counts[k]}{vp}")


def is_pcapng(path):
    with open(path, "rb") as f:
        return f.read(4) == PCAPNG_MAGIC


def parse_file(path, dev, ids):
    return (parse_pcapng if is_pcapng(path) else parse_text)(path, dev, ids)


def fmt(x):
    return (f"t={x['t']:.6f} {x['dir']} {x['kind']} ep={x['ep']} len={x['len']} "
            f"id=0x{x['id']:02x} {x['data'].hex(' ')}")


def le16(b, i):
    return struct.unpack_from("<H", b, i)[0] if i + 2 <= len(b) else None


def diff(a, b):
    ga, gb = defaultdict(list), defaultdict(list)
    for x in a:
        ga[x["id"]].append(x)
    for x in b:
        gb[x["id"]].append(x)
    ndiff = 0
    for rid in sorted(set(ga) | set(gb)):
        la, lb = ga.get(rid, []), gb.get(rid, [])
        for seq in range(max(len(la), len(lb))):
            if seq >= len(la) or seq >= len(lb):
                side = "B" if seq >= len(la) else "A"
                print(f"id=0x{rid:02x} seq={seq}: only in {side}")
                ndiff += 1
                continue
            da, db = la[seq]["data"], lb[seq]["data"]
            offs = [i for i in range(max(len(da), len(db)))
                    if (da[i] if i < len(da) else None) != (db[i] if i < len(db) else None)]
            if not offs:
                continue
            ndiff += 1
            print(f"id=0x{rid:02x} seq={seq}:")
            for i in offs:
                va = f"0x{da[i]:02x}/{da[i]}" if i < len(da) else "--"
                vb = f"0x{db[i]:02x}/{db[i]}" if i < len(db) else "--"
                l16a, l16b = le16(da, i), le16(db, i)
                s = f"  off={i}: A={va} B={vb}"
                if l16a is not None and l16b is not None:
                    s += f"  le16 A=0x{l16a:04x}/{l16a} B=0x{l16b:04x}/{l16b}"
                print(s)
    if not ndiff:
        print("no differences")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture", nargs="?")
    ap.add_argument("--dev", help="USB device number (from lsusb -d 0483:a3d5)")
    ap.add_argument("--ids", help="comma-separated hex report IDs, e.g. 14,15,1a,41")
    ap.add_argument("--list-devices", action="store_true",
                    help="list bus/device, packet counts and vid:pid (pcapng only)")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"))
    args = ap.parse_args()
    ids = {int(s, 16) for s in args.ids.split(",") if s} if args.ids else None
    if args.list_devices:
        if not args.capture:
            ap.error("--list-devices needs a capture file")
        list_devices(args.capture)
    elif args.diff:
        diff(parse_file(args.diff[0], args.dev, ids), parse_file(args.diff[1], args.dev, ids))
    elif args.capture:
        for x in parse_file(args.capture, args.dev, ids):
            print(fmt(x))
    else:
        ap.error("capture file or --diff A B required")


if __name__ == "__main__":
    sys.exit(main())
