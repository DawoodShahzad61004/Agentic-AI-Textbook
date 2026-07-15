_CHUNK_MERGE_PROMPT = """You merge near-duplicate retrieved chunks into one consolidated chunk.

Return ONLY a JSON object with this shape (no code, no markdown fences, no explanation):

{{"content": "...", "sources": [...], "merged_from": <int>}}

EXAMPLE INPUT:
[Source: a.pdf]
ASD affects 1 in 36 children. Early diagnosis improves outcomes.

[Source: b.pdf]
Approximately 1 in 36 kids have autism spectrum disorder. Children diagnosed early respond better to therapy.

EXAMPLE OUTPUT:
{{"content": "ASD affects approximately 1 in 36 children [Source: a.pdf] [Source: b.pdf]. Early diagnosis improves outcomes and response to therapy [Source: a.pdf] [Source: b.pdf].", "sources": ["a.pdf", "b.pdf"], "merged_from": 2}}

RULES:
- Preserve every fact across all input chunks. Never invent new facts.
- Write each distinct fact only once, even if multiple chunks state it.
- Cite every source inline as [Source: filename] after the sentence it supports.
- If multiple sources support the same fact, list them all: [Source: a.pdf] [Source: b.pdf].
- Do NOT write Python code. Do NOT explain your process. Output ONLY the JSON object.

INPUT CHUNKS:
"""

_DC_SCAN_PROMPT = """You are performing sentence-level redundancy annotation.

Your task:
Identify sentences from DIFFERENT chunks that express the SAME FACT.

IMPORTANT:
Two sentences are redundant ONLY if they communicate essentially the SAME information.

The sentences must match on:
- subject
- claim
- meaning

Being about the SAME TOPIC is NOT enough.

You are NOT writing software.
You are NOT generating Python.
You are NOT solving a coding task.
You are ONLY selecting matching factual statements.

Return ONLY a JSON array.

CHUNKS:
{chunks_block}

WHAT COUNTS AS REDUNDANT:
- Same fact
- Same subject
- Same meaning
- Paraphrases are allowed

GOOD EXAMPLE:
Chunk 0:
"ASD affects 1 in 36 children."

Chunk 1:
"Approximately 1 in 36 children have autism."

These ARE redundant because they express the same fact.

ANOTHER GOOD EXAMPLE:
Chunk 0:
"ASDs regulate motor speed by changing voltage and frequency."

Chunk 1:
"An ASD controls motor speed through voltage and frequency adjustment."

These ARE redundant.

WHAT IS NOT REDUNDANT:

NOT REDUNDANT — SAME TOPIC BUT DIFFERENT FACTS:
Chunk 0:
"ASD patients may experience sensory overload."

Chunk 1:
"Healthcare providers should reduce loud noises."

These are RELATED but NOT redundant.

NOT REDUNDANT — DIFFERENT SUBJECTS:
Chunk 0:
"Dawood's policy includes accidents."

Chunk 1:
"Umair's policy includes accidents."

Different subjects = NOT redundant.

NOT REDUNDANT — GENERAL VS SPECIFIC:
Chunk 0:
"Managing ASD patients requires individualized care."

Chunk 1:
"Reduce bright lights and loud sounds."

These are NOT the same fact.

IMPORTANT RULES:
- A group MUST contain sentences from AT LEAST TWO DIFFERENT chunks.
- Never group sentences from only one chunk.
- One shared fact = one group.
- Copy sentences EXACTLY as written.
- Do not rewrite sentences.
- Be CONSERVATIVE.
- If unsure, DO NOT group.
- It is BETTER to miss a redundancy than to create a false match.

If nothing is redundant, return:
[]

OUTPUT FORMAT:
[
  {{
    "members": [
      {{
        "chunk_index": 0,
        "sentence": "Exact sentence from chunk."
      }},
      {{
        "chunk_index": 1,
        "sentence": "Matching sentence from another chunk."
      }}
    ]
  }}
]

BAD OUTPUTS:
- Python
- Pseudocode
- Explanations
- Markdown
- Comments
- Any text outside the JSON

The first character of your response must be '['

Your response will be parsed directly using json.loads().
Invalid JSON will cause failure.

Return ONLY the JSON array.
"""

