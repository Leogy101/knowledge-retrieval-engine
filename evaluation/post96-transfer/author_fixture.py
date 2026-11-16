from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sources = []
cases = []

def add_source(source_id, text, *, collection='public', freshness='fresh', authority='authoritative', origin='source_evidence', state='active'):
    text = text.strip('\n')
    assert text and not text.endswith('\n')
    sources.append(dict(source_id=source_id, text=text, collection=collection, freshness=freshness, authority=authority, origin=origin, state=state))
    return source_id

def gold(source_id, quote):
    source = next(s for s in sources if s['source_id'] == source_id)
    lines = source['text'].splitlines()
    qlines = quote.splitlines()
    matches = [i for i in range(len(lines)-len(qlines)+1) if lines[i:i+len(qlines)] == qlines]
    assert len(matches) == 1, (source_id, quote, matches)
    start = matches[0]
    return dict(source_id=source_id, line_start=start+1, line_end=start+len(qlines), quote=quote)

def add_case(case_id, query, scope, gold_items, forbidden, requirements, *, missing=None, budget=None, distractors=None):
    cases.append(dict(id=case_id, query=query, scope=scope, purpose='current_answer', destination='local_only', budget=budget or dict(max_bytes=12000,max_tokens=12000,max_items=12), gold=gold_items, forbidden_sources=forbidden, answer_requirements=requirements, missing_evidence=missing or [], distractor_sources=distractors or []))

add_source('siltline-service-handbook', '''Siltline estuary recorder — field service handbook, revision 6
This equipment stores salinity and pressure observations on a floating carrier that is serviced from shore.
A carrier contains a sensing head, a removable dry compartment, a power rail, and a small local event journal.
The journal has space for thirty days of ordinary operation; copying it does not acknowledge any alarms.
Identification plates are stamped on the inside of the dry compartment so that fouling cannot obscure the serial number.
The shore receiver may display an older carrier nickname until the next scheduled inventory exchange.
A nickname mismatch is cosmetic when the immutable serial number agrees with the inventory sheet.
Before handling any connector, photograph the cable route and record whether the strain relief was still seated.
Do not clean the optical window with abrasive pads, even when the mark appears to be dried salt.
A scratched window can produce plausible pressure values while distorting the companion turbidity reading.
Routine window cleaning uses the lint-free pad supplied in the dock box and clean water from a sealed container.
Return used pads to the waste pouch; never leave loose material where the tide can carry it into the basin.
The compartment gasket should be inspected in diffuse daylight, because a strong point light can hide a shallow nick.
An intact gasket has a continuous matte surface; glossy patches alone do not establish that a leak has occurred.
If moisture is present in the compartment, isolate the carrier and send the physical assembly for bench inspection.
The battery indicator describes stored charge and does not establish that the sensing head is responding.
A head can continue reporting its last accepted observation while the analog front end is waiting for a restart.
During a scheduled restart, the receiver keeps an explicit gap in the time series instead of interpolating observations.
The gap is useful to downstream auditors and must not be filled merely to make a chart appear continuous.
After a brownout, wait for two consecutive tide samples with no pressure jump greater than 0.4 kPa before resetting the amber latch.
A reset request is permitted only while the local mast switch is in SERVICE; a shore-side green indicator is insufficient.
Use the carrier clock for the two-sample interval; the receiver display can be delayed by a queued uplink.
If the first eligible sample is followed by an ineligible one, discard the pair and begin observing a new pair.
The physical latch is behind the upper inspection cover, which must be replaced before the carrier is returned to the water.
No restart procedure changes the scheduled sampling interval or authorizes any unattended actuation.
Document the observed values in the maintenance record, including a sample that caused a waiting period to begin again.
The service record should describe measurements in ordinary units, rather than copying a screenshot without its scale.
A later technician must be able to distinguish a calm period from a loss of observations at the receiver.
Transport covers are intended for dry storage and must be removed before redeployment to prevent trapped bubbles.
Store spare covers separately from wet cable ties so that grit does not migrate onto the sealing surface.''')
add_source('siltline-return-permit', '''Siltline return-to-service permit rules
A technician's inspection signature records that inspection occurred; it is not authorization to redeploy.
The duty hydrologist must separately approve redeployment after reviewing the maintenance record.
If approval has not been recorded, leave the carrier isolated and report the pending decision.''')
add_source('siltline-pocket-card-old', '''Siltline pocket card, withdrawn revision 2
After a brownout, one calm reading is sufficient and the shore supervisor's inspection signature authorizes redeployment.''', freshness='stale')
add_source('siltline-private-lab', '''Siltline engineering bench exception
For instrumented laboratory rigs only, a bypass harness can skip the mast switch. This is not a field procedure.''', collection='private')
add_source('siltline-mooring-brief', '''Siltline mooring brief
A damaged mooring cleat requires a replacement shackle and a visual check of the shore anchor. This sheet does not cover electrical recovery.''')
add_case('transfer-01-estuary-recovery', 'For the Siltline estuary recorder, I already paused redeployment after a brownout. Continue that work by explaining when the amber latch can be reset, what local condition is required, and whose separate sign-off is still needed. My inspection signature is already on the form; treat it as inspection evidence, not permission to put the carrier back in the water.', 'reader', [gold('siltline-service-handbook', 'After a brownout, wait for two consecutive tide samples with no pressure jump greater than 0.4 kPa before resetting the amber latch.\nA reset request is permitted only while the local mast switch is in SERVICE; a shore-side green indicator is insufficient.'), gold('siltline-return-permit', "A technician's inspection signature records that inspection occurred; it is not authorization to redeploy.\nThe duty hydrologist must separately approve redeployment after reviewing the maintenance record.\nIf approval has not been recorded, leave the carrier isolated and report the pending decision.")], ['siltline-pocket-card-old','siltline-private-lab'], ['State both calm samples and the 0.4 kPa limit.', 'Require the mast switch in SERVICE.', 'Keep redeployment paused pending a separate duty hydrologist approval; do not turn the inspection signature into approval.'], distractors=['siltline-mooring-brief'])

