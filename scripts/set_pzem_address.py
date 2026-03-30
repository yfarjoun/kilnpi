#!/usr/bin/env python3
"""Set the Modbus slave address of a PZEM-016 module.

Usage:
    python scripts/set_pzem_address.py --current 1 --new 2

IMPORTANT: Connect only ONE PZEM at a time when changing addresses.
Stop the kilnpi service first: systemctl --user stop kilnpi
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import settings
from backend.modbus.pzem import set_pzem_address


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set PZEM-016 Modbus address. Connect only ONE PZEM at a time."
    )
    parser.add_argument("--current", type=int, default=1, help="Current address (default: 1)")
    parser.add_argument("--new", type=int, required=True, help="New address (1-247)")
    parser.add_argument("--port", type=str, default=None, help="Serial port (auto-detect if omitted)")
    args = parser.parse_args()

    if not 1 <= args.new <= 247:
        print(f"Error: address must be 1-247, got {args.new}")
        sys.exit(1)

    port = args.port or settings.serial_port
    print(f"Port: {port}")
    print(f"Changing PZEM address from {args.current} to {args.new}...")

    try:
        set_pzem_address(port, args.current, args.new, settings.baud_rate)
        print(f"Success! PZEM address changed to {args.new}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