_LBC_COMPRESS_PROMPT = """You are a query-focused chunk compressor.

USER QUERY:
{query}

COMPRESSION INSTRUCTIONS:
{instructions}

ORIGINAL CHUNK (source: {source}):
{content}

Your task: rewrite the chunk keeping ONLY sentences that directly help answer the USER QUERY.
Follow the COMPRESSION INSTRUCTIONS above as hard constraints.

RULES:
- Preserve every query-relevant sentence verbatim or as a minimal paraphrase.
- Remove sentences that are purely background, metadata, or off-topic for this query.
- Do NOT invent new sentences. Every sentence in your output must come from the original chunk.
- If the entire chunk is relevant, reproduce it unchanged.
- If NOTHING in the chunk is relevant, output exactly: __IRRELEVANT__

Return ONLY a JSON object — no markdown, no prose, no code fences:
{{"compressed": "<retained content, or __IRRELEVANT__>", "dropped_count": <int>, "reason": "<one sentence>"}}"""

_LBC_DEFAULT_INSTRUCTIONS = (
    "1. Remove sentences that are pure metadata (page numbers, headers, document titles).\n"
    "2. Remove sentences that describe document structure rather than facts.\n"
    "3. Remove sentences that repeat context already present in other chunks (assume the "
    "reader will see all chunks together).\n"
    "4. Keep ALL sentences that contain named entities, numbers, definitions, or causal "
    "relationships that bear on the query."
)

_REDUNDANCY_JUDGE_PROMPT = """You are validating proposed redundancy groups.

Your task:
For each proposed group, decide whether all sentences in that group express the SAME FACT.

You are NOT writing software.
You are NOT generating Python.
You are NOT describing an algorithm.
You are ONLY judging whether each proposed group is valid.

CHUNKS:
{chunks_block}

PROPOSED GROUPS:
{groups_block}

A group is CONFIRMED only if:
- all sentences have the same subject
- all sentences make the same claim
- all sentences have the same meaning
- removing duplicate copies would NOT lose unique information

IMPORTANT:
- Same topic is NOT enough.
- Related ideas are NOT enough.
- Similar wording is NOT enough.
- Advice and explanation are NOT automatically the same fact.
- General statements and specific instructions are NOT redundant.
- If one sentence adds a unique detail, the group is REJECTED.
- If the subjects are different real-world entities, the group is REJECTED.
- If meanings conflict or one sentence negates another, the group is REJECTED.

Be STRICT.
Be CONSERVATIVE.
If unsure, REJECT the group.

GOOD:
"ASDs vary motor speed by controlling voltage and frequency."
"An ASD regulates motor speed by adjusting frequency and voltage."
Verdict: CONFIRMED

BAD:
"ASD patients may experience sensory overload."
"Healthcare providers should reduce loud noises."
Verdict: REJECTED
Reason: related topic, but different facts.

BAD:
"Managing ASD patients requires individualized care."
"Reduce bright lights and loud sounds."
Verdict: REJECTED
Reason: general guidance versus specific instruction.

BAD:
"ASDs reduce energy costs and mechanical wear."
"ASDs reduce energy costs."
Verdict: REJECTED
Reason: one sentence contains unique information.

OUTPUT FORMAT:
Return ONLY a JSON array.
One object per proposed group, in the same order as the input groups.

[
  {{
    "group_index": 0,
    "verdict": "CONFIRMED",
    "reason": "Same subject and same factual claim."
  }},
  {{
    "group_index": 1,
    "verdict": "REJECTED",
    "reason": "Related topic but different facts."
  }}
]

BAD OUTPUTS:
- Python code
- Pseudocode
- Markdown
- Explanations outside JSON
- Text before or after the JSON array

The first character of your response must be '['.
Your response will be parsed directly using json.loads().
Invalid JSON will cause failure.

Return ONLY the JSON array.
""" 

_RETRIEVAL_JUDGE_PROMPT = """You are a strict relevance judge for a retrieval system.

ORIGINAL USER QUESTION:
{query}

RETRIEVED CHUNKS (one per block, indexed):
{chunks_block}

Your job: for EACH chunk, decide whether it contains information that
directly helps answer the ORIGINAL USER QUESTION.

A chunk is RELEVANT only if a reader could extract at least one fact from
it that contributes to answering the question. Tangential mentions of the
topic, generic background, or off-topic text are NOT relevant.

Then give an OVERALL verdict:
- "PASS"    : majority of chunks are relevant AND together they could plausibly support an answer.
- "PARTIAL" : some chunks are relevant but coverage is thin or incomplete.
- "FAIL"    : few or no chunks are relevant; the agent should retry with a different query.

Return ONLY a JSON object (no markdown, no prose, no code fences) with this exact shape:

{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "per_chunk": [
    {{"index": 0, "relevant": true,  "reason": "<one short sentence>"}},
    {{"index": 1, "relevant": false, "reason": "<one short sentence>"}}
  ],
  "overall_reason": "<one or two sentences>"
}}
"""

