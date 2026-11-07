from itertools import islice

from sample_data import METADATA_FILE, TRACKING_FILE

from tracking_visualized.providers.dfl import (
    iter_tracking_samples,
)


def main() -> None:
    samples = iter_tracking_samples(
        TRACKING_FILE,
        METADATA_FILE,
    )

    for sample in islice(samples, 20):
        print(sample)


if __name__ == "__main__":
    main()
