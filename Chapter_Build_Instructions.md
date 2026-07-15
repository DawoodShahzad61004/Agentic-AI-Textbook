# Chapter Build Instructions & Template

*Self-Learning Agentic RAG System — Book Project*
*Canonical, self-contained spec for producing any chapter as a Word (.docx) file.*

This file is the single source of truth for building a chapter. It merges (1) the
build-time instructions for the deliverable, (2) the full Document Template
Specification derived from the reference **Chapter 3 — Setting Up Your Development
Environment**, and (3) the pedagogical/author-voice pattern every chapter must follow.
Treat every value below as **exact, not approximate**.

---

## 0. Build Instructions (the deliverable at a glance)

- **Output format:** a Word `.docx` file, rendering identically to the reference chapter.
- **Font:** Times New Roman throughout the readable text; Courier New for code, commands, file paths, and identifiers. No third font anywhere.
- **Page margins:** Top / Left / Right = **2.5 cm**; Bottom = **1.5 cm**.
- **Diagrams:** every diagram is inserted into the Word file as an **SVG / image** (not drawn with Word shapes). Conceptual diagrams and procedural flowcharts are both required elements.
- **Source of format:** the attached reference chapters (PDFs) are the authority for look-and-feel; this spec records what was extracted from them.
- **Print target:** the book is printed in **black-and-white**, so diagram color must never carry information (see §7).

### Required pedagogical elements in every chapter

Each chapter must consistently incorporate:

- **Illustrative examples** that ground each concept in a real-world scenario.
- **Intuitive analogies** that turn complex mechanisms (vector spaces, retrieval pipelines, agentic loops) into reusable mental models.
- **Precise terminology**, used deliberately and consistently.
- **Clear definitions** of every new, important, or technically loaded term at its point of first use.
- **Skeleton code templates** — minimal, modular, intentionally extensible scaffolding, not monolithic copy-paste solutions.
- **Conceptual diagrams** that visualize architectures, data flows, and decision boundaries.
- **Procedural flowcharts** that walk through each pipeline step-by-step.

The goal: by the end of a chapter the reader should be able to **build, debug, and teach** the concept — not merely recognize it.

---

## 1. Page Layout

US Letter (8.5″ × 11″), portrait. Margins are asymmetric — wider on three sides,
narrower at the foot — leaving room for a discreet header rule and page-number footer.

| Property | Value | Notes |
| --- | --- | --- |
| Page size | US Letter (8.5″ × 11″) | 12240 × 15840 DXA |
| Orientation | Portrait | |
| Top margin | 2.5 cm | 1417 DXA |
| Right margin | 2.5 cm | 1417 DXA |
| Left margin | 2.5 cm | 1417 DXA |
| Bottom margin | 1.5 cm | 850 DXA |
| Header offset | 0.5 cm | 708 DXA |
| Footer offset | 0.5 cm | 708 DXA |
| **Content width** | **9070 DXA ≈ 6.30″** | page width − left − right |

### Header and footer

Present but minimal; a single thin gray rule separates each from the body. Empty in
the reference chapter — chapter title and page number may be added if needed.

| Element | Specification |
| --- | --- |
| Header rule | Bottom border, single line, color #CCCCCC, size 2 (0.25pt), space 4 |
| Footer rule | Top border, single line, color #CCCCCC, size 2 (0.25pt), space 4 |
| Header/footer text font | Times New Roman 9pt, color #888888 (muted gray) |
| Footer tab stop | Center at 4680 DXA (page-number alignment) |

---

## 2. Typography

Small, deliberate font stack: Times New Roman for everything readable, Courier New for
everything machine-shaped. Size ladder: 24 / 16 / 13 / 12 / 11 / 10 / 9 pt, each with a role.

