"""Author a frozen synthetic fixture without importing or invoking retrieval code."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sources = []
cases = []


def source(sid, text, *, collection="public", freshness="current", authority="primary",
           state="active", allowed_destinations=None):
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
    item = {
        "source_id": sid, "text": normalized, "collection": collection,
        "freshness": freshness, "authority": authority,
        "origin": "synthetic://fragmented-evidence-v2/" + sid, "state": state,
        "allowed_destinations": allowed_destinations or (["local"] if collection == "private" else ["local", "public"]),
        "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    }
    sources.append(item)
    return normalized


def gold(sid, exact):
    text = next(s["text"] for s in sources if s["source_id"] == sid)
    assert text.count(exact) == 1, (sid, exact)
    offset = text.index(exact)
    assert offset == 0 or text[offset - 1] == "\n"
    assert offset + len(exact) == len(text) or text[offset + len(exact)] == "\n"
    return {"source_id": sid, "line_start": text[:offset].count("\n") + 1,
            "line_end": text[:offset].count("\n") + exact.count("\n") + 1, "quote": exact}


def case(cid, query, refs, forbidden, requirements, *, tight=False, scope="reader",
         destination="public", contextual=()):
    budget = 4600 if tight else 10000
    cases.append({
        "id": cid, "query": query, "scope": scope, "purpose": "answer_question",
        "destination": destination,
        "budget": {"max_bytes": budget, "max_tokens": budget, "max_items": 6 if tight else 10},
        "budget_class": "tight" if tight else "normal",
        "gold": [gold(sid, quote) for sid, quote in refs],
        "forbidden_sources": forbidden, "answer_requirements": requirements,
        "missing_evidence": [],
        "relevance": {"gold_sources": sorted(set(sid for sid, _ in refs)),
                      "contextual_sources": list(contextual),
                      "nongold_lines_are_not_automatically_irrelevant": True},
    })


# 1. Outdoor access: route instructions, an adjoining restriction, and a distance note.
trail_route = "During the Alder Footbridge closure, walkers reach the Cedar Overlook by following the signed Mill Road bypass from marker M2 to marker M5. The bypass adds 0.8 km to the outward walk."
trail_caveat = "The bypass is open only while the creek gauge is below 1.4 m.\n\nAt 1.4 m or above, the Mill Road ford is closed too: turn back at M2; do not substitute the ford for the footbridge."
trail_return = "Return from the overlook using the same Mill Road bypass; the old east-bank spur is fenced for nesting birds and is not an alternative return route."
source("trail-current", f"""# Fern Creek Reserve — Alder closure bulletin
Revision 7, effective 4–18 May 2031. This is an invented reserve and an invented notice.

## A route, not a loop
{trail_route}

The reserve's name comes from the fern nursery that operated beside the creek before the land became a walking reserve. Foundation stones remain visible from the picnic lawn. Please leave stones in place; moving them makes mowing difficult and can damage the interpreted building outline.

## Reading the signs
Temporary bypass signs have an amber arrow and the word OVERLOOK. Permanent white posts still mark the original path, including its closed sections. A volunteer may be stationed at the entrance on weekends, but the absence of a volunteer does not cancel a closure notice.

The visitor shelter contains a drinking-water tap, a noticeboard, and a small map rack. The map rack sometimes holds older brochures for their bird illustrations; those brochures are not closure updates. Mobile reception is patchy beneath the escarpment, so record the gauge reading before leaving the entrance.

## Water condition attached to the bypass
{trail_caveat}

The number painted on each stone step belongs to the maintenance inventory. It is unrelated to distance or water depth. Staff use those numbers when reporting a damaged tread, loose handrail, or blocked drain. Visitors can report a problem at the shelter without attempting repairs themselves.

## Completing the walk
{trail_return}

