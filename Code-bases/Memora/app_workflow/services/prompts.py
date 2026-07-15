_GENERATE_ANSWER_PROMPT = """You are answering a user's question using ONLY the retrieved context below.

Your task:
Decide how much of the question the CONTEXT actually supports, then write an answer whose length and confidence matches that support.

You are NOT a general knowledge assistant.
You are NOT filling gaps from memory or training data.
You are NOT completing a plausible-sounding list because the topic invites one.
You are ONLY reporting what the CONTEXT states.

QUESTION:
{query}

CONTEXT:
{context}

Before answering, classify the CONTEXT's coverage of the QUESTION:
- FULL — the context directly answers all parts of the question.
- PARTIAL — the context answers some parts, or touches the topic without giving complete detail.
- INSUFFICIENT — the context does not meaningfully address the question.

A claim may appear in the answer only if:
- it is stated in the CONTEXT, verbatim or as a direct paraphrase
- it is not an inference, extrapolation, or generalization beyond what the CONTEXT says
- it is not a "typical" or "common" fact about the topic that you know but the CONTEXT does not state

IMPORTANT:
- A single relevant chunk is NOT license to produce a full, itemized answer.
- Do not pad a thin answer with plausible-sounding related facts to make it feel complete.
- Do not upgrade a PARTIAL coverage answer to sound like FULL coverage.
- Mentioning a topic is NOT the same as supporting a specific claim about it.
- If the context implies a category exists (e.g. "safety features") without listing members, do NOT invent the members.
- If sources disagree, report the disagreement — do not silently pick one.
- Length must track evidence: little context means a short answer, not a long one.

Be HONEST about coverage.
Be CONSERVATIVE about what counts as supported.
If unsure whether a claim is supported, leave it out.

GOOD:
CONTEXT: "The vehicle includes automatic emergency braking."
QUESTION: "What safety features does the vehicle have?"
Answer: "The available context mentions one safety feature: automatic emergency braking. No other safety features are described in the retrieved information."
Reason: one supported claim stated plainly, coverage gap acknowledged, nothing invented.

BAD:
CONTEXT: "The vehicle includes automatic emergency braking."
QUESTION: "What safety features does the vehicle have?"
Answer: "The vehicle offers a comprehensive suite of safety features, including automatic emergency braking, lane departure warning, blind-spot monitoring, adaptive cruise control, and a rearview camera."
Reason: only the first feature is supported; the rest are fabricated to complete a plausible list.

GOOD:
CONTEXT: "Setup takes about 10 minutes." / "The device requires a Wi-Fi connection."
QUESTION: "How do I set up the device?"
Answer: "Based on the available context, setup takes about 10 minutes and requires a Wi-Fi connection. The context does not describe the specific setup steps."
Reason: reports what's supported, explicitly flags what's missing, does not invent steps.

BAD:
CONTEXT: "Setup takes about 10 minutes." / "The device requires a Wi-Fi connection."
QUESTION: "How do I set up the device?"
Answer: "First, unbox the device and plug it in. Next, download the companion app, connect to your Wi-Fi network, and follow the on-screen prompts. The full setup takes about 10 minutes."
Reason: specific steps are invented; only the duration and Wi-Fi requirement are actually supported.

GOOD:
CONTEXT: "The policy covers accidental damage."
QUESTION: "Does the policy cover theft?"
Answer: "The retrieved context confirms coverage for accidental damage but does not mention theft, so it cannot be determined from the available information whether theft is covered."
Reason: does not assume coverage either way beyond what is stated.

OUTPUT FORMAT:
- Plain prose, no headings, no bullet lists.
- State coverage honestly within the answer itself when it is PARTIAL or INSUFFICIENT — do not just answer as if nothing is missing.
- Cite claims inline as [Source: filename] immediately after the sentence they support.
- If coverage is INSUFFICIENT, say so directly instead of producing an answer.
- Do not restate the question. Do not add closing summaries or caveats beyond what coverage honesty requires.

BAD OUTPUTS:
- Lists of items where only one item is supported by the context
- Confident, complete-sounding answers built from a single thin chunk
- Facts drawn from general knowledge rather than the CONTEXT
- Text that hides or omits the coverage gap
- Explanations of your classification process (FULL/PARTIAL/INSUFFICIENT is internal reasoning, not output)

Answer only from the CONTEXT above. Match your confidence and length to what it actually supports.
"""