add_source('oriole-resin-process', '''Oriole UV vat printer — resin circulation operating note, revision 4
The circulation loop moves resin through a disposable filter without exposing the full vat to the room.
A new filter may briefly make the sight tube appear cloudy; assess the liquid after the pump has stopped.
The sealed batch label identifies the chemistry and must agree with the cartridge entry on the machine.
For a cold-start circulation run, keep the vat below 41 °C and stop immediately if the return line becomes opaque.
Opacity is a stop condition even when the temperature remains within the stated operating limit.
Do not resume until the cartridge has been inspected and the stop has been logged.''')
add_source('oriole-release-bulletin', '''Oriole materials release bulletin, 2031-03-12
For resin lot RQ-7, the settling hold after circulation is nine minutes before exposure begins.
The earlier four-minute hold is superseded because it left fine bubbles suspended in this lot.
This change does not raise the 41 °C vat limit or remove the return-line opacity stop condition.''')
add_source('oriole-release-bulletin-old', '''Oriole materials release bulletin, 2030-12-08
For resin lot RQ-7, hold for four minutes after circulation before beginning exposure.''', freshness='stale')
add_source('oriole-customer-forum', '''Shop-floor recollection from a visiting operator
I think RQ-7 works at 45 °C and only needs a two-minute wait. I have not checked the release bulletin.''', authority='unverified', origin='user_assertion')
add_source('oriole-display-protector', '''Oriole touchscreen protector brief
Wait nine minutes after wet application before wiping the display protector. This accessory instruction has no bearing on resin processing.''')
add_case('transfer-02-resin-current-rule', 'The Oriole paperwork disagrees: an older RQ-7 sheet says four minutes, while a visitor recalls hotter resin and two minutes. For a current cold-start circulation run, what temperature ceiling, visual stop signal, and delay before exposure should the operator use? Explain which hold instruction supersedes the other.', 'reader', [gold('oriole-resin-process', 'For a cold-start circulation run, keep the vat below 41 °C and stop immediately if the return line becomes opaque.\nOpacity is a stop condition even when the temperature remains within the stated operating limit.'), gold('oriole-release-bulletin', 'For resin lot RQ-7, the settling hold after circulation is nine minutes before exposure begins.\nThe earlier four-minute hold is superseded because it left fine bubbles suspended in this lot.')], ['oriole-release-bulletin-old'], ['Say below 41 °C, not at or below.', 'Treat opacity as an independent reason to stop.', 'Use the current nine-minute hold and identify the four-minute instruction as superseded.', 'Do not adopt the unverified visitor recollection.'], distractors=['oriole-customer-forum','oriole-display-protector'])