Dogs are allowed on the entrance lawn on leads but are not allowed beyond M2. This restriction protects the nesting area and applies throughout the reserve's current management season. Bicycles stay at the entrance racks; a signed walking bypass is not a cycle route.
""")
trail_distance = "The ordinary entrance-to-Cedar-Overlook walk is 2.6 km one way. The 12 May 2031, 09:00 entrance-board reading is 1.1 m; the ranger signed this as the reading for today's guided walk."
source("trail-walk-card", f"# Guided walk card — 12 May 2031\n\n{trail_distance}\n\nThe group meets at the entrance shelter at 09:15. Distances describe the walking route, not straight-line separation. The guided group uses the same published closure rules as other visitors.")
source("trail-old-map", "# Fern Creek map — 2029 edition\n\nThe Alder Footbridge is open. The east-bank spur makes a convenient loop from Cedar Overlook. The ordinary return walk is 5.2 km.\n\nThis map predates the temporary closure and nesting fence.", freshness="stale", authority="secondary")
source("trail-history", "# Fern Creek interpretation panel\n\nThe old nursery supplied ferns to town conservatories. Mill Road once carried peat carts; its name survives on the signed walking bypass. This panel explains the landscape but does not establish whether a route is open.", authority="secondary")
case("fragmented-01", "For the 12 May guided walk, can we get to Cedar Overlook despite the broken footbridge, what route should we take back, and how far is the full walk? Include the water-level condition that could stop us.",
     [("trail-current", trail_route), ("trail-current", trail_caveat), ("trail-current", trail_return), ("trail-walk-card", trail_distance)],
     ["trail-old-map"], ["Today's 1.1 m reading is below the 1.4 m closure threshold.", "Use Mill Road M2–M5 in both directions; the east-bank spur is unavailable.", "Compute 2 × (2.6 + 0.8) = 6.8 km for the round trip.", "At a gauge reading of 1.4 m or above turn back at M2; the ford is also closed."],
     contextual=["trail-history"])


# 2. Amateur astronomy: camera initialization with a condition joined to the rule.
camera_init = "For an L7 camera running firmware 3.2, start a new dark library after changing the sensor target temperature. Set the target to −10 °C and allow 12 minutes after the displayed temperature first reaches that value."
camera_dark = "Acquire twelve dark frames at the science exposure duration, with the lens cap fitted.\n\nA shutter-close command alone is insufficient on the L7: its inspection slit leaks light, so the cap is required even when software reports SHUTTER=CLOSED."
camera_name = "Store the combined master under dark/L7_f32_m10_<seconds>s.fit, replacing <seconds> with the exposure duration as an integer. Do not reuse a master made at −5 °C."
source("observatory-camera", f"""# North Quay Community Observatory: L7 imaging note
Instrument note 3.2-A, approved for the public training night of 7 February 2032.

## Initial temperature state
{camera_init}

The observing desk has a red task lamp and a laminated inventory card. Return the inventory card to its clip so that the next group can see which filters are installed. The large dome handle is unrelated to the camera shutter and should only be moved by the duty guide.

The demonstration target is a bright emission nebula. Its catalogue name appears on the finder chart, but participants do not need to enter that name into calibration software. Calibration records use the instrument, firmware, temperature and duration rather than a target name.

## Removing thermal signal
{camera_dark}

The screen preview stretches faint signal automatically. A dark preview can therefore look surprisingly bright even when its raw values are small. Judge a calibration exposure using the numerical readout and the guide's checklist, not by comparing stretched thumbnails on two different monitors.

## File naming and reuse
{camera_name}

```text
instrument = L7
firmware = 3.2
calibration_type = dark
```

The directory also contains flat-field examples from previous lessons. Flat frames correct uneven illumination; their labels should not be copied into the thermal calibration record. The examples remain available to explain the difference between calibration types, not to prescribe this evening's exposure time.

USB cables are numbered with fabric tags so that guides can report intermittent connectors. Cable numbers are not device serial numbers, and replacing a cable does not by itself require a new dark library. Temperature changes and firmware changes are recorded in the observing log.
""")
camera_seconds = "Tonight's science frames use 90 s exposures. Keep this duration for the dark series; do not apply the older 60 s classroom example."
source("observatory-session", f"# Public session card — 7 February 2032\n\n{camera_seconds}\n\nThe camera is an L7 with firmware 3.2. A guide has just changed its target from −5 °C to −10 °C. The red-light room opens at 19:00.")
source("observatory-revoked", "# L7 shutter shortcut — withdrawn handout\n\nUse six 60 s darks with SHUTTER=CLOSED; the lens cap can be left off. Save dark/L7_quick.fit.\n\nWithdrawal notice: this handout was revoked after the inspection slit was documented.", state="revoked", freshness="stale")
case("fragmented-02", "The guide has changed the L7 temperature for tonight's nebula session. Give the waiting period, dark-frame count and duration, the physical light-blocking step, and the exact master filename.",
     [("observatory-camera", camera_init), ("observatory-camera", camera_dark), ("observatory-camera", camera_name), ("observatory-session", camera_seconds)],
     ["observatory-revoked"], ["Wait 12 minutes after the displayed sensor reaches −10 °C.", "Take twelve 90 s dark frames.", "Fit the lens cap even if the shutter reports closed because the inspection slit leaks light.", "Save dark/L7_f32_m10_90s.fit and do not reuse a −5 °C master."], tight=True)


# 3. Data ingestion: exact code/JSON facts separated by prose.
import_time = "Interpret an offset-free observed_at value in the site's configured timezone, then convert it to UTC. Never treat an offset-free value as already UTC. An explicit numeric offset in the value overrides the site timezone."
import_missing = "Convert the literal reading value -9999 to JSON null and set quality to \"missing\".\n\nThe value 0 is a valid measurement and must remain numeric zero; an empty reading cell is a row-validation error, not the -9999 missing-data code."
import_shape = '''The exported object uses these exact keys:
```json
{"observed_at_utc":"ISO-8601 Z time","reading":0,"quality":"measured","station":"site code"}
```
For a nonmissing numeric reading, quality is "measured".'''
source("importer-contract", f"""# DrizzleCSV adapter contract, version 4
This synthetic contract describes a small weather-station exchange format. Version 4 is current for the demonstration dataset.

