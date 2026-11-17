const find = (id) => document.getElementById(id);
const form = find("ask-form");
const answer = find("answer");
const question = find("question");
const submit = find("submit");
const evalButton = find("eval-button");
const strategies = ["bm25", "vector", "hybrid"];
const strategyLabels = { bm25: "关键词", vector: "语义", hybrid: "混合" };

function node(tag, content, className) {
  const element = document.createElement(tag);
  element.textContent = content;
  if (className) element.className = className;
  return element;
}

async function request(path, options = {}) {
  const token = find("token").value.trim();
  const headers = { ...options.headers };
  if (token) headers.Authorization = "Bearer " + token;
  const response = await fetch(path, { ...options, headers });
  const result = await response.json();
  if (!response.ok) {
    const detail = typeof result.detail === "string" ? result.detail : "请检查输入后重试。";
    throw new Error(detail);
  }
  return result;
}

request("/api/config").then((config) => {
  find("credentials").hidden = config.public_demo;
  find("environment").textContent = config.public_demo ? "公开演示 · 虚构资料" : "私有部署";
}).catch(() => {
  find("environment").textContent = "服务暂不可用";
});

find("examples").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button || submit.disabled) return;
  question.value = button.lastChild.textContent.trim();
  form.requestSubmit();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = question.value.trim();
  if (!text) {
    question.focus();
    return;
  }
  submit.disabled = true;
  answer.hidden = false;
  find("answer-title").textContent = "正在检索";
  find("answer-text").textContent = "";
  find("timing").textContent = "";
  find("citation-title").hidden = true;
  find("citations").replaceChildren();
  try {
    const result = await request("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text, strategy: find("strategy").value }),
    });
    const labels = { generated: "制度问答", evidence: "最相关条款原文", abstain: "资料不足" };
    find("answer-title").textContent = labels[result.outcome];
    find("answer-text").textContent = result.answer;
    find("timing").textContent = "检索 " + result.retrieval_ms + " ms";
    find("citation-title").hidden = result.citations.length === 0;
    result.citations.forEach((citation, index) => {
      const details = document.createElement("details");
      details.open = index === 0;
      details.append(
        node("summary", citation.id + " · " + citation.title),
        node("p", citation.body),
      );
      find("citations").append(details);
    });
  } catch (error) {
    find("answer-title").textContent = "查询失败";
    find("answer-text").textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

evalButton.addEventListener("click", async () => {
  const output = find("eval-result");
  evalButton.disabled = true;
  output.textContent = "正在运行评测…";
  try {
    const result = await request("/api/eval");
    const stats = strategies.map(
      (key) => strategyLabels[key] + " " + result.recall_at_3[key] + "/" + result.relevant_count,
    );
    stats.push("范围外拒答 " + result.reject_count + "/" + result.out_of_scope_count);
    output.replaceChildren(node("p", stats.join("　·　"), "stats"));
    const details = document.createElement("details");
    const wrapper = document.createElement("div");
    wrapper.className = "eval-table-wrap";
    const table = document.createElement("table");
    const heading = table.createTHead().insertRow();
    ["问题", "参考条款", "关键词 Top 3", "语义 Top 3", "混合 Top 3", "混合通过阈值"].forEach(
      (label) => heading.append(node("th", label)),
    );
    const tbody = table.createTBody();
    for (const item of result.cases) {
      const row = tbody.insertRow();
      const cells = [
        item.q, item.expected || "范围外",
        ...strategies.map((key) => item.rankings[key].join("、") || "—"),
        item.accepted.join("、") || "拒答",
      ];
      for (const value of cells) row.append(node("td", value));
    }
    wrapper.append(table);
    details.append(node("summary", "查看逐题结果"), wrapper);
    output.append(details);
  } catch (error) {
    output.textContent = error.message;
  } finally {
    evalButton.disabled = false;
  }
});
