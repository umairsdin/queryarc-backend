const API_BASE = "http://127.0.0.1:8000"; // same origin in production

const urlInput = document.getElementById("url-input");
const analyzeBtn = document.getElementById("analyze-btn");
const loader = document.getElementById("loader");
const statusText = document.getElementById("status-text");
const resultsWrapper = document.getElementById("results-wrapper");

// Result containers
const llmViewContent = document.getElementById("llm-view-content");
const evaluationContent = document.getElementById("evaluation-content");
const summaryBlockEl = document.getElementById("summary-block");
const definitionsBlockEl = document.getElementById("definitions-block");
const faqBlockEl = document.getElementById("faq-block");
const canonicalBlockEl = document.getElementById("canonical-block");

// Arc score UI
const arcScoreEl = document.getElementById("arc-score");
const scoreAioEl = document.getElementById("score-aio");
const scoreAeoEl = document.getElementById("score-aeo");
const scoreGeoEl = document.getElementById("score-geo");

// PDF download
const downloadPdfBtn = document.getElementById("download-pdf-btn");

function setLoading(isLoading) {
  if (!analyzeBtn || !loader) return;
  if (isLoading) {
    loader.classList.remove("hidden");
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = "Analyzing…";
  } else {
    loader.classList.add("hidden");
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "Run analysis";
  }
}

function setStatus(message, isError = false) {
  if (!statusText) return;
  statusText.textContent = message || "";
  statusText.style.color = isError ? "#f97373" : "var(--muted)";
}

async function analyzeUrl() {
  const url = (urlInput && urlInput.value || "").trim();

  if (!url) {
    setStatus("Enter a full page URL to analyze.", true);
    return;
  }

  try {
    setStatus("Sending page to LLM engine…");
    setLoading(true);

    const response = await fetch(`${API_BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed: ${response.status}`);
    }

    const data = await response.json();
    renderResults(data);
    setStatus("Analysis complete.");
  } catch (err) {
    console.error(err);
    setStatus(err.message || "Something went wrong.", true);
  } finally {
    setLoading(false);
  }
}

function renderResults(data) {
  if (!data) return;

  const {
    page_metadata,
    executive_summary,
    llm_interpretation,
    summary_block,
    definitions_block,
    faq_block,
    canonical_resources_block,
    score_matrix,
    fanout_query_analysis,
    clarity_readability,
    eeat_block,
    fix_roadmap,
  } = data;

  renderArcRank(score_matrix, clarity_readability, faq_block, fanout_query_analysis);
  renderLlmView(llm_interpretation);
  renderEvaluation({
    page_metadata,
    executive_summary,
    score_matrix,
    fanout_query_analysis,
    clarity_readability,
    eeat_block,
    fix_roadmap,
  });
  renderBlocks(summary_block, definitions_block, faq_block, canonical_resources_block);
}

/**
 * Arc Rank hero score + AIO/AEO/GEO
 * Mapping:
 * - Overall = score_matrix.final_score (0–100).
 * - AIO = clarity_readability.score (0–10).
 * - AEO = faq_block.score (0–10).
 * - GEO = fanout_query_analysis.coverage_score (0–10).
 */
function renderArcRank(scoreMatrix, clarityBlock, faqBlock, fanoutBlock) {
  if (!scoreMatrix) return;

  const overall = typeof scoreMatrix.final_score === "number" ? scoreMatrix.final_score : 0;
  const aio = clarityBlock && typeof clarityBlock.score === "number" ? clarityBlock.score : 0;
  const aeo = faqBlock && typeof faqBlock.score === "number" ? faqBlock.score : 0;
  const geo =
    fanoutBlock && typeof fanoutBlock.coverage_score === "number"
      ? fanoutBlock.coverage_score
      : 0;

  if (arcScoreEl) {
    arcScoreEl.textContent = isNaN(overall) ? "—" : overall.toString();
  }

  if (scoreAioEl) {
    scoreAioEl.textContent = aio ? aio.toFixed(1) : "—";
    scoreAioEl.title =
      "AIO – AI Index Optimization: clarity and readability of your content for AI models.";
  }

  if (scoreAeoEl) {
    scoreAeoEl.textContent = aeo ? aeo.toFixed(1) : "—";
    scoreAeoEl.title =
      "AEO – Answer Engine Optimization: how well your FAQs and answers cover user questions.";
  }

  if (scoreGeoEl) {
    scoreGeoEl.textContent = geo ? geo.toFixed(1) : "—";
    scoreGeoEl.title =
      "GEO – Generative Engine Optimization: how much topical depth and coverage the page provides.";
  }
}