## Time semantics
{import_time}

Each CSV file belongs to one station, even when an operator has copied the file into a folder named for a regional campaign. Use the station value from the job configuration. Folder names help a person organize uploads but do not become exported station identifiers.

The parser accepts a header row in any column order. Column order is useful for spreadsheet readability and does not change field meaning. Files downloaded from the example station include a comments column for maintenance notes, which the export omits. Comments can contain commas when quoted normally.

## Reading semantics
{import_missing}

The unit selected by a station is documented in its registration record. This adapter does not silently rescale units, round the numeric reading, or append a unit suffix to the JSON number. Downstream chart labels may display units separately. A failed row is reported with its physical CSV line number.

## Output shape
{import_shape}

There is no additional confidence field and no wrapper named data. A consuming application may place several exported objects inside its own array, but that application's container is not part of the single-row conversion contract. Preserve the distinction when creating test fixtures or explaining one row to an operator.

## Reproducibility
Record the adapter version in the batch manifest, not inside each exported measurement. A manifest can also include the filename and a checksum. Those fields establish batch provenance and should not be copied into an individual measurement object merely because they appear beside it in a log.
""")
import_job = '''Job configuration:
```json
{"station":"RQ2","timezone":"UTC+02:00","adapter_version":4}
```
Input rows:
```csv
observed_at,reading
2031-06-08T10:15:00,-9999
2031-06-08T10:20:00,0
```'''
source("importer-job", f"# DrizzleCSV demonstration job 18\n\n{import_job}\n\nUTC+02:00 is a fixed offset in this synthetic job; no seasonal-clock rule is needed. The two displayed rows are complete.")
source("importer-v3", "# DrizzleCSV version 3 migration scratchpad\n\nTreat a time without an offset as UTC. Collapse both 0 and -9999 to null. The old export used timestamp instead of observed_at_utc.\n\nThis scratchpad describes the retired version 3 behavior.", freshness="stale", authority="secondary")
source("importer-rationale", "# Why stations preserve zero\n\nA measured zero can distinguish a dry interval from a sensor that did not report. The DrizzleCSV project therefore discusses missingness separately from magnitude. This explanatory note does not specify parser version, output keys, or timezone precedence.", authority="secondary")
case("fragmented-03", "Show the two JSON measurement objects that job 18 should emit under the current DrizzleCSV contract. Explain briefly why the second reading is not missing, and use the correct UTC times and field names.",
     [("importer-contract", import_time), ("importer-contract", import_missing), ("importer-contract", import_shape), ("importer-job", import_job)],
     ["importer-v3"], ["First object: observed_at_utc 2031-06-08T08:15:00Z, reading null, quality missing, station RQ2.", "Second object: observed_at_utc 2031-06-08T08:20:00Z, reading 0, quality measured, station RQ2.", "Use precisely observed_at_utc, reading, quality, and station as the measurement keys.", "Explain that -9999 is the missing code while zero is a valid measurement."],
     contextual=["importer-rationale"])


# 4. Seed library: counting window and treatment exception.
seed_method = "For a Blue Lantern pea viability check, select 20 seeds at random and place them on damp paper in a lidded box at 18–22 °C. Keep the paper damp but do not leave standing water in the box."
seed_count = "Count a seed as germinated only when its root is at least 5 mm long. Record the final count on day 10, not the first day on which any root appears."
seed_caveat = "Do not nick or soak seeds used for the library's viability check.\n\nNicking and soaking may be appropriate for a separate planting trial, but pretreated seeds cannot be substituted into the untreated viability sample or its recorded percentage."
source("seed-protocol", f"""# Marrow Street Seed Library — pea check protocol
Public protocol P-6, spring 2031. Blue Lantern is a fictional pea variety used in this example.