add_source('larch-archive-overview', '''Larch cold archive — capsule removal overview
The operator selects a capsule by its etched accession number, not by the removable aisle card.
A removal ticket must include the accession number, the destination bay, and the reason for removal.
Only the archive custodian may authorize removal of a sealed capsule.
The public overview intentionally omits the service cradle position and diagnostic release sequence.''')
add_source('larch-internal-service', '''Larch internal service annex, revision 8
For cradle generation C, park the lift at bay E-17 before releasing a capsule clamp.
Read the cradle generation from the fixed frame plate; the handheld console's profile name is not authoritative.
After parking, run the DRY-CHECK diagnostic and retain its output with the removal ticket.
A passing diagnostic establishes mechanical readiness only; it does not replace custodian authorization.''', collection='private')
add_source('larch-internal-withdrawn', '''Larch internal service annex, withdrawn revision 5
For cradle generation C, park the lift at bay B-03 and skip the diagnostic when the console shows ready.''', collection='private', state='revoked')
add_source('larch-shipping-case', '''Larch shipping case instruction
Empty transport shells are staged in bay E-17 during inventory counts. Do not infer a capsule-removal sequence from this staging instruction.''')
add_case('transfer-03-owner-archive-service', 'Using my owner access, finish the written Larch plan for removing a sealed capsule on a generation C cradle. Specify where to park, what readiness check to preserve, and who must authorize the removal. The console is already green, but nobody has approved removal yet; do not treat that status as permission.', 'owner', [gold('larch-internal-service', 'For cradle generation C, park the lift at bay E-17 before releasing a capsule clamp.'), gold('larch-internal-service', 'After parking, run the DRY-CHECK diagnostic and retain its output with the removal ticket.\nA passing diagnostic establishes mechanical readiness only; it does not replace custodian authorization.'), gold('larch-archive-overview', 'Only the archive custodian may authorize removal of a sealed capsule.')], ['larch-internal-withdrawn'], ['Retrieve private service evidence for the owner.', 'Give bay E-17 and preserve DRY-CHECK output.', 'Require the archive custodian authorization; a ready indication cannot supply it.'], distractors=['larch-shipping-case'])

