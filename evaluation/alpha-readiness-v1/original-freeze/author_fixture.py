#!/usr/bin/env python3
"""Deterministic fixture authoring; contains no imports from the evaluated package."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def doc(key, title, text, **metadata):
    return dict(id=key, title=title, text=text.strip() + "\n", collection="shared",
                authority="authoritative", origin="source_evidence", freshness="fresh",
                egress="local_only", lifecycle="active", **metadata)


def altered(key, title, text, **metadata):
    result = doc(key, title, text)
    result.update(metadata)
    return result


def gold(key, source, quote, reason):
    return dict(id=key, source_id=source, quote=quote, reason=reason)


def case(key, category, question, documents, spans, *, budget=11000, items=12,
         kind="retrieve", forbidden=(), required=(), continuity=None, **request):
    result = dict(id=key, category=category, question=question, documents=documents, gold=spans,
                  request=dict(destination="local_only", purpose="current_answer",
                               freshness_requirement="allow_unknown",
                               budget=dict(max_tokens=budget, max_items=items, max_bytes=budget), **request),
                  expectation=dict(kind=kind), forbidden_sources=list(forbidden))
    if required:
        result["required_gold_ids"] = list(required)
    if continuity:
        result["continuity"] = continuity
    return result


cases = []

museum = doc("museum-handbook", "Windlass Museum winter loan handling", """
# Windlass Museum: winter loan handling

This handbook accompanies the travelling collection of small brass instruments. It covers the return journey from visiting schools to the museum store. The cases are reusable, and all packing material remains the museum's property. The purpose of the procedure is to keep the instruments stable while making the handover legible to staff who did not attend the visit. A teacher's signature acknowledges the number of cases received; it does not transfer responsibility for conservation decisions.

## Return appointment

For a winter loan return, book the covered loading bay at least two working days before the van arrives.
The visitor entrance cannot accept wheeled cases during public opening hours. The bay diary is maintained on paper at reception because volunteers rotate between the desk and galleries. Staff should copy the booked time onto the journey envelope. If the driver arrives early, the van remains in the marked waiting area until the receiving pair are ready. An unused booking is crossed out so the next shift can distinguish a cancellation from an overlooked arrival.

## Exterior examination

Look at each closed case before moving it off the trolley. Scuffs already shown in the departure photographs do not count as new damage. Record the case number beside any fresh dent, broken seal or wet patch, then photograph the affected side against the measuring card. A water mark is a reason to call the conservator even when the latch still works. Do not use solvent or a hair dryer on the case; the foam liner can retain moisture that is invisible from outside.

## Settling period

Keep returned winter loan cases sealed in the acclimatisation room for eighteen hours before opening them.
Use the shelving on the interior wall, away from the sink and external door. Set the arrival card upright so that the next shift can read the release time without touching the case. The room's wall clock is the shared time reference. If a power cut makes the temperature log unavailable, leave the cases closed and add a note to the shift book. Conservation staff will decide whether a longer settling period is necessary after the room conditions are restored.

## Paperwork and accessories

The journey envelope contains the collection checklist, a padded pouch for loose labels, the school receipt and the departure photographs. Count the removable stands separately from the instruments; a stand left behind at a school should not be described as a missing collection object. Place clean cotton ties back in the side pocket. Used tissue goes in the conservation waste tray so that fragments can be checked before disposal. The reusable route card stays with the van driver for the final depot return.

## Opening authority

Only the collections technician may release a winter loan case for opening after the settling period.
The receiving volunteer records the technician's initials on the arrival card. A school contact cannot waive this step, even when another class needs the instruments the next morning. A delay must be communicated to the education desk before a replacement session is offered. Staff should avoid promising access to a specific object until the post-return examination has been completed. The education desk can lend the photographic teaching pack while the physical collection remains unavailable.

## Condition record

Once released, open one case at a time on the padded examination table. Compare the instrument with its departure photographs, checking feet, hinges and raised decoration before handling the smaller parts. Copy observations in plain language and avoid guessing how a mark occurred. The conservator assigns condition codes later. An unchanged object still needs a dated entry because the absence of a new observation is otherwise indistinguishable from a missed examination.