## Set up the sample
{seed_method}

Use a pencil to label the box with the variety, lot code, and start date. Ink on a loose paper label can run in the damp chamber. The label helps volunteers keep similar-looking peas apart; the box's shelf position is not an identifier and may change when the room is cleaned.

The community library also lends planting trays. A tray loan is recorded at the reception desk, separately from the seed lot register. Returning a tray does not close a seed-check record. Volunteers may leave an unfinished record in the green folder for the next shift to complete.

## Score at a consistent time
{seed_count}

A swelling seed is not yet a scored germination. The photo guide shows several stages because visitors often want to understand the process. Only the stage stated in this protocol counts toward the recorded viability result; photographs are illustrative and do not change the timing requirement.

## Keep treatment separate
{seed_caveat}

After scoring, place the tested seeds in the compost container. Do not return them to a lending envelope even if a seed has no visible root. The remaining untested lot should stay dry in its labelled jar until the librarian has entered the result and decided whether the lot may be offered.

The library noticeboard contains growing tips contributed by visitors. Those tips may cover sowing depth, garden spacing, trellises, pests, and harvesting. Such advice can be useful for a planting project but does not replace this sample size, scoring rule, or treatment restriction for a lot check.
""")
seed_lot = "Lot BL-31 may be offered for lending only if at least 80% of its viability sample germinates. The recorded untreated sample has 15 roots at least 5 mm long on day 10; one additional seed has a 3 mm root."
source("seed-lot-card", f"# Blue Lantern lot BL-31\n\n{seed_lot}\n\nThe lot was tested with the 20-seed P-6 method. No seeds in this sample were nicked or soaked.")
source("seed-tips", "# Visitor's planting tips\n\nSoak Blue Lantern peas overnight, nick a few hard coats, and count every seed that swells. Fifteen of twenty sounds good enough to lend.\n\nThis is a visitor contribution about garden planting, not an authorized viability protocol.", authority="unreviewed", state="reference_only")
case("fragmented-04", "Does lot BL-31 qualify for lending? Show how its result is counted, state the test conditions and deadline, and explain whether soaking or counting the short root would change the official result.",
     [("seed-protocol", seed_method), ("seed-protocol", seed_count), ("seed-protocol", seed_caveat), ("seed-lot-card", seed_lot)],
     ["seed-tips"], ["Use an untreated random sample of 20 seeds on damp paper at 18–22 °C without standing water.", "Score roots at least 5 mm long on day 10.", "15/20 = 75%, below the 80% requirement, so BL-31 does not qualify.", "Exclude the 3 mm root; soaking or nicking invalidates use as the untreated viability sample."], tight=True)


# 5. Performing arts: accommodation route plus schedule-specific change.
theatre_entry = "For step-free entry to the afternoon performance, use the courtyard door on Birch Lane. The main High Street doors lead to six steps before the foyer; the courtyard route reaches the foyer by a level passage."
theatre_audio = "Borrow a neck-loop receiver from the access desk for seats in rows A–F.\n\nThe neck loop works with a hearing aid set to its T-coil program; an ordinary Bluetooth pairing mode will not connect to this system. Headphones are available for visitors without a T-coil aid."
theatre_return = "Return borrowed receivers to the access desk before leaving the building. A receiver cannot be left in a seat pocket, because the access team checks and recharges each unit immediately after the audience leaves."
source("theatre-access", f"""# Willow Room Theatre — audience access guide
Public access edition, November 2031. This fictional theatre has one auditorium and one courtyard entrance.

## Getting into the foyer
{theatre_entry}

The courtyard mural depicts scenes from the building's former life as a furniture workshop. It is visible from the public lane during daylight hours. The mural is a wayfinding landmark, not a separate entrance, and visitors should continue past it to the door marked Audience Access.

Tickets can be displayed on a phone or printed on paper. The front-of-house team can also find a booking by its booking name at the desk. The performance programme is sold separately; a programme purchase is not required to use any of the published audience accommodations.

## Assisted listening
{theatre_audio}

The auditorium's visual display shows the act number during intervals. It is not a captioning display. Captioned performance dates are listed on their own schedule, and a standard matinee should not be described as captioned merely because the foyer has a screen or the show uses projected scenery.

## End of visit
{theatre_return}