add_source('mallow-solver-notes', '''Mallow linkage solver — numerical diagnostics
A model contains rigid links, revolute joints, fixed supports, and optional measurement constraints.
Joint names are presentation labels; the solver associates constraints with immutable joint identifiers.
A renamed joint therefore keeps its diagnostic history unless the model is rebuilt with new identifiers.
The iteration report lists residual norms before it lists the geometric tolerances used for acceptance.
Numbers in the residual column are not distances unless the constraint family explicitly says so.
Most overconstrained mechanisms produce a rank warning before the iteration count reaches its cap.
A nearly straight pair of links may also produce a poor condition estimate without being structurally overconstrained.
Check the model's unit declaration before interpreting a length residual copied from another project.
The importer preserves source unit metadata, but it cannot infer a missing unit declaration from a file name.
A fixed support removes motion at its own joint and does not automatically constrain an adjacent joint.
Users should avoid stacking duplicate supports to make a sketch look anchored at multiple points.
Duplicate supports can hide an incorrectly specified measurement while leaving the rendered sketch unchanged.
The solver stores a small accepted-state cache to help the interactive editor remain responsive.
That cache is invalidated whenever a constraint's mathematical type changes, even if its label stays the same.
A cache invalidation may increase the next solve time and is not itself evidence of a numerical failure.
For diagnostic code M17, inspect the signed area of the first three non-collinear anchor points.
If that area is negative, reverse the anchor winding and solve again; do not increase the convergence tolerance to silence M17.
If the area is zero, supply a non-collinear third anchor before solving again.
M17 identifies an orientation precondition failure and is not a claim that the linkage dimensions are infeasible.
An infeasible length system is reported separately with the conflicting distance constraints in the trace.
A successful local solve establishes a configuration near the supplied seed and does not enumerate all assemblies.
When a mechanism can fold into multiple assemblies, store a seed configuration for each assembly of interest.
Exports contain the chosen assembly only, so two valid exports can differ while sharing the same dimensions.
The examples directory includes intentionally degenerate models that demonstrate diagnostics during training.
Do not promote one of those examples to a production template merely because its picture matches the intended linkage.
The support package should include the original model, the unit declaration, and the complete diagnostic trace.''')
add_source('mallow-release-scope', '''Mallow 2.4 release scope
This release documents diagnostic meanings and model repair steps.
No measured upper bound for solver execution time on the Finch-S microcontroller is available in the release evidence.
Desktop example timings are illustrative and do not establish a device-specific deadline.''')
add_source('mallow-performance-guess', '''Planning estimate for an untested port
The Finch-S build will probably finish each solve in under 8 ms. This number is a model inference, not a measurement.''', authority='unverified', origin='model_inference')
add_source('mallow-revoked-workaround', '''Mallow draft workaround, withdrawn
For M17, raise the convergence tolerance by a factor of ten and retry without altering the anchors.''', state='revoked')
add_case('transfer-04-solver-missing-bound', 'A Mallow model reports M17 after I entered the anchors clockwise. Explain the geometric check and repair, including why loosening tolerance is not the documented fix. Also determine whether the available release evidence establishes an 8 ms worst-case solve deadline on Finch-S; if it does not, say what is missing instead of estimating it.', 'reader', [gold('mallow-solver-notes', 'For diagnostic code M17, inspect the signed area of the first three non-collinear anchor points.\nIf that area is negative, reverse the anchor winding and solve again; do not increase the convergence tolerance to silence M17.\nIf the area is zero, supply a non-collinear third anchor before solving again.\nM17 identifies an orientation precondition failure and is not a claim that the linkage dimensions are infeasible.'), gold('mallow-release-scope', 'No measured upper bound for solver execution time on the Finch-S microcontroller is available in the release evidence.\nDesktop example timings are illustrative and do not establish a device-specific deadline.')], ['mallow-revoked-workaround'], ['Check signed area and repair the winding when negative; require a non-collinear third point if zero.', 'Do not relax tolerance to silence M17.', 'State that a measured Finch-S upper bound is missing and the 8 ms deadline is not established.'], missing=['A measured worst-case execution-time bound on Finch-S.'], distractors=['mallow-performance-guess'])