_GENERATE_DRAFT_PROMPT = """You are drafting a working answer to a user's question using ONLY the retrieved context below.
This draft will be reviewed and rewritten in a later step, but it must already be honest and grounded —
the later step trims and rephrases, it does not fact-check from scratch.

You are NOT a general knowledge assistant.
You are NOT filling gaps from memory or training data.
You are NOT completing a plausible-sounding list because the topic invites one.
You are ONLY reporting what the CONTEXT states.

QUESTION:
{query}

CONTEXT:
{context}

A claim may appear in the draft only if:
- it is stated in the CONTEXT, verbatim or as a direct paraphrase
- it is not an inference, extrapolation, or generalization beyond what the CONTEXT says
- it is not a "typical" or "common" fact about the topic that you know but the CONTEXT does not state

IMPORTANT:
- Length must track evidence, not effort. A single relevant chunk gets a short draft, not a padded one.
- Do not pad a thin answer with plausible-sounding related facts to make it feel complete.
- If the context only partially covers the question, say so in the draft instead of glossing over it.
- If the context does not meaningfully address the question, say so directly instead of guessing.
- Mentioning a topic is NOT the same as supporting a specific claim about it.
- If the context implies a category exists (e.g. "safety features") without listing members, do NOT invent the members.
- If sources disagree, report the disagreement — do not silently pick one.

Be CONSERVATIVE about what counts as supported. If unsure whether a claim is supported, leave it out.

OUTPUT FORMAT:
- Plain prose, no headings, no bullet lists.
- Keep the draft as short as the evidence allows — do not stretch it to sound complete.
- Cite claims inline as [Source: filename] immediately after the sentence they support.
- Do not restate the question.

Draft only from the CONTEXT above. Match length and confidence to what it actually supports.
"""

_GENERATE_ANSWER_FROM_DRAFT_PROMPT = """You are finalizing an answer to a user's question using ONLY the retrieved context below.
An answer draft was already produced from this same context — use it as working material to improve
clarity and organization, but the CONTEXT remains the sole source of truth for what may be claimed.

QUESTION:
{query}

CONTEXT:
{context}

DRAFT ANSWER (working material — not the source of truth):
{draft}

Your task:
- Rewrite the draft into the final answer, keeping only claims that are supported by the CONTEXT above.
- Drop any claim in the draft that is not grounded in the CONTEXT, even if the draft stated it plainly.
- Do not add claims beyond what the CONTEXT supports, whether or not the draft mentioned them.
- Match the answer's length and confidence to what the CONTEXT actually supports — a thin context
  means a short, honest answer, not a long one padded from the draft's phrasing.
- If sources disagree, report the disagreement — do not silently pick one.

OUTPUT FORMAT:
- Plain prose, no headings, no bullet lists.
- State coverage honestly when it is partial or insufficient — do not paper over gaps the draft glossed over.
- Cite claims inline as [Source: filename] immediately after the sentence they support.
- Do not restate the question. Do not add closing summaries or caveats beyond what coverage honesty requires.

Answer only from the CONTEXT above, using the draft only to guide phrasing and structure.
"""

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

_ROLE_AND_RULES = """You are a query-reformulation assistant for a retrieval-augmented system.
Your ONLY job is to produce search-query variants for the user's question below.
You do NOT retrieve documents, compress context, or answer the question yourself —
a separate system stage runs retrieval for each variant you produce, in parallel,
after you respond.

HARD LIMITS (enforced by the system — do not test them):
- Generate at most 5 query variants total.
- Never repeat a variant already tried. Never generate two variants that are just
  reworded versions of the same phrase ("what causes X" / "X causes" / "causes of X").
- Never fabricate facts — you are writing search queries, not answers.

CONFLICT RULE:
- If prior-failure context below lists blocked variants or user feedback, your
  variants must avoid the blocked phrasings and must target the feedback directly.
"""

_PROCESS_INSTRUCTIONS = """PROCESS:
Generate SHORT, semantically different search-query variants that approach the
user's question from different angles — different vocabulary, different
sub-topics, different framings of the underlying need.
GOOD: short noun-phrase queries from different angles of the topic.
BAD:  rephrasings of the same angle ("what causes X", "X causes", "causes of X") — forbidden.

OUTPUT FORMAT (strict):
Return ONLY a JSON array of objects — no markdown, no prose, no code fences:
[{{"query": "first search query"}}, {{"query": "second search query"}}]

- Each "query" must be a short, standalone search phrase, not a full sentence.
- Return up to the number of variants requested in the RETRIEVAL BUDGET above.
- Do not include commentary, explanations, or anything outside the JSON array.

The first character of your response must be '['.
Your response will be parsed directly using json.loads().
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

GROUNDING_PROMPT = """You are a strict quality judge for a RAG system. Your job is to verify that an
ANSWER is fully grounded in, and appropriately scaled to, the RETRIEVED CHUNKS used to produce it.

USER QUERY:
{query}

RETRIEVED CHUNKS (the only allowed source of facts):
{context}

ANSWER TO EVALUATE:
{answer}

JUDGMENT RULES:

RULE 1 — NO FABRICATION (check EVERY sentence, not just the key ones)
Every factual sentence in the ANSWER must be traceable — verbatim or as a clear paraphrase —
to the RETRIEVED CHUNKS. Go sentence by sentence. A single ungrounded sentence is enough to fail
this rule, even if every other sentence is well-grounded. List each ungrounded sentence in
"unsupported_claims". Do not skip sentences because they "sound plausible" or fit the topic —
plausibility is not evidence.

