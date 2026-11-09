# Tracking Visualized

A Python project for generating polished 2D football match replays from player tracking, ball tracking, and event data.

The project aims to transform real professional football match data into animated tactical sequences that can eventually be exported as vertical videos.


## Dataset

This project uses the **Integrated Dataset of Synchronized Spatiotemporal and Event Data in Elite Soccer (IDSSE)** provided by the **Deutsche Fußball Liga (DFL)** and **Sportec Solutions**.

The dataset contains synchronized:

- Match metadata
- Event data
- Player tracking data
- Ball tracking data

Tracking data is recorded at **25 frames per second**.

### Sample Match

The raw match consists of three files:

```text
DFL_02_01_matchinformation_DFL-COM-000001_DFL-MAT-J03WMX.xml

DFL_03_02_events_raw_DFL-COM-000001_DFL-MAT-J03WMX.xml

DFL_04_03_positions_raw_observed_DFL-COM-000001_DFL-MAT-J03WMX.xml
```

These contain the match metadata, event data, and tracking data respectively.

## Dataset License and Attribution

The IDSSE dataset is distributed under the **Creative Commons Attribution 4.0 International (CC BY 4.0)** license.

When using the dataset, credit should be given to the **Deutsche Fußball Liga (DFL)** as the data provider.

This project uses data from:

> Bassek, M., Rein, R., Weber, H., & Memmert, D. (2025).  
> *An integrated dataset of spatiotemporal and event data in elite soccer.*  
> Scientific Data, 12, 195.

Original dataset DOI:

```text
10.6084/m9.figshare.28196177
```

The raw dataset is **not committed to this repository**.

## Downloading the Sample Data

The project expects the sample match data to be stored locally under:

```text
data/
└── raw/
    └── dfl/
        └── J03WMX/
```

A public mirror of the IDSSE dataset is available through the `pysport/idsse-data` dataset on Hugging Face.

Using `uvx`, the required files can be downloaded without adding the Hugging Face CLI as a permanent project dependency:

```bash
uvx --from huggingface-hub hf download pysport/idsse-data \
  DFL_02_01_matchinformation_DFL-COM-000001_DFL-MAT-J03WMX.xml \
  DFL_03_02_events_raw_DFL-COM-000001_DFL-MAT-J03WMX.xml \
  DFL_04_03_positions_raw_observed_DFL-COM-000001_DFL-MAT-J03WMX.xml \
  --repo-type dataset \
  --local-dir data/raw/dfl/J03WMX
```

## Rendering Video

Animations are encoded as **H.264 MP4** (`yuv420p`, 1080x1920 at 25 fps by default) with [FFmpeg](https://ffmpeg.org/). FFmpeg, including `ffprobe` and the `libx264` encoder, must be installed separately:

```bash
brew install ffmpeg        # macOS
sudo apt install ffmpeg    # Debian / Ubuntu
```

### Generating a video from an event

One command turns a shot or goal of a match into a TikTok-ready MP4 (1080x1920, with the pitch rotated and the event type, time, shirt number and team shown above it):

```bash
uv run generate-video --match J03WMX --event EVENT_ID --format tiktok
```

The match files are read from `data/raw/dfl/<MATCH_ID>/` (see [Downloading the Sample Data](#downloading-the-sample-data)). List the shots and goals of a match with their event IDs first:

```bash
uv run generate-video --match J03WMX --list-events
```

| Option | Meaning |
| --- | --- |
| `--match MATCH_ID` | Match to use, e.g. `J03WMX` (`DFL-MAT-J03WMX` works too). |
| `--event EVENT_ID` | Shot or goal to render. |
| `--format` | Output format; `tiktok` (default) is the only one for now. |
| `-o`, `--output` | Output file, default `output/<match>_<event>_<format>.mp4`. Folders are created and an existing file is replaced. |
| `--pre`, `--post` | Seconds before (default 5) and after (default 3) the event; they cannot both be 0. |
| `--data-dir` | Folder with the match folders, default `data/raw/dfl`. |
| `--ffmpeg PATH` | FFmpeg to use, default `$FFMPEG_BINARY`, then `ffmpeg` on `PATH`. |
| `--verbose` | Show the full traceback on errors. |

`python scripts/generate_video.py ...` and `python -m tracking_visualized.cli.generate_video ...` do the same. Loading reads the large tracking file twice, so expect a minute or two before rendering starts; rendering an 8 second clip takes about the same again. Progress is printed along the way. Problems such as missing data files, an unknown event ID or a missing FFmpeg end with a single `error:` line and exit code 1.

The older helper script renders the first goal of the sample match:

```bash
uv run python scripts/render_players.py --video
```

## Development

### Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

### Install Dependencies

```bash
uv sync
```

### Run Tests

```bash
uv run pytest
```

### Run Linting

```bash
uv run ruff check .
```

### Check Formatting

```bash
uv run ruff format --check .
```

To automatically format the project:

```bash
uv run ruff format .
```

### Run All Pre-commit Hooks

```bash
uv run pre-commit run --all-files
```

## Project Structure

```text
football-tactical-replay/
├── data/
│   ├── raw/
│   │   └── dfl/
│   │       └── J03WMX/
│   └── processed/
├── output/
├── scripts/
├── src/
│   └── tracking-visualized/
├── tests/
├── .github/
│   └── workflows/
├── pyproject.toml
├── uv.lock
└── README.md
```