## Final filing

File the signed winter loan return sheet in the blue acquisitions cabinet, drawer four.
The digital image folder is an additional working copy and does not replace the signed sheet. Put photographs in date order, with the case number at the beginning of each filename. The registrar checks the filing list at the end of the week and reconciles any missing signatures with the receiving pair. Spare blank forms belong in the stationery cupboard, not among the completed records. This separation prevents an unfilled sheet being mistaken for a documented return.

## End of shift

Move empty trolleys back to the bay only after all collection cases are on the assigned shelves. Check that the exterior door is latched and that the examination lamps are off. Leave one clear handover note naming any case still waiting for conservation advice. The following shift should be able to identify outstanding work without reconstructing a conversation. Routine replenishment of tissue, gloves and pencils can wait until the collection has been secured.
""")
cases.append(case("H01", "long_fragmented", "How should staff handle a winter loan return: reserve arrival space, wait before opening, obtain release, and file the signed record?", [museum], [
    gold("h01-a", museum["id"], "For a winter loan return, book the covered loading bay at least two working days before the van arrives.", "Arrival booking and lead time"),
    gold("h01-b", museum["id"], "Keep returned winter loan cases sealed in the acclimatisation room for eighteen hours before opening them.", "Waiting period and location"),
    gold("h01-c", museum["id"], "Only the collections technician may release a winter loan case for opening after the settling period.", "Release authority"),
    gold("h01-d", museum["id"], "File the signed winter loan return sheet in the blue acquisitions cabinet, drawer four.", "Record destination")]))

cases.append(case("H02", "cross_source", "For Saturday's mobile pantry stop, where is the van placed, who performs the chilled-food check, and what time ends voucher collection?", [
    doc("pantry-site", "Saturday mobile pantry site note", """# Saturday mobile pantry site note

Park the Saturday mobile pantry van beside the east basketball gate, leaving the pedestrian ramp clear.
The school has reserved two cones for the turning area. Drivers should collect them from the caretaker's porch and return them after unloading. The west gate is for the sports club and must remain available throughout the morning.
"""),
    doc("pantry-shift", "Saturday mobile pantry rota", """# Saturday mobile pantry rota

Mara Chen performs the chilled-food temperature check before the first crate leaves the Saturday van.
Felix handles table assembly and puts the empty boxes under the canopy. Rotating volunteers should sign the attendance sheet before taking a station. Late arrivals report to the queue marshal, who can assign relief duties without interrupting food handling.
"""),
    doc("pantry-vouchers", "Voucher desk instructions", """# Voucher desk instructions

Voucher collection for the Saturday mobile pantry ends at 11:20 a.m.
People already holding a voucher may remain in the distribution queue after the desk closes. Unused vouchers are counted into the envelope with the date written on the flap. The count measures issued places, not the number of household members receiving food.
""")], [
    gold("h02-a", "pantry-site", "Park the Saturday mobile pantry van beside the east basketball gate, leaving the pedestrian ramp clear.", "Van placement"),
    gold("h02-b", "pantry-shift", "Mara Chen performs the chilled-food temperature check before the first crate leaves the Saturday van.", "Responsible person"),
    gold("h02-c", "pantry-vouchers", "Voucher collection for the Saturday mobile pantry ends at 11:20 a.m.", "Voucher deadline")], budget=6000))

cases.append(case("H03", "current_and_obsolete", "What are the current reed-bed sensor checks: rinse fluid, stabilisation interval, and the place to record a rejected reading?", [
    doc("sensor-current", "Reed-bed sensor field card", """# Reed-bed sensor field card

This card applies to the small optical probe used at the reed-bed boardwalk. Record the visit date before opening the transport tube. The spare batteries live in a separate dry pouch, and neither the batteries nor the probe should be left in direct sun while the field kit is being assembled. The boardwalk can become slippery after the morning irrigation cycle, so put the open case on the raised bench.

## Cleaning

Rinse the reed-bed sensor face with distilled water before lowering it into the sampling cup.
Do not wipe the optical window with the cotton towel used for the outside of the case. Grit on a towel can scratch the window even when the instrument still appears to give stable readings. Keep the rinse bottle upright and replace its cap immediately. If the clean water has been exhausted, postpone the reading rather than borrowing an unlabelled bottle from the maintenance shed.

