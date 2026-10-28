# VNM Direct Drive vendor protocol (0483:a3d5) — findings

Source: `capture/vnm.pcapng` (USBPcap, real Windows PC, SimCenter 6.3.0.2, device address 18; parsed with
`tools/usbmon_parse.py capture/vnm.pcapng --dev 18 --ids 14,15,1a,41`), plus the failed VM captures
`capture/00-connect.txt`, `capture/01-reconnect.txt`. Screenshot of start state: `capture/initialvalues.png`.
All offsets below are into the 64-byte interrupt report INCLUDING the report-ID byte (byte 0), as on the wire and as `/dev/hidraw` shows it.

## Transport
- Interrupt endpoint 1 OUT/IN, 64 B. Report IDs: OUT `0x14` (command), OUT `0x1a` (constant `1a 01 00…`, ~500 Hz while SimCenter runs — purpose unknown, may be a keepalive),
  IN `0x41` (command reply, plus page `0xaa` heartbeat at 1 Hz = temperatures as float32).
- Settings live in numbered "pages" (3, 5, 8 seen). SimCenter edits are whole-page read-modify-write.

## Read page (SimCenter -> device)
`14 0c 0a 00 <page> <seq> 00 00 ff ff ff ff <bytes that look like uninitialised host memory>`
Reply: `41 <page> <seq> <payload...>`; payload starts at reply byte 3. SimCenter sends each request, then retries `14 0c 00 90 90 <seq> …` ~3x about 3 ms apart (the device also repeats the reply).
Page 7 (`seq fd`) replies `41 07 fd 90 00…`, page 4 replies all zero — meaning unknown.

## Write page
`14 <len+12> 07 01 <page> 00 00 <len> <payload[len]>`
| page | len | note |
|---|---|---|
| 3 | 52 | base settings |
| 5 | 28 | user effects |
| 8 | 7 | `00 64 00 64 00 64 00` in all captures; never changed (likely DirectInput effect gains, not yet proven) |

While a slider is being dragged SimCenter sends only the changed page about once per second; on release / Apply it sends pages 3, 5, 8 together. After a write the device echoes the page as `41 <page> 00 …`.

## Fields resolved (payload index = offset inside `<payload>`; wire offset = 8 + index for writes, 3 + index for replies)
| key | label | page | payload idx | width | scale | initial | evidence |
|---|---|---|---|---|---|---|---|
| steering_range | Steering Range (deg) | 3 | 8 | le16 | 1 | 0x0384=900 | screenshot 900; sweep 900→…528…→900 |
| overall_gain | Overall Gain (%) | 3 | 22 | le16 | 1/100 | 0x2328=9000 | screenshot 90; 3800, 3700 (38, 37), 9100, back to 9000 |
| damper_gain | Damper Gain | 5 | 2 | le16 | 1/100 | 300 | screenshot 3 |
| friction_gain | Friction Gain | 5 | 6 | le16 | 1/100 | 200 | screenshot 2 |
| inertia_gain | Inertia Gain | 5 | 10 | le16 | 1/100 | 0 | screenshot 0 |
| spring_gain | Spring Gain | 5 | 14 | le16 | 1/100 | 0 | screenshot 0 |
| overall_filter | Overall Filter | 3 | 14 | le16 | wire = 501 - value | 276 (wire 0x00e1) | capture/02-filter.pcapng: typed 100/300/470/276 -> 0x0191/0x00c9/0x001f/0x00e1 |

Ordering of changes in the pcapng matched the requested order (steering, gain, filter, damper, friction, inertia, spring), which is how each field was assigned.

## Unresolved
- (resolved) Overall Filter: see table; SimCenter slider range 0..500 (wire 501..1), manual recommends 300-470.
- FFB Mode, Calibrate, Advanced tab, Game Settings: not captured.
- Connect/handshake with firmware version (1.1.1.51): the pcapng starts after SimCenter was already connected. In the VM SimCenter never got replies (VERSION 0.0.0.0, controls disabled); there its first and only request was `14 40 00 09 04 00 00 34 00…` and the device never answered.
- Page 3 other bytes (`01 50 bc 03`, several `10 27` = 10000 fields, `00 08 aa`), page 5 other `10 27` fields.
- Whether `0x1a` keepalive is required for writes.