add_source('nacre-link-envelope', '''Nacre buoy relay — envelope and receiver contract
Each radio envelope has a station identifier, a boot epoch, a monotonically increasing ordinal, and a payload checksum.
The boot epoch changes on a full transmitter restart and is preserved across a radio-only reconnect.
An ordinal has meaning only within one boot epoch; comparing ordinals from different epochs loses the restart boundary.
The receiver should retain the original receive timestamp even when it later retries delivery to a consumer.
Checksums detect payload corruption and do not authenticate the identity of the station that sent a packet.
Authentication is supplied by the deployment's separate transport association.
A receiver may acknowledge an envelope before its consumer has written an application-level record.
For that reason, a radio acknowledgement is not proof that a downstream dashboard has incorporated an observation.
A missing dashboard point can reflect consumer delay, filtering, or a retained duplicate rather than a lost radio packet.
The packet journal records the admission decision and a compact reason code for rejected envelopes.
Operators can export that journal without changing the forwarding queue or its current retry schedule.
The deduplication key is the pair (station identifier, boot epoch) together with the ordinal.
Retain each accepted key for 26 hours after its first admission, even if forwarding succeeds sooner.
A repeated key with a different checksum is a conflict: quarantine both versions and emit reason Q4.
Do not select the later arrival merely because its receive timestamp is newer.
Station clocks are not assumed to agree, and receive order does not imply that a conflicting payload is correct.
An envelope that fails authentication must never populate the accepted-key store.
Memory pressure should be handled by refusing new admission, rather than silently shortening retention for existing keys.
The journal includes separate counters for duplicate keys and checksum conflicts so they can be diagnosed independently.
A high duplicate counter alone often indicates reconnect retries and does not show that payload data changed.
A high conflict counter warrants investigation of transmitter state and the source of each authenticated association.
After a receiver replacement, restore the accepted-key store before opening the forwarding path.
Restoring only the packet journal leaves the receiver unable to recognize envelopes that were already admitted.
The migration utility prints record counts and a checksum so that operators can compare the restored state with the export.''')
add_source('nacre-consumer-limit', '''Nacre consumer compatibility notice
Consumers that cannot accept a quarantine notification must receive a local audit entry instead; conflicting payloads still must not be forwarded.
A consumer timeout does not permit bypassing deduplication or reducing the 26-hour retention window.''')
add_source('nacre-trial-proposal', '''Unapproved Nacre trial proposal
Consider retaining keys for six hours and taking the latest conflicting payload to reduce memory usage. This trial has not been approved.''', authority='unverified', origin='user_assertion')
add_source('nacre-bridge-revoked', '''Retired Nacre bridge instruction
Deduplicate on station identifier alone and keep the last arrival when checksums differ.''', state='revoked')
add_source('nacre-battery-interval', '''Nacre battery-service interval
Keep replacement batteries indoors for 26 hours before a winter installation. This interval is unrelated to receiver state.''')
add_case('transfer-05-relay-integrity', 'For the Nacre buoy receiver, summarize what identifies a duplicate, how long that identity must be remembered, and what happens when the same identity arrives with different payload checksums. Our consumer cannot handle a quarantine notification. Explain the fallback without allowing either conflicting payload through; do not adopt the unapproved memory-saving trial.', 'reader', [gold('nacre-link-envelope', 'The deduplication key is the pair (station identifier, boot epoch) together with the ordinal.\nRetain each accepted key for 26 hours after its first admission, even if forwarding succeeds sooner.\nA repeated key with a different checksum is a conflict: quarantine both versions and emit reason Q4.\nDo not select the later arrival merely because its receive timestamp is newer.'), gold('nacre-consumer-limit', 'Consumers that cannot accept a quarantine notification must receive a local audit entry instead; conflicting payloads still must not be forwarded.\nA consumer timeout does not permit bypassing deduplication or reducing the 26-hour retention window.')], ['nacre-bridge-revoked'], ['Include station identifier, boot epoch, and ordinal in the identity.', 'Retain for 26 hours measured from first admission.', 'Quarantine both versions, use Q4, and use a local audit entry when notifications are unsupported.', 'Do not forward either conflict or shorten retention because of the trial.'], distractors=['nacre-trial-proposal','nacre-battery-interval'])

