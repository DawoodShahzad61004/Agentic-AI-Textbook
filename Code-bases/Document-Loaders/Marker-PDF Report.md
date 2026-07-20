# ASSESSMENT OF THE MARKER-PDF LIBRARY

## Introduction
This report evaluates the observed working of the marker-pdf library by comparing
six source PDFs in source/ with the corresponding Markdown files in
marker_results/. The test corpus contains 251 pages and includes procurement
forms, an EPC agreement, a long legal terms document, engineering scopes of work,
technical specifications, tables, title blocks, diagrams, text boxes, lists,
footnotes, colored text, and a conventionally designed book chapter. It examines two distinct aspects of conversion quality:

1. Content extraction: whether Marker recognizes and preserves the words,
   emphasis, lists, footnotes, headings, and table cell text.
2. Structural and visual reconstruction: whether the Markdown preserves reading
   order, semantic hierarchy, page boundaries, table geometry, merged cells,
   borders, forms, text boxes, images, and repeated page furniture.

The findings describe the tested Marker workflow and its delivered outputs. Some
failures—especially referenced images that were not written beside the Markdown—
may arise from export or integration configuration rather than from the core
recognition model alone. They are nevertheless real failures of the evaluated
end-to-end workflow.



## Overall Assessment
Marker performs well as a content-oriented PDF-to-Markdown extractor when the
source consists mainly of linear prose or relatively simple tables. Across the
corpus, output word counts remain close to the text available from the PDFs. The
91-page legal document contains approximately 45,450 PDF words and 44,443 output
words; the RAG chapter contains approximately 4,023 PDF words and 4,032 output
words. This supports the qualitative observation that Marker usually captures
ordinary body text and can produce useful material for search, indexing,
retrieval-augmented generation, and rough content review.

The library also demonstrates several more specific strengths:

- All-capital text and ordinary block text are generally recognized accurately.
- Bold and italic emphasis is often retained in Markdown.
- Footnote text is retained in the tested agreement material.
- Colored text is recognized as text, although its color is not preserved.
- Simple tables with a fixed number of columns are usually recognized as tables.
- Some tables with changing column counts are converted acceptably when their
  layout is not too dense.
- Multilevel or nested lists are detected, although their original numbering and
  indentation are not always preserved.
- Captions and most surrounding prose remain available even where the associated
  figure is missing.

Marker is considerably weaker as a layout-faithful reconstruction system. Its
Markdown output does not reliably preserve page design or document semantics.
The principal weaknesses are:

- Complex tables and forms are flattened into pipe tables that cannot express
  merged cells, row spans, column spans, selective borders, or precise geometry.
- Narrow or multirow headers may be split into individual letters and syllables
  separated by "br" tags, making cells unreadable.
- Tables without visible internal borders may not be recognized as tables, while
  letter-format forms may be incorrectly classified as tables.
- Internal and external borders, shading, cell alignment, column widths, revision
  boxes, and engineering title blocks are not faithfully represented.
- Heading levels are inferred inconsistently. Running headers, ordinary labels,
  definitions, list items, and subordinate headings are frequently promoted to
  H1-H4.
- Repeated headers and footers are mixed into the reading stream instead of being
  recognized as page furniture and removed or separately represented.
- Page breaks are absent, which obscures pagination, continuation relationships,
  and the point at which repeated page elements occur.
- Centered content becomes left-aligned, and signature blocks, blank fields, and
  fillable-form spacing lose their function.
- Text boxes, callouts, colored panels, and highlighted annotations are flattened
  into headings and paragraphs without their visual boundaries.
- The Markdown contains 131 image references, but all 131 target files are
  missing from marker_results/. The delivered output therefore loses every
  referenced logo, map, diagram, engineering graphic, and page image.
- The RAG chapter contains at least 26 mojibake sequences, showing an encoding or
  downstream file-handling defect despite otherwise excellent prose extraction.

Accordingly, the evaluated workflow is suitable for text-centric ingestion with
post-processing, but it is not suitable without remediation for archival
reproduction, contract/forms processing, engineering-document reconstruction,
fillable documents, or any task in which visual relationships carry meaning.



## Document-by-Document Assessment

### 1-9-RFT 6000042656_ ENQ22-108_ EPC Rejuvenation Project_1-250
   250 pages; assessment: MODERATE for text recovery, HIGH for cross-page structure

The page-level review confirms that Marker can recover unusually small or
visually emphasized text. Small highlighted passages on PDF pages 9 and 11 are
identified and transcribed correctly; the compact, organized highlighted text
on page 16 is also reproduced accurately; and the highlighted footnote on page
124 is retained. The highlighted material spanning pages 14-15 is reordered,
but the result remains human-readable. These examples reinforce the broader
finding that text recognition is often stronger than layout reconstruction.

