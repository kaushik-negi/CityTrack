## Benefits

**For police / investigators**
- A vehicle's full route across every camera that saw it, searchable in seconds instead of requiring manual footage 
requests from each camera over days.
- Automatic alerts the moment a blacklisted vehicle is seen anywhere in the network, instead of relying on an officer
happening to notice.
- A single exportable report per vehicle (all sightings, all alerts) usable as case evidence.

**For theft victims**
- A materially better chance of recovery, since the system is actively watching rather than waiting for a human to notice 
by chance.

**For traffic authorities / urban planners**
- Real density and congestion data instead of guesswork for signal timing and infrastructure decisions.
- Camera health monitoring means a "quiet" reading is never silently mistaken for "no traffic" when it's actually a dead
camera.

**For the city/government**
- No new hardware spend — the value comes from software on top of cameras that are already installed and already paid for.
- A data-backed case for which specific junctions need camera hardware upgrades (see Limitations — accuracy is 
camera-quality dependent, and that's itself a useful signal).

**For the public**
- Safer roads (flagged vehicles caught faster), and less time lost to unmanaged congestion.

## Feasibility

### Technical feasibility — mostly yes, with real caveats
- Vehicle detection, plate localization, and OCR are all solved problems with mature, pretrained, open-source models 
available (see `docs/adr/` and project chat log for specific repos evaluated). This is not unproven research — 
it's assembly and fine-tuning of existing components.
- The harder, more original part — confidence-based routing, human-in-the-loop review, cross-camera trajectory
reconstruction, blacklist/anomaly logic — is standard software engineering, not a research risk.
- **Real caveat:** most available pretrained models are trained on non-Indian plates/vehicles and will 
need fine-tuning on Indian data before they're reliably usable — this is a real, budgeted task, not a free plug-in.

### Operational feasibility — depends on institutional access, not on the software
- The system's core value (blacklist alerts, real camera feeds, real vehicle registration lookups) depends entirely on 
getting official access to government/police data. This cannot be secured independently by a student/prototype team 
— it requires a genuine government partnership.
- Without that access, the system is fully demonstrable and logically complete, but running on synthetic/self-collected 
data rather than real city data.

### Economic feasibility — favorable, if institutional access is secured
- No new camera hardware is required — this is a software layer on existing infrastructure, which is a materially 
cheaper proposition for a city than most "smart city" pitches that assume new sensors.
- Ongoing cost is primarily compute (running detection/OCR at scale) and storage (mitigated by the tiered hot/warm/cold
storage design already documented).

### Legal / compliance feasibility — unresolved, flagged honestly
- Data retention rules, surveillance consent/notice requirements, and how long trajectory data can legally be kept are 
jurisdiction-specific and have not been researched for this project. This is a real open item, not a solved one.

## Usability

- **Operators and officers** interact only through simple confirm/dismiss/approve actions with visible evidence 
(image, confidence score) — no technical AI knowledge required to use the system day to day.
- **Traffic authorities** get a dashboard view, not raw data — no querying skill needed.
- **Risk to usability:** if the review queue or alert volume grows faster than expected (e.g. many ambiguous 
ANPR-evasion or old-camera cases), the system could become noisy rather than helpful — this is why review 
clustering (see `requirements.md`, FR-16/27) exists specifically to keep this manageable, and should be monitored,
not assumed solved.

## Pros

- No new hardware required — works with what cities already have.
- Designed against its own biggest failure mode from the start (false accusation from a misread plate),
not as an afterthought.
- Clear separation of "routine data-quality work" (operator) from "real law-enforcement action"
(officer) keeps human workload proportional and realistic.
- Every consequential action requires human confirmation — defensible against the standard "unaccountable AI surveillance"
criticism.
- Modular design (perception layer vs. intelligence layer) means individual pieces (OCR model, classifier) can be upgraded
or swapped without rebuilding the system.
- Gives cities a genuine, data-backed argument for where to invest in camera upgrades, rather than treating hardware 
quality as a hidden assumption.

## Cons 

- **Cannot resolve two genuinely visually identical vehicles with both plates unreadable.** This is a hard limit of 
vision-only systems, not a solved problem — the system is designed to flag this as unresolved rather 
than guess, but it cannot always produce an answer.
- **Anti-ANPR sprays/reflective covers are a real, currently unmitigated evasion technique.** The system can detect 
the *pattern* of evasion (consistently unreadable across multiple cameras) but cannot decode a deliberately defeated plate.
- **Accuracy is directly dependent on camera hardware quality.** Old, low-resolution, or black-and-white 
cameras will produce materially more ambiguous cases than modern ones — this has not been benchmarked yet and should not
be assumed uniform across a real camera network.
- **No real government/police data access currently exists.** All current demos and testing run on synthetic or 
self-collected data, not live city data.
- **RFID/FASTag correlation, where it could help disambiguate identical vehicles, is only available at highway toll 
points, not typical city junctions** — so it cannot be relied on as a general solution inside a city.
- **Cross-camera identity resolution (route-plausibility-based tracking) is a genuinely advanced capability** not 
yet implemented in the current prototype — see `requirements.md` planned items.
- **Plate OCR and vehicle-model classification models will need fine-tuning on Indian data** before they can be 
trusted at the accuracy levels claimed for international benchmarks.

## Bottom line

The system is technically buildable today using existing open-source components plus original 
systems-engineering work, and the design has been deliberately stress-tested against its own realistic failure 
modes rather than assuming a clean, ideal-world data feed. The primary blocker to a *real deployment* is not the 
technology — it's securing institutional access to government/police data, camera infrastructure, and legal clarity
on data retention, none of which a student/prototype project can resolve independently.