add_source('vesper-cure-sheet', '''Vesper porous ceramic tile — cure sheet, process C
Place tiles on the open lattice rack with a finger-width gap between adjacent pieces.
Begin the humidity ramp only after the witness coupon has reached 18 percent moisture by dry mass.
Hold chamber humidity at 72 percent for 35 minutes before the final drying stage.
The timer starts when the chamber sensor first remains within one percentage point of the target for a full minute.
A rack timer that began at loading cannot substitute for that chamber condition.''')
add_source('vesper-deviation-register', '''Vesper process deviation register
A production engineer must approve any reduction in the 35-minute humidity hold before the batch enters the chamber.
An operator may extend the hold to recover from a logged interruption, but this does not authorize a shorter hold on later batches.
The register contains no approval for a 20-minute hold on process C.''')
add_source('vesper-inspection-guidance', '''Vesper inspection guidance
Use the retained witness coupon for the dry-mass calculation; an ambient humidity reading is not a moisture measurement of the tile.
Record the coupon identifier with the batch so that the moisture result remains traceable.''')
add_source('vesper-old-cure-sheet', '''Vesper porous ceramic tile — obsolete process C sheet
Begin the ramp at 22 percent moisture and hold 72 percent humidity for 20 minutes.''', freshness='stale')
add_source('vesper-private-costing', '''Vesper experimental costing memo
A proposed 20-minute hold might reduce chamber occupancy. The proposal has no production-engineering approval.''', collection='private', authority='unverified', origin='model_inference')
add_case('transfer-06-cure-no-implicit-approval', 'Continue preparing the Vesper process C batch instructions from this explicit status: the rack is loaded, an operator has suggested a 20-minute hold, and no production engineer has approved a deviation. State the moisture prerequisite, the normal humidity target and hold, when its timer actually begins, and what approval would be needed to shorten it. Do not turn the suggestion into an approved change.', 'reader', [gold('vesper-cure-sheet', 'Begin the humidity ramp only after the witness coupon has reached 18 percent moisture by dry mass.\nHold chamber humidity at 72 percent for 35 minutes before the final drying stage.\nThe timer starts when the chamber sensor first remains within one percentage point of the target for a full minute.\nA rack timer that began at loading cannot substitute for that chamber condition.'), gold('vesper-deviation-register', 'A production engineer must approve any reduction in the 35-minute humidity hold before the batch enters the chamber.\nAn operator may extend the hold to recover from a logged interruption, but this does not authorize a shorter hold on later batches.\nThe register contains no approval for a 20-minute hold on process C.'), gold('vesper-inspection-guidance', 'Use the retained witness coupon for the dry-mass calculation; an ambient humidity reading is not a moisture measurement of the tile.')], ['vesper-old-cure-sheet','vesper-private-costing'], ['Use the witness coupon and 18 percent dry-mass moisture prerequisite.', 'Specify 72 percent humidity for 35 minutes, with the full-minute stability condition for timer start.', 'State that a production engineer must approve shortening before chamber entry, and the suggested 20 minutes is unapproved.'])

add_source('rookfold-format-migration', '''Rookfold block compressor — format 3 migration memo
Format 3 separates a block's byte length from its logical record count.
Readers must compare the stored byte length with the number of bytes actually consumed before returning records.
A matching record count alone cannot establish that the compressed block has been read completely.
The field formerly named span is now encoded_length and continues to count compressed bytes, not records.
The field formerly named units is now record_count and counts logical records after decoding.
Do not copy span into record_count merely because a block happens to contain one byte per record.
A zero-record block may still carry a nonzero encoded length because it contains a framing header.
Writers use little-endian integers for the framing header; the payload codec specifies its own internal bit order.
A reader should reject a framing header that extends past the advertised block boundary.
Keeping a partial result from such a block would make later blocks appear to begin at an arbitrary offset.
The migration utility verifies framing and reconstructs block boundaries before rewriting field names.
It does not reconstruct application records that were never written to the source file.
The utility writes an audit sidecar with the original file digest and each rejected block offset.
Retain that sidecar with the migrated file when evidence of the migration path is required.
A validation pass verifies structure, while a separate application comparison verifies the decoded record meaning.
These checks have distinct purposes and neither should be replaced by a file-size comparison.
Compression ratios can change after migration because the encoder groups records differently.
A smaller output is not itself evidence that records were discarded, nor is a larger output proof of corruption.
Streams remain individually decodable only when the original application schema is supplied to the consumer.
The format package does not infer that schema from field labels or from the first decoded record.''')
add_source('rookfold-release-a', '''Rookfold format 3 service integration notice A
For a live reader, switch to the migrated file only after a clean checkpoint.
The integration notice requires stopping the service for the file switch.
This notice is marked current and provides no measured restart-time bound.''')
add_source('rookfold-release-b', '''Rookfold format 3 service integration notice B
For a live reader, switch to the migrated file only after a clean checkpoint.
The integration notice permits the file switch without stopping the service.
This notice is marked current and does not identify notice A as superseded.''')
add_source('rookfold-private-resolution', '''Rookfold restricted deployment decision
The service-specific resolution is maintained in the private deployment dossier. Reader access to the public corpus does not include that dossier.''', collection='private')
add_source('rookfold-field-glossary-old', '''Rookfold abandoned format proposal
Rename span to record_count and units to encoded_length.''', state='revoked')
add_case('transfer-07-migration-unresolved-conflict', 'I am preparing a reader-visible Rookfold format 3 migration summary. Map span and units to their new fields and meanings, and identify the audit artifact to retain. Then assess whether the supplied current integration notices settle whether the service must stop for the file switch. Report an unresolved contradiction if neither notice supersedes the other; do not resolve it using inaccessible deployment information.', 'reader', [gold('rookfold-format-migration', 'The field formerly named span is now encoded_length and continues to count compressed bytes, not records.\nThe field formerly named units is now record_count and counts logical records after decoding.'), gold('rookfold-format-migration', 'The utility writes an audit sidecar with the original file digest and each rejected block offset.\nRetain that sidecar with the migrated file when evidence of the migration path is required.'), gold('rookfold-release-a', 'For a live reader, switch to the migrated file only after a clean checkpoint.\nThe integration notice requires stopping the service for the file switch.\nThis notice is marked current and provides no measured restart-time bound.'), gold('rookfold-release-b', 'For a live reader, switch to the migrated file only after a clean checkpoint.\nThe integration notice permits the file switch without stopping the service.\nThis notice is marked current and does not identify notice A as superseded.')], ['rookfold-private-resolution','rookfold-field-glossary-old'], ['Map span to encoded_length in compressed bytes and units to record_count in decoded records.', 'Retain the audit sidecar containing original digest and rejected block offsets.', 'Name the common clean-checkpoint prerequisite.', 'Preserve the contradiction about stopping; no public supersession or tie-break is available.'], missing=['An accessible authoritative resolution or supersession relationship for the conflicting stop requirements.'])