The access desk normally opens 30 minutes before a performance. A dated performance notice can publish an earlier opening. The general access guide deliberately avoids repeating every special-event time so that the dated notice can remain the authoritative schedule for an individual show.

Coats may be hung on the public rack near the foyer bench. The theatre does not allocate numbered coat-check tags for matinees. Keep medicines, keys, and valuables with you; the rack is convenient but is not staffed storage. Folding walkers can remain in the designated space beside an aisle seat.
""")
theatre_notice = "For the 16 November 2031 matinee, curtain is at 14:00 and the courtyard door and access desk open at 13:15. The usual 13:30 opening is replaced for this performance because the access team is offering receiver familiarization."
source("theatre-matinee", f"# Dated audience notice: 16 November matinee\n\n{theatre_notice}\n\nThe performance uses the standard neck-loop system for rows A–F. The programme running time is 95 minutes including a short interval.")
source("theatre-private-rota", "# Synthetic staff rehearsal rota\n\nInternal draft: courtyard key handoff at 13:40; leave demonstration receivers in row G.\n\nThis invented draft is private staff planning material and is not an audience notice.", collection="private", authority="draft")
case("fragmented-05", "For the 16 November matinee, explain how a visitor in row D with a T-coil hearing aid and a wheeled walker should enter, when they can collect a receiver, how to connect it, and where to leave it afterward.",
     [("theatre-access", theatre_entry), ("theatre-access", theatre_audio), ("theatre-access", theatre_return), ("theatre-matinee", theatre_notice)],
     ["theatre-private-rota"], ["Use the step-free courtyard door on Birch Lane, not the stepped High Street route.", "The door and desk open at 13:15 for the 14:00 matinee.", "Row D is covered by rows A–F; borrow a neck loop and select the hearing aid's T-coil program, not Bluetooth.", "Return the receiver to the access desk before leaving."], tight=True)


# 6. Ceramics: owner-only synthetic plan; an adjoining applicability exception.
kiln_profile = "For load C17, select the studio's SLOW-6 profile and program a 20-minute hold at the top temperature. The profile's controlled cooling segment ends at 900 °C."
kiln_caveat = "Keep the kiln closed until its display is below 80 °C before unloading C17.\n\nThe earlier 120 °C unloading shortcut applies only to unglazed test tiles; C17 contains glazed bowls and does not qualify for that shortcut."
kiln_label = "Mark each C17 box with the firing date and the literal batch label C17-S6-H20. The label records the profile and top hold, not an artist's name or a glaze recipe."
source("kiln-load-plan", f"""# Studio firing plan — C17
Synthetic private owner notebook. All names, codes, and work described here are invented for this benchmark.

## Selected profile
{kiln_profile}

The shelves have been brushed and checked for drips. Shelf numbers are maintenance labels; they do not indicate which profile a load should use. The kiln room's wall chart illustrates several firing curves for classes, including profiles that are not appropriate for this particular load.

The bowls were placed with space around the rims so that no glazed surface touches another piece. The packing sketch is kept in the paper load folder. It helps compare results after firing, but the sketch does not override a written instruction about temperature, holding time, or unloading.

## Unloading condition
{kiln_caveat}

Use the padded cart when moving cool ware from the kiln room to the inspection bench. The cart's shelf liners were replaced this month. They prevent rims from rubbing during the short trip and are not thermal protection; the cart is not permission to unload a hot load.

## Identification after firing
{kiln_label}

Glaze names are recorded on individual test tabs in the load folder. A public workshop sign may add a special rule for a particular glaze batch. Read a glaze exception together with the current load plan before deciding which pieces may be included in a firing; a shared clay body alone does not settle compatibility.

