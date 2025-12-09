const API_BASE = "http://127.0.0.1:8000"; // for production you can switch to "" (same origin)

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

// Arc score UI (new)
const arcScoreEl = document.getElementById("arc-score");
const scoreAioEl = document.getElementById("score-aio");
const scoreAeoEl = document.getElementById("score-aeo");
const scoreGeoEl = document.getElementById("score-geo");

// PDF download (new)
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
    analyzeBtn.textContent = "Analyze";
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
    setStatus("Enter a URL to analyze.", true);
    return;
  }

  try {
    setStatus("Sending page to LLM engine…");
    setLoading(true);
    if (resultsWrapper) {
      resultsWrapper.classList.add("hidden");
    }

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

    if (resultsWrapper) {
      resultsWrapper.classList.remove("hidden");
    }
    setStatus("Analysis complete.");
  } catch (err) {
    console.error(err);
    setStatus(err.message || "Something went wrong.", true);
  } finally {
    setLoading(false);
  }
}

function renderResults(data) {
  const { llm_view, evaluation, blocks } = data || {};

  // New: Arc Rank hero card
  renderArcRank(evaluation);

  // Existing sections
  renderLlmView(llm_view);
  renderEvaluation(evaluation);
  renderBlocks(blocks);
}

/**
 * Arc Rank hero score + AIO/AEO/GEO
 * This is the main visual center of the app.
 */
function renderArcRank(evaluation) {
  if (!evaluation || !evaluation.scores) return;

  const scores = evaluation.scores;
  const {
    intent_clarity = 0,
    coverage = 0,
    structure = 0,
    definitions = 0,
    answerability = 0,
    trust = 0,
    overall = 0,
  } = scores;

  // Simple first version mapping:
  // - AIO ~ intent clarity (how clear the page is for AI)
  // - AEO ~ answerability (how well it answers concrete Qs)
  // - GEO ~ coverage (how complete the topic is)
  const aio = intent_clarity;
  const aeo = answerability;
  const geo = coverage;

  // Arc Rank shown as 0–100 (e.g. overall 7.8 => 78)
  if (arcScoreEl) {
    const arcNumeric = Math.round((overall || 0) * 10);
    arcScoreEl.textContent = isNaN(arcNumeric) ? "—" : arcNumeric;
  }

  if (scoreAioEl) {
    scoreAioEl.textContent = aio ? aio.toFixed(1) : "—";
    scoreAioEl.title = "AIO – AI Index Optimization: how clearly the page expresses its main topic and purpose for AI models.";
  }

  if (scoreAeoEl) {
    scoreAeoEl.textContent = aeo ? aeo.toFixed(1) : "—";
    scoreAeoEl.title = "AEO – Answer Engine Optimization: how well your content directly answers user questions.";
  }

  if (scoreGeoEl) {
    scoreGeoEl.textContent = geo ? geo.toFixed(1) : "—";
    scoreGeoEl.title = "GEO – Generative Engine Optimization: how much topical depth is available for generative engines to work with.";
  }
}

function renderLlmView(view) {
  if (!view || !llmViewContent) return;
  const {
    primary_topic,
    primary_intent,
    audience,
    user_questions_answered = [],
    user_questions_missing = [],
    key_facts = [],
    important_entities = [],
  } = view;

  llmViewContent.innerHTML = `
    <div class="llm-kv">
      <div class="llm-kv-label">Primary topic</div>
      <div class="llm-kv-value">${primary_topic || "—"}</div>

      <div class="llm-kv-label">Intent</div>
      <div class="llm-kv-value">${primary_intent || "—"}</div>

      <div class="llm-kv-label">Audience</div>
      <div class="llm-kv-value">${audience || "—"}</div>
    </div>

    ${
      important_entities.length
        ? `<h4 class="llm-subheading">Important entities</h4>
           <div class="tag-list">
             ${important_entities
               .map((e) => `<span class="tag">${e}</span>`)
               .join("")}
           </div>`
        : ""
    }

    ${
      key_facts.length
        ? `<h4 class="llm-subheading">Key facts AI detects</h4>
           <ul class="list">
             ${key_facts.map((f) => `<li>• ${f}</li>`).join("")}
           </ul>`
        : ""
    }

    ${
      user_questions_answered.length
        ? `<h4 class="llm-subheading">Questions this page already answers</h4>
           <ul class="list">
             ${user_questions_answered.map((q) => `<li>• ${q}</li>`).join("")}
           </ul>`
        : ""
    }

    ${
      user_questions_missing.length
        ? `<h4 class="llm-subheading">Questions still missing (opportunities)</h4>
           <ul class="list">
             ${user_questions_missing.map((q) => `<li>• ${q}</li>`).join("")}
           </ul>`
        : ""
    }

    <p class="llm-help-text">
      This view is a simplified snapshot of how an LLM might summarize and reason about your page.
      Use it to see if the page is telling the right story.
    </p>
  `;
}

