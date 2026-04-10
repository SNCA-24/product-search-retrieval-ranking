# UI Plan & Spec

## **UI Plan**

Build a **single-page search console** with **2 layers**:

### **Layer 1: must-have**

This is the real ROI layer.

* search box  
* mode selector  
  * BM25  
  * vector  
  * hybrid  
  * hybrid \+ LTR  
* results list  
* per-result:  
  * title  
  * brand  
  * color  
  * product id  
  * rank  
  * scores  
  * small metadata block  
* request latency  
* top-level stats  
  * mode used  
  * results returned  
  * p50/p95 for current sampled session if available  
  * retrieval/ranking time split if available

### **Layer 2: nice-to-have but still worth it**

Add only if low effort.

* expandable “why this ranked” panel  
* score breakdown  
* badges like:  
  * exact brand match  
  * title overlap  
  * vector hit  
  * reranked  
* side-by-side compare mode for 2 retrieval modes on same query  
* query history in current session  
* failure-analysis flag button or “save example”

## **What not to build**

Do **not** spend time on:

* user auth  
* full analytics backend  
* dashboards with persistence  
* advanced charts everywhere  
* complex frontend framework  
* pagination/infinite scroll unless needed  
* mobile optimization  
* admin panel

Those are low ROI for this repo.

## **Best UI framing for portfolio**

Position it as:

**Search relevance demo and qualitative inspection UI**

Not as:

“full production frontend”

That keeps expectations correct and makes the UI support the ML/system story instead of becoming the story.

## **Good final feature set**

This is the version I’d actually recommend you ship:

### **Top bar**

* search input  
* search button  
* mode dropdown  
* optional filter chips:  
  * brand  
  * color  
* optional “show debug details” toggle

### **Summary strip**

* query  
* mode  
* total results  
* end-to-end latency  
* retrieval latency  
* ranking latency  
* reranking latency if applicable

### **Results cards**

Each result card shows:

* rank number  
* product title  
* brand / color / locale  
* product id  
* short searchable text preview  
* score panel:  
  * BM25 score  
  * vector similarity  
  * hybrid/RRF indicator  
  * LTR score  
* badges:  
  * brand match  
  * title exact/partial match  
  * reranked  
* expandable debug section:  
  * feature values  
  * rank positions from different modes  
  * raw metadata

### **Optional comparison drawer**

For one selected query:

* compare top 5 from BM25 vs hybrid vs hybrid+LTR

This is high value if easy to add.

## **Styling level to target**

You do **not** want barebones.  
You also do **not** want “frontend project.”

Aim for:

* clean modern layout  
* cards  
* search console feel  
* subtle shadows  
* badges/pills  
* expandable accordions  
* nice spacing  
* one accent color  
* dark mode optional only if trivial

That is enough.

## **Recommended stack**

Since you chose FastAPI \+ HTML:

* FastAPI  
* Jinja2 templates  
* minimal JS for interactivity  
* Tailwind via CDN or a small custom CSS file  
* maybe HTMX if you want fast interactivity without React

### **Best practical choice**

Use:

* **FastAPI \+ Jinja2 \+ Tailwind**  
* optional tiny JS/HTMX

This gives the best polish-to-effort ratio.

## **Timeboxed ROI plan**

### **Phase A — 80% ROI**

Build in 1 focused session:

* search box  
* mode selector  
* results cards  
* latency strip  
* debug toggle  
* decent styling

### **Phase B — extra polish only if easy**

Add:

* compare mode  
* feature breakdown accordion  
* filter chips

Stop there.

## **Final recommendation**

Yes, add a UI.  
Make it **polished but thin**.

The winning principle is:

**The UI should make the ranking system legible, not become a separate product build.**

## **Exact scope I would lock**

Ship this:

* one-page search console  
* four modes  
* result cards with scores \+ metadata  
* latency panel  
* debug expandable section  
* clean styling

That is the right ROI line for GitHub and interviews.

## UI Spec

Yes — let’s **lock the UI spec**.