_MERGE_JUDGE_PROMPT = """You are a faithfulness judge for a chunk-merging step.

The merging step received several near-duplicate SOURCE CHUNKS and produced one MERGED CHUNK.
Your job is to verify that the MERGED CHUNK is faithful: it must not invent facts, and it must
preserve every substantive fact from the source chunks.

CRITICAL RULES FOR JUDGING FACTS:
RULE 1 — PARAPHRASE = PRESENT
If two source chunks state the same fact in different words, and the merged chunk expresses
that fact ONCE (in any wording), the fact is PRESERVED for BOTH source chunks.
Do NOT list it as dropped just because one source's exact wording is absent.
RULE 2 — DEDUPLICATE BEFORE CHECKING
Multiple source chunks often overlap heavily. Before listing a dropped fact, confirm that
the underlying information is genuinely absent from the merged chunk — not merely rephrased.
RULE 3 — IGNORE FORMATTING
Citation tags like "[Source: filename]", inline references, and sentence order changes are
formatting choices, not factual differences. Never treat them as fabrication or omission.
RULE 4 — SUBSTANTIVE FACTS ONLY
Only flag facts with meaningful informational content. Generic connector phrases, filler
sentences, and stylistic differences are NOT facts and must never appear in either list.

SOURCE CHUNKS (the only allowed evidence):
{sources_block}

MERGED CHUNK (the output to validate):
{merged_block}

PROCESS (follow in this exact order):
1. CHECK FOR FABRICATION — For every factual claim in the MERGED CHUNK, ask: "Is this claim
   supported by at least one SOURCE CHUNK above — either verbatim or as a clear paraphrase?"
   GOOD: "ASDs minimize electricity costs." ← supported by "They lower electricity costs." ✓
   BAD:  Listing "minimize electricity costs" as fabricated when a source says "lower electricity
         costs" — these are paraphrases of the same fact. Do NOT list it. ✗
   • If YES → the claim is supported. Do NOT list it.
   • If NO  → list it in "fabricated_claims".
2. CHECK FOR DROPPED FACTS — Collect every distinct substantive fact from ALL source chunks.
   For each fact, ask: "Does the MERGED CHUNK express this fact — verbatim OR as a paraphrase?"
   GOOD: Source says "They lower electricity costs." Merged says "minimize electricity costs."
         → Same fact, different words. Do NOT list as dropped. ✓
   BAD:  Listing a fact as dropped when the merged chunk expresses it in different wording. ✗
   • If YES → the fact is preserved. Do NOT list it.
   • If NO  → list it in "dropped_claims".

OUTPUT FORMAT
Return ONLY a JSON object — no markdown, no code fences, no prose outside the JSON.
{{
  "fabricated_claims": ["<exact claim from merged chunk that has no source support>", ...],
  "dropped_claims":    ["<substantive fact from sources genuinely absent from merged chunk>", ...],
  "overall_reason": "<one or two sentences explaining your verdict>"
}}
If both lists are empty, return empty arrays. Do not invent items to fill them.
"""

