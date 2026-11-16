// Offline, pinned public-source replay. No package bootstrap, SDK, network or live state.
// Run through context-probe.py to generate the fictional MCP response with real KRE.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';

const [root, fixture] = process.argv.slice(2);
if (!root || !fixture) throw new Error('public_package_root_and_fictional_fixture_required');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const sources = new Map();
const read = name => {
  if (!sources.has(name)) sources.set(name, fs.readFileSync(path.join(root, name), 'utf8'));
  return sources.get(name);
};
const version = JSON.parse(read('package.json')).version;
if (version !== '2026.11.1') throw new Error('Review extraction against the new public package version first');
for (const name of [
  'dist/agent-bundle-mcp-materialize-DFCjlBPG.mjs',
  'docs/plugins/codex-harness-runtime.md',
  'docs/plugins/codex-harness-runtime/v1-support-contract.md',
  'docs/plugins/codex-harness-reference/dynamic-tools.md',
  'node_modules/@openclaw/ai/dist/openai-responses-ytmKcG9V.mjs',
]) read(name); // Hash the static call-path/boundary evidence too.
const ai = 'node_modules/@openclaw/ai/dist/';
const clean = source => source.split('\n').filter(line => !line.startsWith('import ') && !line.startsWith('export ')).join('\n');
const chunks = [];
const extractions = [];
function functions(name, names) {
  const source = read(name);
  for (const symbol of names) {
    const start = source.search(new RegExp(`^(?:async )?function ${symbol}\\(`, 'm'));
    if (start < 0) throw new Error(`Missing function ${symbol}`);
    const end = source.indexOf('\n}', start);
    if (end < 0) throw new Error(`Missing function end ${symbol}`);
    const code = source.slice(start, end + 2);
    chunks.push(code);
    extractions.push({file: name, symbol, sha256: sha(code)});
  }
}
function region(name, start, end, includeEnd = false) {
  const source = read(name);
  const first = source.indexOf(start), last = source.indexOf(end, first);
  if (first < 0 || last < 0) throw new Error(`Missing region ${start}`);
  const code = source.slice(first, last + (includeEnd ? end.length : 0));
  chunks.push(code);
  extractions.push({file: name, symbol: start, sha256: sha(code)});
}
for (const name of ['record-coerce-TIsquoVR', 'stable-stringify-Djn3uxNo', 'mcp-structured-mirror-1Cuz_E2Y', 'mcp-content-BHTPz8cL']) {
  chunks.push(clean(read(`dist/${name}.mjs`)));
}
chunks.push(clean(read(ai + 'sanitize-unicode-CRGuMONI.mjs')));
functions(ai + 'string-coerce-Cj8sqWHx.mjs', ['normalizeNullableString', 'normalizeOptionalString', 'normalizeOptionalLowercaseString', 'normalizeLowercaseStringOrEmpty']);
functions(ai + 'host-rCxf5Tjd.mjs', ['hasMediaPayload', 'isImageWithMediaPayload', 'normalizeModelId', 'normalizeApi',
  'resolveReplayModelBoundIdentity', 'resolveModelBoundThinkingReplayMode', 'resolveFailedAssistantReplay',
  'replaceImagesWithPlaceholder', 'transformAssistant', 'transformMessages']);