This matches the plan you uploaded: a **single-page search relevance demo and qualitative inspection UI**, not a full frontend product, with four modes, result cards, latency panel, and expandable debug details. It also fits the PRD serving surface and core retrieval modes: `/search`, `/debug/search`, plus BM25, vector, hybrid, and LTR-backed flows.

# **Locked UI thesis**

Build **one polished search console page** that makes the ranking system legible.

## **Positioning**

Use this wording in the README/UI:  
**Search relevance demo and qualitative inspection UI**

Not:  
**Full production frontend**

---

# **Final scope to ship**

## **Must-have**

* one-page search console  
* search box  
* mode selector  
* results cards  
* latency summary strip  
* debug toggle  
* polished styling

## **Nice-to-have if easy**

* compare drawer  
* filter chips  
* query history  
* feature accordion polish

## **Explicitly out of scope**

* auth  
* persistence-heavy analytics  
* dashboards backend  
* admin panel  
* complex frontend framework  
* mobile-first work  
* pagination unless needed later

---

# **Page layout**

## **1\. Header**

Top-left:

* project name: **ESCI Search Console**  
* subtitle: **Search relevance demo for BM25, vector, hybrid, and LTR**

Top-right:

* small badge showing environment:  
  * `local demo`  
  * optional `OpenSearch connected`

---

## **2\. Query control bar**

Single horizontal control row.

### **Controls**

* **Search input**  
  * placeholder: `Search products, e.g. "wireless mouse logitech"`  
* **Search button**  
* **Mode selector**  
  * BM25  
  * Vector  
  * Hybrid  
  * Hybrid \+ LTR  
* **Top-K selector**  
  * 10 / 20 / 50  
* **Debug toggle**  
  * off by default

### **Optional low-cost additions**

* brand filter  
* color filter  
* reset button

---

## **3\. Summary strip**

A thin metrics/status band directly under the search bar.

### **Show**

* query text  
* selected mode  
* results returned  
* end-to-end latency  
* retrieval latency  
* ranking latency  
* reranking latency if applicable  
* optional request id

### **Layout**

Use small stat cards or pills.

Example:

* `Mode: Hybrid + LTR`  
* `Results: 20`  
* `E2E: 168 ms`  
* `Retrieval: 61 ms`  
* `Ranking: 82 ms`  
* `Rerank: 0 ms`

---

## **4\. Main content area**

Two-column responsive layout.

### **Left column**

Results list  
This should take most of the width.

### **Right column**

Compact debug/legend panel  
This avoids cluttering the results too much.

---

# **Results card spec**

Each result should be a clean card.

## **Card header**

* **Rank number**  
* **Product title**  
* subtle mode/result badges

## **Metadata row**

* brand  
* color  
* locale  
* product id

## **Preview row**

* one short searchable text preview  
  * title \+ first useful description snippet

## **Score panel**

Show only the relevant scores for the selected mode, but preserve placeholders for consistency.

### **Possible score fields**

* BM25 score  
* vector similarity  
* hybrid/RRF indicator or hybrid rank  
* LTR score

### **Recommended rendering**

Use 2x2 compact stat chips:

* `BM25: 11.23`  
* `Vector: 0.812`  
* `Hybrid Rank: 4`  
* `LTR: 2.14`

## **Badges**

Low-cost, high-value badges:

* brand match  
* exact/partial title match  
* vector hit  
* reranked

## **Action row**

* `Show details` accordion button

---

# **Expandable debug panel per result**

When expanded, show:

## **Ranking explanation block**

* original BM25 rank  
* original vector rank  
* hybrid rank  
* final LTR rank

## **Feature snapshot**

Only key features, not the whole raw vector:

* title overlap  
* brand match  
* color match  
* text completeness  
* vector similarity  
* retrieval scores

## **Raw metadata block**

* product id  
* locale  
* source if available  
* optional label only in evaluation/demo mode

This is enough for qualitative inspection without overwhelming the page.

---

# **Right-side debug/legend panel**

Keep this narrow and helpful.

## **Show**

* mode explanation  
* what each score means  
* current top-K  
* selected filters  
* latency target reminder  
  * `Target P95: 250 ms`  