/**
 * LLM interpretation card
 */
function renderLlmView(view) {
  if (!view || !llmViewContent) return;

  const {
    primary_topic,
    secondary_topics = [],
    detected_intent,
    summary_llm_generated,
    key_claims_llm_detected = [],
    confidence_level,
  } = view;

  llmViewContent.innerHTML = `
    <div class="llm-kv">
      <div class="llm-kv-label">Primary topic</div>
      <div class="llm-kv-value">${primary_topic || "—"}</div>

      <div class="llm-kv-label">Detected intent</div>
      <div class="llm-kv-value">${detected_intent || "—"}</div>

      <div class="llm-kv-label">Confidence</div>
      <div class="llm-kv-value">${confidence_level || "—"}</div>
    </div>

    ${
      secondary_topics.length
        ? `<h4 class="llm-subheading">Secondary topics</h4>
           <div class="tag-list">
             ${secondary_topics.map((t) => `<span class="tag">${t}</span>`).join("")}
           </div>`
        : ""
    }

    ${
      summary_llm_generated
        ? `<h4 class="llm-subheading">How AI summarizes this page</h4>
           <p class="llm-summary">${summary_llm_generated}</p>`
        : ""
    }

    ${
      key_claims_llm_detected.length
        ? `<h4 class="llm-subheading">Key claims AI detects</h4>
           <ul class="list">
             ${key_claims_llm_detected.map((c) => `<li>• ${c}</li>`).join("")}
           </ul>`
        : ""
    }

    <p class="llm-help-text">
      This view is a snapshot of how an LLM might interpret your page. Compare it with your intent
      to see if the page is telling the right story.
    </p>
  `;
}

/**
 * Evaluation, scores, roadmap card
 */