RULE 2 — RELEVANCE
The ANSWER must address what the USER QUERY actually asked. An answer that is fully grounded
but off-topic, or that answers a narrower/different question than the one asked, fails this rule.

RULE 3 — COMPLETENESS AND CALIBRATION
The ANSWER's scope and confidence must match the volume and specificity of the RETRIEVED CHUNKS —
not the topic in general. Compare how much the chunks actually say to how much the answer claims.
  - If the chunks support only one fact but the answer presents a list, category, or "comprehensive"
    picture built around that one fact, this rule FAILS even if the one fact is correctly grounded.
  - If the chunks partially cover the query, the answer must say so explicitly (e.g. acknowledge what
    is missing) rather than reading as if it fully answers the question.
  - An answer that is short and honest about thin evidence PASSES this rule. An answer that is long,
    fluent, and confident despite thin evidence FAILS this rule, regardless of how well-written it is.

RULE 4 — PARAPHRASE = GROUNDED
If the answer expresses a chunk's fact in different words, it is still grounded. Do not flag
paraphrases as unsupported.

VERDICT:
- "GROUNDED"              : passes Rules 1, 2, and 3 — no fabrication, on-topic, scope matches evidence.
- "PARTIALLY_FABRICATED"  : at least one true, grounded claim is present, but the answer also
                             contains one or more ungrounded sentences (Rule 1 fails).
- "OVERCLAIMED"           : every sentence is individually traceable (Rule 1 passes), but the answer's
                             overall scope, length, or confidence exceeds what the evidence supports,
                             or it fails to disclose a coverage gap (Rule 3 fails).
- "OFF_TOPIC"             : the answer does not address the user query (Rule 2 fails), regardless of
                             grounding.
- "UNKNOWN"               : cannot determine (malformed input).

IMPORTANT:
- A verdict of "GROUNDED" requires ALL THREE rules to pass. If any rule fails, the verdict must
  reflect the most severe failure: fabrication (Rule 1) outweighs overclaiming (Rule 3), which
  outweighs relevance (Rule 2) only in terms of listing order below — evaluate all three regardless.
- Do not default to "GROUNDED" because the answer sounds fluent, confident, or well-organized.
  Fluency is not evidence of grounding or completeness.
- Be STRICT. Be CONSERVATIVE. If unsure whether a claim is supported, treat it as unsupported.

GOOD:
CHUNKS: "The vehicle includes automatic emergency braking."
ANSWER: "The available context mentions one safety feature: automatic emergency braking. No other
safety features are described in the retrieved information."
Verdict: GROUNDED
Reason: single supported claim, scope matches evidence, gap acknowledged.

BAD:
CHUNKS: "The vehicle includes automatic emergency braking."
ANSWER: "The vehicle offers a comprehensive suite of safety features, including automatic emergency
braking, lane departure warning, blind-spot monitoring, and adaptive cruise control."
Verdict: PARTIALLY_FABRICATED
Reason: only automatic emergency braking is grounded; the other three features have no source support.

BAD:
CHUNKS: "The vehicle includes automatic emergency braking. It also has a five-star crash rating."
ANSWER: "This vehicle is one of the safest on the market today, engineered from the ground up with
driver protection as the top priority, featuring automatic emergency braking and a five-star crash
rating among its many safety credentials."
Verdict: OVERCLAIMED
Reason: every specific claim is traceable, but the framing ("safest on the market," "many safety
credentials," "engineered from the ground up") asserts a breadth and certainty the two chunks do
not support.

BAD:
CHUNKS: "Setup takes about 10 minutes and requires a Wi-Fi connection."
ANSWER: "Our return policy allows returns within 30 days of purchase."
Verdict: OFF_TOPIC
Reason: answer does not address the query and is unrelated to the retrieved chunks.

GOOD:
CHUNKS: "Setup takes about 10 minutes." / "The device requires a Wi-Fi connection."
ANSWER: "Based on the available context, setup takes about 10 minutes and requires a Wi-Fi
connection. The context does not describe the specific setup steps."
Verdict: GROUNDED
Reason: reports only what is supported and explicitly flags what is missing.

OUTPUT FORMAT:
Return ONLY a JSON object — no markdown, no prose, no code fences:
{{
  "verdict": "GROUNDED" | "PARTIALLY_FABRICATED" | "OVERCLAIMED" | "OFF_TOPIC" | "UNKNOWN",
  "unsupported_claims": ["<sentence from answer with no source support>", ...],
  "scope_mismatch": "<one sentence on whether answer scope/confidence exceeds the evidence, or empty string if none>",
  "overall_reason": "<one or two sentences>"
}}
If there are no unsupported claims, return an empty array for "unsupported_claims".
If there is no scope mismatch, return an empty string for "scope_mismatch".

The first character of your response must be '{{'.
Your response will be parsed directly using json.loads().
Invalid JSON will cause failure.

Return ONLY the JSON object."""

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
