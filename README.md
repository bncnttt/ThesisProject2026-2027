# AgapAI (Phase 1)

## Overview

This repository contains a thesis-phase prototype for a disaster monitoring and data ingestion pipeline built around the Bluesky social platform. The project demonstrates how to collect disaster-related posts using multilingual keyword search, map author social graphs, extract location context for the Philippines, and persist structured data into MongoDB.

## Core Components

- `pipeline.py`
  - FastAPI pipeline implementation with MongoDB persistence.
  - Loads a dynamic Philippine geographic registry for location extraction.
  - Collects posts and author details, then stores results into `posts` and `users` collections.
  - Includes fallback behavior when the remote geographic registry cannot be loaded.

## Features

- Multilingual disaster keyword search across English, Bisaya, and Tagalog.
- Location recognition using Philippine provinces and administrative markers.
- Author social graph discovery via Bluesky follow/follower relationships.
- Deduplication of posts and users during collection.
- MongoDB storage support via `pymongo`.
- Configurable API parameters:
  - `search_limit`
  - `days_back`
  - `graph_limit`

## Requirements

- Python 3.11+ (recommended)
- `fastapi`
- `uvicorn`
- `atproto`
- `pymongo`

## Installation

1. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
python -m pip install fastapi uvicorn atproto pymongo
```

3. Configure MongoDB:

- Ensure a MongoDB instance is available and accessible.
- Optionally set `MONGO_URI` before running the pipeline.

```powershell
$env:MONGO_URI = "mongodb://localhost:27017/"
```

4. Review and secure credentials:

- `BLUESKY_HANDLE` and `BLUESKY_PASSWORD` are defined in code.
- For production use, replace these with environment variables or a secure configuration mechanism.

## Running the Pipeline

### Start the API from `pipeline.py`

```powershell
uvicorn pipeline:app --reload --host 127.0.0.1 --port 8000
```

### Start the POC from `blueskyPOC.py`

```powershell
uvicorn blueskyPOC:app --reload --host 127.0.0.1 --port 8001
```

## API Endpoints

- `GET /disaster-alerts`
  - Parameters:
    - `search_limit` (default: 5)
    - `days_back` (default: 5)
    - `graph_limit` (default: 10 in `pipeline.py`)
  - Example:

```powershell
curl "http://127.0.0.1:8000/disaster-alerts?search_limit=5&days_back=7&graph_limit=10"
```

## Suggested Improvements

- Move Bluesky credentials out of source code.
- Add robust logging and alerting.
- Add unit and integration tests.
- Expand location parsing to capture finer-grained place names.
- Add a scheduling or event-driven ingestion mechanism.

## Notes

- This repository is intended as a research and prototype artifact for a thesis project.
- The code is actively focused on early-stage data ingestion and social graph verification rather than production-readiness.

---

AgapAI is designed to help validate the feasibility of using Bluesky as a disaster signal source while mapping verified actor relationships and Philippine location context.