function renderEvaluation(ctx) {
  if (!evaluationContent) return;

  const {
    page_metadata = {},
    executive_summary = {},
    score_matrix = {},
    fanout_query_analysis = {},
    clarity_readability = {},
    eeat_block = {},
    fix_roadmap = {},
  } = ctx || {};

  const {
    overall_llm_readiness_score = 0,
    verdict = "",
    main_issue = "",
    top_3_fixes = [],
  } = executive_summary;

  const {
    summary_block = 0,
    definitions = 0,
    faq = 0,
    fanout_match = 0,
    canonical_resources = 0,
    structure = 0,
    clarity = 0,
    eeat = 0,
    final_score = 0,
  } = score_matrix;

  const {
    sub_questions_generated = [],
    coverage_score = 0,
    main_gaps = [],
  } = fanout_query_analysis;

  const { issues: clarity_issues = [], fixes: clarity_fixes = [] } = clarity_readability;

  const {
    score: eeat_score = 0,
    author_info_found = false,
    expertise_visibility = "",
    experience_signals = "",
    trust_signals = "",
    missing_elements = [],
  } = eeat_block;

  const {
    immediate_fixes_next_24h = [],
    medium_priority_next_7_days = [],
    long_term_next_30_days = [],
  } = fix_roadmap;

  const url = page_metadata.url || "";

  const scoreRows = [
    ["Summary block", summary_block, "Quality of the LLM summary block for quick retrieval."],
    ["Definitions", definitions, "Coverage and clarity of key term definitions."],
    ["FAQ", faq, "How well FAQs cover real user questions."],
    ["Fanout coverage", fanout_match, "How well content answers the model's sub-questions."],
    ["Canonical resources", canonical_resources, "Internal + external anchors for context."],
    ["Structure", structure, "Heading hierarchy and section layout."],
    ["Clarity / readability", clarity, "Language clarity, flow, and examples."],
    ["EEAT", eeat, "Expertise, experience, authority, and trust signals."],
  ];

  const verdictClass =
    verdict === "Ready" || verdict === "Partially Ready"
      ? "verdict-pill verdict-pill--good"
      : "verdict-pill verdict-pill--poor";

  evaluationContent.innerHTML = `
    <div class="${verdictClass}">
      <span>Verdict: <strong>${verdict || "—"}</strong></span>
      <span class="llm-ready-flag" title="If 'Yes', this page is in a decent state for AI-powered search.">
        LLM-ready: ${final_score >= 60 ? "Yes" : "No"}
      </span>
    </div>

    <p class="eval-help-text">
      This report estimates how ready ${url || "this page"} is for LLMs, answer engines, and
      generative search. Focus first on the weakest scores and the 24-hour fixes.
    </p>

    ${main_issue ? `<p class="main-issue"><strong>Main issue:</strong> ${main_issue}</p>` : ""}

    ${
      top_3_fixes && top_3_fixes.length
        ? `<h4 class="eval-subheading">Top 3 fixes</h4>
           <ul class="list">
             ${top_3_fixes.map((f) => `<li>• ${f}</li>`).join("")}
           </ul>`
        : ""
    }

    <div class="score-badges-row">
      <span class="score-pill" title="Overall Arc Rank on a 0–100 scale.">
        Overall score: <strong>${overall_llm_readiness_score}</strong>/100
      </span>
      <span class="score-pill" title="Fanout coverage: how well content answers the model's sub-questions.">
        Fanout coverage: <strong>${coverage_score.toFixed
          ? coverage_score.toFixed(1)
          : coverage_score}</strong>/10
      </span>
      <span class="score-pill" title="EEAT signals: expertise, experience, authority, and trust.">
        EEAT: <strong>${eeat_score}</strong>/10
      </span>
    </div>

    <div class="score-bars">
      ${scoreRows
        .map(([label, value, help]) => {
          if (typeof value !== "number") return "";
          const pct = Math.min(10, Math.max(0, value)) * 10;
          return `
            <div class="score-row">
              <span class="score-label" title="${help}">${label}</span>
              <div class="score-bar-track">
                <div class="score-bar-fill" style="width:${pct}%;"></div>
              </div>
              <span class="score-value">${value.toFixed(1)}</span>
            </div>
          `;
        })
        .join("")}
    </div>

    <h4 class="eval-subheading">Fix roadmap</h4>
    <div class="fix-roadmap-grid">
      <div class="fix-card fix-card--now">
        <h5>Next 24 hours</h5>
        <ul class="list">
          ${
            immediate_fixes_next_24h.length
              ? immediate_fixes_next_24h.map((i) => `<li>• ${i}</li>`).join("")
              : "<li>• Add substantial article content and key sections.</li>"
          }
        </ul>
      </div>
      <div class="fix-card fix-card--week">
        <h5>Next 7 days</h5>
        <ul class="list">
          ${
            medium_priority_next_7_days.length
              ? medium_priority_next_7_days.map((i) => `<li>• ${i}</li>`).join("")
              : "<li>• Add FAQ, definitions, and improve internal linking.</li>"
          }
        </ul>
      </div>
      <div class="fix-card fix-card--month">
        <h5>Next 30 days</h5>
        <ul class="list">
          ${
            long_term_next_30_days.length
              ? long_term_next_30_days.map((i) => `<li>• ${i}</li>`).join("")
              : "<li>• Strengthen EEAT with author info, case studies, and references.</li>"
          }
        </ul>
      </div>
    </div>

    ${
      main_gaps && main_gaps.length
        ? `<h4 class="eval-subheading">Fanout coverage gaps</h4>
           <ul class="list">
             ${main_gaps.map((g) => `<li>• ${g}</li>`).join("")}
           </ul>`
        : ""
    }

    ${
      clarity_issues && clarity_issues.length
        ? `<h4 class="eval-subheading">Clarity & readability</h4>
           <p><strong>Issues:</strong></p>
           <ul class="list">
             ${clarity_issues.map((i) => `<li>• ${i}</li>`).join("")}
           </ul>`
        : ""
    }

    ${
      clarity_fixes && clarity_fixes.length
        ? `<p><strong>Suggested fixes:</strong></p>
           <ul class="list">
             ${clarity_fixes.map((f) => `<li>• ${f}</li>`).join("")}
           </ul>`
        : ""
    }

    <h4 class="eval-subheading">EEAT signals</h4>
    <ul class="list">
      <li><strong>Author info present:</strong> ${author_info_found ? "Yes" : "No"}</li>
      ${expertise_visibility ? `<li><strong>Expertise visibility:</strong> ${expertise_visibility}</li>` : ""}
      ${experience_signals ? `<li><strong>Experience signals:</strong> ${experience_signals}</li>` : ""}
      ${trust_signals ? `<li><strong>Trust signals:</strong> ${trust_signals}</li>` : ""}
      ${
        missing_elements && missing_elements.length
          ? `<li><strong>Missing elements:</strong> ${missing_elements.join(", ")}</li>`
          : ""
      }
    </ul>
  `;
}

/**
 * Summary / definitions / FAQ / canonical blocks
 */
