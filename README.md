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