Several structural errors remain. The repeated header title, "RFT Title: [EPC
for Train 1 & 2 Rejuvenation Project]," is missing from every page. On page 5,
the Company Contact Details table is mapped incorrectly: one principal row is
expanded into multiple Markdown rows, "Contracts Department" is split across
two rows, and "ADNOC LNG" is merged into the preceding row. The words are
largely present, but the row associations—and therefore the meaning of the
contact record—are unreliable.

Pagination and cross-page continuity also degrade in the longer document. The
table of contents on page 204 omits its page numbers. From approximately page
220 onward, lists that continue across pages are interrupted by running-header
text, breaking list continuity and mixing page furniture into the content.
These failures make the raw output unsuitable for page-based navigation or
automatic interpretation of long lists without cleanup.

### 2-9-RFT 6000042656_ ENQ22-108_ EPC Rejuvenation Project_251-500
   continuation volume; assessment: HIGH for table and sequence reliability

The page-level review of the continuation volume identifies a significant
failure around PDF pages 61-62. The table content is reordered or jumbled, and
section number "2.1.2" is emitted twice. Content following that duplication
then begins to disappear. This is more serious than a presentation-only defect:
it indicates that a dense cross-page table or nearby layout transition can
produce both duplicated and omitted content, so word-count similarity alone
cannot establish completeness. Pages 61-62 require comparison with the source
before this output is used for retrieval, compliance review, or downstream
chunking.

### 2_1-9-RFT 6000042656_ ENQ22-108_ EPC Rejuvenation Project_1-250
   11 pages; assessment: CRITICAL for complex tables/forms, MODERATE for prose

Marker correctly recognizes most block text, all-capital labels, bold/italic
emphasis, and colored text. The Bid Timetable and other regular fixed-column
tables are broadly usable. The test notes also show that some multilevel headers
inside text boxes are transcribed correctly and that tables with stable column
counts perform reasonably well.

The main failure is the handling of complex forms. Appendix 2 and Appendix 3 on
PDF pages 3-4 contain colored form bands, merged headers, changing column counts,
and narrow cells. Their Markdown headers are broken into fragments such as
"R F T" and numerous isolated syllables or letters. Extra blank columns
appear, contractual/commercial and technical sections lose their grouping, and
the tables become difficult or impossible to read.

Appendix 4 is a letter-format submission form, but Marker represents it as a
one-column table. This destroys paragraph structure, indentation, address and
signature layout, and the distinction between narrative text and form fields.
Pages 8-10 likewise lose merged section labels, column proportions, orange
instructions, and continuation relationships in the Technical and Commercial
Bid Structure tables.

The hierarchy is inconsistent: appendices appear at different heading levels,
subordinate labels are promoted to H1, and "ADNOC Classification: Internal" is
incorrectly treated as a document heading. The source title and RFT number are
not handled consistently across pages. One referenced image is missing. Overall,
this document shows that Marker works for regular text and simpler tables but
breaks down when table geometry itself communicates meaning.

### 3_1-9-RFT 6000042656_ ENQ22-108_ EPC Rejuvenation Project_1-250
   9 pages; assessment: HIGH for form fidelity, MODERATE for text

Body text, footnotes, and much of the agreement content are retained. Nested
lists are recognized, and a table with varying column structure is more
successful here than the malformed tables in document 1. This demonstrates that
changing column counts alone do not guarantee failure; density, merged regions,
cell width, and source geometry also influence the result.

The conversion does not preserve layout. Centered titles are left-aligned and
there is no page-break representation. Nested list numbers and letters are often
kept as literal text while Markdown bullets are added, weakening the original
legal hierarchy.

The key-provisions form on PDF pages 4-5 loses exact merged-cell relationships,
widths, shading, and dependable borders. The signature page loses line lengths,
spacing, and the two-party grouping required for a usable agreement form. The
Special Conditions table loses its shaded header and field geometry. The table
of contents retains words and page numbers but loses dot leaders, alignment, and
navigation. Heading levels are also unreliable: "ANNEXURE 2" is H1 while a
normal sentence beginning "2. The PARTIES..." is H3. The ADNOC logo is referenced
but its image file is absent.

### 4_1-9-RFT 6000042656_ ENQ22-108_ EPC Rejuvenation Project_1-250
   91 pages; assessment: MODERATE

This is Marker's strongest result for large-scale text recovery. Approximately
44,443 Markdown words were produced from about 45,450 PDF words, and no major
page-scale omission was identified. The document is predominantly continuous
legal prose, which suits Marker's content extraction strengths.