## Measurement

Allow the reed-bed sensor reading to stabilise for ninety seconds after immersion.
Hold the cable loosely so that movement at the boardwalk rail does not drag the probe against the cup. The displayed number may settle earlier, but the common interval makes visits comparable. A passing bird or a shadow across the cup does not require restarting the interval. Visible bubbles on the optical face do require a fresh placement and a new interval.

## Rejected measurements

Enter each rejected reed-bed sensor reading in the amber field ledger with the reason for rejection.
The electronic table contains only accepted measurements. Keeping rejected observations in the paper ledger prevents a gap from being interpreted as a missed visit. Never overwrite an earlier rejected number with the repeat measurement. Draw a single line through a transcription error and initial it so that the original entry remains readable during the monthly review.
"""),
    altered("sensor-old", "Retired reed-bed quick card", "# Retired reed-bed quick card\n\nThe reed-bed sensor was once rinsed with tap water and read after thirty seconds. Rejected values were erased from the sheet.\n", lifecycle="superseded"),
    altered("sensor-withdrawn", "Withdrawn vendor advice", "# Withdrawn vendor advice\n\nReed-bed sensor readings require no stabilisation. Wipe the window with abrasive paper to remove stains.\n", lifecycle="revoked", authority="unverified")], [
    gold("h03-a", "sensor-current", "Rinse the reed-bed sensor face with distilled water before lowering it into the sampling cup.", "Rinse fluid"),
    gold("h03-b", "sensor-current", "Allow the reed-bed sensor reading to stabilise for ninety seconds after immersion.", "Interval"),
    gold("h03-c", "sensor-current", "Enter each rejected reed-bed sensor reading in the amber field ledger with the reason for rejection.", "Rejected-reading record")], forbidden=["sensor-old", "sensor-withdrawn"]))

cases.append(case("H04", "fragmented_procedure", "Before the map cabinet move, what should be removed, how are the drawers secured, and who signs the delivery check?", [
    doc("map-move", "Map cabinet relocation brief", """# Map cabinet relocation brief

The archive is moving its flat map cabinet to the new reading room during the scheduled floor repair. The cabinet will travel on the service lift, with a porter ahead of the trolley to keep the route clear. This is a furniture move and does not change the catalogue location of individual maps until the receiving check has finished. Researchers should be directed to the temporary digital terminal during the closure.

## Preparing contents

Remove every map and loose divider from the cabinet before the move begins.
Lay maps flat in the numbered transit trays. A tray may contain several folders only when all their catalogue numbers remain visible at the top edge. The archive assistant checks the tray list against the drawer inventory while the porter prepares the trolley. Work from the top drawer down so that the unloaded cabinet remains stable. Keep the emptied dividers together in a separate sleeve.

## Securing the furniture

Secure the empty map cabinet drawers with the two woven straps stored in the porter cupboard.
Adhesive tape is unsuitable because it can pull the surface finish away when removed. Place a clean felt square under each buckle and tighten only enough to prevent a drawer sliding. The cabinet must remain upright on the trolley. The lift attendant checks the route before the team enters the corridor, including the turn beside the drinking fountain.

## Receiving check

The duty archivist signs the map cabinet delivery check after counting the transit trays.
The porter records any fresh marks on the cabinet separately from the archive's map condition notes. Do not return the contents until the cabinet is standing level and the drawers open without rubbing. Refit the dividers in their original sequence, then check the catalogue numbers from the tray list. Once the final drawer is complete, remove the temporary closure notice from the reading-room desk.
"""),
    doc("map-digital", "Digital map terminal", "# Digital map terminal\n\nThe temporary map terminal starts in catalogue view. Visitors may print a location slip at the enquiry desk, but full-size map printing is unavailable while the reading room floor is repaired.\n")], [
    gold("h04-a", "map-move", "Remove every map and loose divider from the cabinet before the move begins.", "Contents removed"),
    gold("h04-b", "map-move", "Secure the empty map cabinet drawers with the two woven straps stored in the porter cupboard.", "Drawer restraint"),
    gold("h04-c", "map-move", "The duty archivist signs the map cabinet delivery check after counting the transit trays.", "Signatory and check")]))

access = doc("event-access", "Canal Hall spoken-history evening", """
# Canal Hall spoken-history evening: access and front-of-house guide

