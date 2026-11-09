"""Generate a video of a shot or goal from a match, e.g.

    python scripts/generate_video.py --match J03WMX --event EVENT_ID --format tiktok

This is the same command as the ``generate-video`` console script. Use ``--list-events``
to see the event IDs of a match.
"""

import sys

from tracking_visualized.cli.generate_video import main

if __name__ == "__main__":
    sys.exit(main())