region(ai + 'host-rCxf5Tjd.mjs', 'const NON_VISION_USER_IMAGE_PLACEHOLDER', 'function replaceImagesWithPlaceholder');
region(ai + 'openai-responses-contracts-DCG51Us0.mjs', 'const OPENAI_RESPONSES_APIS', '\n]);', true);
chunks.push(clean(read(ai + 'types-BXd0kI8-.mjs')));
functions(ai + 'assistant-output-BdFoDBYQ.mjs', ['projectUserMediaForTransport', 'transformProviderMessages']);
region(ai + 'simple-options-BdJJbzZk.mjs', 'const SYSTEM_PROMPT_CACHE_BOUNDARY', 'function prependSystemPromptAdditionAfterCacheBoundary');
region(ai + 'simple-options-BdJJbzZk.mjs', 'const PREPARED_REQUEST_SUFFIX', '//#endregion');
region(ai + 'simple-options-BdJJbzZk.mjs', 'const STRUCTURED_TOOL_RESULT_MAX_CHARS', '/** Describe media that cannot');
region(ai + 'simple-options-BdJJbzZk.mjs', 'const REQUEST_BODY', '//#endregion');
functions(ai + 'transport-stream-shared-DdnJGEj0.mjs', ['sanitizeTransportPayloadText']);
functions(ai + 'provider-replay-context-BC23HyZo.mjs', ['hashReplayContextValue', 'buildProviderReplayContext']);
functions(ai + 'openai-responses-endpoint-JbBT8IDv.mjs', ['supportsNativeOpenAIResponsesEndpoint']);
const shared = ai + 'openai-responses-shared-CD3Sd1NC.mjs';
functions(shared, ['buildOpenAIResponsesCompactionReplayPlan', 'readResponsesInputReplayState', 'readResponsesInputReplay',
  'createResponsesInputReplay', 'resolveReplayableResponsesMessageId', 'resolveResponsesInstructionRole',
  'responsesAssistantTurnKey', 'orderResponsesAsyncToolResults', 'parseOpenAIResponsesTextSignature',
  'normalizeResponsesReplayItemId', 'buildResponsesInputMessage', 'convertResponsesMessagesWithStyle',
  'convertProviderResponsesMessages', 'isAsyncIterable', 'commitResponsesEncryptedContentAttempt',
  'readResponsesRecoveryEvent', 'createResponsesStreamWithRecovery']);
