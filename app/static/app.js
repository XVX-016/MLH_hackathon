// videograph Vanilla JS frontend controller
let currentAnalysis = null;
let visNetworkInstance = null;

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initForms();
  initSampleLoader();
  initDrawer();
});

// Tab switching between URL and Upload
function initTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      tab.classList.add("active");
      const targetId = tab.dataset.tab;
      document.getElementById(targetId === "tab-url" ? "form-url" : "form-upload").classList.add("active");
    });
  });
}

// Ingestion Form Submissions
function initForms() {
  const urlForm = document.getElementById("form-url");
  const uploadForm = document.getElementById("form-upload");

  urlForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = document.getElementById("input-url").value.trim();
    const model = document.getElementById("select-model-url").value;
    if (!url) return;

    toggleLoading("url", true, "Fetching & analyzing video source...");
    try {
      const formData = new FormData();
      formData.append("url", url);
      formData.append("model", model);

      const resp = await fetch("/api/analyze/url", {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Analysis failed");
      }

      const data = await resp.json();
      loadAnalysisData(data);
    } catch (err) {
      alert(`Error analyzing video: ${err.message}`);
    } finally {
      toggleLoading("url", false);
    }
  });

  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById("input-file");
    const model = document.getElementById("select-model-file").value;
    if (!fileInput.files || fileInput.files.length === 0) return;

    toggleLoading("upload", true, "Uploading and transcribing file...");
    try {
      const formData = new FormData();
      formData.append("file", fileInput.files[0]);
      formData.append("model", model);

      const resp = await fetch("/api/analyze/upload", {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Upload analysis failed");
      }

      const data = await resp.json();
      loadAnalysisData(data);
    } catch (err) {
      alert(`Error processing upload: ${err.message}`);
    } finally {
      toggleLoading("upload", false);
    }
  });

  // QA Form
  const qaForm = document.getElementById("qa-form");
  qaForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("qa-input");
    const question = input.value.trim();
    if (!question || !currentAnalysis) {
      if (!currentAnalysis) alert("Please load or analyze a video first.");
      return;
    }

    appendChatMessage("user", question);
    input.value = "";
    toggleQALoading(true);

    try {
      const resp = await fetch("/api/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video_id: currentAnalysis.video_id,
          question: question,
        }),
      });

      if (!resp.ok) throw new Error("QA retrieval failed");
      const qaResult = await resp.json();
      appendBotResponse(qaResult);
    } catch (err) {
      appendChatMessage("system", `Failed to get answer: ${err.message}`);
    } finally {
      toggleQALoading(false);
    }
  });
}

function initSampleLoader() {
  const btn = document.getElementById("btn-load-sample");
  btn.addEventListener("click", async () => {
    try {
      const resp = await fetch("/api/sample/load", { method: "POST" });
      const data = await resp.json();
      loadAnalysisData(data);
    } catch (err) {
      alert(`Could not load sample: ${err.message}`);
    }
  });
}

function initDrawer() {
  const closeBtn = document.getElementById("btn-close-drawer");
  closeBtn.addEventListener("click", () => {
    document.getElementById("edge-evidence-drawer").classList.add("hidden");
  });
}

function toggleLoading(type, isLoading, text = "") {
  const spinner = document.getElementById(`spinner-${type}`);
  const banner = document.getElementById("processing-banner");
  const statusText = document.getElementById("processing-status-text");

  if (isLoading) {
    if (spinner) spinner.classList.remove("hidden");
    banner.classList.remove("hidden");
    statusText.textContent = text;
  } else {
    if (spinner) spinner.classList.add("hidden");
    banner.classList.add("hidden");
  }
}

function toggleQALoading(isLoading) {
  const spinner = document.getElementById("spinner-qa");
  if (isLoading) spinner.classList.remove("hidden");
  else spinner.classList.add("hidden");
}

// Populate UI with analysis result
function loadAnalysisData(data) {
  currentAnalysis = data;

  // Title and duration
  document.getElementById("video-title").textContent = data.title || "Untitled Video";
  const m = Math.floor(data.duration / 60);
  const s = Math.floor(data.duration % 60);
  document.getElementById("video-duration-badge").textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;

  // Executive Summary
  document.getElementById("video-summary").textContent = data.summary || "No summary provided.";

  // Chapters
  renderChapters(data.chapters || []);

  // Transcript
  renderTranscript(data.transcript || []);

  // Knowledge Graph
  renderKnowledgeGraph(data.graph);
}