_LBC_JUDGE_PROMPT = """You are a compression-safety judge for a query-focused chunk compression step.

A compression step received an ORIGINAL CHUNK and a USER QUERY, and produced a COMPRESSED CHUNK
by removing sentences it deemed irrelevant to the query. Your job is to verify the compression
is safe — it must not invent facts, and it must not discard sentences that are relevant to the query.

USER QUERY:
{query}

ORIGINAL CHUNK (source: {source}):
{original_content}

COMPRESSED CHUNK:
{compressed_content}

JUDGMENT RULES:
RULE 1 — NO FABRICATION
Every sentence in the COMPRESSED CHUNK must be traceable (verbatim or as a clear paraphrase)
to the ORIGINAL CHUNK. If any sentence in the compressed output introduces new information
not present in the original, list it in "fabricated_claims".

RULE 2 — NO RELEVANT FACTS LOST
A sentence from the ORIGINAL CHUNK is a "lost relevant fact" only if BOTH conditions hold:
  (a) It contains information that directly helps answer the USER QUERY.
  (b) It is absent from the COMPRESSED CHUNK (neither verbatim nor as a paraphrase).
Generic background, preamble, metadata, and facts with zero bearing on the query are NOT
relevant facts and must never appear in "lost_relevant_facts".

RULE 3 — PARAPHRASE = PRESENT
If the compressed chunk expresses a fact in different words from the original, the fact is
still present. Do not list it as lost.

VERDICT:
- "SAFE"            : no fabrications and no relevant facts were lost
- "OVER_COMPRESSED" : at least one query-relevant fact was dropped (no fabrications)
- "FABRICATED"      : at least one sentence in the compressed output has no source support
- "UNKNOWN"         : cannot determine (malformed input)

Return ONLY a JSON object — no markdown, no prose, no code fences:
{{
  "verdict": "SAFE" | "OVER_COMPRESSED" | "FABRICATED" | "UNKNOWN",
  "fabricated_claims":   ["<sentence from compressed chunk with no source support>", ...],
  "lost_relevant_facts": ["<query-relevant sentence from original that was dropped>", ...],
  "overall_reason": "<one or two sentences>"
}}
If both lists are empty, return empty arrays."""

NO_CONTEXT_ANSWER = (
    "The knowledge base does not contain information about this query. "
    "No relevant documents were retrieved across all search attempts."
)

_ROLE_AND_RULES = """You are a research assistant. Answer ONLY from retrieved chunks — never from memory.

HARD LIMITS (enforced by the system — do not test them):
- retrieve_documents: max 5 calls total. Stop at 3 if results are poor.
- Never repeat a query already tried. Never generate two queries with identical words.
- If the knowledge base has no answer after 3 tries, say: "The knowledge base does not contain information about [topic]."
- Never fabricate facts.

TOOLS (these are the ONLY tools available to you):
- retrieve_documents(query): searches documents and learned QA separately.
- compress_context(): independently consolidates the document and learned-QA
  tracks (NAC → DC → LBC). Takes no arguments. The system remembers both.

CONFLICT RULE:
- Use both context tracks. If learned QA conflicts with document context,
  prefer learned QA.

NOTE: Drafting, quality-checking, and final-answer generation are handled by
the system AFTER compress_context returns. Do NOT try to write the final answer
in the same turn as your tool calls — your job is to drive retrieval and
trigger compression. The system will handle the remaining answer stages.
"""

_PROCESS_INSTRUCTIONS = """PROCESS (follow in this exact order — do NOT batch tool calls):
1. FIRST, call retrieve_documents 2-3 times with SHORT, semantically different queries.
   Wait for results before doing anything else. Do NOT call compress_context yet.
   GOOD: short noun-phrase queries from different angles of the topic.
   BAD:  rephrasings of the same angle ("what causes X", "X causes", "causes of X") — forbidden.
2. If results are insufficient → one more rephrased query, then stop retrieving.
3. AFTER retrieval is finished, call compress_context() ONCE with no arguments.
   This consolidates and deduplicates the learned-QA and document tracks
   separately. The raw retrieve_documents results will be removed from the chat
   after this — the compress_context tool result is your sole context from that
   point on. If the tracks conflict, prefer learned QA.
4. After compress_context returns, STOP emitting tool calls. In separate turns
   with no tools available, the system will handle any configured draft and
   quality-check stages, then generate the final answer from the compressed
   context. If the system reports a draft is insufficient, it will give you
   another retrieval round — use it to try genuinely different query angles.

OUTPUT FORMAT (final-answer turn only):
- Plain prose paragraphs. No headings, no bullet lists, no markdown.
- Citations appear ONLY inline within sentences as [Source: filename]. Never as a trailing list.
- Max 400 words. Stop when the question is answered — do not pad or restate.
- Do not repeat the same sentence or citation twice.
"""

DISTILL_PROMPT = """You are a knowledge distillation assistant.

Given:
- ORIGINAL QUESTION: {query}
- VERIFIED ANSWER: {answer}
- SOURCE CHUNKS: {chunks}

Your job: produce a JSON array (no markdown, no preamble) of 1-3 objects, each with:
  "question" : a distinct rephrasing of the original question
  "answer"   : a concise, self-contained answer grounded ONLY in the source chunks above

Rules:
- Do not invent facts not present in SOURCE CHUNKS.
- Each rephrasing must be semantically distinct (different vocabulary).
- Answers should be 2-5 sentences.
- Output ONLY the JSON array."""