add_source('juniper-alignment-brief', '''Juniper beam scanner alignment brief
Use the matte ceramic target at 1.8 m for the weekly alignment check.
Accept a centroid displacement no greater than 0.6 mm from the engraved crosshair.''')
add_source('juniper-record-brief', '''Juniper alignment record rule
Save the raw centroid image and the target serial number with the weekly check.
A passing check does not authorize changing the factory gain.''')
add_source('juniper-background-handbook', '''Juniper beam scanner — background handbook for facility planners
The enclosure uses a passive ventilation path to reduce dust accumulation near the optical assembly.
The facility should reserve clearance around the enclosure so that ordinary housekeeping does not block that path.
Nearby equipment can introduce vibration through a shared mounting rail even when the floor feels stationary.
Mounting surveys should consider operating machinery, loading patterns, and the schedule of adjacent work cells.
A brief walk-through during a quiet shift may miss intermittent disturbances that occur during normal production.
The facility planner should collect observations across a representative operating cycle before finalizing the mount.
The product's shipping crate includes removable transit restraints that protect the assembly during freight handling.
Remove those restraints according to the installation checklist before connecting the scanner to the facility controller.
Packaging foam and spare fasteners must be cleared from the work area because they can obstruct ventilation.
The scanner's front window should remain accessible for routine visual inspection after nearby equipment is installed.
Do not design an access panel that forces a technician to disturb the scanner mount to inspect that window.
A service clearance diagram is available to the installer as part of the mechanical drawing package.
The optional cable tray supports routing choices but does not provide strain relief for the optical assembly connector.
Cable bending radius should follow the cable manufacturer's marking, especially near the fixed entry gland.
A label on the enclosure describes its environmental class and the acceptable facility supply connection.
Facility power interruptions should be recorded by the controller to distinguish a restart from an ordinary idle period.
The display may show a setup illustration when no inspection program is loaded into the controller.
That illustration is explanatory and is not a measured image from the installed target or the production surface.
Operators should rely on the actual inspection record when investigating a reported position change.
The planner's handbook deliberately omits weekly alignment acceptance limits and required record attachments.
Those operational details are maintained in the short alignment brief and alignment record rule.
The facility commissioning packet should include the final mounting drawing and the agreed service-access route.
A drawing revision is necessary when a neighboring machine changes the clearance or maintenance access around the scanner.
Keeping this background information current helps later teams understand why the original installation used its chosen location.''')
add_source('juniper-gain-draft', '''Juniper withdrawn gain draft
Use a polished target at 0.8 m and increase factory gain whenever the check appears weak.''', state='revoked')
add_case('transfer-08-compact-alignment', 'Give a compact weekly Juniper beam scanner checklist: target type and distance, displacement acceptance limit, and the two items to save. Include whether passing the check grants permission to change factory gain. I only need the two short operational briefs, within this small evidence budget.', 'reader', [gold('juniper-alignment-brief', 'Use the matte ceramic target at 1.8 m for the weekly alignment check.\nAccept a centroid displacement no greater than 0.6 mm from the engraved crosshair.'), gold('juniper-record-brief', 'Save the raw centroid image and the target serial number with the weekly check.\nA passing check does not authorize changing the factory gain.')], ['juniper-gain-draft'], ['Use matte ceramic at 1.8 m and displacement at most 0.6 mm.', 'Save the raw centroid image and target serial number.', 'Do not infer factory-gain change permission from a passing check.'], budget=dict(max_bytes=1100,max_tokens=300,max_items=2), distractors=['juniper-background-handbook'])

