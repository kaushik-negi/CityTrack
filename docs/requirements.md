# CityTrack — Requirements

## What this is

CityTrack connects a city's existing CCTV/ANPR cameras into one system that can search any vehicle's route across the city, automatically catch blacklisted vehicles, and show real traffic data — instead of thousands of cameras that just record in isolation with no connection to each other.

## Who uses it

| Role | What they do with it |
|---|---|
| **Operator** (control room) | Confirms or corrects plate reads the AI wasn't fully sure about |
| **Manager** | Approves or disapproves flagged/uncertain detections and alerts; sees confidence scores and audit history |
| **Police officer** | Searches a vehicle's route; confirms or dismisses blacklist/anomaly alerts |
| **Traffic authority** | Views density and congestion data to inform signal/planning decisions |
| **Admin** | Manages the camera list, blacklist, and user roles/permissions |

## What it needs to do (functional requirements)

**Reading plates**
1. Detect and read the plate clearly from a camera image.
2. Score how confident it is in that reading.
3. Check the reading looks like a real plate format before trusting it.
4. If confident and correctly formatted → log it automatically.
5. If not → send it to an operator for a quick confirm instead of guessing.
6. Detect when a plate doesn't match expected format, is broken, blurred, or missing entirely — route these differently 
rather than forcing a guess (see "Planned, not built yet" below for the broken/missing handling).

**Fraud & identity checks**
7. Detect fake plates — text that doesn't correspond to any real/valid format.
8. Detect the same plate number appearing on two different vehicles (duplicate/cloned plate), using vehicle attributes 
to tell a real duplicate apart from a simple misread.
9. Check every new reading against a blacklist of stolen/wanted vehicles and alert the moment there's a match.
10. Notice if a plate is seen in two places too fast to be physically possible, and flag it as a likely misread or
likely cloning case.

**Tracking & search**
11. Store every confirmed reading (plate, camera, location, time) in one place.
12. Let anyone search a plate and see its full route across the city, in order, on a live map (GIS trajectory).
13. Let a user search by vehicle name/model, not just plate number.
14. Keep a running log of sightings per vehicle as it's seen over time, so a vehicle's history builds up rather than 
existing only as isolated points.
15. Support a vehicle report split into car and bike sections, searchable by model name.
16. Generate a full exportable report for a single vehicle — every sighting, every camera, every alert tied to 
it — for handoff to an investigation.

**Approval workflow**
17. Let an authorized manager approve or disapprove a flagged/uncertain detection.
18. Show the confidence score alongside every item awaiting approval, so the decision isn't a blind guess either.
19. Keep an audit trail of every approval/disapproval — who decided, what they decided, and when.
20. Never take action automatically — every alert or uncertain read needs a person to confirm or dismiss it first.

**Traffic insight**
21. Show how many vehicles each camera has seen, as a basis for a congestion/density dashboard.

**System management**
22. Let an admin add or update blacklist entries.
23. Let an admin manage the camera list and user roles/permissions.
24. Detect when a camera itself has gone offline or stopped reporting, and flag it — a silent camera should be 
visible as a system issue, not mistaken for "no traffic."

**Planned, not built yet**
25. Store half-readable plates as a searchable partial match instead of discarding them.
26. Log vehicles with no readable plate using their appearance (type/color) instead, with an explicit limit: 
this narrows candidates, it does not uniquely identify a vehicle when two vehicles are genuinely visually identical.
27. Group multiple pending reviews that are probably the same vehicle into one review instead of many. Resolving a 
cluster supports three outcomes, not just approve/reject:
    - **Approve all** — confirms every sighting in the cluster at once
    - **Reject all** — none get confirmed; sightings return to individual review
    - **Approve with exclusion** — confirm the cluster minus one or more sightings that don't actually belong, which go 
    back for separate review instead of being wrongly confirmed or wrongly discarded along with the rest
28. Cross-camera identity resolution using route plausibility (time, direction, distance) in addition to appearance, 
so identity can be inferred across many cameras from a single clear "anchor" sighting rather than needing every camera 
to independently resolve ambiguity.

## What it needs to be like (non-functional requirements)

- **Accurate** — should read plates correctly most of the time under normal conditions; when unsure, it should 
say so rather than guess.
- **Safe** — nothing happens automatically to a real vehicle/person without a human confirming it first.
- **Easy to use** — confirming or dismissing something should take one or two clicks, not a form.
- **Fast enough** — searching a plate's route should feel instant, not like a report generating.
- **Honest about scale** — built to work with a small dataset now, but designed so it can grow to real city-scale 
storage later without a rewrite.
- **Traceable** — every alert that gets confirmed or dismissed should record who did it and when.
- **Self-contained** — runs locally for development, no paid services required to build or demo it.

## What's in scope right now

- OCR pipeline, review queue, trajectory search, blacklist alerts, anomaly/duplicate-plate detection, traffic density 
view, manager approval workflow with confidence display and audit trail, camera health/offline detection, and the web dashboard for all of the above.

## What's out of scope right now

- Real camera hardware integration
- Real user accounts/login system
- Connecting to government databases (Vahan, e-Challan, etc.)
- Handling real city-scale traffic volume
- A mobile app

## Assumptions

- Plate images come in as uploaded files for now, not a live camera stream.
- Tesseract OCR is available wherever this runs.
- SQLite is fine for now; a bigger database is a later problem, not a now problem.

## Known open questions

- How do we handle a plate that's been deliberately sprayed/covered to defeat the camera? 
(Partial answer: flag the pattern as suspicious, fall back to vehicle appearance — see project notes.)
- What are the actual legal rules for how long this data can be kept? Not yet researched.
- No real government data access exists yet — this is a self-contained prototype until that changes.