* optional system note:  
  * `Default deployable path: Hybrid`  
  * `High-quality path: Hybrid + LTR`

This helps tie the UI back to the engineering story.

---

# **Optional compare drawer**

Only add if easy.

## **Trigger**

Button:  
**Compare modes**

## **Behavior**

For the current query, show top 5 side-by-side:

* BM25  
* Hybrid  
* Hybrid \+ LTR

## **Purpose**

This is high ROI because it makes ranking differences obvious in screenshots.

If it feels costly, skip it for v1.

---

# **Visual style guide**

## **Style target**

* clean modern search console  
* subtle shadows  
* rounded cards  
* one accent color  
* neutral background  
* badges/pills  
* accordion details  
* strong spacing

## **Recommended stack**

* FastAPI  
* Jinja2  
* Tailwind  
* minimal vanilla JS  
* optional HTMX only if it simplifies partial updates

## **Design preference**

* light theme first  
* dark mode only if trivial  
* no heavy animations

---

# **Interaction rules**

## **Default behavior**

* mode defaults to **Hybrid**  
* top-K defaults to **10**  
* debug defaults to **off**

## **Search flow**

1. user enters query  
2. selects mode  
3. hits search  
4. summary strip updates  
5. results render as cards  
6. user optionally expands details

## **Error states**

Need three simple states:

* no results  
* backend unavailable  
* loading

Keep these polished but simple.

---

# **Exact fields to expose in UI**

## **At top-level**

* query  
* mode  
* top\_k  
* total\_results  
* end\_to\_end\_ms  
* retrieval\_ms  
* ranking\_ms  
* reranking\_ms  
* request\_id

## **Per result**

* rank  
* title  
* brand  
* color  
* locale  
* product\_id  
* preview\_text  
* bm25\_score  
* vector\_score  
* hybrid\_rank or hybrid\_indicator  
* ltr\_score  
* badges  
* debug\_details

---

# **Final v1 page wireframe**

┌──────────────────────────────────────────────────────────────────────┐  
│ ESCI Search Console                          \[local demo\]            │  
│ Search relevance demo for BM25, vector, hybrid, and LTR             │  
├──────────────────────────────────────────────────────────────────────┤  
│ \[ Search query ........................................ \] \[Search\]   │  
│ Mode: \[Hybrid ▼\]   Top-K: \[10 ▼\]   \[Debug details ☐\]   \[Reset\]      │  
├──────────────────────────────────────────────────────────────────────┤  
│ Query: wireless mouse logitech   Mode: Hybrid   Results: 10         │  
│ E2E: 168 ms   Retrieval: 61 ms   Ranking: 82 ms   Rerank: 0 ms      │  
├───────────────────────────────────────┬──────────────────────────────┤  
│ 1\. Logitech M510 Wireless Mouse       │ Mode notes                  │  
│ Brand: Logitech  Color: Black         │ \- BM25 \= lexical baseline   │  
│ Locale: us   Product ID: B00...       │ \- Hybrid \= default online   │  
│ Preview: Comfortable full-size ...    │ \- LTR \= quality mode        │  
│ \[BM25 11.2\] \[Vec 0.81\] \[LTR 2.14\]     │                              │  
│ \[brand match\] \[vector hit\]            │ Current target P95: 250 ms  │  
│ \[Show details ▼\]                      │                              │  
│                                       │ Filters: none               │  
│ 2\. Logitech MX Master 3 ...           │                              │  
│ ...                                   │                              │  
└───────────────────────────────────────┴──────────────────────────────┘

---

# **Locked build order**

## **UI v1**

* search box  
* mode selector  
* results cards  
* summary strip  
* debug accordion  
* clean styling

## **UI v1.1 if time remains**

* filter chips  
* compare drawer  
* query history

---

# **Final recommendation**

This is the version I would lock and build.

It is:

* polished enough for GitHub screenshots  
* product-like enough for interviews  
* thin enough to stay high ROI  
* directly supportive of the retrieval/ranking story rather than distracting from it