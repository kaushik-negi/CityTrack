# CityTrack

**AI-powered, multi-camera ANPR and vehicle trajectory platform that connects a city's existing CCTV/ANPR network into one searchable, alerting system — instead of thousands of cameras that only record in isolation.**

## Table of Contents

- [Problem](#problem)
- [Objective](#objective)
- [Proposed Solution](#proposed-solution)
- [Key Features](#key-features)
- [Solution Architecture](#solution-architecture)
- [Documentation](#documentation)
- [Project Status](#project-status)

## Problem

Indian cities have deployed thousands of CCTV and ANPR cameras for traffic and security, but these cameras operate in isolated silos — each one only records and locally reads plates, with no connection to any other camera in the network. As a result, authorities have no way to search for a vehicle's movement across the city, no automatic way to detect a blacklisted vehicle unless someone is manually watching, and no aggregate view of city-wide traffic patterns — even though all of this data already exists, camera by camera, unused. Investigations that should take minutes take days, and stolen or wanted vehicles routinely pass multiple cameras without being flagged, simply because nothing is watching for them.

**Who this affects:** police doing investigations, victims waiting for their stolen vehicle to be found, commuters stuck in traffic that nobody is actively managing, and every city that has already spent money on cameras but isn't getting real value from them.

**Cost of doing nothing:** cities keep spending money on cameras that don't help catch anyone or fix anything — they just record. Stolen vehicles keep slipping past, investigations stay stuck taking days instead of minutes, and traffic keeps getting managed by guesswork instead of data.

## Objective

Turn cameras that only record into a system that actively watches — so cities can find any vehicle in minutes, catch flagged vehicles automatically, and manage traffic using real data, instead of letting all of it sit unused until after something has already gone wrong.

## Proposed Solution

CityTrack is a centralized, AI-powered software platform that connects a city's existing ANPR/CCTV camera network into one unified system — turning cameras that currently only record in isolation into a system that actively watches, searches, and alerts across the entire city.

**1. Reads every plate reliably, and knows when it isn't sure**
Each camera feed is processed through an AI pipeline: vehicle and plate detection, image preprocessing (lighting correction, deblurring, perspective correction) to handle real-world conditions, and OCR to extract the plate text with a confidence score. High-confidence, correctly formatted reads are logged automatically. Anything uncertain — blurry, angled, or malformed — is routed to a quick human review step instead of being guessed, so a single misread character can never wrongly implicate the wrong vehicle.

**2. Connects every camera into one searchable timeline**
Every accepted plate reading — vehicle, camera, location, and timestamp — is stored in one unified database instead of separate silos. An authority can search any plate number and instantly see its full route across the city, plotted chronologically on a live GIS map, replacing what today takes days of manual footage requests with a search that takes seconds.

**3. Watches automatically, instead of waiting to be asked**
Every new detection is checked in real time against a blacklist of stolen/wanted vehicles — triggering an instant alert the moment a flagged vehicle is seen anywhere in the city. The system also detects anomalies on its own: if the same plate appears at two locations in a time gap that's physically impossible to travel, it's flagged as a likely OCR error or, if the vehicle's type/color also differs, a likely case of plate cloning.

**4. Turns raw footage into city-wide traffic intelligence**
Beyond individual vehicles, aggregated detection data powers a live traffic analytics dashboard — density per camera, congestion hotspots, and movement patterns — giving traffic authorities and urban planners real data instead of guesswork for signal timing and infrastructure decisions.

**5. Keeps a human in control at every consequential step**
No alert results in automatic action. Every blacklist match or anomaly is shown to a human — an operator for routine confirmations, an officer only for genuine flagged matches — with the actual captured evidence, before anything happens. This keeps the system fast where it can be, and careful exactly where it needs to be.

**Why this is different from just "adding AI cameras":**
- No new hardware required — works with the camera infrastructure cities have already paid for.
- Doesn't just detect — it connects. The core innovation is cross-camera trajectory reconstruction and city-wide correlation, not the OCR model itself (plate recognition alone is a solved problem).
- Designed against its own failure modes — confidence-based routing and human confirmation directly prevent the single biggest realistic risk: a wrong OCR read causing a false accusation.

**Outcome:** existing camera infrastructure shifts from passive recording to active protection — vehicles get found in minutes instead of days, flagged vehicles are caught automatically, and traffic decisions are backed by real data, with a human always in control of anything consequential.

## Key Features

| # | Feature | Description |
|---|---|---|
| 1 | High-Accuracy ANPR/OCR Engine | Vehicle and plate detection with a preprocessing pipeline (lighting correction, deblurring, perspective correction, upscaling) built for real-world conditions, not just clean images |
| 2 | Confidence-Based Review Queue | High-confidence, correctly formatted reads auto-log; anything uncertain routes to a human review step instead of being guessed |
| 3 | Multi-Camera Trajectory Tracking | Every confirmed detection stored in one unified database; any plate searchable to reconstruct its full route on a live GIS map |
| 4 | Real-Time Blacklist Alerts | Every new detection checked against a watchlist the instant it's logged |
| 5 | Anomaly & Plate-Cloning Detection | Flags physically impossible travel between sightings; distinguishes likely OCR error from likely cloning via vehicle type/color mismatch |
| 6 | Human-in-the-Loop Verification | No alert ever triggers automatic action; routine uncertainty goes to an operator, genuine matches go to a police officer |
| 7 | City-Wide Traffic Analytics Dashboard | Density, congestion, and movement pattern data for traffic authorities and planners |
| 8 | Works with Existing Infrastructure | No new cameras or hardware required |

## Solution Architecture

**Major components:**
- **Camera / ANPR Network** — the existing city cameras, unchanged.
- **Ingestion Layer** — a message-queue-based service pulling feeds from every camera concurrently.
- **Detection + OCR Engine** — detects the vehicle and plate, preprocesses the image, runs OCR, produces a confidence score and format check.
- **Auto-accept vs. Human Review split** — high-confidence reads log immediately; uncertain reads wait for operator confirmation.
- **Unified Detection Database** — every confirmed reading lands in one place, regardless of which camera saw it.
- **Trajectory Engine** — reconstructs a plate's full route across cameras for the GIS map.
- **Analytics Engine** — aggregates detections into density, congestion, and traffic-pattern data.
- **Alert Engine** — checks every new detection against the blacklist and runs anomaly/cloning checks.
- **Web Dashboard** — where police and traffic authorities search trajectories, confirm/dismiss alerts, resolve review items, and view analytics.

Data flows one way up to the database, then fans out to three independent engines (trajectory, analytics, alerts) that all read from the same source of truth — so search results, alerts, and analytics are always consistent with each other.

```
Camera Network → Ingestion Layer → Detection + OCR Engine
                                          │
                          ┌───────────────┴───────────────┐
                    Auto-accept                    Human Review Queue
                          │                                │
                          └───────────────┬────────────────┘
                                Unified Detection Database
                                          │
                    ┌─────────────────────┼─────────────────────┐
            Trajectory Engine     Analytics Engine        Alert Engine
                    │                     │                     │
                    └─────────────────────┴─────────────────────┘
                                    Web Dashboard
```

## Documentation

| Document | Contents |
|---|---|
| [`docs/requirements.md`](docs/requirements.md) | Functional and non-functional requirements, user roles, scope, open questions |
| `docs/adr/` | Architecture Decision Records — the reasoning behind non-obvious design choices |
| `docs/updates/` | Dated project progress logs |

More documents (user stories, database design, Git workflow, testing plan) are being added incrementally — see Project Status below.

## Project Status

Currently in the **documentation and requirements phase**: locking down requirements, architecture, and design decisions before continuing implementation. A working prototype (OCR pipeline, trajectory API, blacklist/anomaly alerts, dashboard) already exists and runs locally; it will be hardened and extended once the documentation phase is complete.

**Planned next:**
- [ ] User stories / backlog
- [ ] Database design document
- [ ] Git workflow and branching strategy
- [ ] Kanban board setup
- [ ] Testing plan