region(shared, 'const responsesInputSource', '/** Source identity');
// Fake SDK only: source conversion/encoding/send logic is unmodified. Unvisited
// media, compaction, failure-recovery and reasoning branches have no mock helpers.
// If the fixture reaches one, replay fails rather than inventing host behavior.
const sandbox = vm.createContext({Blob, TextEncoder});
vm.runInContext(chunks.join('\n'), sandbox, {timeout: 2000});
sandbox.fixtureJSON = fs.readFileSync(fixture, 'utf8');
const replay = await vm.runInContext(`(async () => {
  const mcp = JSON.parse(fixtureJSON);
  const projected = projectMcpCallToolResult(mcp);
  const model = {id:'fictional-context-probe', provider:'fixture', api:'openai-responses', input:['text'], reasoning:false};
  const messages = [
    {role:'user', content:'What is the fictional project code?'},
    {role:'assistant', provider:model.provider, api:model.api, model:model.id, stopReason:'toolUse',
      content:[{type:'toolCall', id:'call_fixture', name:'kre_retrieve', arguments:{query:'project code'}}]},
    {role:'toolResult', toolCallId:'call_fixture', toolName:'kre_retrieve', content:projected.content}
  ];
  const records = [];
  const fakeUsage = [
    {input_tokens:1000, output_tokens:20, total_tokens:1020, input_tokens_details:{cached_tokens:200}, output_tokens_details:{reasoning_tokens:5}},
    {input_tokens:1050, output_tokens:30, total_tokens:1080, input_tokens_details:{cached_tokens:300}, output_tokens_details:{reasoning_tokens:7}}
  ];
  class Stream {}
  globalThis.Stream = Stream;
  for (let index = 0; index < 2; index++) {
    if (index) messages.push(
      {role:'assistant', provider:model.provider, api:model.api, model:model.id, stopReason:'stop',
        content:[{type:'text', text:'The fictional project code is stated in the evidence.'}]},
      {role:'user', content:'Continue using the same evidence.'});
    const input = convertProviderResponsesMessages(model, {systemPrompt:'Use the supplied evidence.', messages}, new Set(['fixture']),
      {replayMode:'full-history', replayResponsesItemIds:false});
    // Same public buildParams input/stream/store fields; fixture model/config only.
    // No cache continuation, relay, compaction, prompt injector or model call is run.
    const request = {model:model.id, input, stream:true, store:false};
    const fakeClient = {responses:{create: (params, options) => ({withResponse:async () => {
      const body = await options.body.text();
      if (JSON.stringify(JSON.parse(body)) !== JSON.stringify(params)) throw new Error('Body mismatch');
      records.push({request:JSON.parse(body), body, tool_output:input.find(item => item.type === 'function_call_output').output});
      return {response:{body:null}, data:{async *[Symbol.asyncIterator]() {yield {type:'response.completed', response:{usage:fakeUsage[index]}};}}};
    }})}};
    const result = await createResponsesStreamWithRecovery({model, request, client:fakeClient});
    for await (const event of result.stream) records[index].synthetic_terminal_usage = event.response.usage;
  }
  return JSON.stringify({mcp, projected, records});
})()`, sandbox, {timeout: 2000});
const parsed = JSON.parse(replay);
const marker = 'SYNTHETIC_DUPLICATION_SENTINEL_7C9A';
const count = value => value.split(marker).length - 1;
const bytes = value => Buffer.byteLength(value, 'utf8');
const metrics = parsed.records.map((record, index) => ({
  request: index + 1,
  serialized_request_body_bytes: bytes(record.body),
  serialized_request_input_bytes: bytes(JSON.stringify(record.request.input)),
  model_visible_tool_text_bytes: bytes(record.tool_output),
  model_visible_text_bytes: bytes(record.request.input.flatMap(item => item.type === 'function_call_output'
    ? [item.output] : (item.content ?? []).map(part => part.text ?? '')).join('')),
  tool_text_local_estimate_tokens: Math.ceil(bytes(record.tool_output) / 4),
  estimate_method: 'ceil(UTF-8 bytes / 4); not a provider tokenizer or billed tokens',
  sentinel_occurrences_in_tool_output: count(record.tool_output),
  exact_projected_text_preserved: record.tool_output === parsed.projected.content[0].text,
  request_sha256: sha(record.body),
  synthetic_terminal_usage: record.synthetic_terminal_usage,
}));
console.log(JSON.stringify({
  format:'kre-context-attribution/1', evidence_kind:'synthetic_offline_public_source_replay',
  openclaw_version:version, ai_version:JSON.parse(read('node_modules/@openclaw/ai/package.json')).version,
  node_version:process.version, no_network_or_live_state:true,
  scope:'generic Responses full-history text-only converter and encoded request; fake SDK response',
  exclusions:['native Codex provider request', 'actual SDK internals', 'Gateway context assembly',
    'compaction', 'server-side continuation', 'provider tokenizer', 'real model or billing'],
  native_host_final_request_verified:false, actual_provider_input_tokens:null, actual_billed_usage:null,
  source_files:[...sources].map(([name, source]) => ({name, sha256:sha(source)})), extracted_functions:extractions,
  mcp_result_serialized_bytes:bytes(JSON.stringify(parsed.mcp)),
  mcp_text_bytes:bytes(parsed.mcp.content[0].text), projected_agent_text_bytes:bytes(parsed.projected.content[0].text),
  requests:metrics,
  aggregate:{request_count:2, transmitted_tool_text_bytes:metrics.reduce((n,r) => n+r.model_visible_tool_text_bytes,0),
    transmitted_sentinel_occurrences:metrics.reduce((n,r) => n+r.sentinel_occurrences_in_tool_output,0),
    synthetic_input_tokens:2050, synthetic_output_tokens:50, synthetic_total_tokens:2100,
    synthetic_cached_tokens_included_in_input:500, synthetic_reasoning_tokens_included_in_output:12,
    actual_provider_tokens:null, actual_billed_charge:null},
  warning:'Fake usage numbers verify accounting distinctions; they do not measure duplication token impact or real savings.'
}, null, 2));
