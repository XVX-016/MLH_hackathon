// Job-based explorer controller. Demo results use the same frozen API shape.
let currentAnalysis = null;
let currentJobId = null;
let currentVideoUrl = null;
let currentYoutubeId = null;
let visNetworkInstance = null;

document.addEventListener("DOMContentLoaded", function () {
  initForms();
  document.getElementById("btn-load-sample").addEventListener("click", loadDemo);
  document.getElementById("btn-new-video").addEventListener("click", resetToHero);
  document.getElementById("btn-upload").addEventListener("click", function () {
    document.getElementById("input-file").click();
  });
  document.getElementById("input-file").addEventListener("change", function (event) {
    if (event.target.files.length) document.getElementById("form-upload").requestSubmit();
  });
  document.getElementById("btn-close-drawer").addEventListener("click", closeEvidenceDrawer);
  document.getElementById("inspector-timestamp").addEventListener("click", function (event) {
    seekVideo(event.currentTarget.dataset.start);
  });
  document.getElementById("video-player").addEventListener("timeupdate", updateActiveTranscript);
  document.querySelectorAll(".study-tab").forEach(function (tab) {
    tab.addEventListener("click", function () { selectTab(tab); });
    tab.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      event.preventDefault();
      var tabs = Array.from(document.querySelectorAll(".study-tab"));
      var next = tabs[(tabs.indexOf(tab) + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      selectTab(next);
      next.focus();
    });
  });
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
  document.getElementById("form-url").addEventListener("submit", async function (event) {
    event.preventDefault();
    var url = document.getElementById("input-url").value.trim();
    var youtubeId = getYoutubeId(url);
    if (!youtubeId) {
      showInputError("Enter a valid YouTube video URL.");
      return;
    }
    showInputError("");
    toggleLoading(true, "Fetching video details...", { title: "Fetching video details..." });
    try {
      updateProcessingDetails(await readJson(await fetch("/api/youtube/metadata", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url })
      })));
      var formData = new FormData();
      formData.append("url", url);
      formData.append("model", document.getElementById("select-model-file").value);
      var result = await readJson(await fetch("/api/analyze/url", { method: "POST", body: formData }));
      if (result.job_id) {
        updateProcessingDetails(result.metadata || result);
        await waitForResult(result.job_id);
        result = await readJson(await fetch("/result/" + result.job_id));
      }
      loadAnalysisData(result, null, youtubeId);
    } catch (error) {
      showInputError(error.message);
    } finally {
      toggleLoading(false);
    }
  });

  document.getElementById("form-upload").addEventListener("submit", async function (event) {
    event.preventDefault();
    var file = document.getElementById("input-file").files[0];
    if (!file) return;
    showInputError("");
    toggleLoading(true, "Uploading and processing...", { title: file.name, channel: "Local upload" });
    try {
      var formData = new FormData();
      formData.append("file", file);
      formData.append("model", document.getElementById("select-model-file").value);
      var job = await readJson(await fetch("/process", { method: "POST", body: formData }));
      await waitForResult(job.job_id);
      var playable = /\.(mp4|mkv|webm|mp3|wav)$/i.test(file.name);
      loadAnalysisData(await readJson(await fetch("/result/" + job.job_id)), playable ? URL.createObjectURL(file) : null);
    } catch (error) {
      showInputError("Processing failed: " + error.message);
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

function getYoutubeId(value) {
  try {
    var url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol)) return null;
    var host = url.hostname.toLowerCase();
    var id = host === "youtu.be" ? url.pathname.slice(1) :
      ["youtube.com", "www.youtube.com", "m.youtube.com"].includes(host) ?
        (url.searchParams.get("v") || url.pathname.match(/^\/(?:shorts|embed|live)\/([^/]+)/)?.[1]) : null;
    return /^[-\w]{11}$/.test(id || "") ? id : null;
  } catch (_) { return null; }
}

function showInputError(message) {
  var element = document.getElementById("input-error");
  element.textContent = message;
  element.classList.toggle("hidden", !message);
}

function selectTab(tab) {
  document.querySelectorAll(".study-tab").forEach(function (item) {
    var selected = item === tab;
    item.classList.toggle("active", selected);
    item.setAttribute("aria-selected", String(selected));
    item.tabIndex = selected ? 0 : -1;
    document.getElementById(item.getAttribute("aria-controls")).hidden = !selected;
  });
  if (tab.id === "tab-graph" && currentAnalysis) renderKnowledgeGraph(currentAnalysis.graph || { nodes: [], edges: [] });
}

async function loadDemo() {
  try {
    showInputError("");
    toggleLoading(true, "Loading the offline demo...", { title: "Offline demo", channel: "Offline demo" });
    var status = await readJson(await fetch("/status/demo_attention"));
    if (status.status !== "completed") throw new Error("Demo result is not ready");
    loadAnalysisData(await readJson(await fetch("/result/demo_attention")));
  } catch (error) {
    showInputError("Could not load demo: " + error.message);
  } finally {
    toggleLoading(false);
  }
}

async function waitForResult(jobId) {
  for (;;) {
    var status = await readJson(await fetch("/status/" + jobId));
    updateProcessingDetails(status.metadata || status);
    document.getElementById("processing-status-text").textContent = status.status === "queued" ? "Waiting to start..." : "Analyzing the video...";
    if (status.status === "completed") return;
    if (status.status === "failed") throw new Error(status.error || "Job failed");
    await new Promise(function (resolve) { setTimeout(resolve, 500); });
  }
}

function updateProcessingDetails(metadata) {
  if (metadata.title) document.getElementById("processing-title").textContent = metadata.title;
  var details = [];
  if (metadata.channel) details.push(metadata.channel);
  if (metadata.duration != null) details.push(formatTime(metadata.duration));
  document.getElementById("processing-channel").textContent = metadata.channel || "";
  document.getElementById("processing-duration").textContent = metadata.duration != null ? formatTime(metadata.duration) : "";
}

function toggleLoading(loading, text, metadata) {
  document.getElementById("spinner-upload").classList.toggle("hidden", !loading);
  document.getElementById("hero-content").hidden = loading;
  document.getElementById("processing-card").hidden = !loading;
  if (loading) {
    document.getElementById("processing-title").textContent = metadata?.title || "Analyzing video...";
    document.getElementById("processing-channel").textContent = "";
    document.getElementById("processing-duration").textContent = "";
    if (metadata) updateProcessingDetails(metadata);
  }
  if (text) document.getElementById("processing-status-text").textContent = text;
}


function loadAnalysisData(data, videoUrl, youtubeId) {
  currentAnalysis = data;
  currentJobId = data.video_id;
  if (currentVideoUrl) URL.revokeObjectURL(currentVideoUrl);
  currentVideoUrl = videoUrl || null;
  currentYoutubeId = youtubeId || null;
  var player = document.getElementById("video-player");
  player.src = videoUrl || "";
  player.classList.toggle("hidden", !videoUrl);
  var youtubePlayer = document.getElementById("youtube-player");
  youtubePlayer.src = youtubeId ? "https://www.youtube.com/embed/" + youtubeId : "";
  youtubePlayer.classList.toggle("hidden", !youtubeId);
  document.getElementById("video-player-placeholder").classList.toggle("hidden", Boolean(videoUrl || youtubeId));
  document.getElementById("video-title").textContent = data.title || "Untitled Video";
  document.getElementById("video-duration-badge").textContent = formatTime(data.duration);
  document.getElementById("video-summary").textContent = data.summary || "No summary provided.";
  renderChapters(data.chapters || []);
  renderFlashcards(data.flashcards || [], data.transcript || []);
  renderTranscript(data.transcript || []);
  document.getElementById("qa-chat-history").replaceChildren();
  appendChatMessage("system", "Ask a question about this video.");
  closeEvidenceDrawer();
  if (!document.getElementById("panel-graph").hidden) renderKnowledgeGraph(data.graph || { nodes: [], edges: [] });
  document.getElementById("hero").hidden = true;
  document.getElementById("results").hidden = false;
  document.getElementById("btn-new-video").hidden = false;
  window.scrollTo(0, 0);
}

function resetToHero() {
  var player = document.getElementById("video-player");
  player.pause();
  player.removeAttribute("src");
  if (visNetworkInstance) {
    visNetworkInstance.destroy();
    visNetworkInstance = null;
  }
  document.getElementById("youtube-player").removeAttribute("src");
  if (currentVideoUrl) URL.revokeObjectURL(currentVideoUrl);
  currentVideoUrl = null;
  currentYoutubeId = null;
  currentJobId = null;
  currentAnalysis = null;
  showInputError("");
  document.getElementById("input-file").value = "";
  document.getElementById("results").hidden = true;
  document.getElementById("hero").hidden = false;
  document.getElementById("btn-new-video").hidden = true;
  document.getElementById("input-url").focus();
}

function renderFlashcards(cards, segments) {
  cards = cards.filter(function (card) {
    var quote = String(card.key_quote || "").toLowerCase().replace(/\s+/g, " ").trim();
    var evidence = segments.filter(function (segment) {
      return segment.end >= card.start_sec && segment.start <= card.end_sec;
    }).map(function (segment) { return segment.text; }).join(" ").toLowerCase().replace(/\s+/g, " ");
    return quote && evidence.includes(quote);
  });
  var container = document.getElementById("flashcards-list");
  document.getElementById("flashcards-count").textContent = cards.length + (cards.length === 1 ? " Card" : " Cards");
  container.replaceChildren();
  if (!cards.length) {
    container.innerHTML = "<p class='placeholder-text'>No flashcards with verbatim transcript evidence are available.</p>";
    return;
  }
  cards.forEach(function (card) {
    var item = document.createElement("article");
    item.className = "flashcard";
    item.innerHTML = "<button type='button' class='flashcard-flip' aria-pressed='false'><span class='flashcard-inner'><span class='flashcard-face flashcard-front'></span><span class='flashcard-face flashcard-back'><strong class='flashcard-answer'></strong><q class='flashcard-quote'></q></span></span></button><button type='button' class='citation-pill flashcard-jump'></button>";
    var flip = item.querySelector(".flashcard-flip");
    flip.setAttribute("aria-label", "Reveal answer: " + card.question);
    item.querySelector(".flashcard-front").textContent = card.question;
    item.querySelector(".flashcard-answer").textContent = card.answer;
    item.querySelector(".flashcard-quote").textContent = card.key_quote || "No supporting quote provided.";
    flip.addEventListener("click", function () {
      var flipped = item.classList.toggle("flipped");
      flip.setAttribute("aria-pressed", String(flipped));
      flip.setAttribute("aria-label", (flipped ? "Show question: " : "Reveal answer: ") + card.question);
    });
    var jump = item.querySelector(".flashcard-jump");
    jump.textContent = "[" + formatTime(card.start_sec) + "] Jump to evidence";
    jump.addEventListener("click", function () { seekVideo(card.start_sec); });
    container.appendChild(item);
  });
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
  if (currentVideoUrl) {
    player.currentTime = Number(seconds) || 0;
    player.play().catch(function () {});
  }
  if (currentYoutubeId) document.getElementById("youtube-player").src =
    "https://www.youtube.com/embed/" + currentYoutubeId + "?start=" + Math.max(0, Math.floor(Number(seconds) || 0)) + "&autoplay=1";
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
  var groundedEdges = graphData.edges.filter(function (edge) { return edge.grounded; });
  document.getElementById("stat-nodes").textContent = graphData.nodes.length + " Nodes";
  document.getElementById("stat-edges").textContent = groundedEdges.length + " Grounded Edges";
  if (!window.vis) {
    container.replaceChildren();
    var fallback = document.createElement("div");
    fallback.className = "graph-fallback";
    graphData.nodes.forEach(function (node) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = node.label;
      button.addEventListener("click", function () { showNodeMentions(node); });
      fallback.appendChild(button);
    });
    groundedEdges.forEach(function (edge) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = edge.source + " → " + edge.relation + " → " + edge.target + " [" + formatTime(edge.start_time) + "]";
      button.addEventListener("click", function () { showEvidenceDrawer(edge); });
      fallback.appendChild(button);
    });
    container.appendChild(fallback);
    return;
  }
  var nodes = graphData.nodes.map(function (node) {
    return Object.assign({}, node, { title: node.label, group: node.type, mentions: node.mentions || [] });
  });
  var edges = groundedEdges.map(function (edge, index) {
    return Object.assign({}, edge, { id: edge.id || "edge-" + index, from: edge.source, to: edge.target, label: window.innerWidth < 600 ? "" : edge.relation, arrows: "to", timestamp_str: formatTime(edge.start_time) });
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
  document.getElementById("inspector-relation").textContent = edge.relation || edge.label || "RELATION";
  document.getElementById("inspector-quote").textContent = "“" + (edge.evidence_quote || "No quote") + "”";
  var timestamp = document.getElementById("inspector-timestamp");
  timestamp.textContent = "[" + formatTime(edge.start_time) + "] Jump to evidence";
  timestamp.dataset.start = edge.start_time;
  timestamp.disabled = false;
  document.getElementById("inspector-confidence").textContent = Math.round((edge.confidence == null ? 1 : edge.confidence) * 100) + "%";
  document.getElementById("inspector-mentions").classList.add("hidden");
  document.getElementById("edge-evidence-drawer").classList.remove("hidden");
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
  document.getElementById("inspector-timestamp").disabled = true;
  document.getElementById("inspector-timestamp").textContent = "Select a mention";
  document.getElementById("inspector-confidence").textContent = "—";
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
  var citations = (result.citations || []).filter(function (item) { return item.verified; });
  var shown = new Set();
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
      shown.add(citation);
    }
    cursor = pattern.lastIndex;
  }
  message.appendChild(document.createTextNode(answer.slice(cursor)));
  citations.filter(function (citation) { return !shown.has(citation); }).forEach(function (citation) {
    var chip = document.createElement("button");
    chip.type = "button";
    chip.className = "citation-pill verified";
    chip.textContent = "[" + formatTime(citation.start_time) + "]";
    chip.title = citation.quote;
    chip.addEventListener("click", function () { seekVideo(citation.start_time); });
    message.appendChild(chip);
  });
  var history = document.getElementById("qa-chat-history");
  history.appendChild(message);
  history.scrollTop = history.scrollHeight;
}
