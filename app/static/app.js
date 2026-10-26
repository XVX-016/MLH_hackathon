// Job-based explorer controller. Demo results use the same frozen API shape.
let currentAnalysis = null;
let currentJobId = null;
let currentVideoUrl = null;
let visNetworkInstance = null;

document.addEventListener("DOMContentLoaded", function () {
  initForms();
  document.getElementById("btn-load-sample").addEventListener("click", loadDemo);
  document.getElementById("btn-close-drawer").addEventListener("click", closeEvidenceDrawer);
  document.getElementById("video-player").addEventListener("timeupdate", updateActiveTranscript);
});

function formatTime(seconds) {
  var total = Math.max(0, Math.floor(Number(seconds) || 0));
  return String(Math.floor(total / 60)).padStart(2, "0") + ":" + String(total % 60).padStart(2, "0");
}

async function readJson(response) {
  var body = await response.json().catch(function () { return {}; });
  if (!response.ok) throw new Error(body.detail || "Request failed");
  return body;
}

function initForms() {
  document.getElementById("form-upload").addEventListener("submit", async function (event) {
    event.preventDefault();
    var file = document.getElementById("input-file").files[0];
    if (!file) return;
    toggleLoading(true, "Uploading and processing...");
    try {
      var formData = new FormData();
      formData.append("file", file);
      formData.append("model", document.getElementById("select-model-file").value);
      var job = await readJson(await fetch("/process", { method: "POST", body: formData }));
      currentJobId = job.job_id;
      await waitForResult(currentJobId);
      loadAnalysisData(await readJson(await fetch("/result/" + currentJobId)), URL.createObjectURL(file));
    } catch (error) {
      appendChatMessage("system", "Processing failed: " + error.message);
    } finally {
      toggleLoading(false);
    }
  });

  document.getElementById("qa-form").addEventListener("submit", async function (event) {
    event.preventDefault();
    var input = document.getElementById("qa-input");
    var question = input.value.trim();
    if (!question || !currentJobId) {
      appendChatMessage("system", "Load a demo or process a video first.");
      return;
    }
    input.value = "";
    appendChatMessage("user", question);
    document.getElementById("spinner-qa").classList.remove("hidden");
    try {
      var response = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: currentJobId, question: question })
      });
      appendBotResponse(await readJson(response));
    } catch (error) {
      appendChatMessage("system", "Q&A failed: " + error.message);
    } finally {
      document.getElementById("spinner-qa").classList.add("hidden");
    }
  });
}

async function loadDemo() {
  try {
    var status = await readJson(await fetch("/status/demo_attention"));
    if (status.status !== "completed") throw new Error("Demo result is not ready");
    currentJobId = "demo_attention";
    loadAnalysisData(await readJson(await fetch("/result/demo_attention")));
  } catch (error) {
    appendChatMessage("system", "Could not load demo: " + error.message);
  }
}

async function waitForResult(jobId) {
  for (;;) {
    var status = await readJson(await fetch("/status/" + jobId));
    if (status.status === "completed") return;
    if (status.status === "failed") throw new Error(status.error || "Job failed");
    await new Promise(function (resolve) { setTimeout(resolve, 500); });
  }
}

function toggleLoading(loading, text) {
  document.getElementById("spinner-upload").classList.toggle("hidden", !loading);
  document.getElementById("processing-banner").classList.toggle("hidden", !loading);
  if (text) document.getElementById("processing-status-text").textContent = text;
}

function loadAnalysisData(data, videoUrl) {
  currentAnalysis = data;
  if (currentVideoUrl) URL.revokeObjectURL(currentVideoUrl);
  currentVideoUrl = videoUrl || null;
  var player = document.getElementById("video-player");
  player.src = videoUrl || "";
  player.classList.toggle("hidden", !videoUrl);
  document.getElementById("video-player-placeholder").classList.toggle("hidden", Boolean(videoUrl));
  document.getElementById("video-title").textContent = data.title || "Untitled Video";
  document.getElementById("video-duration-badge").textContent = formatTime(data.duration);
  document.getElementById("video-summary").textContent = data.summary || "No summary provided.";
  renderChapters(data.chapters || []);
  renderTranscript(data.transcript || []);
  renderKnowledgeGraph(data.graph || { nodes: [], edges: [] });
}