function renderBlocks(summary, defs, faq, canon) {
  // Summary
  if (summaryBlockEl) {
    const score = summary && typeof summary.score === "number" ? summary.score : 0;
    const quality = summary && summary.quality ? summary.quality : "not_applicable";
    const recommended = summary && summary.recommended_summary_block;

    summaryBlockEl.innerHTML = `
      <div class="block-section">
        <p><strong>Recommended LLM summary (place near the top of the page):</strong></p>
        <p>${recommended || "No recommended summary. Add a concise 120–150 word summary at the top of the page that clearly states what the page is about, who it is for, and the main outcome."}</p>
        <p class="block-meta">
          Summary score: ${score}/10 · Current summary quality: ${quality}
        </p>
        <p class="block-help-text">
          This summary is designed for fast LLM consumption. Keep it concise, specific, and placed high on the page.
        </p>
      </div>
    `;
  }

  // Definitions
  if (definitionsBlockEl) {
    const recDefs = defs && Array.isArray(defs.recommended_definitions)
      ? defs.recommended_definitions
      : [];
    const missing = defs && defs.missing_critical_terms ? defs.missing_critical_terms : [];
    const score = defs && typeof defs.score === "number" ? defs.score : 0;

    definitionsBlockEl.innerHTML = `
      <div class="block-section">
        ${
          recDefs.length
            ? `<ul class="list">
                 ${recDefs
                   .map(
                     (d) =>
                       `<li><strong>${d.term}:</strong> ${d.definition}</li>`
                   )
                   .join("")}
               </ul>`
            : "<p>No recommended definitions.</p>"
        }
        ${
          missing && missing.length
            ? `<p class="block-meta">Missing critical terms: ${missing.join(", ")}</p>`
            : ""
        }
        <p class="block-meta">Definitions score: ${score}/10</p>
        <p class="block-help-text">
          Add these definitions near the first mention of each term so AI systems clearly understand your key concepts.
        </p>
      </div>
    `;
  }

  // FAQ
  if (faqBlockEl) {
    const recFaqs =
      faq && Array.isArray(faq.recommended_faqs) ? faq.recommended_faqs : [];
    const score = faq && typeof faq.score === "number" ? faq.score : 0;

    faqBlockEl.innerHTML = `
      <div class="block-section">
        ${
          recFaqs.length
            ? `<ul class="list">
                 ${recFaqs
                   .map(
                     (f) =>
                       `<li><strong>Q:</strong> ${f.q}<br/><strong>A:</strong> ${f.a}</li>`
                   )
                   .join("")}
               </ul>`
            : "<p>No FAQ suggestions generated.</p>"
        }
        <p class="block-meta">FAQ score: ${score}/10</p>
        <p class="block-help-text">
          Use these FAQs to improve answerability and capture long-tail questions asked in AI chat and search.
        </p>
      </div>
    `;
  }

  // Canonical resources
  if (canonicalBlockEl) {
    const recRes =
      canon && Array.isArray(canon.recommended_resources)
        ? canon.recommended_resources
        : [];
    const score =
      canon && typeof canon.score === "number" ? canon.score : 0;
    const why = canon && canon.why_it_matters ? canon.why_it_matters : "";

    canonicalBlockEl.innerHTML = `
      <div class="block-section">
        ${
          recRes.length
            ? `<ul class="list">
                 ${recRes
                   .map(
                     (c) =>
                       `<li><a href="${c.url}" target="_blank" rel="noopener noreferrer">${c.title ||
                         c.url}</a></li>`
                   )
                   .join("")}
               </ul>`
            : "<p>No canonical resources recommended.</p>"
        }
        <p class="block-meta">Canonical resources score: ${score}/10</p>
        <p class="block-help-text">
          ${why ||
            "Canonical resources help AI models place your page in a trusted context. Include core internal pillar pages and 1–2 authoritative external sources where relevant."}
        </p>
      </div>
    `;
  }
}

// Event listeners
if (analyzeBtn) {
  analyzeBtn.addEventListener("click", analyzeUrl);
}
if (urlInput) {
  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") analyzeUrl();
  });
}

// Sample URL buttons (optional)
document.querySelectorAll(".sample-link").forEach((btn) => {
  btn.addEventListener("click", () => {
    const sampleUrl = btn.getAttribute("data-sample-url");
    if (urlInput && sampleUrl) {
      urlInput.value = sampleUrl;
      analyzeUrl();
    }
  });
});

// Download as PDF (simple version using print)
if (downloadPdfBtn) {
  downloadPdfBtn.addEventListener("click", () => {
    window.print();
  });
}