| Role | Font | Size | Weight & Color |
| --- | --- | --- | --- |
| Body paragraph | Times New Roman | 11pt | Regular, #000000 |
| Code (inline & block) | Courier New | 10pt | Regular, #000000 |
| Chapter title (cover) | Times New Roman | 24pt | Bold, #000000 |
| Chapter heading (in flow) | Times New Roman | 16pt | Bold, #000000 |
| Section heading (4.1, 4.2 …) | Times New Roman | 16pt | Bold, #2E74B5 |
| Sub-section heading | Times New Roman | 13pt | Bold, #2E74B5 |
| Bold inline emphasis | Times New Roman | 11pt | Bold, #000000 |
| Italic inline emphasis | Times New Roman | 11pt | Italic, #000000 |
| Figure caption | Times New Roman | 10pt | Italic, #555555 |
| Table header | Times New Roman | 11pt | Bold, #FFFFFF on dark blue |
| Header / footer | Times New Roman | 9pt | Regular, #888888 |

### Paragraph spacing and alignment

- Body text is **justified**.
- Headings are **left-aligned**.
- Captions and the chapter cover lines are **centered**.
- Default line spacing inside paragraphs: single (multiplier 1.25 for code, 1.5 for callouts).
- Default spacing-after on body paragraphs: 6pt (120 DXA). Heading spacing-before: 12–14pt (240–280 DXA); spacing-after: 4–6pt (80–120 DXA).

---

## 3. Color Palette

Five intentional groups. Use these exact hex values — not "close enough" — so chapters
read continuously in sequence.

### Headings and accents

| Use | Hex |
| --- | --- |
| Section heading text | #2E74B5 (brand blue) |
| Sub-section heading text | #1F4D78 (deeper blue) |
| Caption / figure subtitle text | #555555 (dark gray) |
| Header / footer text | #888888 (muted gray) |

### Callout box palette (3 variants)

| Callout kind | Border / title text | Fill | Used for |
| --- | --- | --- | --- |
| Definition (blue) | #2E5FA3 | #EEF4FB | Term definitions |
| Analogy (gold) | #C47B00 | #FFFBF0 | Mental models |
| Common pitfall (rust) | #B05000 | #FFF8F0 | Warnings, gotchas |

### Code blocks and tables

| Element | Value |
| --- | --- |
| Code-block fill | #F5F5F5 (light gray) |
| Code-block border | #CCCCCC, single, 0.5pt |
| Table header fill | #2C3E6B (dark blue) |
| Table header text | #FFFFFF (white), bold |
| Table alternate-row fill | #F7F9FC (very pale blue) |
| Table border | #CCCCCC, single, 0.5pt |

---

## 4. Headings and Section Numbering

Numbered hierarchy `N → N.M → N.M.K`, mirroring the Book Index. The cover page shows
three centered, increasingly large lines, followed by an italic epigraph in #555555.

| Level | Example | Style |
| --- | --- | --- |
| Cover — Part label | PART II — BUILDING THE INGESTION PIPELINE | 12pt bold #555555 centered |
| Cover — Chapter number | Chapter 4 | 18pt bold #2E74B5 centered |
| Cover — Title | The Document Structure | 15pt bold black centered |
| Cover — Epigraph | "Quote here." | 11pt italic #555555 centered |
| Chapter heading (in flow) | Chapter 4 — The Document Structure | 16pt bold #1A3A5C, left |
| Section (H2) | 4.1 What a Document Object Really Is | 16pt bold #2E74B5, left |
| Sub-section (H3) | Layer 1 — What the loader gave you | 13pt bold #1F4D78, left |

---

## 5. Callout Boxes

Callouts are single-cell tables with a colored fill, a thin border on three sides, and a
thicker **3pt accent border on the left**. The first paragraph is the title — always of
the form **"Label — Title"**, bold, in the accent color. Body paragraphs follow in black
11pt. Cell margins: 140 DXA top/bottom, 200 DXA left/right.

**Definition — example**
> An immutable, two-field data container defined in `langchain_core.documents`. It holds `page_content` (a string) and `metadata` (a dictionary).

**Analogy — example**
> Think of a Document as a padded envelope: inside is a letter (`page_content`); on the outside is the address label, postmark, return address, tracking barcode (`metadata`).

**Common pitfall — example**
> ChromaDB metadata filters are exact-match. "Policy", "policy", and "policies" are three distinct values.

### When to use which