The spoken-history evening brings together former boatyard workers, their families and local students. Doors open before the exhibition walk so that visitors can choose seats and become familiar with the room. The access arrangements below are part of the event plan, not optional additions to be improvised once a visitor asks for help. Volunteers should know which colleague can resolve a problem while keeping the reception desk attended.

## Arrival route

Visitors using the step-free entrance should enter Canal Hall through the courtyard door on Mill Lane.
The door opens into a short level corridor beside the cloakroom. Keep the stack of spare chairs out of that corridor, even when it is raining and the courtyard is quiet. A volunteer should check the outside sign at the start of the shift because delivery vehicles sometimes obscure it. The public staircase on the canal side remains available to visitors who prefer that route, but signs must never direct everyone there by default.

## Reception

The desk has printed programmes in large type and a box of ordinary programmes. Offer the large-type copy alongside the standard version without asking a visitor to explain why they want it. Programme stock should be counted after the room settles, not while a queue is waiting. Tickets are checked by name; the organiser has already warned that two households share a surname, so staff must also confirm the number of places on the booking.

## Listening support

Collect a hearing receiver from the sound desk by showing the numbered ticket stub; no identity document is required.
The sound technician will demonstrate the volume dial using the pre-event test recording. Used earpieces go in the labelled tray after the event, while the receiver bodies return to their charging slots. Visitors who bring their own compatible headset may use it. If a receiver stops working during a talk, the aisle volunteer carries a replacement over rather than asking the listener to leave and join the reception queue.

## Seating

Two front-row places have been left without fixed chairs so that visitors can choose how to sit with their companions. Do not use this space to store camera cases or folded coats. Other aisle seats are reserved until the first talk starts; after that, the front-of-house lead may release them if they are not needed. Keep one ordinary chair near the exhibition entrance for anyone who needs a rest while looking at the photographs.

## Quiet space

The quiet room is the small pottery studio opposite the courtyard corridor, and its door remains unlocked throughout the evening.
The studio lights have been dimmed and a jug of water is on the worktable. It is not a second performance room, so do not relay the talks over a loudspeaker there. A visitor may leave and return without explaining their reason. Volunteers should check the room discreetly between talks and make sure the route back to the hall remains clear. Children using the space should stay with their accompanying adult.

## Speaker preparation

Speakers have been asked to name the people in photographs and describe the details they discuss. The lectern microphone should remain at the same distance from each speaker's mouth. The chair will repeat questions from the audience before inviting an answer, even if the person asking believes they spoke loudly enough. Short breaks between talks allow listeners to change seats or replace equipment without missing the beginning of a story.

## Problems during the event

Direct unresolved access problems to front-of-house lead Noor Iqbal, who wears a green lanyard.
The lead can adjust seating, arrange a quieter conversation or contact the building caretaker. Volunteers should describe the practical obstacle instead of guessing a visitor's diagnosis. Record any equipment failure on the desk sheet before the shift ends, including what was tried and whether the visitor received an alternative. Private details belong only in a direct conversation with the lead, not in a general incident note.

## Closing the building