frozen_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
fixture = dict(schema_version='1.0', suite_id='kre-offline-transfer-eight-v1', fixture_status='frozen_before_any_retrieval_run', frozen_at_utc=frozen_at, synthetic=True, authoring_kind='independent_fixture_authorship_not_independent_human_semantic_review', default_destination='local_only', scope_definitions={'reader': {'collections':['public']}, 'owner': {'collections':['public','private']}}, sources=sources, cases=cases)
fixture_path = ROOT/'offline-transfer-eight.v1.json'
fixture_path.write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
notes = f'''# Offline transfer fixture authoring notes

Frozen UTC: {frozen_at}

This is independent fixture authorship, not independent human semantic review. The author received the task specification and metadata enum descriptions only. The author did not inspect the existing retrieval implementation, benchmark tasks, benchmark results, or proposed correction. No query tuning or retrieval/evaluation run was performed. No model, HTTP, network, Gateway, or Ollama calls were made for authoring or validation.

All systems, procedures, measurements, names, and documents are invented for this fixture. Facts are authoritative only inside this synthetic corpus. Eight standalone queries cover different technical domains, with paraphrased retrieval needs, multiple sources and facts, buried details, explicit continuity and approval constraints, missing evidence, conflicting current sources, freshness restrictions, revoked evidence, and public/private collection access. The two scopes are reader={{public}} and owner={{public,private}}. Every request has destination local_only and purpose current_answer. Seven cases use max_bytes=12000, max_tokens=12000, max_items=12. One intentionally compact case uses 1100 bytes, 300 tokens, and two items; its requested evidence fits in its two short sources.

Sources use normal Store metadata enum values: freshness fresh/stale/unknown, authority authoritative/unverified, origin source_evidence/user_assertion/model_inference, and state active/revoked. Collection is public or private. A harness should map source_id to the Store's corresponding identity/provenance field if that field has a different name, preserving the fixture identity in outputs. Gold line numbers are one-based and inclusive over text.splitlines(); every quote is exactly the joined source lines in that range. Gold entries identify minimal evidence passages, not a required retrieval snippet boundary. Forbidden sources are hard eligibility exclusions for that case. Distractor sources are allowed evidence that must not substitute for the required facts. Unverified material is not marked forbidden merely for having low authority; answer_requirements state how unsupported claims should be treated.

The questions, source text, gold spans, restrictions, and answer requirements were authored before any retrieval run. The authoring script computes line locations from exact unique passages; it does not invoke retrieval. Validation is data-only: schema checks, exact quote/range equality, scope/metadata checks for gold, corpus size checks, and compact-case source byte/token-bound checks. The companion SHA256 manifest commits the frozen JSON, this note, the authoring script, validator, and validation report. Do not edit these frozen artifacts in response to evaluation outcomes. Any later change must become a separately named version with its own pre-run freeze record.

Initial disclosure to the implementation agent is limited to paths, counts, freeze time, and cryptographic hashes. Cases and semantic results should be disclosed only after the root agent confirms the implementation is frozen.
'''
(ROOT/'AUTHORING_NOTES.md').write_text(notes, encoding='utf-8')
print(json.dumps({'fixture':str(fixture_path),'sources':len(sources),'cases':len(cases),'frozen_at_utc':frozen_at,'fixture_sha256':hashlib.sha256(fixture_path.read_bytes()).hexdigest()}))
