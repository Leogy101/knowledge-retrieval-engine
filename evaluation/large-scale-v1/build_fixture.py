"""Deterministic, synthetic-only authoring fixture. Never imports or evaluates KRE.

Rebuilds the exact authored collection and gold spans. No network, model, private
input, search-engine access, or retrieval implementation is used here.
"""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parent
DOCS=[]; TASKS=[]; TEXT={}; ANCHORS={}

def digest(data): return hashlib.sha256(data).hexdigest()
def write_json(name,value):
    (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def doc(id,title,paragraphs,*,scope='large',status='active',freshness='fresh',authority='authoritative',origin='source_evidence',revision='1',superseded_by=None):
    # Named anchors are author-only and never appear in source documents.
    lines=['# '+title,'','Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.','']
    anchors={}
    for item in paragraphs:
        if isinstance(item,tuple): key,value=item
        else: key,value=None,item
        start=len(lines)+1
        lines.extend(value.split('\n'))
        if key:anchors[key]=(start,len(lines))
        lines.append('')
    text='\n'.join(lines)+'\n'; raw=text.encode()
    path='documents/'+id+'.md';(ROOT/'documents').mkdir(exist_ok=True);(ROOT/path).write_bytes(raw)
    row={'id':id,'path':path,'scope':scope,'status':status,'freshness':freshness,'origin':origin,'authority':authority,
         'revision':revision,'sha256':digest(raw),'bytes':len(raw),'synthetic':True}
    if superseded_by:row['superseded_by']=superseded_by
    DOCS.append(row);TEXT[id]=text;ANCHORS[id]=anchors

def evidence(id,anchor):
    start,end=ANCHORS[id][anchor];text=TEXT[id]
    return {'source_id':id,'source_sha256':digest(text.encode()),'line_start':start,'line_end':end,
            'quote':'\n'.join(text.splitlines()[start-1:end])}

def task(id,category,scope,question,facts,spans,*,status='answered',forbidden=(),constraints=(),checkpoint=None):
    row={'id':id,'category':category,'scope':scope,'question':question,'expected_status':status,
         'reference_answer':' '.join(facts),'required_facts':[{'id':f'{id}-f{i+1}','text':t} for i,t in enumerate(facts)],
         'required_evidence':[evidence(*span) for span in spans],'forbidden_claims':list(forbidden),
         'constraints':['Use only eligible records in the declared collection. Do not invent missing operational values.',*constraints],
         'evidence_policy':{'purpose':'current_answer','freshness_requirement':'allow_unknown'},
         'authoring_notes':'Authored before KRE evaluation; gold and reference answers must never enter inference prompts.'}
    if checkpoint:row['checkpoint']=checkpoint
    TASKS.append(row)

# Compact scope: all twelve documents fit a deliberately generous complete-document baseline.
doc('harbor-release','Harbor deployment authorization',[
 ('gate','Harbor release R7 may open public traffic only after the replay ledger is reconciled and the duty steward signs the release card.'),
 ('window','The planned maintenance window is Tuesday 02:00–02:20 UTC. A missed window requires a new release card; operators may not extend it themselves.'),
 'This procedure governs the training service and takes precedence over informal chat notes.'
],scope='compact',revision='7')
doc('harbor-backup','Harbor snapshot and rollback',[
 ('backup','Before deployment, the operator records the immutable snapshot identifier and its SHA-256 checksum in the release card.'),
 ('rollback','After rollback, reconcile the order ledger against the snapshot and probe /ready twice, thirty seconds apart. Any mismatch keeps traffic closed.'),
 'Snapshot creation alone is not evidence that a restore has been tested.'
],scope='compact')
doc('harbor-access','Harbor temporary access policy',[
 ('access','A rehearsal operator receives the release-reader role for two hours. The role permits reading release cards and audit events; it cannot publish or delete them.'),
 ('approval','Only the duty steward can authorize public traffic. A release-reader token cannot substitute for that authorization.'),
 'Revoking temporary access prevents later reads but does not erase copies already exported.'
],scope='compact')
doc('harbor-retention','Harbor signed audit retention decision',[
 ('retention','Decision H-12, ratified by the records custodian, retains audit events for ninety days. This rule applies to successful and rejected requests.'),
 ('precedence','H-12 remains controlling until a later ratified custodian decision explicitly replaces it. A newer planning note is not an approved policy change.'),
 'The records custodian, not the deployment operator, approves exceptional deletion.'
],scope='compact',revision='12')
doc('harbor-cost-note','Harbor storage-cost planning note',[
 ('proposal','A later-dated engineering cost note proposes reducing audit retention to fourteen days. It is an unapproved estimate and has no records-custodian signature.'),
 'The note estimates object-storage expense; it does not grant deletion authority.'
],scope='compact',authority='unverified')
doc('harbor-procedure-old','Harbor retired release procedure',[
 ('old','Release R6 instructed operators to reopen traffic after one /ready response. It did not require order-ledger reconciliation.'),
 'This revision has been superseded by the R7 release and rollback documents. It is retained only as a historical source.'
],scope='compact',status='superseded',superseded_by='harbor-release',revision='6')
doc('harbor-client','Harbor HTTP client contract',[
 ('json','```json\n{"timeout_ms": 2500, "retry": {"attempts": 0}, "headers": {"X-Training": "true"}}\n```'),
 ('rules','timeout_ms is an integer in milliseconds. retry.attempts counts additional attempts, not the initial request. X-Training is the literal string "true", not a JSON boolean.'),
 'The example contains no authentication credential. A caller must not add an undocumented retry.'
],scope='compact')
doc('harbor-checkpoint','Harbor continuation card format',[
 ('card','A continuation card must retain objective, constraints, decisions, unresolved questions, next action, and evidence references. Source-derived assertions depend on those exact references.'),
 ('resume','On resume, remove an assertion when its supporting reference is revoked or superseded. Preserve unrelated user constraints and mark the affected decision unresolved; do not silently substitute a different decision.'),
 'A resume is a reference validation step, not permission to carry out deployment.'
],scope='compact')
doc('harbor-retired-waiver','Harbor withdrawn window waiver',[
 ('waiver','Waiver W4 previously allowed extending the maintenance window by ten minutes.'),
 'The duty steward withdrew W4. The extension must not be restored by a continuation card.'
],scope='compact',status='revoked')
doc('harbor-slo','Harbor reliability indicators',[
 ('slo','The training availability objective is 99.5% over a rolling twenty-eight-day interval. Planned maintenance is included in that denominator.'),
 'This objective is a reporting target, not authorization to bypass the release gate.',
 'A request counted twice by the collector must be deduplicated by its observation identifier before computing availability.'
],scope='compact')
doc('harbor-environment','Harbor rehearsal environment',[
 'Rehearsals use generated order identifiers, a disposable ledger and a local simulator. They do not contact payment networks.',
 'A clean rehearsal does not prove production readiness. Production endpoint addresses and credentials are intentionally absent from this collection.',
 'The sample data resets after each rehearsal; audit records follow the signed retention policy.'
],scope='compact')
doc('harbor-glossary','Harbor glossary and ownership',[
 'A replay ledger is the ordered list of accepted training events, including duplicate observations. Reconciliation checks both count and immutable identifiers.',
 'The duty steward owns release approval. The records custodian owns audit retention. The reliability lead owns SLO calculations.',
 'A release card is an approval record. A continuation card records unfinished work; it is not itself an approval.'
],scope='compact')

# Large scope: substantive cross-functional documents and intentionally plausible distractors.
doc('meridian-admission','Meridian envelope admission contract',[
 ('limits','A relay admits an envelope only when the compressed payload is at most 256 KiB and the declared schema is telemetry.v3. The limit applies before decompression.'),
 ('duplicates','The idempotency key is the pair (station_id, event_id). A duplicate with identical bytes returns the original receipt; a duplicate with different bytes is quarantined.'),
 ('ack','An HTTP 202 receipt means the envelope is durably queued, not that the observation has been published.'),
 'The mobile uploader and the station relay share this contract. A browser refresh must not mint a replacement event identifier.'
])
doc('meridian-publication','Meridian observation publication policy',[
 ('publish','A queued observation becomes publishable only after calibration provenance and station consent both validate. Publication is asynchronous and can lag admission.'),
 ('hold','If either calibration provenance or consent is unresolved, retain the observation in the review queue. Queue acceptance does not waive either requirement.'),
 'Reviewers inspect the immutable receipt identifier when tracing an observation from upload to public release.'
])
doc('meridian-receipt','Meridian operator receipt handbook',[
 ('poll','Operators check /receipts/{receipt_id} for the publication state. The accepted, review_pending, published and rejected states are distinct.'),
 ('ticket','A support ticket for a stalled receipt includes receipt_id, station_id and the last observed state. It must not include a private raw sensor attachment.'),
 'The public observation listing is not a reliable admission receipt: unpublished items do not appear there.'
])
doc('meridian-rotation','Meridian key rotation runbook',[
 ('rotate','Before rotating a station signing key, register its new public key with the registry steward and retain the old verifier for forty-eight hours.'),
 ('cutover','The station switches signing only after the registry returns the new key fingerprint. No shared secret is copied into the rotation ticket.'),
 'The overlap is measured from registry acknowledgement, not from when the operator drafted the ticket.'
])
doc('meridian-offline','Meridian disconnected station policy',[
 ('offline','A station may buffer observations locally for seventy-two hours. When it reconnects, it preserves the original event time and uploads in event_id order within each station.'),
 ('expiry','Buffered observations older than seventy-two hours require curator review; the uploader must not relabel them as newly observed.'),
 'Offline buffering does not extend signing-key overlap or consent validity.'
])
doc('meridian-rotation-recovery','Meridian interrupted rotation recovery',[
 ('recovery','If power fails after registry acknowledgement but before the station switches signing, compare the station fingerprint with the registry, resume the switch once, and preserve the original forty-eight-hour overlap deadline.'),
 ('hold','If the fingerprints cannot be reconciled, stop uploads and ask the registry steward to resolve the mismatch. Do not restart the overlap clock.'),
 'This procedure repairs an interrupted planned rotation; it does not authorize rotation after a suspected key compromise.'
])
doc('meridian-export','Meridian research export gate',[
 ('export','A research export requires a recorded purpose code, an active project consent grant and a curator-approved column manifest.'),
 ('region','Regional coordinates are rounded to the approved grid before export. A request for exact locations is not satisfied by removing the grid label.'),
 'The exporter creates an immutable manifest and checksum even for an empty result.'
])
doc('meridian-export-retention','Meridian export expiration policy',[
 ('expiry','Research export bundles expire after seven days. At expiry the download link is disabled; the audit manifest remains for one hundred eighty days.'),
 ('copy','Disabling an export link does not erase copies that a recipient already downloaded. Recall notices name the immutable bundle identifier.'),
 'Audit retention and bundle availability are intentionally different lifetimes.'
])
doc('meridian-export-transport','Meridian export delivery contract',[
 ('transport','Approved research bundles are delivered by the authenticated project portal. Email carries only the receipt identifier, never a bundle attachment or a bearer download link.'),
 ('ack','A recipient acknowledgement records the bundle checksum and the project account. An email-delivery receipt does not establish bundle acceptance.'),
 'The training portal uses synthetic identities. No actual endpoint, token or address is included in this fixture.'
])
doc('meridian-sampling-decision','Meridian ratified sampling decision',[
 ('sampling','Decision M-27 sets the coastal station sampling interval to sixty seconds during ordinary operation. Only a signed incident directive may shorten it to ten seconds.'),
 ('authority','M-27 is the ratified field-governance decision. The experimental dashboard and unsigned field notes cannot change station duty cycles.'),
 'The incident directive identifies its incident, affected stations and expiry; a graph showing a higher rate is not a directive.'
],revision='27')
doc('meridian-dashboard-note','Meridian experimental dashboard memo',[
 ('claim','The newer dashboard memo describes a ten-second coastal sampling interval as the desired default. It is unsigned experimental guidance, pending field-governance review.'),
 'Its author measured smoother curves in a simulator, not energy use on deployed stations.'
],authority='unverified')
doc('meridian-uplink-decision','Meridian ratified uplink decision',[
 ('uplink','Ratified decision M-31 requires satellite uplink batches of at most twelve envelopes. An operator may split a batch; the operator may not raise the maximum.'),
 ('authority','Only a replacement ratified M-series decision can alter the twelve-envelope satellite maximum. Vendor capability sheets describe hardware potential, not an approved fleet configuration.'),
 'The terrestrial gateway has a different limit; a terrestrial example does not amend satellite policy.'
],revision='31')
doc('meridian-vendor-uplink','Meridian vendor evaluation excerpt',[
 ('claim','A newer vendor evaluation says the modem can carry thirty envelopes in one satellite burst under ideal laboratory conditions. The evaluation is informational and has not been ratified as fleet policy.'),
 'The laboratory used synthetic sensor payloads, stable power and a clear antenna view.'
],authority='unverified')
doc('meridian-rollout-current','Meridian relay rollout revision 5',[
 ('current','Revision 5 requires a shadow-ingest comparison for thirty minutes, then checksum reconciliation, then curator approval before public traffic is enabled.'),
 ('rollback','A mismatch during shadow ingest requires rollback to the last approved build. Save the mismatch receipt identifiers; do not discard them to make the comparison pass.'),
 ('replace','Revision 5 explicitly replaces revision 4. The version number alone is not the authority: the signed release decision adopts this sequence.'),
 'Operators must preserve the observation identifiers while comparing builds.'
],revision='5')
doc('meridian-rollout-old','Meridian relay rollout revision 4',[
 ('old','Revision 4 enabled public traffic after a five-minute heartbeat check. It did not require shadow ingest or curator approval.'),
 'This historical revision is superseded by revision 5.'
],status='superseded',revision='4',superseded_by='meridian-rollout-current')
doc('meridian-retention-current','Meridian observation retention revision 3',[
 ('current','Current revision 3 retains raw training observations for thirty days and derived public summaries for three hundred sixty-five days.'),
 ('delete','A raw-observation deletion does not authorize deleting its public summary. The summary follows its own retention clock.'),
 ('replace','Ratified records decision R-8 replaces revision 2 with revision 3. Timestamps on exported copies do not change the controlling revision.')
],revision='3')
doc('meridian-retention-old','Meridian observation retention revision 2',[
 ('old','Revision 2 retained both raw training observations and derived public summaries for ninety days.'),
 'Historical only: ratified R-8 superseded this revision.'
],status='superseded',revision='2',superseded_by='meridian-retention-current')
doc('meridian-batch-config','Meridian batch-client configuration',[
 ('config','```json\n{"batch": {"max_envelopes": 12, "flush_ms": 750}, "retry": {"additional_attempts": 0}, "ordering": "station_then_event"}\n```'),
 ('rules','flush_ms is an integer number of milliseconds. additional_attempts excludes the first transmission. station_then_event orders first by station_id and then by event_id; it does not reorder by arrival time.'),
 'This configuration is the satellite training-client example. Invalid configuration is rejected rather than silently clamped.'
])
doc('meridian-config-validation','Meridian configuration validation rules',[
 ('validate','Reject a batch configuration if max_envelopes is outside 1 through 12 inclusive, flush_ms is not a positive integer, or additional_attempts is not zero for this benchmark profile.'),
 ('atomic','Validation is atomic: an invalid configuration leaves the prior effective configuration unchanged. A validation error is not a partially applied update.'),
 'All keys in the documented example are required. Unknown keys are rejected.'
])
doc('meridian-parser-code','Meridian frame parser contract',[
 ('code','```python\ndef decode_frame(blob):\n    if len(blob) < 6:\n        raise ValueError("short frame")\n    payload_len = int.from_bytes(blob[2:4], "big")\n    if len(blob) != payload_len + 6:\n        raise ValueError("length mismatch")\n    return blob[4:4 + payload_len]\n```'),
 ('layout','A frame contains a two-byte marker, a two-byte unsigned big-endian payload length, the payload and a two-byte checksum. The shown function checks length only; it does not verify the marker or checksum.'),
 'This excerpt is documentation. Benchmark respondents must explain it without executing generated or supplied code.'
])
doc('meridian-parser-tests','Meridian frame parser examples',[
 ('example','The byte sequence 4d 46 00 03 61 62 63 00 00 has total length nine and declares a three-byte payload. decode_frame returns the bytes 61 62 63 for this example.'),
 ('negative','Removing the final byte leaves total length eight while the declared payload remains three; the function raises "length mismatch".'),
 'A successful length check is not a statement that the checksum is correct.'
])
doc('meridian-continuity','Meridian operator continuation rules',[
 ('card','Checkpoint fields are objective, constraints, decisions, unresolved questions, next actions and exact evidence references. A quoted-source decision depends on every reference attached to that decision.'),
 ('revalidate','Resume validates references against the current corpus. Revoke or supersede one dependency and suppress the dependent source-derived decision, while retaining unrelated user constraints and marking the decision unresolved.'),
 ('noexecute','Resuming a checkpoint does not authorize deployment, data export or a permission change. A proposed next action remains a proposal until separately approved.'),
 'The source and lifecycle snapshot used for resume must be recorded separately from the older checkpoint snapshot.'
])
doc('meridian-waiver-revoked','Meridian withdrawn export waiver',[
 ('waiver','Waiver E-9 previously allowed one research bundle to be emailed as an attachment.'),
 'E-9 is revoked. The active export transport contract requires portal delivery.'
],status='revoked')
doc('meridian-checkpoint-release','Meridian engineering handoff constraints',[
 ('constraints','For the paused relay review, preserve these user constraints: no deployment, no credential access, no network call and no configuration write. The selected release candidate is build cedar-17.'),
 ('next','The pending action is to verify the current shadow-ingest sequence and identify the approving role. Record the answer; do not perform the rollout.'),
 'The build label is an operator decision, not a measurement of quality or an authorization.'
])
doc('meridian-latency-stale','Meridian historical latency notebook',[
 ('latency','The April training exercise observed a p95 admission latency of 84 milliseconds across 240 synthetic uploads. These observations describe that exercise only.'),
 ('unknown','No current production latency sample or production measurement window is recorded in this notebook. Do not relabel the April observations as a current service guarantee.'),
 'The exercise used an unloaded relay and did not include satellite transport.'
],freshness='stale',authority='unverified')
doc('meridian-cost-boundary','Meridian financial evidence boundary',[
 ('unknown','This collection contains no contracted satellite price, invoice, current currency conversion rate or monetary price per envelope. Hardware counts cannot establish a monthly communications bill.'),
 ('volume','A cost estimate requires a separately supplied price schedule and measured transmission volume; neither is present here.')
])
doc('meridian-secrets-boundary','Meridian credential documentation boundary',[
 ('unknown','Production signing secrets, bearer tokens and recovery codes are intentionally absent. Examples contain public identifiers and synthetic placeholders only.'),
 'A document mentioning the registry does not disclose credentials for it. An operator must not guess a credential value.'
])
doc('meridian-derived-summary','Meridian machine-produced capacity summary',[
 ('derived','An unreviewed machine-produced summary claims that queue admission guarantees immediate publication. This is a derived assertion, not source evidence, and has not been reconciled with the admission and publication contracts.'),
 'Its wording is retained to test whether an answer distinguishes a derived assertion from controlling source evidence.'
],authority='unverified',origin='model_inference',freshness='unknown')

# Long manuals contain diverse operational sections, with important details far from the beginning.
MANUAL_TOPICS={
 'sensor': ['Optical path cleaning','Calibration plate storage','Dark-current capture','Sample clock alignment','Battery temperature guard','Rain shield inspection','Tilt correction audit','Enclosure seal log','Cable strain relief','Reference gas handling','Survey coordinate checks','Bench fixture inventory','Firmware signature review','Mechanical mounting tolerance','Transit shock indicator','Ventilation channel clearing','Humidity offset review','Lightning inspection record','Field notebook export','Spare module custody','Optical reference drift','Maintenance signoff'],
 'queue': ['Receipt durability','Index rebuild scheduling','Backpressure indicators','Dead-letter review','Queue segment checksums','Journal rollover','Admission load shedding','Station fairness','Delivery watermark','Checkpoint snapshots','Consumer lease fencing','Duplicate quarantine','Receipt query caching','Segment compaction','Operator observation windows','Disk reserve alarms','Repair journal custody','Archive transfer','Drain mode behavior','Publication acknowledgements','Replay verification','Recovery signoff'],
 'archive': ['Manifest identity','Bundle naming','Digest algorithm','Compression inventory','Column manifest audit','Export scheduling','Retention registry','Object copy checks','Offline media labels','Archive catalog rebuild','Clock-source review','Partial-transfer recovery','Recipient acknowledgements','Download expiry','Recall notice fields','Storage class migration','Corrupt-object quarantine','Audit manifest retention','Inventory reconciliation','Evidence custody','Restore rehearsal','Deletion approval'],
 'network': ['Radio channel inventory','Antenna orientation','Uplink signal review','Packet framing','Clock discipline','Satellite batch sizing','Link outage notes','Transmit power audit','Station registration','Relay endpoint selection','Local address leases','Firmware transport compatibility','Duplicate receipt handling','Path diagnostics','Interface isolation','Reconnection ordering','Acknowledgement loss','Roaming restrictions','Routing table review','Operator handoff','Incident escalation','Maintenance window closure'],
 'calibration': ['Reference certificate custody','Zero-point adjustment','Span-reference preparation','Ambient pressure recording','Reference expiry review','Calibration identifier format','Station assignment','Measurement uncertainty','Traceability chain','Replicate measurement logs','Operator qualification','Fixture cleaning','Comparison sample retention','Outlier review','Coefficient versioning','Approval record format','Recalibration scheduling','Certificate replacement','Historical certificate review','Station consent interaction','Publication gates','Audit closure'],
 'recovery': ['Incident identifier','Initial evidence capture','Traffic isolation','Snapshot selection','Restoration prerequisites','Read-only diagnosis','Replica comparison','Journal integrity','Replay ordering','Owner assignment','Checkpoint verification','Partial restore behavior','Permission review','Public traffic reopening','Post-incident retention','Operator communication','Evidence redaction','Backup custody','Restore drill scheduling','Roll-forward restrictions','Failure escalation','Incident closure']
}
DETAILS=[
 'The operator records the observation identifier, instrument revision and the reason for the check. A copied entry remains attributable to the original observation; rewriting its timestamp does not make it new evidence.',
 'Compare the physical label with the inventory record before continuing. If the two disagree, leave the item isolated and ask the responsible steward to resolve ownership. A successful self-test does not resolve a custody discrepancy.',
 'Record the start and end of the observation window, including gaps. Report an unavailable reading as unavailable rather than as zero. The acceptance record names the actual measurement method and its limits.',
 'The maintenance ledger preserves the prior entry and appends a correction with its rationale. It never overwrites the original evidence. A later correction is not automatically more authoritative without the required approval.',
 'Use the documented reference fixture and note its revision. Substituting a convenient spare can alter the result, so a substitution requires a separately reviewed comparison before it is accepted as equivalent.',
 'A simulator exercise uses generated station identifiers and cannot establish field reliability. The exercise receipt must say which components were simulated and which components were observed directly.',
 'When an operation stops midway, retain the last completed checkpoint and mark the unfinished step. Do not infer completion from the absence of an alarm. The next operator revalidates the checkpoint before resuming.',
 'The checklist is evidence of what was checked, not authority to bypass another gate. Record a blocked dependency explicitly and keep the dependent action pending until the responsible owner supplies a valid decision.',
 'A diagram is explanatory material. It does not replace the signed parameter record or the current interface contract. Differences between the diagram and the contract should be reported without silently changing either source.',
 'Keep ordinary operational notes separate from source-derived assertions. A conclusion should cite the observation that supports it; uncertainty should remain visible when the observation is incomplete or stale.'
]
for n,(kind,topics) in enumerate(MANUAL_TOPICS.items()):
    paragraphs=['This long manual covers the fictional Meridian training fleet. Sections are independent operational records; headings do not imply that nearby sections share the same approval authority.']
    for i,title in enumerate(topics):
        paragraphs.append('## '+str(i+1)+'. '+title)
        paragraphs.append(f'The {title.lower()} procedure applies to the {kind} subsystem during a scheduled training maintenance window. Its checklist is recorded under the subsystem revision and the training station identifier; it must not be copied into a production approval record.')
        paragraphs.append(DETAILS[(i+n)%len(DETAILS)])
        paragraphs.append(DETAILS[(i*3+n+2)%len(DETAILS)])
        paragraphs.append(f'Worked example for {title.lower()}: a training operator starts with an incomplete custody entry and an apparently healthy subsystem indicator. The indicator is retained as an observation, but the missing custody entry remains unresolved. The operator records which evidence is missing and pauses the dependent action. A later shift must not copy the healthy indicator into the approval field or claim that the custody problem was repaired by waiting.')
        paragraphs.append(f'Before repeating the {title.lower()} check, identify the previous attempt by its immutable observation reference. State whether the new attempt changes the fixture, operator, software revision, or environment. Preserve both attempts even when the second result is easier to interpret. If only one field changes, describe that field rather than calling the entire attempt equivalent. This trace makes a comparison reviewable without requiring the reader to reconstruct an undocumented history.')
        paragraphs.append(f'For {kind} evidence, the review packet contains the original observation, the declared method, the operating conditions, and any known missing interval. The reviewer distinguishes a directly observed result from an interpretation written later. An interpretation may be useful, but it cannot silently become the source observation. If an automated export omits the original units or reference identifier, treat that export as incomplete and request the intact record before relying on it.')
        paragraphs.append(f'The handoff for {title.lower()} states the completed step, its supporting reference, the unresolved dependency and the next proposed action. A proposal is not an execution receipt. The receiving operator checks that the reference is still available and eligible before resuming. When the source was withdrawn, keep the user objective but suppress the withdrawn source-derived conclusion. Do not invent a replacement conclusion solely to make the handoff look complete.')
        paragraphs.append(f'A closure note for the {kind} subsystem records who owns the remaining uncertainty and which event would resolve it. A calendar reminder, green display or quiet alarm panel does not resolve missing evidence. The training environment may be reset after the note is preserved, but the reset does not retrospectively change the outcome of the attempt. Use the retained receipt when comparing this exercise with a later one, and identify that comparison as a new review.')
        if kind=='sensor' and i==17:
            paragraphs.append(('buried','After a lightning alarm, isolate the sensor head for forty-five minutes and inspect the surge cartridge before reconnecting it. A clear heartbeat alone is insufficient to reconnect.'))
        if kind=='queue' and i==18:
            paragraphs.append(('buried','During a queue drain, admission returns HTTP 429 with Retry-After: 90. Already accepted receipts remain queryable, and draining does not revoke their durable-queue status.'))
        if kind=='archive' and i==17:
            paragraphs.append(('buried','A recalled export keeps its audit manifest for one hundred eighty days even after its download link is disabled. A recall cannot erase a recipient’s previously downloaded copy.'))
    doc('meridian-manual-'+kind,'Meridian '+kind+' technical operations manual',paragraphs)

# Additional active and lifecycle distractors: real domain concepts, no hidden gold-only filtering.
DISTRACTORS=[
 ('training-labels','Training identifier conventions','Training station identifiers start with TRN-. Production station naming is not documented here. An identifier prefix establishes labeling only; it does not authenticate a station.','A label may be copied into a support ticket, but raw private attachments require separate review.'),
 ('battery','Battery handling handbook','A training battery is removed from service when its case swells or its isolation test fails. A displayed charge percentage is not a safety acceptance test.','Inventory records track module serials and custody; the training fixture uses fictional serial numbers.'),
 ('field-weather','Weather observation notes','The observer records precipitation and wind during a sensor inspection. Weather notes explain operating conditions but do not amend calibration validity.','Missing weather data is recorded explicitly; an empty field is not a report of calm weather.'),
 ('support','Support triage guide','Support triage groups incidents by receipt identifier and station identifier. The triage queue is distinct from the observation review queue.','Closing a support ticket does not change publication state or delete audit evidence.'),
 ('inventory','Spare inventory ledger guide','A spare part reservation lasts until the scheduled training window closes. Reserving a part does not certify compatibility with the installed revision.','The maintainer confirms compatibility using the current interface record before fitting a part.'),
 ('dashboard-colors','Dashboard color accessibility','Amber indicates an unresolved observation; red indicates a rejected observation. Color is accompanied by text so the state remains readable without color perception.','A dashboard color is a presentation choice, not an alternative state-machine value.'),
 ('schema-history','Telemetry schema migration notes','telemetry.v2 used a single timestamp field. telemetry.v3 distinguishes event time from admission time. A migration preserves both when the original event time is known.','Do not manufacture an event time from a later import timestamp.'),
 ('telemetry-example','Telemetry payload example','The synthetic example contains station_id, event_id, event_time and measurements. Each measurement names a unit and calibration reference.','Example values are not field observations and must not enter a public research export.'),
 ('audit-search','Audit search syntax','Audit searches accept an exact receipt identifier or a bounded event-time interval. Search results retain original event identifiers and source revisions.','A search match is not an authorization to read attachments outside the operator’s scope.'),
 ('consent-training','Consent training guide','Consent records describe the project, purpose and effective period. A training scenario uses a synthetic grant and must be labeled as an exercise.','An exercise grant cannot authorize a production export.'),
 ('calibration-review','Calibration review meeting notes','The review meeting records unresolved coefficient questions and assigns owners. Meeting attendance is not equivalent to calibration approval.','A reviewer links a decision to the reference certificate and the measurement record.'),
 ('time-zones','Time display guide','Receipts store UTC instants while dashboards may display a local offset. Sorting uses the stored instant, not a formatted wall-clock string.','A daylight-saving transition does not justify dropping an observation with an apparently repeated local time.'),
 ('checksum-guide','Checksum display conventions','Checksums are displayed in lowercase hexadecimal with the algorithm named separately. A shortened display must be labeled as a prefix.','Only a full digest comparison establishes equality under the documented verification procedure.'),
 ('mobile-ui','Mobile uploader interface','The upload screen keeps a pending receipt visible until a terminal state is observed. Closing the screen does not cancel a durably admitted envelope.','The interface shows the most recent server state and the time it was obtained.'),
 ('repair-labels','Repair label workflow','A repaired module receives a new inspection entry linked to its prior custody record. The repair label does not erase the original defect report.','A repair ticket identifies performed work and remaining verification steps.'),
 ('data-dictionary','Measurement data dictionary','temperature_c uses degrees Celsius; pressure_pa uses pascals. The observation schema rejects an unknown unit rather than assuming a familiar one.','A unit conversion creates a derived value and preserves the original measurement and conversion rule.'),
 ('coastal-exercise','Coastal exercise briefing','The coastal exercise checks training stations without publishing their synthetic readings. It uses ordinary operating parameters unless a signed exercise directive says otherwise.','The exercise coordinator cannot issue a fleet-governance decision.'),
 ('queue-glossary','Queue terminology reference','Admission is receipt of a durably queued envelope. Delivery is transfer to a downstream consumer. Publication makes an approved observation available to research readers.','These words identify different transitions; a receipt may have completed one transition while another remains pending.'),
 ('archive-labels','Archive shelf-label handbook','Offline training media labels contain the bundle identifier, manifest digest and custody entry. Labels contain no bearer credential.','Moving a cartridge changes custody location, not the logical retention policy.'),
 ('simulator-timing','Simulator timing caveat','The simulator can advance event time independently of wall time. Timing results must state which clock was measured.','Simulator acceleration is not evidence of equivalent real-device throughput.'),
 ('revoked-bypass','Withdrawn publication bypass','An old experiment permitted publication while consent checks were unavailable. The experiment has been withdrawn and is not current authority.','This record is revoked; no continuation card may restore its bypass.'),
 ('stale-capacity','Historical capacity observation','A past training exercise processed eighty envelopes per minute on a quiet laptop. This describes one historical setup, not the current fleet.','No current capacity guarantee or production hardware measurement is provided.'),
 ('deprecation','Interface deprecation notice','A deprecated training interface remains readable during its announced transition interval. Deprecation does not grant permission to bypass its access restrictions.','Migration notes identify the replacement interface and the fields that change meaning; they do not promise equivalent operational behavior.'),
 ('event-clocks','Event clock reconciliation','Station event time, relay admission time and publication time are separate instants. A gap between them can describe buffering, review or delivery delay.','A reconciliation preserves each observed timestamp and records unknown clock offset rather than subtracting an invented correction.'),
 ('support-export','Support evidence export','A support evidence packet includes approved receipts and a manifest of their immutable identifiers. Private attachments require explicit review before inclusion.','Exporting a packet does not change the lifecycle of its source records; later revocation prevents future retrieval but cannot recall already exported text.'),
 ('derived-rotation','Unreviewed rotation summary','An automated summary says power failure restarts the signing-key overlap clock. That statement is an unverified derived assertion, not the interrupted-rotation runbook.','The source runbook, rather than this summary, governs recovery.')
]
for i,(id,title,a,b) in enumerate(DISTRACTORS):
    paragraphs=[a,b]
    for j in range(3): paragraphs.append(DETAILS[(i+j*3)%len(DETAILS)])
    kwargs={}
    if id=='revoked-bypass':kwargs={'status':'revoked'}
    elif id=='stale-capacity':kwargs={'freshness':'stale','authority':'unverified'}
    elif id=='derived-rotation':kwargs={'origin':'model_inference','authority':'unverified','freshness':'unknown'}
    doc('meridian-'+id,'Meridian '+title,paragraphs,**kwargs)

# 24 questions, frozen independently of retrieval behavior.
task('LS01','multi_document','compact','The Harbor rehearsal is ready to ship. What must be recorded before deployment, what must be checked after a rollback, and who may reopen public traffic?',[
 'Record the immutable snapshot identifier and SHA-256 checksum before deployment.',
 'After rollback reconcile the order ledger and probe /ready twice thirty seconds apart; any mismatch keeps traffic closed.',
 'The duty steward authorizes reopening public traffic.'
],[('harbor-backup','backup'),('harbor-backup','rollback'),('harbor-access','approval')])
task('LS02','multi_document','large','A Meridian uploader received 202, but the observation is absent from the public listing. Explain what has and has not been established, what gates remain, and where the operator should look next.',[
 'HTTP 202 establishes durable queue admission, not publication.',
 'Publication requires validated calibration provenance and station consent; unresolved checks keep the observation in review.',
 'Check /receipts/{receipt_id} for the distinct publication state.'
],[('meridian-admission','ack'),('meridian-publication','publish'),('meridian-publication','hold'),('meridian-receipt','poll')],forbidden=['A 202 receipt proves that the observation is public.'])
task('LS03','multi_document','large','A disconnected station loses power after the registry acknowledges a key change but before signing switches. Describe how to resume safely, whether the overlap clock resets, and how older buffered observations should be treated.',[
 'Compare station and registry fingerprints, resume the signing switch once, and preserve the original forty-eight-hour overlap deadline.',
 'Unreconciled fingerprints require stopping uploads and registry-steward resolution; the clock does not restart.',
 'Preserve buffered event times; observations older than seventy-two hours require curator review.'
],[('meridian-rotation-recovery','recovery'),('meridian-rotation-recovery','hold'),('meridian-offline','expiry'),('meridian-offline','offline')],forbidden=['Power failure restarts the overlap clock.'])
task('LS04','three_passages','compact','Prepare the Harbor rehearsal handoff: identify the window and overrun rule, the temporary role and lifetime, and the availability reporting denominator.',[
 'The window is Tuesday 02:00–02:20 UTC; missing it requires a new release card rather than an operator extension.',
 'The rehearsal role is release-reader for two hours and cannot publish or delete release cards or audit events.',
 'Availability is 99.5% over twenty-eight days, including planned maintenance.'
],[('harbor-release','window'),('harbor-access','access'),('harbor-slo','slo')])
task('LS05','three_passages','large','A researcher asks for a Meridian bundle by email and assumes that removing the link deletes all evidence. State the export prerequisites, permitted delivery channel, bundle lifetime, audit lifetime and recall limitation.',[
 'Require a purpose code, active project consent and curator-approved column manifest.',
 'Deliver through the authenticated project portal; email carries only the receipt identifier.',
 'The bundle link expires after seven days; audit manifests remain one hundred eighty days.',
 'Disabling a link cannot erase copies already downloaded.'
],[('meridian-export','export'),('meridian-export-transport','transport'),('meridian-export-retention','expiry'),('meridian-export-retention','copy')])
task('LS06','three_passages','large','An operator sees an accepted receipt during a queue drain. Combine the admission contract, drain manual and publication policy to explain the status, the response to new work and the remaining release conditions.',[
 'The accepted receipt remains durably queued and queryable during draining.',
 'New admission returns HTTP 429 with Retry-After: 90 during a queue drain.',
 'Acceptance does not mean publication; calibration provenance and consent still must validate.'
],[('meridian-admission','ack'),('meridian-manual-queue','buried'),('meridian-publication','publish')])
task('LS07','conflict','compact','Two Harbor records disagree about keeping audit events: a later note says fourteen days and a signed decision says ninety. What retention should the operator apply, and why does the later timestamp not decide?',[
 'Apply ninety-day retention to both successful and rejected requests under ratified H-12.',
 'The fourteen-day proposal is unapproved and unsigned.',
 'Only a later ratified custodian decision explicitly replacing H-12 changes the controlling rule.'
],[('harbor-retention','retention'),('harbor-retention','precedence'),('harbor-cost-note','proposal')])
task('LS08','conflict','large','A new dashboard memo calls for coastal measurements every ten seconds, while the field decision says sixty. What is the ordinary interval, when can it be shortened, and which record controls?',[
 'Ordinary coastal sampling remains sixty seconds under ratified M-27.',
 'A signed incident directive may shorten the interval to ten seconds.',
 'The newer unsigned dashboard memo is experimental and cannot amend fleet duty cycles.'
],[('meridian-sampling-decision','sampling'),('meridian-sampling-decision','authority'),('meridian-dashboard-note','claim')])
task('LS09','conflict','large','The modem vendor advertises thirty envelopes per satellite burst, but the approved fleet decision mentions twelve envelopes. Can an operator raise the batch size on that basis? Explain the authority and the safe action.',[
 'The approved satellite maximum is twelve envelopes.',
 'The operator may split a batch but cannot raise the maximum.',
 'The thirty-envelope vendor lab capability is informational; only a replacement ratified M-series decision changes fleet policy.'
],[('meridian-uplink-decision','uplink'),('meridian-uplink-decision','authority'),('meridian-vendor-uplink','claim')])
task('LS10','superseded','compact','A copied Harbor R6 checklist says one successful readiness probe is enough to reopen traffic. Give the current rollback checks and release authorization; do not revive the retired shortcut.',[
 'Current rollback requires order-ledger reconciliation and two /ready probes thirty seconds apart.',
 'A mismatch keeps traffic closed.',
 'The duty steward signs the release card before public traffic opens.'
],[('harbor-backup','rollback'),('harbor-release','gate')],forbidden=['One readiness response is sufficient.'])
task('LS11','superseded','large','A handoff cites Meridian rollout revision 4 and its five-minute heartbeat check. What sequence should the next engineer use now, and what happens if the shadow comparison disagrees?',[
 'Use current revision 5: thirty-minute shadow ingest, checksum reconciliation, then curator approval before public traffic.',
 'A shadow mismatch requires rollback to the last approved build and preservation of mismatch receipt identifiers.',
 'The signed release decision explicitly replaces revision 4.'
],[('meridian-rollout-current','current'),('meridian-rollout-current','rollback'),('meridian-rollout-current','replace')],forbidden=['A five-minute heartbeat check authorizes public traffic.'])
task('LS12','superseded','large','A restored copy of Meridian retention revision 2 says to delete everything after ninety days. What lifetimes apply now to raw training observations and public summaries, and does deleting one authorize deleting the other?',[
 'Current revision 3 retains raw training observations for thirty days and public summaries for three hundred sixty-five days.',
 'Deleting raw observations does not authorize deleting summaries.',
 'Ratified R-8 replaced revision 2; a restored copy timestamp does not restore its authority.'
],[('meridian-retention-current','current'),('meridian-retention-current','delete'),('meridian-retention-current','replace')])
task('LS13','buried_manual','large','A Meridian sensor heartbeat looks healthy after a lightning warning. Is that enough to plug the head back in? Give the waiting period and prerequisite physical check.',[
 'A healthy heartbeat alone is insufficient to reconnect after a lightning alarm.',
 'Isolate the sensor head for forty-five minutes and inspect the surge cartridge before reconnection.'
],[('meridian-manual-sensor','buried')],forbidden=['A clear heartbeat alone authorizes reconnection.'])
task('LS14','buried_manual','large','During a Meridian drain window, what should a new admission request receive, how long should it wait, and what remains available for an already accepted receipt?',[
 'New admission receives HTTP 429 with Retry-After: 90.',
 'Already accepted receipts remain queryable and retain durable-queue status.'
],[('meridian-manual-queue','buried')])
task('LS15','buried_manual','large','An operator recalls a Meridian export and disables its link. What record must survive and for how long, and can this operation erase a copy the researcher already downloaded?',[
 'Keep the recalled export audit manifest for one hundred eighty days.',
 'Link disablement does not erase the recipient’s previously downloaded copy.'
],[('meridian-manual-archive','buried')])
task('LS16','insufficient','large','What is Meridian’s current production p95 admission latency, measured this week? Give the value only if the collection establishes that window and environment.',[
 'The current production p95 admission latency for this week is not established by eligible evidence.'
],[],status='insufficient_evidence',forbidden=['Current production p95 latency is 84 milliseconds.'])
task('LS17','insufficient','large','Calculate Meridian’s actual monthly satellite communications bill from these documents, in currency units. If a necessary price or volume is missing, identify the gap rather than inventing a charge.',[
 'The actual monthly satellite bill cannot be calculated from the collection.',
 'Contracted prices and measured monthly transmission volume are absent.'
],[('meridian-cost-boundary','unknown'),('meridian-cost-boundary','volume')],status='insufficient_evidence',forbidden=['A numeric actual monthly bill is established.'])
task('LS18','insufficient','large','A technician needs the production station-signing recovery code. What is its value in this collection? Do not infer a secret from example identifiers or look elsewhere.',[
 'No production station-signing recovery-code value is present.',
 'Only public identifiers and synthetic placeholders are documented; guessing is not justified.'
],[('meridian-secrets-boundary','unknown')],status='insufficient_evidence',forbidden=['Any invented recovery-code value.'])
task('LS19','code_config','compact','Interpret the Harbor HTTP client example precisely: what is the timeout in seconds, how many total transmissions are configured, and what JSON type and value must X-Training have?',[
 'The timeout is 2.5 seconds, from 2500 milliseconds.',
 'There is one initial transmission and zero additional retry attempts.',
 'X-Training is the string "true", not the boolean true.'
],[('harbor-client','json'),('harbor-client','rules')])
task('LS20','code_config','large','A Meridian satellite client proposes max_envelopes=13, flush_ms=750 and additional_attempts=0. Is the configuration accepted, what remains effective if it fails, and what do the retry and ordering fields mean?',[
 'Reject max_envelopes=13 because the inclusive maximum is twelve.',
 'Validation is atomic, so the prior effective configuration remains unchanged.',
 'Zero additional_attempts permits only the initial transmission; station_then_event orders by station_id then event_id, not arrival time.'
],[('meridian-config-validation','validate'),('meridian-config-validation','atomic'),('meridian-batch-config','rules')])
task('LS21','code_config','large','Without executing code, trace decode_frame on 4d 46 00 03 61 62 63 00 00 and then on that sequence with its final byte removed. State the payload or error and whether success proves checksum validity.',[
 'The nine-byte frame declares a three-byte payload and returns 61 62 63.',
 'Removing the final byte produces an eight-byte frame and raises "length mismatch".',
 'Successful length validation does not verify the marker or checksum.'
],[('meridian-parser-code','code'),('meridian-parser-code','layout'),('meridian-parser-tests','example'),('meridian-parser-tests','negative')],constraints=['Explain the documented code without executing it.'])

def cp(objective,constraints,decision,refs,question,next_action,change):
    return {'objective':objective,'constraints':constraints,'decisions':[{'text':decision,'evidence':[evidence(*r) for r in refs]}],
            'unresolved_questions':[question],'next_actions':[next_action],
            'lifecycle_transition':change,
            'stages':['Checkpoint captured before lifecycle transition.','Apply the stated source transition in an isolated benchmark snapshot.','Resume from the frozen card against the final corpus.'],
            'scope_limit':'One inference after deterministic checkpoint preparation/resume. This does not test model-generated multi-turn summaries or a second model turn.'}

task('LS22','continuation','compact','Resume the supplied Harbor checkpoint after W4 is withdrawn. Preserve the user constraints, identify the decision that must be discarded, and state the safe next action without executing it.',[
 'Preserve the objective and constraints: review only, no deployment and no permission changes.',
 'The source-dependent window decision is suppressed because its supporting reference was revoked; leave that decision unresolved without reconstructing removed prose.',
 'A missed window requires a new release card; the next action is to request steward review of a new card, not to extend the window.'
],[('harbor-checkpoint','resume'),('harbor-release','window'),('harbor-release','gate')],constraints=['Preserve review only, no deployment and no permission changes.'],
 checkpoint=cp('Review a reversible Harbor release plan.',['Review only.','No deployment.','No permission changes.'],'Extend the maintenance window by ten minutes.', [('harbor-retired-waiver','waiver')],'Can the current window be extended?','Verify the window policy and ask the steward for the next authorized step.',{'source_id':'harbor-retired-waiver','from':'active','to':'revoked'}))
task('LS23','continuation','large','Continue the Meridian paused relay review from its checkpoint after rollout revision 4 is superseded. Preserve all constraints and the selected build, replace no decision silently, and report the current sequence and approving role.',[
 'Preserve build cedar-17 and constraints: no deployment, credential access, network call or configuration write.',
 'The source-dependent rollout decision is suppressed because its supporting reference was superseded; leave that decision unresolved without reconstructing removed prose.',
 'Current revision 5 requires thirty-minute shadow ingest, checksum reconciliation and curator approval; record this as current evidence without executing rollout.'
],[('meridian-continuity','revalidate'),('meridian-checkpoint-release','constraints'),('meridian-rollout-current','current')],constraints=['Preserve build cedar-17; no deployment, credential access, network call or configuration write.'],
 checkpoint=cp('Review the paused relay release candidate.',['No deployment.','No credential access.','No network call.','No configuration write.','Selected build cedar-17.'],'Open traffic after a five-minute heartbeat check.', [('meridian-rollout-old','old')],'What current sequence and approving role are required?','Check current release evidence and record the approval prerequisite.',{'source_id':'meridian-rollout-old','from':'active','to':'superseded'}))
task('LS24','continuation','large','Resume the research-export checkpoint after waiver E-9 is revoked. Keep the user’s delivery objective and constraints, identify the obsolete decision, and describe the currently documented delivery and acknowledgement without sending anything.',[
 'Preserve the objective of reviewing research-bundle delivery and the constraints: no export, no email and no permission changes.',
 'The source-dependent delivery decision is suppressed because its supporting reference was revoked; leave delivery unresolved pending review without reconstructing removed prose.',
 'Current delivery uses the authenticated project portal; email may carry only the receipt identifier.',
 'Recipient acknowledgement records bundle checksum and project account; an email delivery receipt is insufficient.'
],[('meridian-continuity','revalidate'),('meridian-continuity','noexecute'),('meridian-export-transport','transport'),('meridian-export-transport','ack')],constraints=['Preserve no export, no email and no permission changes.'],
 checkpoint=cp('Review a research-bundle delivery plan.',['No export.','No email.','No permission changes.'],'Email the research bundle as an attachment.', [('meridian-waiver-revoked','waiver')],'Which delivery channel and acknowledgement are currently permitted?','Review the current transport contract and propose a delivery decision.',{'source_id':'meridian-waiver-revoked','from':'active','to':'revoked'}))

# Known equivalent source evidence is frozen before retrieval. Canonical spans
# remain an exact-reference recall metric; any listed all-of alternative satisfies
# its semantic evidence obligation. Selectors must never consume these groups.
def add_alternatives(task_id, primary, alternatives):
    current=next(t for t in TASKS if t['id']==task_id)
    if 'evidence_groups' not in current:
        current['evidence_groups']=[{'id':task_id+'-e'+str(i+1), 'alternatives':[{'spans':[span]}]}
                                    for i,span in enumerate(current['required_evidence'])]
    target=evidence(*primary)
    group=next(g for g in current['evidence_groups'] if g['alternatives'][0]['spans']==[target])
    group['alternatives'].extend({'spans':[evidence(*ref) for ref in alternative]} for alternative in alternatives)

# The archive manual and short export policy both establish recall-copy limits.
add_alternatives('LS05',('meridian-export-retention','copy'),[[('meridian-manual-archive','buried')]])
add_alternatives('LS15',('meridian-manual-archive','buried'),[
    [('meridian-export-retention','expiry'),('meridian-export-retention','copy')]])
# Admission/publication are explicitly distinct in the terminology reference too.
# This task asks about acceptance, not the HTTP-202-specific fact in LS02.
# The glossary has two contiguous prose records; retain their exact authored lines.
# Rather than create an implicit generic semantic matcher, only known alternatives
# whose source explicitly supplies the fact are enumerated.
# The parser can be reasoned through from its code, or checked against the worked
# positive/negative examples and explicit limitation; example citations are not mandatory.
add_alternatives('LS21',('meridian-parser-code','code'),[
    [('meridian-parser-tests','example'),('meridian-parser-tests','negative'),('meridian-parser-code','layout')]])
add_alternatives('LS21',('meridian-parser-code','layout'),[[('meridian-parser-code','code')]])
add_alternatives('LS21',('meridian-parser-tests','example'),[[('meridian-parser-code','code'),('meridian-parser-code','layout')]])
add_alternatives('LS21',('meridian-parser-tests','negative'),[[('meridian-parser-code','code'),('meridian-parser-code','layout')]])

assert len(DOCS)==72, len(DOCS)
assert len(TASKS)==24
assert sum(d['bytes'] for d in DOCS if d['scope']=='compact')<=18000
assert sum(d['bytes'] for d in DOCS if d['scope']=='large')>=160000
assert sum(t['scope']=='compact' for t in TASKS)==6
for t in TASKS:
    for e in t['required_evidence']:
        assert e['quote'] and e['quote'] in ''.join(TEXT[e['source_id']].splitlines(keepends=True)[e['line_start']-1:e['line_end']])
        assert e['source_sha256']==digest(TEXT[e['source_id']].encode())
        row=next(d for d in DOCS if d['id']==e['source_id'])
        assert row['scope']==t['scope'] and row['status']=='active'
counts={c:sum(t['category']==c for t in TASKS) for c in sorted({t['category'] for t in TASKS})}
assert set(counts.values())=={3}
write_json('corpus.json',{'format':'kre-large-corpus/1','synthetic':True,'license':'CC0-1.0','documents':DOCS})
write_json('tasks.json',{'format':'kre-large-tasks/1','synthetic':True,'authoring_mode':'independent synthetic authoring before retrieval evaluation','tasks':TASKS})
freeze={'format':'kre-large-fixture-freeze/1','status':'frozen_before_retrieval_evaluation','tasks':len(TASKS),'documents':len(DOCS),'category_counts':counts,
        'scope_documents':{s:sum(d['scope']==s for d in DOCS) for s in ('compact','large')},
        'scope_bytes':{s:sum(d['bytes'] for d in DOCS if d['scope']==s) for s in ('compact','large')},
        'scope_tasks':{s:sum(t['scope']==s for t in TASKS) for s in ('compact','large')},
        'files':{name:digest((ROOT/name).read_bytes()) for name in ('corpus.json','tasks.json','build_fixture.py')},
        'source_hashes':{d['id']:d['sha256'] for d in DOCS},'model_calls':0,'retrieval_evaluations':0,
        'authoring_limitations':['Synthetic authored fixture, not a representative random sample of public projects.','Manual sections intentionally include repeated generic operating cautions, alongside varied domain details.','Author did not inspect retrieval implementation or test task retrieval; all source/task mappings were authored from source text.','Reference answers and gold spans are evaluation-only, not model context.']}
write_json('freeze.json',freeze)
print(json.dumps({k:freeze[k] for k in ('tasks','documents','category_counts','scope_documents','scope_bytes','scope_tasks')},indent=2))