function renderEvaluation(ev) {
  if (!ev || !evaluationContent) return;

  const scores = ev.scores || {};
  const {
    intent_clarity = 0,
    coverage = 0,
    structure = 0,
    definitions = 0,
    answerability = 0,
    trust = 0,
    overall = 0,
  } = scores;

  const {
    verdict,
    issues = [],
    recommendations = [],
    priority_fixes = [],
    canonical_score,
    canonical_issues = [],
    canonical_recommendations = [],
    llm_ready,
  } = ev;

  const scoreRows = [
    ["Intent clarity", intent_clarity, "How clearly the page expresses its purpose and main topic."],
    ["Coverage", coverage, "How completely the page covers the topic and related subtopics."],
    ["Structure", structure, "How well the headings, sections, and layout support AI parsing."],
    ["Definitions", definitions, "Whether key concepts and entities are clearly defined for AI."],
    ["Answerability", answerability, "How well the page answers concrete questions users ask."],
    ["Trust", trust, "Signals of expertise, accuracy, and reliability."],
    ["Canonical", canonical_score, "Internal + external resources that help AI place this page in context."],
  ];

  const verdictClass =
    verdict === "excellent" || verdict === "good"
      ? "verdict-pill verdict-pill--good"
      : "verdict-pill verdict-pill--poor";

  evaluationContent.innerHTML = `
    <div class="${verdictClass}">
      <span>Verdict: <strong>${verdict || "—"}</strong></span>
      <span class="llm-ready-flag" title="If 'Yes', this page is in a decent state for AI-powered search.">
        LLM-ready: ${llm_ready ? "Yes" : "No"}
      </span>
    </div>

    <p class="eval-help-text">
      Each score reflects a dimension that affects whether AI systems will trust and reuse this page in answers.
      Focus on the lowest scores first for the fastest improvements.
    </p>

    <div class="score-badges-row">
      <span class="score-pill" title="Overall Arc Rank on a 0–10 scale.">
        Overall score: <strong>${overall}/10</strong>
      </span>
      ${
        typeof canonical_score === "number"
          ? `<span class="score-pill" title="How solid your canonical resources are for this page.">
               Canonical score: <strong>${canonical_score}/10</strong>
             </span>`
          : ""
      }
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

    ${
      priority_fixes.length
        ? `<h4 class="eval-subheading">Priority fixes (do these first)</h4>
           <ul class="list">
             ${priority_fixes.map((p) => `<li>• ${p}</li>`).join("")}
           </ul>`
        : ""
    }

    ${
      issues.length
        ? `<h4 class="eval-subheading">Issues detected</h4>
           <ul class="list">
             ${issues.map((i) => `<li>• ${i}</li>`).join("")}
           </ul>`
        : ""
    }

    ${
      recommendations.length
        ? `<h4 class="eval-subheading">Recommended improvements</h4>
           <ul class="list">
             ${recommendations.map((r) => `<li>• ${r}</li>`).join("")}
           </ul>`
        : ""
    }

    ${
      canonical_issues.length || canonical_recommendations.length
        ? `<h4 class="eval-subheading">Canonical resource notes</h4>
           <ul class="list">
             ${canonical_issues.map((i) => `<li>• ${i}</li>`).join("")}
             ${canonical_recommendations.map((r) => `<li>• ${r}</li>`).join("")}
           </ul>`
        : ""
    }
  `;
}

function renderBlocks(blocks) {
  if (!blocks) return;
  const summary = blocks.summary_block || {};
  const defs = blocks.definitions_block || [];
  const faq = blocks.faq_block || [];
  const canon = blocks.canonical_resources || [];

  if (summaryBlockEl) {
    summaryBlockEl.innerHTML = `
      <div class="block-section">
        <p><strong>Purpose:</strong> ${summary.purpose || "—"}</p>
        <p><strong>Audience:</strong> ${summary.audience || "—"}</p>
        ${
          summary.key_points && summary.key_points.length
            ? `<p><strong>Key points:</strong></p>
               <ul class="list">
                 ${summary.key_points.map((p) => `<li>• ${p}</li>`).join("")}
               </ul>`
            : ""
        }
        <p class="block-help-text">
          Use this summary as the canonical, LLM-ready description of this page in internal tools, docs, or RAG systems.
        </p>
      </div>
    `;
  }

  if (definitionsBlockEl) {
    definitionsBlockEl.innerHTML = `
      <div class="block-section">
        ${
          defs.length
            ? `<ul class="list">
                 ${defs
                   .map(
                     (d) =>
                       `<li><strong>${d.term}:</strong> ${d.definition} <span style="color:var(--muted)">(${d.context || ""})</span></li>`
                   )
                   .join("")}
               </ul>`
            : "<p>No definitions generated.</p>"
        }
        <p class="block-help-text">
          Add these definitions near the first mention of each term so AI models clearly understand your key concepts.
        </p>
      </div>
    `;
  }

  if (faqBlockEl) {
    faqBlockEl.innerHTML = `
      <div class="block-section">
        ${
          faq.length
            ? `<ul class="list">
                 ${faq
                   .map(
                     (f) =>
                       `<li><strong>Q:</strong> ${f.question}<br/><strong>A:</strong> ${f.answer}</li>`
                   )
                   .join("")}
               </ul>`
            : "<p>No FAQ generated.</p>"
        }
        <p class="block-help-text">
          Use these FAQs to improve answerability and capture long-tail questions asked in AI chat and search.
        </p>
      </div>
    `;
  }

  if (canonicalBlockEl) {
    canonicalBlockEl.innerHTML = `
      <div class="block-section">
        ${
          canon.length
            ? `<ul class="list">
                 ${canon
                   .map(
                     (c) =>
                       `<li><a href="${c.url}" target="_blank" rel="noopener noreferrer">${c.title || c.url}</a></li>`
                   )
                   .join("")}
               </ul>`
            : "<p>No canonical resources.</p>"
        }
        <p class="block-help-text">
          Canonical resources help AI models place this page in a wider, trusted context. Include your best internal pillar pages and 1–2 authoritative external sources.
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

// Download as PDF (simple version using print)
if (downloadPdfBtn) {
  downloadPdfBtn.addEventListener("click", () => {
    window.print();
  });
}