GROUNDING_PROMPT = """You are a strict quality judge for a RAG system. Your job is to decide
whether the ANSWER actually addresses the USER QUERY using evidence from the RETRIEVED CHUNKS.

USER QUERY:
{query}

RETRIEVED CHUNKS (the only allowed source of facts):
{context}

ANSWER TO EVALUATE:
{answer}

Evaluate on these two criteria:
1. Relevance — does the answer address what the user actually asked?
2. Grounding — are the key claims in the answer traceable to the retrieved chunks (not invented)?

Reply with EXACTLY one of these two lines (nothing else):
OK
INSUFFICIENT — <one concise sentence explaining what is missing or wrong>"""

GROUNDING_PROMPT_WITH_THUMBDOWN = """You are a strict quality judge for a RAG system. Your job is to decide
whether the ANSWER actually addresses the USER QUERY using evidence from the RETRIEVED CHUNKS,
AND whether it specifically addresses the user's previously stated feedback about what was wrong.

USER QUERY:
{query}

PRIOR USER FEEDBACK (what was missing or wrong in earlier answers to this same question):
{thumbdown_feedback}

RETRIEVED CHUNKS (the only allowed source of facts):
{context}

ANSWER TO EVALUATE:
{answer}

Evaluate on these three criteria:
1. Relevance — does the answer address what the user actually asked?
2. Grounding — are the key claims in the answer traceable to the retrieved chunks (not invented)?
3. Feedback addressed — does the answer specifically address the gap or error the user flagged in
   their prior feedback above? If the feedback mentions specific missing topics or facts, those
   topics must appear in the answer with supporting evidence from the chunks.

Reply with EXACTLY one of these two lines (nothing else):
OK
INSUFFICIENT — <one concise sentence explaining what is missing or wrong, referencing the prior feedback if criterion 3 fails>"""

COMPRESSED_PLACEHOLDER = (
    "[Raw chunks for this retrieval have been compressed and consolidated. "
    "See the compress_context tool result for the canonical context.]"
)

_VALUE_VERIFY_PROMPT = """\
You are a JSON value-correction model. You are given two inputs:
1. RAW RESPONSE — the original, possibly messy text produced by an LLM.
2. VALIDATED JSON — a structurally correct JSON object/array derived from \
that raw response. Its keys and types are already valid.

Your job is to check whether the VALUES in VALIDATED JSON faithfully represent \
what the RAW RESPONSE actually said. Fix any value that was incorrectly \
extracted, truncated, misinterpreted, or defaulted to a placeholder when real \
data was present in the RAW RESPONSE.

RULES:
- Return ONLY the corrected JSON — no prose, no markdown, no code fences.
- Keep the exact same structure (keys, nesting, top-level type) as VALIDATED JSON.
- Do NOT add or remove keys.
- Do NOT fabricate information that is absent from the RAW RESPONSE — use the \
existing default (empty string, 0, [], or the first enum value) for genuinely \
missing fields.
- Preserve values that are already correct.

RAW RESPONSE:
{raw_response}

VALIDATED JSON:
{validated_json}

Corrected JSON:"""

_JSON_REPAIR_PROMPT = """\
You are a JSON repair model. You receive a malformed or partially broken string \
and return a single, valid, complete JSON {top_level} matching the required schema exactly.

Return ONLY a JSON {top_level} with this structure \
(no prose, no markdown, no code fences, no keys outside the schema):

{schema_block}

EXAMPLE INPUT:
{{"content": "Motor speed is regulated by voltage.", "sources": ["a.pdf",, "merged_from": "two"}}

EXAMPLE OUTPUT:
{{"content": "Motor speed is regulated by voltage.", "sources": ["a.pdf"], "merged_from": 2}}

RULES:
- Preserve all values from the raw input exactly — never fabricate data not present in the input.
- Each key must appear exactly once — if a key is duplicated, keep the last occurrence.
- If a required field is completely absent from the input, use its default: "" for strings, 0 for integers, [] for lists, or the first listed enum value.
- Output nothing outside the JSON value — no explanation, no comments, no trailing text.

RAW INPUT:
"""


_THIN  = "─" * 70
_THICK = "═" * 70