function renderChapters(chapters) {
  var container = document.getElementById("chapters-list");
  document.getElementById("chapters-count").textContent = chapters.length + " Chapters";
  container.replaceChildren();
  if (!chapters.length) {
    container.innerHTML = "<p class='placeholder-text'>No chapters available.</p>";
    return;
  }
  chapters.forEach(function (chapter) {
    var start = chapter.start_sec == null ? chapter.start : chapter.start_sec;
    var item = document.createElement("button");
    item.type = "button";
    item.className = "chapter-item";
    item.innerHTML = "<div class='chapter-title-row'><span class='chapter-title'></span><span class='chapter-time'></span></div><p class='chapter-desc'></p>";
    item.querySelector(".chapter-title").textContent = chapter.title;
    item.querySelector(".chapter-time").textContent = "[" + formatTime(start) + "]";
    item.querySelector(".chapter-desc").textContent = chapter.summary;
    item.addEventListener("click", function () { seekVideo(start); });
    container.appendChild(item);
  });
}

function renderTranscript(segments) {
  var container = document.getElementById("transcript-list");
  container.replaceChildren();
  segments.forEach(function (segment) {
    var row = document.createElement("button");
    row.type = "button";
    row.className = "transcript-segment-row";
    row.dataset.start = segment.start;
    row.dataset.end = segment.end;
    row.innerHTML = "<span class='seg-timestamp'></span><span class='seg-text'></span>";
    row.querySelector(".seg-timestamp").textContent = "[" + formatTime(segment.start) + "]";
    row.querySelector(".seg-text").textContent = segment.text;
    row.addEventListener("click", function () { seekVideo(segment.start, false); });
    container.appendChild(row);
  });
  var search = document.getElementById("transcript-search");
  search.oninput = function () {
    var query = search.value.toLowerCase();
    container.querySelectorAll(".transcript-segment-row").forEach(function (row) {
      row.classList.toggle("filtered-out", !row.textContent.toLowerCase().includes(query));
    });
  };
}

function seekVideo(seconds, scroll) {
  var player = document.getElementById("video-player");
  if (player.src) {
    player.currentTime = Number(seconds) || 0;
    player.play().catch(function () {});
  }
  if (scroll !== false) scrollToTranscriptTime(seconds);
}

function updateActiveTranscript() {
  var time = document.getElementById("video-player").currentTime;
  document.querySelectorAll(".transcript-segment-row").forEach(function (row) {
    row.classList.toggle("active", time >= Number(row.dataset.start) && time < Number(row.dataset.end));
  });
}