function renderChapters(chapters) {
  const container = document.getElementById("chapters-list");
  const countBadge = document.getElementById("chapters-count");
  countBadge.textContent = `${chapters.length} Chapters`;
  container.innerHTML = "";

  if (chapters.length === 0) {
    container.innerHTML = `<p class="placeholder-text">No chapters available.</p>`;
    return;
  }

  chapters.forEach((ch) => {
    const item = document.createElement("div");
    item.className = "chapter-item";
    const sm = Math.floor(ch.start / 60);
    const ss = Math.floor(ch.start % 60);
    const timeStr = `${String(sm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;

    item.innerHTML = `
      <div class="chapter-title-row">
        <span class="chapter-title">${ch.title}</span>
        <span class="chapter-time">[${timeStr}]</span>
      </div>
      <p class="chapter-desc">${ch.summary}</p>
    `;
    item.addEventListener("click", () => {
      scrollToTranscriptTime(ch.start);
    });
    container.appendChild(item);
  });
}

function renderTranscript(segments) {
  const container = document.getElementById("transcript-list");
  container.innerHTML = "";

  segments.forEach((seg) => {
    const row = document.createElement("div");
    row.className = "transcript-segment-row";
    row.id = `seg-${seg.id}`;
    row.dataset.start = seg.start;

    const sm = Math.floor(seg.start / 60);
    const ss = Math.floor(seg.start % 60);
    const ts = `[${String(sm).padStart(2, '0')}:${String(ss).padStart(2, '0')}]`;

    row.innerHTML = `
      <span class="seg-timestamp">${ts}</span>
      <span class="seg-text">${seg.text}</span>
    `;
    container.appendChild(row);
  });

  // Filter input
  const searchInput = document.getElementById("transcript-search");
  searchInput.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll(".transcript-segment-row").forEach((row) => {
      const txt = row.querySelector(".seg-text").textContent.toLowerCase();
      row.style.display = txt.includes(q) ? "flex" : "none";
    });
  });
}

function scrollToTranscriptTime(timeSec) {
  const rows = document.querySelectorAll(".transcript-segment-row");
  for (const row of rows) {
    const s = parseFloat(row.dataset.start);
    if (s >= timeSec - 1.0) {
      row.scrollIntoView({ behavior: "smooth", block: "center" });
      row.style.backgroundColor = "rgba(99, 102, 241, 0.25)";
      setTimeout(() => {
        row.style.backgroundColor = "";
      }, 1800);
      break;
    }
  }
}

// Build Vis.js Interactive Network
function renderKnowledgeGraph(graphData) {
  const container = document.getElementById("graph-network");
  const statNodes = document.getElementById("stat-nodes");
  const statEdges = document.getElementById("stat-edges");

  statNodes.textContent = `${graphData.nodes.length} Nodes`;
  statEdges.textContent = `${graphData.edges.length} Grounded Edges`;

  // Fetch Vis formatted data directly or convert locally
  fetch(`/api/graph/${currentAnalysis.video_id}`)
    .then((r) => r.json())
    .then((res) => {
      const vis = res.vis;
      const data = {
        nodes: new vis.DataSet(vis.nodes),
        edges: new vis.DataSet(vis.edges),
      };

      const options = {
        nodes: {
          shape: "dot",
          size: 20,
          font: { color: "#f8fafc", size: 13, face: "Plus Jakarta Sans" },
          borderWidth: 2,
        },
        edges: {
          arrows: { to: { enabled: true, scaleFactor: 0.8 } },
          smooth: { type: "continuous" },
        },
        physics: {
          stabilization: { iterations: 120 },
          barnesHut: { gravitationalConstant: -3000, springLength: 95 },
        },
        interaction: { hover: true, tooltipDelay: 150 },
      };

      if (visNetworkInstance) visNetworkInstance.destroy();
      visNetworkInstance = new vis.Network(container, data, options);

      // On Edge Select -> Display Grounding Evidence Drawer
      visNetworkInstance.on("selectEdge", (params) => {
        if (params.edges.length > 0) {
          const edgeId = params.edges[0];
          const edgeObj = vis.edges.find((e) => e.id === edgeId);
          if (edgeObj) {
            showEvidenceDrawer(edgeObj);
          }
        }
      });
    });
}

function showEvidenceDrawer(edge) {
  const drawer = document.getElementById("edge-evidence-drawer");
  document.getElementById("inspector-relation").textContent = edge.label;
  document.getElementById("inspector-quote").textContent = `“${edge.evidence_quote}”`;
  document.getElementById("inspector-timestamp").textContent = `[${edge.timestamp_str}] (${edge.start_time.toFixed(1)}s - ${edge.end_time.toFixed(1)}s)`;
  document.getElementById("inspector-confidence").textContent = `${Math.round(edge.confidence * 100)}% Verified Grounding`;
  drawer.classList.remove("hidden");

  // Scroll transcript to evidence quote
  scrollToTranscriptTime(edge.start_time);
}

// Chat UI helpers
function appendChatMessage(sender, text) {
  const history = document.getElementById("qa-chat-history");
  const msg = document.createElement("div");
  msg.className = `qa-message ${sender}-message`;
  msg.textContent = text;
  history.appendChild(msg);
  history.scrollTop = history.scrollHeight;
}

function appendBotResponse(qaResult) {
  const history = document.getElementById("qa-chat-history");
  const msg = document.createElement("div");
  msg.className = "qa-message bot-message";

  let formattedAnswer = qaResult.answer;

  // Replace [MM:SS] with interactive verified clickable pills
  if (qaResult.citations) {
    qaResult.citations.forEach((cit) => {
      const matchPattern = new RegExp(`\\[${cit.timestamp_str}\\]`, "g");
      const verifiedClass = cit.verified ? "verified" : "";
      const replacement = `<span class="citation-pill ${verifiedClass}" data-start="${cit.start_time}" title="Evidence quote: '${cit.quote}' (${cit.match_score}% verified match)">[${cit.timestamp_str}]</span>`;
      formattedAnswer = formattedAnswer.replace(matchPattern, replacement);
    });
  }

  msg.innerHTML = formattedAnswer;

  // Add click listener to citation pills
  msg.querySelectorAll(".citation-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      const startTime = parseFloat(pill.dataset.start);
      scrollToTranscriptTime(startTime);
    });
  });

  history.appendChild(msg);
  history.scrollTop = history.scrollHeight;
}
