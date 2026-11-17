const find = (id) => document.getElementById(id);
const fields = [
  ["p95_ttft_ms", "P95 首 token 延迟", "ms", "越低越好"],
  ["p95_e2e_ms", "P95 完整回答耗时", "ms", "越低越好"],
  ["output_tokens_per_second", "总输出吞吐", "token/s", "越高越好"],
];

function textNode(tag, text, className = "") {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

function renderMetrics(runs) {
  for (const [field, title, unit, direction] of fields) {
    const card = document.createElement("section");
    card.append(textNode("h3", title), textNode("p", direction, "benchmark-note"));
    const max = Math.max(...runs.map((run) => run[field]));
    for (const run of runs) {
      const row = document.createElement("div");
      row.className = "benchmark-row";
      row.append(textNode("span", "并发 " + run.concurrency));
      const meter = document.createElement("meter");
      meter.max = max;
      meter.value = run[field];
      meter.setAttribute("aria-label", title + "，并发 " + run.concurrency);
      row.append(meter, textNode("strong", run[field] + " " + unit));
      card.append(row);
    }
    find("benchmark-metrics").append(card);
  }
}

async function load() {
  try {
    const response = await fetch("/vllm-benchmark.json");
    if (!response.ok) throw new Error("没有已发布的验收结果。");
    const report = await response.json();
    renderMetrics(report.runs);
    find("benchmark-status").textContent = report.date + " · GitHub Actions 实测";
    find("benchmark-environment").textContent = report.environment;
    const runLink = find("benchmark-run");
    runLink.href = report.run_url;
    runLink.hidden = false;
    find("download").hidden = false;
  } catch (error) {
    find("benchmark-status").textContent = error.message;
  }
}

load();