function scrollToTranscriptTime(seconds) {
  var rows = Array.from(document.querySelectorAll(".transcript-segment-row"));
  var row = rows.find(function (candidate) { return Number(candidate.dataset.start) >= Number(seconds) - 1; }) || rows[rows.length - 1];
  if (row) row.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderKnowledgeGraph(graphData) {
  var container = document.getElementById("graph-network");
  document.getElementById("stat-nodes").textContent = graphData.nodes.length + " Nodes";
  document.getElementById("stat-edges").textContent = graphData.edges.length + " Grounded Edges";
  if (!window.vis) {
    container.textContent = "Graph library unavailable.";
    return;
  }
  var nodes = graphData.nodes.map(function (node) {
    return Object.assign({}, node, { title: node.label, group: node.type, mentions: node.mentions || [] });
  });
  var edges = graphData.edges.map(function (edge, index) {
    return Object.assign({}, edge, { id: edge.id || "edge-" + index, from: edge.source, to: edge.target, label: edge.relation, arrows: "to", timestamp_str: formatTime(edge.start_time) });
  });
  var data = { nodes: new window.vis.DataSet(nodes), edges: new window.vis.DataSet(edges) };
  if (visNetworkInstance) visNetworkInstance.destroy();
  visNetworkInstance = new window.vis.Network(container, data, {
    nodes: { shape: "dot", size: 20, font: { color: "#f8fafc", size: 13 } },
    edges: { arrows: { to: { enabled: true, scaleFactor: 0.8 } }, smooth: { type: "continuous" } },
    physics: { stabilization: { iterations: 120 }, barnesHut: { gravitationalConstant: -3000, springLength: 95 } },
    interaction: { hover: true, tooltipDelay: 150 }
  });
  visNetworkInstance.on("selectEdge", function (event) { if (event.edges.length) showEvidenceDrawer(data.edges.get(event.edges[0])); });
  visNetworkInstance.on("selectNode", function (event) { if (event.nodes.length) showNodeMentions(data.nodes.get(event.nodes[0])); });
}

function showEvidenceDrawer(edge) {
  document.getElementById("inspector-relation").textContent = edge.label || "RELATION";
  document.getElementById("inspector-quote").textContent = "“" + (edge.evidence_quote || "No quote") + "”";
  document.getElementById("inspector-timestamp").textContent = "[" + formatTime(edge.start_time) + "]";
  document.getElementById("inspector-confidence").textContent = Math.round((edge.confidence == null ? 1 : edge.confidence) * 100) + "%";
  document.getElementById("inspector-mentions").classList.add("hidden");
  document.getElementById("edge-evidence-drawer").classList.remove("hidden");
  seekVideo(edge.start_time);
}

function showNodeMentions(node) {
  var label = String(node.label || node.id);
  var terms = [label, String(node.id).replaceAll("_", " ")];
  var mentions = (currentAnalysis && currentAnalysis.transcript || []).filter(function (segment) {
    return terms.some(function (term) { return new RegExp("(^|\\W)" + escapeRegExp(term) + "(\\W|$)", "i").test(segment.text); });
  });
  var panel = document.getElementById("inspector-mentions");
  panel.replaceChildren();
  var heading = document.createElement("strong");
  heading.textContent = label + " mentions";
  panel.appendChild(heading);
  (mentions.length ? mentions : (node.mentions || []).map(function (start) { return { start: start, text: "Graph mention" }; })).forEach(function (mention) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "node-mention";
    button.textContent = "[" + formatTime(mention.start) + "] " + mention.text;
    button.addEventListener("click", function () { seekVideo(mention.start); });
    panel.appendChild(button);
  });
  document.getElementById("inspector-relation").textContent = "ENTITY";
  document.getElementById("inspector-quote").textContent = "Select a mention to seek to its transcript timestamp.";
  panel.classList.remove("hidden");
  document.getElementById("edge-evidence-drawer").classList.remove("hidden");
}

function escapeRegExp(value) { return value.replace(/[.*+?^$()|[\]\\{}]/g, "\\$&"); }
function closeEvidenceDrawer() { document.getElementById("edge-evidence-drawer").classList.add("hidden"); }

function appendChatMessage(sender, text) {
  var message = document.createElement("div");
  message.className = "qa-message " + sender + "-message";
  message.textContent = text;
  var history = document.getElementById("qa-chat-history");
  history.appendChild(message);
  history.scrollTop = history.scrollHeight;
}

function appendBotResponse(result) {
  var message = document.createElement("div");
  message.className = "qa-message bot-message";
  var answer = String(result.answer || "");
  var citations = result.citations || [];
  var pattern = /\[(\d{2}:\d{2})\]/g;
  var cursor = 0;
  var match;
  while ((match = pattern.exec(answer))) {
    message.appendChild(document.createTextNode(answer.slice(cursor, match.index)));
    let citation = citations.find(function (item) { return item.timestamp_str === match[1]; });
    if (citation) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "citation-pill" + (citation.verified ? " verified" : "");
      chip.textContent = "[" + match[1] + "]";
      chip.title = citation.quote || "Verified transcript evidence";
      chip.addEventListener("click", function () { seekVideo(citation.start_time); });
      message.appendChild(chip);
    } else message.appendChild(document.createTextNode(match[0]));
    cursor = pattern.lastIndex;
  }
  message.appendChild(document.createTextNode(answer.slice(cursor)));
  var history = document.getElementById("qa-chat-history");
  history.appendChild(message);
  history.scrollTop = history.scrollHeight;
}
