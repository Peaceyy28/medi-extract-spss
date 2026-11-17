---
version: 2.0.0
name: MediExtract — The Evidence Lab
tagline: Every value has a source.
theme: The Evidence Lab (Archive · Instrument · Research)
owner: Peace (Oluwanifemi Ojewusi · @Peaceyy28)
---

# DESIGN.md — MediExtract ("The Evidence Lab") Design System

> **Tagline:** *Every value has a source.*  
> **Personality:** Intelligent, precise, editorial, human, technically sophisticated, calm under high information density.

---

## 1. Color Palette & Surface Roles

The review workspace primarily uses the warm **Archive** environment (`#F3F0E8` / `#FBFAF6`). Darker **Instrument** surfaces (`#17201D`) are reserved for focused analytical, document-viewport, and technical control areas.

| Token | Name | Hex | Role & Usage |
| :--- | :--- | :--- | :--- |
| `--bg-archive` | **Archive Paper** | `#F3F0E8` | Primary workspace canvas background |
| `--bg-sheet` | **Clean Sheet** | `#FBFAF6` | Elevated panels, queue rows, interpretation cards |
| `--ink-carbon` | **Carbon Ink** | `#202824` | Primary interface text, high-contrast hairline rules |
| `--bg-graphite` | **Deep Graphite** | `#17201D` | Instrument surfaces (document viewport, keyboard shortcut bar, technical telemetry) |
| `--signal-oxide` | **Oxide Red** | `#B9553D` | Processing failures, validation exceptions, destructive/blocked states |
| `--signal-amber` | **Instrument Amber** | `#D5A34E` | Low-confidence extraction, flagged items, awaiting human review |
| `--signal-verified` | **Verified Green** | `#477660` | Confirmed/verified decisions, completed states |
| `--ink-grey` | **Technical Grey** | `#858B83` | Secondary metadata, technical labels, subtle dividers |

### Accessibility & Multi-Modal Status Rules
- **Never rely on color alone:** Every status pairs color + icon/glyph + explicit text label (`Awaiting Review`, `Verified`, `Flagged`, `Validation Exception`, `Processing Failed`).
- **Exception-based default:** A document with one uncertain field never forces the reviewer to manually re-inspect every other field.

---

## 2. Typography

| Role | Font Family | Usage |
| :--- | :--- | :--- |
| **Interface & Headings** | `IBM Plex Sans` | Navigation, queue rows, field labels, decision controls |
| **Editorial Statements** | `Newsreader` | Occasional editorial headers, workstation tagline (*Every value has a source.*) |
| **Technical Metadata** | `IBM Plex Mono` | Document IDs, page numbers, OCR confidence, codebook similarity, timestamps, shortcut keys |

---

## 3. Core Workstation Architecture (Batch 1: Evidence Review Workstation)

1. **Upload & Ingestion Boundary**
   - Supports JPG, PNG, and multi-page PDF uploaded directly through MediExtract.
   - Zero preloaded fictitious clinic data and zero fabricated scanner connections.
   - Honest backend integration boundary: displays real local file/page metadata and clear pending-backend state when the extraction server is not connected.

2. **Batch Review Queue**
   - Compact batch progress visualization (Total pages, Processed, Awaiting review, Verified, Flagged, Processing failures).
   - Searchable, filterable, and paginated queue (never renders thousands of thumbnails simultaneously).
   - Filters: `All unresolved`, `Low-confidence extraction`, `Unrecognised clinical terms`, `Missing or incomplete values`, `Validation failures`, `Processing failures`, `Flagged items`.
   - Views: `Needs Review`, `All Documents`, `Verified`, `Flagged`, `Processing Failed`.

3. **Evidence Split (Signature Workstation View)**
   - **Left — Original Evidence:** Displays the actual uploaded JPG/PNG/PDF page with Zoom (`+`/`-`), Pan, Fit-to-Page, Full-Page view, Page navigation, region highlight overlay (when coordinates exist), and honest missing-source fallback.
   - **Right — Machine Interpretation:** Strictly separates **OCR Confidence** from **Codebook Similarity**. Shows Field Name, Extracted Text, Suggested Codebook Value, Validation Information, Source Ref, and Review Status.
   - **Human Decision & Audit Trail:** `Confirm`, `Edit` (preserving original extracted text, allowing codebook selection or marking handwriting unreadable/unrecognised), and `Flag`—recording full provenance and audit history without silent overwrites.
   - **Keyboard Shortcuts (Disabled inside inputs):** `Enter` (Confirm & Next), `E` (Edit), `F` (Flag), `←`/`→` (Prev/Next issue), `+`/`-` (Zoom).
