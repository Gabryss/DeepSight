from __future__ import annotations

import json
import sys
from pathlib import Path

from deepsight.bags import inspect_bag
from deepsight.pointcloud import _read_pointcloud_from_bag


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: python -m deepsight.pointcloud_cli BAG_PATH TOPIC MAX_POINTS", file=sys.stderr)
        return 2

    bag_path = Path(sys.argv[1]).expanduser()
    topic = sys.argv[2]
    max_points = int(sys.argv[3])
    bag = inspect_bag(bag_path)
    if not bag:
        print(json.dumps({"ok": False, "error": "bag metadata not found", "points": []}))
        return 0

    print(json.dumps(_read_pointcloud_from_bag(bag, topic, max_points), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