The weakness is semantic structure. Defined terms such as "ABANDONMENT",
"AFFILIATE", and "DEFECT" are treated as headings, and even continuation text
such as "and shall include" is assigned a heading level. Major clauses,
subclauses, definitions, and normal prose do not form a stable hierarchy. A TOC,
section-based retrieval system, or legal clause parser built directly on these
headings would therefore be unreliable.

Repeated document codes, tender numbers, classifications, page numbers, headers,
and footers enter the reading stream at page boundaries. Numbered and lettered
subclauses lose indentation and nesting, while the lack of page markers makes it
hard to distinguish genuine repetition from page furniture. The content remains
useful for full-text search, but requires header/footer removal and hierarchy
reconstruction before semantic use.

### 5_1-9-RFT 6000042656_ ENQ22-108_ EPC Rejuvenation Project_1-250
   80 pages; assessment: CRITICAL as a standalone deliverable

Marker captures a substantial amount of technical text: approximately 15,490
output words compared with about 15,961 words extractable from the PDF. It also
recognizes a number of tables and section labels. This makes the output potentially
useful as a text index after cleanup.

However, this document depends heavily on engineering page frames, title blocks,
revision tables, cover sheets, maps, diagrams, and visually structured pages.
Marker produces 79 image links, but none of the 79 image files is present. Cover
and divider pages—including PDF pages 1, 5-7, 9, 32, and 80—are consequently
reduced to repeated text and broken references. Logos, maps, drawings, borders,
revision boxes, and other visual evidence are unavailable.

Engineering title blocks are flattened into ordinary tables without faithful
merged cells, outer and internal borders, alignment, or revision grouping. The
running project banner is repeatedly emitted as H1; the document contains 86 H1
headings across 80 pages. Genuine headings also alternate among H1-H4, creating
a contradictory outline. Repeated metadata interrupts paragraphs and lists, and
tables continuing across pages do not preserve reliable header or continuation
semantics. The output is therefore inadequate for engineering-document review or
archival use unless the missing assets and structure are restored.

### 6_1-9-RFT 6000042656_ ENQ22-108_ EPC Rejuvenation Project_1-250
   48 pages; assessment: HIGH

Text recovery is again relatively strong: approximately 13,513 Markdown words
were produced from about 13,899 PDF words. Technical requirements, many bullets,
and table cell text remain searchable.

All 48 referenced images are missing. Page header tables, logos, revision cells,
and engineering frames therefore cannot be reviewed from the output. The full
tender banner is marked as H1 on most pages; the output contains 51 H1 headings
for a 48-page document. Genuine subsections are mostly H4 regardless of depth,
and numbered items such as "3. HAZOP Reviews" are also made H4.

Nested bullets and requirements lose some indentation and list depth, while
continuation paragraphs can become detached from their parent items at page
boundaries. Highlights and colored annotations survive only as plain text, with
no indication of emphasis. Pipe tables retain some content but not widths,
shading, repeated headers, merged cells, or border styles. This output can support
keyword retrieval but not reliable reconstruction of the technical specification.

### Chapter_1_Why_RAG
   12 pages; assessment: HIGH for encoding and visuals, LOW for basic text loss

This is the clearest demonstration of Marker's prose strength. Approximately
4,032 Markdown words correspond to about 4,023 PDF words, and no major body-text
passage is missing. Definitions, examples, captions, and explanatory prose are
largely recovered in sensible reading order. The comparison table also retains
its essential cell text.

Structural and delivery problems remain. The Transformer figure and RAG workflow
figure are referenced but both files are missing. Their captions survive without
the illustrations they describe. The part title, chapter label, numbered
sections, and minor labels such as "Tokens", "Embeddings", "Definition", and
"Concrete examples" are promoted to H1 inconsistently. Colored Definition,
Analogy, Key Insight, Example, and warning boxes are flattened into headings and
plain paragraphs, losing boundaries, colors, padding, and visual association.

The comparison table loses its header color, border treatment, and column
proportions. Most importantly, at least 26 mojibake sequences corrupt punctuation
and symbols, including the em dash and approximately-equal sign. The underlying
text recognition is strong, but encoding normalization and asset export are
required before publication or ingestion.

 

## Discussion
The results indicate that Marker operates primarily as a semantic-content
extractor rather than a page-layout reproduction engine. It appears to identify
text blocks, classify certain blocks as headings, lists, tables, captions, or
images, and then serialize those classifications into Markdown. This design is
effective when the source reading order is linear and the desired output is
searchable text. It is inherently less expressive when the source depends on
two-dimensional relationships that Markdown cannot encode.