When the audience has left, count receivers against the numbered charging spaces and return spare programmes to the crate. Inspect the courtyard corridor before moving chairs back from the store. The caretaker locks the external door only after the front-of-house lead confirms that the quiet room and toilets are empty. Leave the guide on the desk for the morning team, together with a short note about any sign or piece of equipment that needs attention.
""")
cases.append(case("H05", "long_access_plan", "Summarise the spoken-history evening's step-free entry, hearing-receiver collection, quiet-room location, and access-problem contact.", [access,
    doc("event-menu", "Canal Hall refreshments", "# Canal Hall refreshments\n\nTea is served from the kitchen hatch between talks. Cups remain inside the building. The refreshments team should put the reusable jugs back on the drying rack before leaving.\n")], [
    gold("h05-a", access["id"], "Visitors using the step-free entrance should enter Canal Hall through the courtyard door on Mill Lane.", "Entrance route"),
    gold("h05-b", access["id"], "Collect a hearing receiver from the sound desk by showing the numbered ticket stub; no identity document is required.", "Receiver collection"),
    gold("h05-c", access["id"], "The quiet room is the small pottery studio opposite the courtyard corridor, and its door remains unlocked throughout the evening.", "Quiet room"),
    gold("h05-d", access["id"], "Direct unresolved access problems to front-of-house lead Noor Iqbal, who wears a green lanyard.", "Escalation contact")], budget=13000))

cases.append(case("H06", "hard_paraphrase", "What lets a courier establish that the recipient personally accepted the parcel?", [
    doc("delivery-proof", "Handover evidence", "# Handover evidence\n\nA signed acknowledgment from the addressee is the sole admissible confirmation of receipt. A doorstep photograph or a neighbour's initials cannot substitute for that acknowledgment. Retain the original slip with the dispatch register.\n"),
    doc("courier-parking", "Courier parcel access", "# Courier parcel access\n\nA courier carrying a parcel may park in the loading space for ten minutes. The recipient parking area is reserved for visitors with appointments. Staff personally check the loading-space sign each morning.\n")], [
    gold("h06-a", "delivery-proof", "A signed acknowledgment from the addressee is the sole admissible confirmation of receipt.", "Direct synonym-only support")], budget=4000))

cases.append(case("H07", "unresolved_conflict", "What opening time is recorded for the Monday seed exchange, and do the two issued notices agree?", [
    doc("seed-board", "Seed exchange noticeboard sheet", "# Seed exchange noticeboard sheet\n\nThe Monday seed exchange opens at 8:45 a.m. in the glasshouse foyer. This notice was approved by the allotment committee on 6 March. Volunteers should bring their own mug for the tea table.\n"),
    doc("seed-letter", "Seed exchange member letter", "# Seed exchange member letter\n\nThe Monday seed exchange opens at 9:15 a.m. in the glasshouse foyer. This letter was approved by the allotment committee on 6 March. Tables are grouped by vegetable family, with flower seeds near the door.\n")], [
    gold("h07-a", "seed-board", "The Monday seed exchange opens at 8:45 a.m. in the glasshouse foyer.", "First issued time"),
    gold("h07-b", "seed-letter", "The Monday seed exchange opens at 9:15 a.m. in the glasshouse foyer.", "Conflicting issued time")], budget=4000))

cases.append(case("H08", "short_unicode", "Where should café staff leave the repaired grinder key?", [
    doc("cafe-key", "Café grinder handover", "# Café grinder handover\n\nLeave the repaired grinder key in the rôle-labelled tin marked “Équipe du matin” beneath the till. The spare key stays with the café manager.\n"),
    doc("cafe-clean", "Café closing note", "# Café closing note\n\nThe grinder hopper is emptied into the compost caddy at closing. Leave the counter dry and put the cleaning brush beside the sink.\n")], [
    gold("h08-a", "cafe-key", "Leave the repaired grinder key in the rôle-labelled tin marked “Équipe du matin” beneath the till.", "Exact location with non-ASCII bytes")], budget=3000))

cases.append(case("H09", "missing_evidence", "Who is authorised to approve an overnight extension for the community telescope loan?", [
    doc("telescope-care", "Community telescope loan care", "# Community telescope loan care\n\nKeep the community telescope in its padded case while travelling. Return the eyepiece caps with the instrument and report condensation on the lens. The desk records the scheduled return date on a yellow card.\n"),
    doc("telescope-night", "Community telescope evening session", "# Community telescope evening session\n\nThe astronomy club's overnight observing event uses its own instruments. Community telescope loan paperwork is stored separately from event attendance sheets. Staff approve room bookings through the ordinary calendar.\n")], [], kind="missing", budget=4000))

cases.append(case("H10", "private_scope", "Which number should a public visitor call about the weaving workshop?", [
    doc("weaving-public", "Weaving workshop visitor card", "# Weaving workshop visitor card\n\nPublic visitors with weaving workshop questions should call the reception number 020 7946 0128. Reception can confirm access times and the materials list.\n"),
    altered("weaving-private", "Weaving workshop staff contingency", "# Weaving workshop staff contingency\n\nWeaving workshop staff must call the private emergency line 020 7946 0991 if the tutor is absent. This line must not appear in visitor information.\n", collection="private")], [
    gold("h10-a", "weaving-public", "Public visitors with weaving workshop questions should call the reception number 020 7946 0128.", "Public contact")], forbidden=["weaving-private"], budget=4000))

remote_case = case("H11", "local_only_egress", "What is the combination recorded for the restoration cage?", [
    doc("cage-local", "Restoration cage combination", "# Restoration cage combination\n\nThe restoration cage combination is 42-17-68. Keep this note in the local workshop records and do not include it in a remotely processed response.\n")], [], kind="policy", forbidden=["cage-local"], budget=4000)
remote_case["request"]["destination"] = "approved_remote"
cases.append(remote_case)

cases.append(case("H12", "caller_required_fit", "Prepare the mobile darkroom start-up evidence packet.", [
    doc("darkroom-water", "Mobile darkroom water", "# Mobile darkroom water\n\nFill the mobile darkroom rinse tank with twelve litres of clean water before the session. Check the drain hose for a kink before placing the tank on the low shelf.\n"),
    doc("darkroom-light", "Mobile darkroom light check", "# Mobile darkroom light check\n\nTest the mobile darkroom safelight with a covered scrap sheet for three minutes before opening the paper box. Keep the exposed test beside the untouched scrap for comparison.\n"),
    doc("darkroom-stock", "Mobile darkroom stock", "# Mobile darkroom stock\n\nCount the paper sheets after the session and write the remaining total on the packet. Store opened packets in the sealed cupboard.\n")], [
    gold("h12-a", "darkroom-water", "Fill the mobile darkroom rinse tank with twelve litres of clean water before the session.", "Declared required water evidence"),
    gold("h12-b", "darkroom-light", "Test the mobile darkroom safelight with a covered scrap sheet for three minutes before opening the paper box.", "Declared required light evidence")], kind="required_fit", required=["h12-a", "h12-b"], budget=6000))

cases.append(case("H13", "caller_required_tight", "Prepare the ceramic kiln handover evidence packet.", [
    doc("kiln-handover", "Ceramic kiln handover", """# Ceramic kiln handover