- **Definition (blue)** — the first introduction of any technical term. Exactly one per term.
- **Analogy (gold)** — a mental-model crutch for a non-trivial mechanism (~one per major section).
- **Common pitfall (rust)** — a mistake actually seen breaking, with the fix. Not hypothetical risks.

---

## 6. Code Blocks, Tables, and Lists

### Code blocks

Single-cell tables: 0.5pt #CCCCCC border on all four sides, #F5F5F5 fill, Courier New
10pt content. Each line is its own paragraph, line spacing 260, no spacing-after. Cell
margins: 120 DXA top/bottom, 180 DXA left/right. Comments (`#`) are inline in the same
monospaced font — no syntax-highlighting color.

### Reference tables

White-on-dark-blue header (#2C3E6B fill, white bold text); body rows alternate white and
#F7F9FC; continuous #CCCCCC border. Always use DXA widths (never percent); column widths
must sum to the table width. Cell margins: 80 DXA top/bottom, 160 DXA left/right.

### Bulleted lists

Round dot (•) at level 0, 720 DXA hanging indent. Same 11pt Times New Roman body font and
justification as surrounding text. Keep bullets ≤ 3 lines; 3–7 items per list. Longer or
denser material becomes a table or a sub-section.

---

## 7. Diagrams — Print-Friendly Color Rules

Every diagram is printed in **black-and-white**. Rules below were derived by converting
the reference chapter's figures to grayscale.

### The two failure modes to avoid

1. **Hue-only distinctions disappear.** Green "Yes" vs red "No" both become medium-dark gray — the reader cannot tell the success path from the failure path.
2. **Similar-luminance shapes look identical.** Mid blue (#2E5FA3) and mid gold (#C47B00) have nearly identical luminance and flatten to the same gray.

### The five rules

1. **Carry information on luminance, never on hue.** Three box categories → light / medium / dark fill, not blue / gold / rust.
2. **Always pair color with a non-color signal** — checkmark vs cross, solid vs dashed border, the word "Recommended" in bold, arrow direction, or a different shape.
3. **Pick fills from the safe luminance ladder** — only #FFFFFF, #F2F2F2, #D9D9D9, #808080, #2C3E6B. Avoid all mid-saturation colors.
4. **Test every diagram in grayscale before sign-off.** If two different-meaning boxes now match, or a success/warning label lost its emphasis, the diagram fails — fix it before shipping.
5. **Reserve color for non-essential charm.** Color is decoration; shape, position, label, and luminance are information.

### Print-safe diagram palette

| Token | Hex | When to use |
| --- | --- | --- |
| Fill — white | #FFFFFF | Default box, optional / inactive items |
| Fill — very light gray | #F2F2F2 | Secondary box, supporting role |
| Fill — light gray | #D9D9D9 | Tertiary level / grouping band |
| Fill — mid gray | #808080 | Highlighted item, white text on top |
| Fill — dark navy | #2C3E6B | Primary / featured box, white text on top |
| Border — solid | #000000, 1–1.5pt | Default |
| Border — dashed | #000000, 1pt dash | Optional / proposed / future-state |
| Border — double | #000000, 1.5pt double | Current focus / recommended choice |
| Text — dark | #000000 | On any fill lighter than #808080 |
| Text — light | #FFFFFF | On #808080 and #2C3E6B only |

### Shape vocabulary

| Shape | Meaning |
| --- | --- |
| Rectangle (rounded corners) | A component, module, file, or stable artifact |
| Rectangle (sharp corners) | A data object or value (Document, vector, record) |
| Diamond | A decision point in a flowchart |
| Ellipse / pill | Start or end of a process |
| Cylinder | A persistent store (vector DB, file system, database) |
| Solid arrow | Required data or control flow |
| Dashed arrow | Optional flow, fallback, or future extension |

### Labelling and emphasis without color

- **Bold** the title text inside every diagram box; regular weight for body labels only.
- Mark the recommended option with a thicker border (1.5pt double or 2pt solid), never a brighter color.
- Place a small ✓ or ✗ glyph beside binary states; never rely on green/red.
- Separate parallel paths by **horizontal position**, not color. In left-to-right diagrams, put the success path on the right.
- Caption every figure with **"Figure X.Y — short title."**, italic, 10pt, #555555, centered, below the image.

### Figure sizing

| Property | Value |
| --- | --- |
| Width | 4.88 inches (4457700 EMU; or a percent of content width) |
| Height | Variable, by aspect ratio |
| Resolution | ≥ 200 dpi at print size; 300 dpi is safer |
| Format | Insert as SVG / image (PNG rasterised acceptable; verify the renderer) |
| Alignment | Centered, with figure caption immediately below |

Content area is ≈ 6.30″, so a 4.88″ figure leaves comfortable side margins. Set figure
dimensions in the source SVG/diagram tool, then export at ≥ 200 dpi.

---

## 8. Build-Time Configuration

Values that reproduce the reference document when generating with a docx-js script.

```js
// Page setup
sections: [{
  properties: {
    page: {
      size:   { width: 12240, height: 15840 },        // US Letter
      margin: { top: 1417, right: 1417, bottom: 850, left: 1417 },
    },
  },
  children: [/* paragraphs, tables, images */],
}]

// Default styles (Times New Roman 11pt body)
styles: {
  default: {
    document: { run: { font: "Times New Roman", size: 22 } },
  },
}

// Bullet numbering
numbering: {
  config: [{
    reference: "bullets",
    levels: [{
      level: 0,
      format: LevelFormat.BULLET,
      text: "\u2022",
      alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } },
    }],
  }],
}
```

### Conversion shortcuts

| From | To | Multiplier |
| --- | --- | --- |
| Centimetres | DXA | × 567 |
| Inches | DXA | × 1440 |
| Points | DXA | × 20 |
| Points (font size) | Half-points (sz) | × 2 |
| Inches | EMU (image extents) | × 914400 |
| Pixels at 96 dpi | Inches | ÷ 96 |

---

## 9. Author Voice and Pedagogical Pattern

Format alone is not enough — every chapter follows a recognisable cadence. The reference
chapter's structure is the canonical pattern.

- Open every chapter with a **one-line epigraph** (italic, centered, #555555).
- Follow with a **2–3 paragraph chapter intro** stating what the reader will be able to do by the end.
- Number every section as **N.M** with a heading; sub-sections take a **13pt H3 heading** without numbering.
- Use **exactly one Definition box** at the first appearance of any technical term.
- Use **one Analogy box** per non-trivial mechanism (~one per major section).
- Reserve **Common pitfall boxes** for things actually seen breaking, not hypothetical risks.
- Every figure is **referenced from the body text by number** ("See Figure 4.2") and captioned beneath it.
- Close every chapter with **one paragraph** that names the next chapter and the bridge between them.

Every chapter bridges the *why* and the *how*: the reader should not just know what a
Self-Learning Agentic RAG System is, but be able to build one, debug one, and teach it.

---

## 10. Chapter-Build Checklist

Work through this in order when producing a chapter file:

1. Read the target chapter's outline in the Book Index; adopt its `N.M` numbering.
2. Set page size, margins (2.5 / 2.5 / 2.5 / 1.5 cm), header/footer rules per §1.
3. Set default font Times New Roman 11pt; Courier New 10pt for code per §2.
4. Build the cover page (Part label / Chapter number / Title / epigraph) per §4.
5. Write the 2–3 paragraph intro stating end-of-chapter capabilities per §9.
6. Draft sections in prose that bridges why and how; add examples and precise terms.
7. Add one Definition box per new term; one Analogy per non-trivial mechanism; Common pitfall boxes only for real, observed traps (§5).
8. Format all code as skeleton templates in code-block tables (§6).
9. Design conceptual diagrams and procedural flowcharts to §7 rules; **grayscale-test each one**; export ≥ 200 dpi; insert as SVG/image at 4.88″ wide, centered, captioned.
10. Reference every figure by number in the body text.
11. Apply the table palette to all reference tables (§6).
12. Close with the one-paragraph bridge to the next chapter.
13. Final pass: confirm palette hex values are exact, fonts consistent, and the chapter renders identically to the reference.