Table behavior illustrates this distinction. Regular grids with stable columns
can be represented adequately as pipe tables. Once a table uses merged headers,
changing column counts, borderless grouping, nested form sections, narrow cells,
or text boxes, the same serialization loses information. Forced line breaks then
attempt to fit recognized text into incorrect cell geometry, producing the
letter-by-letter fragmentation seen in Appendix 2. Some variable-column tables
do work, so the limitation is not purely the number of columns; it is the combined
complexity of segmentation, merged regions, reading order, and Markdown's table
model.

The heading results suggest that visual prominence is being used without enough
document-level context. Large or repeated running banners become H1, while legal
definitions and ordinary labels become H2-H4. Marker does not consistently infer
the global outline from numbering, recurrence, location, and neighboring blocks.
For retrieval systems, this matters because incorrect headings create bad chunks,
misleading metadata, and false section boundaries even when the words themselves
are correct.

Page furniture and page boundaries are another systemic issue. Repeated headers,
footers, classifications, tender numbers, revision labels, and page numbers are
not reliably separated from content. Because page breaks are omitted, downstream
processing cannot easily determine where these elements recur or reconstruct
cross-page tables and lists. Adding explicit page markers and repetition-based
header/footer filtering would materially improve the output.

The detailed page checks also show that page furniture can fail in both
directions: the main RFT title is omitted from the repeated header throughout the
first 250-page volume, while other running-header text is injected into lists
from about page 220 onward. Similarly, the page-204 table of contents retains its
entries but drops the page numbers needed for navigation. Cross-page validation
must therefore check for missing furniture and pagination as well as unwanted
header/footer intrusion.

The image result should be interpreted as an end-to-end packaging defect. Marker
recognized image regions well enough to create 131 links, but the tested workflow
did not deliver the linked files. This is different from failing to detect an
image, yet the practical result is the same for the user: the Markdown is broken
and visually incomplete. The conversion runner should export image assets to a
stable relative directory and validate every link before declaring success.

The tested workflow would benefit from the following remediation:

1. Export all referenced images and perform an automated broken-link check.
2. Preserve page markers and bounding-box metadata in an accompanying JSON file.
3. Detect repeated headers and footers across pages and remove or tag them.
4. Infer headings from numbering, recurrence, position, and document-wide
   hierarchy rather than visual size alone.
5. Use HTML tables with rowspan/colspan, or page images plus accessible text, for
   complex forms that cannot be represented in pipe-table Markdown.
6. Add quality rules for excessive br tags, one-letter cell fragments, empty
   columns, inconsistent row widths, and implausible heading counts.
7. Preserve list markers and nesting as true Markdown ordered/unordered lists.
8. Normalize output to UTF-8 and scan for mojibake before saving.
9. Retain visual semantics such as callout type, highlighting, border presence,
   and cell shading in HTML or structured metadata when Markdown is insufficient.
10. Apply document-specific post-processing for legal clauses, engineering title
    blocks, procurement forms, and book-style callouts.

For RAG and search applications, the recommended workflow is therefore not to use
the raw Markdown directly. It should first pass through asset validation,
encoding repair, header/footer removal, heading normalization, table-quality
checks, and—where needed—manual review of complex pages. The strong prose recovery
then becomes a valuable foundation rather than being undermined by structural
noise.



## Conclusion
The evaluated marker-pdf workflow is effective at recovering text from diverse
PDFs and is especially capable on conventional prose. It retains most body text,
often preserves bold and italic emphasis, captures footnotes and colored text,
and handles many simple tables. These qualities make it a useful first-stage
extractor for search, indexing, RAG ingestion, and content analysis.

It is not, in its current tested configuration, a faithful document conversion
solution. Complex forms, merged and border-sensitive tables, engineering title
blocks, page furniture, page breaks, heading hierarchy, nested lists, text boxes,
and visual styling are inconsistently represented. The complete absence of 131
referenced image assets and the encoding corruption in the RAG chapter are major
delivery defects.

The appropriate conclusion is therefore conditional: Marker is strong for
text-centric extraction but requires systematic post-processing and validation
for structured documents. It should not be used as the sole authoritative
representation of contracts, tender forms, engineering specifications, or
visually rich publications. With reliable asset export, UTF-8 normalization,
page-aware cleanup, hierarchy reconstruction, and a richer representation for
complex tables and callouts, it could serve as a robust component in a broader
document-ingestion pipeline.

The supplemental page-level review sharpens that conclusion: highlighted and
very small text may be recovered correctly even when surrounding structure is
not, while table row associations, TOC page numbers, section sequencing, and
content after a cross-page table can be duplicated, reordered, or omitted.
High-stakes use therefore requires targeted source-to-output checks at table and
page boundaries, not only aggregate word-count comparison.