The evening kiln operator must leave the firing log, witness-cone photograph, controller printout and shelf diagram together in the red handover wallet before signing out. The morning operator checks all four records before opening the kiln. A missing record is reported to the studio manager; memory of the firing does not replace the written handover. Keep unrelated class attendance sheets out of the wallet so that the technical records can be checked without searching through participant details.
""")], [
    gold("h13-a", "kiln-handover", "The evening kiln operator must leave the firing log, witness-cone photograph, controller printout and shelf diagram together in the red handover wallet before signing out.", "Declared required handover")], kind="required_budget", required=["h13-a"], budget=300, items=2))

cases.append(case("H14", "checkpoint_resume", "What instruction should the boat shed volunteer retain for the morning launch checklist?", [
    doc("boat-launch", "Morning launch checklist", "# Morning launch checklist\n\nBefore the morning launch, the boat shed volunteer checks that each lifejacket has an intact buckle and records the count on the pier board. A damaged jacket goes in the marked repair crate.\n"),
    doc("boat-evening", "Evening boat shed", "# Evening boat shed\n\nThe evening key holder closes the upper window and returns the trolley to the dry rack. The radio remains on its charger overnight.\n")], [
    gold("h14-a", "boat-launch", "Before the morning launch, the boat shed volunteer checks that each lifejacket has an intact buckle and records the count on the pier board.", "Fact checkpointed then invalidated")], kind="checkpoint", budget=4000,
    continuity=dict(source_id="boat-launch", action="revoke", independent_assertion="Keep the volunteer briefing to one page.")))

historical = case("H15", "historical_lifecycle", "What did the superseded orchard ladder instruction require, and what does its active replacement require?", [
    altered("orchard-old", "Superseded orchard ladder instruction", "# Superseded orchard ladder instruction\n\nThe orchard ladder instruction required one volunteer to carry each ladder from the store. This version is superseded and retained only for the incident review.\n", lifecycle="superseded"),
    doc("orchard-current", "Current orchard ladder instruction", "# Current orchard ladder instruction\n\nThe orchard ladder instruction now requires two volunteers to carry each ladder from the store. The shift leader assigns pairs before unlocking the equipment room.\n"),
    altered("orchard-revoked", "Revoked orchard ladder tip", "# Revoked orchard ladder tip\n\nThe orchard ladder instruction permits dragging ladders behind a moving cart.\n", lifecycle="revoked")], [
    gold("h15-a", "orchard-old", "The orchard ladder instruction required one volunteer to carry each ladder from the store.", "Historical requirement"),
    gold("h15-b", "orchard-current", "The orchard ladder instruction now requires two volunteers to carry each ladder from the store.", "Current replacement")], forbidden=["orchard-revoked"], budget=5000)
historical["request"]["purpose"] = "historical_evidence"
cases.append(historical)

cases.append(case("H16", "ordinary_tight_budget", "What three checks are required for the travelling puppet booth: floor, ballast, and public clearance?", [
    doc("puppet-booth", "Travelling puppet booth setup", """# Travelling puppet booth setup