The owner uses a weekly notebook page to track studio chores such as cleaning the sink trap, changing cloths, and recycling dry trimmings. Those tasks share a page with firing observations for convenience. They are unrelated to the C17 firing cycle and must not be mistaken for additional programmed segments.
""", collection="private")
kiln_exception = "Guest-workshop pieces marked GL-9 must stay out of C17: that glaze batch requires a separate cone-5 firing with no top hold. All other pieces already approved on the C17 load sheet keep the SLOW-6 plan."
source("kiln-workshop-sign", f"# Workshop glaze notice — current\n\n{kiln_exception}\n\nGL-9 is an invented studio glaze code. This sign is public so participants can identify the affected workshop work.")
source("kiln-old-plan", "# C17 preliminary firing draft\n\nUse FAST-6 with no top hold. Include GL-9 pieces and unload all work at 120 °C.\n\nDraft replaced by the signed current load plan and current workshop notice.", collection="private", freshness="stale", authority="draft", state="superseded")
case("fragmented-06", "For my local studio checklist, combine the current C17 plan with the guest-workshop exception: state the profile and top hold, cooling endpoint, unloading threshold, box label, and whether GL-9 pieces go in this load.",
     [("kiln-load-plan", kiln_profile), ("kiln-load-plan", kiln_caveat), ("kiln-load-plan", kiln_label), ("kiln-workshop-sign", kiln_exception)],
     ["kiln-old-plan"], ["Select SLOW-6 and a 20-minute top hold; controlled cooling ends at 900 °C.", "Unload only below 80 °C; the 120 °C shortcut is for unglazed test tiles and does not cover these glazed bowls.", "Label boxes with the firing date and C17-S6-H20.", "Exclude GL-9; it needs a separate cone-5 firing with no top hold."],
     scope="owner", destination="local")


# 7. Community food service: positive option accompanied by a cross-contact limitation.
kitchen_option = "At the 9 June community breakfast, the sealed oat cups labelled O-4 are the listed option made without peanut ingredients. Hand the cup to the visitor unopened, together with a fresh wrapped spoon."
kitchen_caveat = "Do not describe any item prepared on the shared toast counter as peanut-free.\n\nThe toaster, tongs, and spreading board are shared with peanut-butter toast; removing a topping or wiping a visible crumb does not turn that service into the sealed-cup option."
kitchen_limits = "Staff should repeat the event's ingredient and handling information without guaranteeing that a meal is safe for a particular person's allergy. The visitor can read the sealed cup's manufacturer label before deciding whether to accept it."
source("kitchen-service", f"""# Juniper Hall breakfast — public service information
Current event sheet for 9 June 2031. This fictional event and product code are used only as synthetic evaluation content.

## Listed alternative
{kitchen_option}

Breakfast tickets help the volunteers count how many portions to prepare. A ticket is valid for either the standard plate or the listed alternative, subject to availability. Visitors do not need to explain a medical history to exchange a ticket for a sealed cup or ask to see an ingredient label.

The hall's coffee station uses mugs from the washable cup rack. Bring used mugs to the marked return table rather than to the service counter. The return table is near the exit, and its volunteer clears crockery throughout the event. This arrangement keeps the serving queue moving.

## Shared equipment limitation
{kitchen_caveat}

Volunteer aprons are colour coded by task: green for ticket collection and blue for serving. Apron colour does not certify a food as free of an ingredient. Ask the serving lead for the current product label when a visitor needs information that is not printed on the event sheet.

## Communicating accurately
{kitchen_limits}

The fruit display is decorative as well as functional, and its position may change when the room becomes busy. Location on a separate table should not be presented as evidence of ingredient controls. Only the products and handling steps explicitly listed in this sheet establish the event's stated alternative service.

After breakfast, volunteers stack chairs along the west wall before cleaning the floor. The folding-table trolley stays clear of the fire exit during this work. These room arrangements are part of the volunteer timetable and do not extend the food-service window or establish later availability of a menu item.
""")
kitchen_count = "The O-4 sealed-cup stock for 9 June is 18 cups, reserved at the serving desk rather than on the toast counter. Service runs from 08:30 to 10:00, or until the relevant item runs out."
source("kitchen-stock", f"# Public menu availability — 9 June\n\n{kitchen_count}\n\nThe stock notice describes initial quantities, not a live count. The serving lead can confirm remaining cups during the event.")
source("kitchen-withdrawn", "# Withdrawn volunteer shortcut card\n\nA wiped toaster is peanut-free. Offer ordinary toast with no topping as the guaranteed allergy-safe substitute. There are unlimited oat cups on the toast counter.\n\nThis card was withdrawn before the event and must not guide service.", state="revoked", authority="draft")
case("fragmented-07", "Write a short public response for a breakfast visitor asking for a no-peanut-ingredients option: say what the event offers, where and when to request it, how it is handed over, and what limitation prevents promising that ordinary toast or the alternative is safe for their allergy.",
     [("kitchen-service", kitchen_option), ("kitchen-service", kitchen_caveat), ("kitchen-service", kitchen_limits), ("kitchen-stock", kitchen_count)],
     ["kitchen-withdrawn"], ["Offer an unopened O-4 sealed oat cup with a fresh wrapped spoon, and let the visitor inspect its manufacturer label.", "Request at the serving desk during 08:30–10:00, subject to stock; 18 is initial stock, not guaranteed remaining stock.", "Shared toaster, tongs, and board contact peanut-butter toast; removing toppings or wiping crumbs is insufficient.", "Do not guarantee suitability or allergy safety for either the shared-counter food or the alternative."], tight=True)


# 8. Archive publication: owner can read private material, but public destination is constrained.
archive_file = "Publish a JPEG derivative whose longest edge is 1600 px and whose embedded metadata contains the public credit line only. Keep the 600 dpi TIFF master in the preservation store; the master is not the web download."
archive_credit = "For accession R-42, use the exact public credit: \"Rivermark Archive, R-42; courtesy of the Bellweather Collection.\" Do not substitute the donor's administrative contact record for a public credit."
archive_release = "The image can be included in the public river-history page only after the Rights Register marks R-42 as cleared for web publication.\n\nA scanning-complete flag confirms capture, not permission; it does not satisfy the rights-clearance requirement."
source("archive-publication", f"""# Rivermark Archive — public image publication specification
Specification W-8, current in July 2031. The archive, accession, and collection in this fixture are fictional.

