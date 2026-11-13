# 03 — Open-Weight Models & Clinical Auto-Coding Strategy

All runtime AI operations in **MediExtract SPSS** use open-weight models capable of running 100% locally on agency hardware (offline, zero cloud data leakage, NDPA compliant).

---

## 1. Model Inventory & Licences

| Pipeline Stage | Model ID | Parameters | Licence | Role |
| :--- | :--- | :--- | :--- | :--- |
| **Stage 1a: Full-Form Vision & Layout** | `Qwen/Qwen2.5-VL-7B-Instruct` *(or `3B`)* | 7B / 3B | Apache-2.0 | Reads full scanned encounter pages, extracts structured JSON, and discovers schemas from blank PDFs |
| **Stage 1b: Lightweight Grounding & OCR** | `microsoft/Florence-2-large` | 0.77B | MIT | Fast CPU/GPU phrase grounding and region bounding-box extraction |
| **Stage 1c: Handwritten Line Specialist** | `microsoft/trocr-base-handwritten` | 0.33B | MIT | High-precision ink transcription on cropped handwritten text boxes |
| **Stage 2: Medical Semantic Auto-Coder** | `BAAI/bge-small-en-v1.5` | 33M | MIT | 384-d embeddings mapping handwritten clinical terms to SPSS numeric codes |
| **Stage 3: Analyst Report Narrative** | `meta-llama/Llama-3.2-3B-Instruct` | 3B | Llama 3.2 Community | Summarises statistical anomalies in plain English |

---

## 2. Confidence Scoring & Verification Gate

For every extracted field $f_i$:
1. The vision model outputs raw text $t_i$ and token log-probabilities $\log p_1, \dots, \log p_m$.
2. Field confidence is computed as the geometric mean probability:
   $$\text{Conf}_{\text{OCR}}(f_i) = \exp\left(\frac{1}{m}\sum_{j=1}^m \log p_j\right)$$
3. For coded clinical fields (`Diagnosis1..7`, `Investigation1..7`, `Treatment1..7`, `LGA`), the semantic auto-coder computes cosine similarity $\text{Sim}_{\text{code}}(t_i, c^*)$ against the best codebook label $c^*$:
   $$\text{Conf}_{\text{total}}(f_i) = \min\left(\text{Conf}_{\text{OCR}}(f_i),\ \text{Sim}_{\text{code}}(t_i, c^*)\right)$$
4. **Decision Rule:**
   - If $\text{Conf}_{\text{total}}(f_i) \ge 0.90$ and validation rules pass $\rightarrow$ `AUTO_VERIFIED`.
   - If $\text{Conf}_{\text{total}}(f_i) < 0.90$ $\rightarrow$ `NEEDS_REVIEW` (routed to Guided Verification Station with cropped image snippet).