## Floor

The travelling puppet booth requires a level floor with no loose mat beneath its feet.
Walk the proposed footprint before taking the fabric panels out of their bag. A doorway threshold can tilt one corner even when the surrounding surface appears flat. Ask the host to clear a different position if a stable footprint is unavailable; folding paper under a foot is not an approved adjustment. Keep the packing bag outside the performance area so that a late arrival cannot trip over it.

## Ballast

Attach one sealed ten-kilogram ballast bag to each rear foot of the travelling puppet booth.
The bags remain attached until the fabric panels have been removed at the end of the show. Inspect the loops for fraying before clipping them in place and lay the excess strap inside the footprint. A volunteer should stay beside the frame while the second bag is fitted. Never substitute an audience member's bag for the labelled ballast supplied with the booth.

## Clearance

Maintain a clear public aisle at least one metre wide along the travelling puppet booth's left side.
Measure the aisle after the audience chairs have been set out, because chair legs can narrow the route without changing the position of the booth. Keep the prop trunk behind the backdrop. During the show, the door volunteer redirects anyone who tries to stand in the aisle and checks that pushchairs have not rolled into the marked space. Remove the floor tape when packing away.
""")], [
    gold("h16-a", "puppet-booth", "The travelling puppet booth requires a level floor with no loose mat beneath its feet.", "Floor requirement"),
    gold("h16-b", "puppet-booth", "Attach one sealed ten-kilogram ballast bag to each rear foot of the travelling puppet booth.", "Ballast requirement"),
    gold("h16-c", "puppet-booth", "Maintain a clear public aisle at least one metre wide along the travelling puppet booth's left side.", "Clearance requirement")], budget=700, items=3))


def main():
    for c in cases:
        docs = {d["id"]: d for d in c["documents"]}
        assert len(docs) == len(c["documents"])
        for d in docs.values():
            d["utf8_bytes"] = len(d["text"].encode())
            d["sha256"] = hashlib.sha256(d["text"].encode()).hexdigest()
        for span in c["gold"]:
            text = docs[span["source_id"]]["text"]
            assert text.count(span["quote"]) == 1, span
            start = text.index(span["quote"])
            end = start + len(span["quote"])
            span.update(char_start=start, char_end=end, line_start=text.count("\n", 0, start) + 1,
                        line_end=text.count("\n", 0, end - 1) + 1,
                        sha256=hashlib.sha256(span["quote"].encode()).hexdigest())
        c["expected_sources"] = sorted({g["source_id"] for g in c["gold"]})
    payload = dict(suite_id="kre-independent-alpha-holdout-v1", fixture_version=1,
                   authoring_date="2026-11-16", semantic_review="unknown", cases=cases)
    target = ROOT / "fixture.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(path=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                         cases=len(cases), documents=sum(len(c["documents"]) for c in cases),
                         gold_spans=sum(len(c["gold"]) for c in cases))))


if __name__ == "__main__":
    main()