## Connect sequence (capture/02-filter.pcapng, wheel plugged in after SimCenter started)
1. t=5.68 `14 40 00 09 04 00 00 34 …` (no reply seen), `0x1a` stream begins.
2. t=7.88 `14 0c 0b 00 00 e0 …` -> device streams `41 00 e0 01 01 01 33` (~every 2 ms until the next request) = firmware 1.1.1.51 (matches SimCenter's VERSION).
3. `14 0c 0b 00 01 e1`, `14 0c 0b 00 02 e2` (pages 1, 2 all zero), `14 0c 0a 02 00 fe`, then `0a` reads of pages 3,5,4,8 (seq e3,e4,e5,ea).
Unknown whether the device needs 1-2 or the 0x1a stream before answering `0a` page reads from another host.

## Center and Save (capture/03-save.pcapng, 04-center-30-deg-left.pcapng, 04b-center-90-deg-right.pcapng)
- **Center** (current wheel position becomes zero): `14 0c 07 05 00 00 00 00 00 00 00 00 …`. Identical in both Center captures
  (30 deg left, 90 deg right), including SimCenter's uninitialised trailing bytes, so it carries no angle. No reply.
- **Apply**: write pages 3, 5, 8 (same `14 <len+12> 07 01 <page> 00 00 <len> …` format) and nothing else.
- **Save** (SimCenter): the same three page writes with identical payloads, then `14 0c 0a 03 07 fd …` (page 7, flag 3), answered by
  `41 07 fd 90`, which SimCenter acknowledges with `14 0c 00 90 90 fd 00 00 ff ff ff ff` three times, ~4 ms apart.
  The ~300 ms before the reply is the wheelbase's page-8 echo flood after any three-page write (Apply has it too), not a flash delay.
- **Persistence: the wheelbase keeps NOTHING we write.** Tested on hardware with a full replay of SimCenter's session (handshake with
  acks, `14 0d 00 ec … 01`, 500 Hz `1a 01 00…` keepalive, Apply triple, 9 s, Save triple + commit + acks): after a power cycle the flash
  value was unchanged every time (also with just triple + commit, and with plain slider writes). SimCenter's Save persisting is most likely
  SimCenter re-applying its stored profile when the wheelbase reconnects (vnm.pcapng t=5.5 shows a three-page write + the page-7 read at
  startup). So Obelisk stores the values itself (profiles in `~/.config/obelisk/profiles/<name>.json`, active profile name in
  `~/.config/obelisk/active.json`) and re-applies them on every connect
  (`Device.apply_values`, or `obelisk --apply`). The commit/ack packets are intentionally NOT implemented.

## Windows session 2026-10-24 (capture/05..10, notes in capture/NOTES.md; key claims re-verified with tools/usbmon_parse.py)
- **Max Torque Mode is a wheelbase command, not UI-only:** `14 0d 00 ec 00 00 00 00 <m> 00 …`, m = 1 (ON) / 0 (OFF), sent the moment the
  toggle is clicked, independent of Apply (capture 10: t=27.68 m=0, t=76.18 m=1; no reply within 0.5 s). Apply bursts carry nothing about it
  (identical with the toggle on or off). SimCenter sends its current mode once when it *launches* (capture 07, t=16.10) but NOT when the
  wheelbase reconnects after a power cycle while SimCenter keeps running (capture 06). The physical effect (OFF = half torque per the manual
  and the operator) was not measured. This is the `14 0d 00 ec … 01` packet our earlier replays also sent (wheel was already ON).
- **SimCenter does not re-apply anything on reconnect.** Capture 06 (PSU cycled, SimCenter running): 0 page writes on the new device
  address; it only reads pages 0/1/2/3/5/4/8 about 3 s after the wheelbase reappears and displays what the wheel returns (first page-3 reply:
  steering 360, gain 9000, filter wire 208). Capture 07 (SimCenter closed during the cycle): same replies, no writes. Profiles live in
  SimCenter; switching profile = a 3/5/8 burst of that profile's values + the page-7 commit read. The write header byte 2 is the
  profile id (`07` = "iRacing TF", `09` = new profile "zz-test"; inferred, tested with two profiles).
- **Settings saved in SimCenter (540 / gain 50, capture 05: Apply + Save) were NOT in the wheelbase after a power cycle.** What came back was
  360 / 90 / filter 293, the state the wheel already had before the capture.
- **UNRESOLVED CONTRADICTION, Center across power cycles:** on Windows (capture 06, 07) the axis stayed at about 0 (-5 before, -9 after) after a
  power cycle while the physical wheel stayed about 30 deg off its original straight-ahead, i.e. the Center offset SURVIVED a power cycle with
  nothing re-sending it (no `07 05` after reconnect). On Linux (this repo, 2026-10-24) the same measurement went the other way: Center made the
  axis 0, and after a power cycle with the wheel untouched it read 16471 again (hardware zero). Not explained. Differences between the two
  setups that are untested: SimCenter's session start (`14 40 00 09 04`, `14 0d 00 ec … 01`, 500 Hz `1a` keepalive) was active on Windows;
  the delay between Center and power-off (about 64 s on Windows); our Center packet zeroes the trailing bytes SimCenter leaves as stale memory.
- **Slider ranges (SimCenter UI):** Steering Range 180-1080, Overall Gain 0-100, Overall Filter 0-500, Damper/Friction/Inertia/Spring 0-100.
  Overall Filter UI 0 was written as wire 0, not 501 (UI 500 -> wire 1), so `wire = 501 - x` does not hold at x = 0.
  Sliders write live (single page, full page re-sent); Apply = 3/5/8 burst; Save = 3/5/8 burst + page-7 commit read.

- **Dropped:** a "Saved center" display built on the assumption that Center is lost at power-off. It is not implemented any more
  (`obelisk/center.py` keeps only the counts-to-degrees scale for the live angle row).
- **jstest deadzone:** the kernel's input device reports `flat = 4095` (12.5% of the axis half-range) for ABS_X/Y/Z; joydev (`/dev/input/js*`)
  applies it, so `jstest` shows 0 within about +/-56 deg at a 900 deg range while the wheelbase reports the true position
  (measured: raw 13.8 deg, js axis 0).