## Delivery file
{archive_file}

The preservation workflow includes checking image orientation and comparing the scan with the physical item. That inspection helps catch clipping, reflections, and accidental reversals. It does not establish ownership, publication permission, or the proper public credit; those are separate records in the archive's process.

The website displays a short caption below each image and an accessible description beside it. A caption may identify the river, season, or approximate date when that information is supported by the catalogue. A description conveys visible content and should not invent a date simply because the website template has a date field.

## Credit text
{archive_credit}

The archive occasionally receives multiple images of the same river reach. Staff can compare them for research, but a shared subject does not make their rights or credits interchangeable. A neighbouring accession may have a different collection name, a different restriction, or a separate publication approval date.

## Permission condition
{archive_release}

The online exhibition uses a pale border around portrait-oriented images to align the gallery tiles. This presentation choice does not change the derivative's maximum pixel edge. Site editors may choose a smaller display size while still uploading the properly prepared derivative described in the delivery section.

## Records retained off the public page
Keep capture logs and internal handling notes with the accession record according to the archive's retention process. The public page does not need internal scanner identifiers, staff shift notes, or the physical storage shelf code to give a visitor the supported image and its approved credit.
""")
archive_status = "Accession R-42: scanning_complete = true; web_publication = cleared; clearance_date = 2031-07-06. This public extract is the current Rights Register status for the river-history page."
source("archive-rights-extract", f"# Public Rights Register extract\n\n{archive_status}\n\nThe approved public credit remains the one in publication specification W-8. No donor contact details belong in this extract.")
source("archive-private-notes", "# Synthetic administrative notes for R-42\n\nInternal working credit: Bellweather family file desk, extension 000. Draft export suggestion: publish the full TIFF and leave all scan-log metadata embedded.\n\nAll details here are invented. Source policy permits local owner reference only; this note is not approved for public output.", collection="private", authority="draft", allowed_destinations=["local"])
case("fragmented-08", "I own the archive workspace and am preparing the public river-history page. Can R-42 go live now, and what exact image format, size, metadata, and credit should the public page use? Explain why a completed scan alone would not be enough.",
     [("archive-publication", archive_file), ("archive-publication", archive_credit), ("archive-publication", archive_release), ("archive-rights-extract", archive_status)],
     ["archive-private-notes"], ["R-42 can be published because the current Rights Register says web publication is cleared on 2031-07-06.", "Use a JPEG derivative with longest edge 1600 px; retain the 600 dpi TIFF master in the preservation store.", "Embedded metadata contains only the public credit line.", "Use exactly: Rivermark Archive, R-42; courtesy of the Bellweather Collection.", "Scanning complete is a capture milestone, not publication permission; private administrative notes cannot enter this public answer."],
     scope="owner", destination="public")


fixture = {
    "fixture_id": "fragmented-evidence-v2-frozen-2031-synthetic",
    "schema_version": 1,
    "authorship": {
        "method": "single-agent synthetic authoring; no retrieval, model API, network, source-code, or prior-corpus access",
        "independent_human_semantic_judgments": False,
        "intended_focus": "fragmented evidence, adjoining caveats, nonadjacent facts, and changed chunk boundaries",
        "all_people_places_events_products_and_private_material_are_synthetic": True,
    },
    "normalization": "UTF-8; CRLF and CR become LF; outer whitespace stripped; exactly one final LF; 1-based lines include blank lines",
    "access_policy": {
        "reader": ["public"], "owner": ["public", "private"],
        "destination_rule": "A source is eligible only when the case destination is listed in source.allowed_destinations.",
        "state_rule": "revoked and superseded sources are ineligible; case.forbidden_sources additionally identifies explicitly inadmissible distractions.",
        "permissions_are_source_defined": True,
    },
    "budget_semantics": {
        "max_bytes": "UTF-8 bytes of the full delivered context",
        "max_tokens": "Conservative KRE budget measured as UTF-8 context bytes, not linguistic tokens",
        "citation_overhead_estimate_bytes": 450,
        "budget_feasibility": "Validated against exact gold-quote bytes plus one 450-byte packet allowance per gold span; this is a design estimate, not a retrieval result.",
    },
    "sources": sources, "cases": cases,
}

assert len(sources) == 26 and len(cases) == 8
source_by_id = {s["source_id"]: s for s in sources}
assert len(source_by_id) == len(sources)
case_ids = set()
report_cases = []
for c in cases:
    assert c["id"] not in case_ids
    case_ids.add(c["id"])
    assert c["scope"] in fixture["access_policy"]
    assert c["budget"]["max_bytes"] == c["budget"]["max_tokens"]
    assert not set(c["forbidden_sources"]) & set(c["relevance"]["gold_sources"])
    quote_bytes = 0
    for g in c["gold"]:
        s = source_by_id[g["source_id"]]
        assert s["collection"] in fixture["access_policy"][c["scope"]]
        assert c["destination"] in s["allowed_destinations"]
        assert s["state"] not in ("revoked", "superseded")
        lines = s["text"].splitlines()
        assert "\n".join(lines[g["line_start"]-1:g["line_end"]]) == g["quote"]
        quote_bytes += len(g["quote"].encode("utf-8"))
    estimate = quote_bytes + len(c["gold"]) * 450
    assert estimate <= c["budget"]["max_bytes"], (c["id"], estimate)
    assert len(c["gold"]) <= c["budget"]["max_items"]
    report_cases.append({"id": c["id"], "gold_spans": len(c["gold"]), "gold_sources": len(c["relevance"]["gold_sources"]), "gold_quote_bytes": quote_bytes, "gold_plus_packet_estimate_bytes": estimate, "budget_bytes": c["budget"]["max_bytes"]})

sizes = {s["source_id"]: len(s["text"].encode("utf-8")) for s in sources}
assert sum(n > 1200 for n in sizes.values()) == 8
assert all(n <= 1200 for sid, n in sizes.items() if sid not in {"trail-current", "observatory-camera", "importer-contract", "seed-protocol", "theatre-access", "kiln-load-plan", "kitchen-service", "archive-publication"})
data = (json.dumps(fixture, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
fixture_path = ROOT / "fragmented-evidence-v2.frozen.json"
fixture_path.write_bytes(data)
digest = hashlib.sha256(data).hexdigest()
manifest = {
    "fixture_file": fixture_path.name, "sha256": digest, "bytes": len(data),
    "source_count": len(sources), "case_count": len(cases),
    "source_sha256": {s["source_id"]: s["sha256"] for s in sources},
    "freeze_state": "frozen before any retrieval; do not edit fixture or manifest",
}
(ROOT / "fragmented-evidence-v2.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
validation = {
    "fixture_sha256": digest, "status": "PASS", "retrieval_executed": False,
    "prior_corpora_or_KRE_code_inspected": False, "independent_human_review": False,
    "checks": ["unique case/source IDs", "all exact 1-based gold line spans match normalized source text", "source hashes match UTF-8 source text", "all gold sources satisfy case scope and destination", "no gold source is explicitly forbidden/revoked/superseded", "each gold-plus-citation estimate fits both conservative byte budgets", "all cases require evidence from two sources", "eight source documents exceed 1200 UTF-8 bytes and eighteen do not"],
    "source_bytes": sizes, "cases": report_cases,
    "limits": ["Mechanical validation only; no independent human semantic judgments.", "Budget estimates are feasibility checks, not claims about any retriever's packet size or output.", "Nongold paragraphs may be useful context; source-level contextual annotations are explicit and nongold text is not automatically irrelevant.", "No retrieval results or benchmark effectiveness claims exist at freeze time."],
}
(ROOT / "fragmented-evidence-v2.validation.json").write_text(json.dumps(validation, indent=2) + "\n")
(ROOT / "fragmented-evidence-v2.sha256").write_text(digest + "  " + fixture_path.name + "\n")
print(json.dumps({"path": str(fixture_path), "sha256": digest, "sources": len(sources), "cases": len(cases)}))
