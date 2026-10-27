# tools/

## Files

| File              | What                                                                         | When to read                                                    |
| ----------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `usbmon_parse.py` | Parses usbmon text and USBPcap `.pcapng`; lists devices, diffs two captures  | Decoding new protocol behavior, verifying a claim in the docs   |
| `axis.py`         | Prints the live steering position from the wheelbase (read-only)             | Checking that axis reports and Center behave as documented      |

## Run

`python tools/usbmon_parse.py capture.pcapng --dev <addr> --ids 14,15,1a,41`

`python tools/axis.py [seconds]`
