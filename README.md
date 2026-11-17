# 医院后勤制度助手

面向后勤服务台的制度检索项目。科室人员可以查询设备报修、物资采购、库房管理和设施巡检，直接核对条款原文。示例数据为虚构的后勤流程。

- [在线制度助手](https://fde-hospital-ops.onrender.com/)（Render 免费实例，首次访问可能需要唤醒）
- [在线推理压测报告](https://fde-hospital-ops.onrender.com/benchmark.html)
- [Docker、Compose 和 Kubernetes 实跑验收](https://github.com/Hyxxt/fde-hospital-ops/actions/runs/44054609325)

## 架构

```text
浏览器 → FastAPI → ONNX Runtime（BGE-Small-ZH INT8）→ PostgreSQL + pgvector
                          ↓                             ↓
                    查询文本向量                  权限过滤、余弦排序
                          └────── BM25 + RRF 加权融合 ──┘
                                       ↓
                           相似度过滤、拒答或展示条款
                                       ↓
                         私有环境可接 vLLM 生成带引用回答
```

公开演示是只读沙箱，以本地 PostgreSQL Unix socket 连接同容器内的 pgvector。数据库由镜像内的示例资料重建，公开请求只能看到普通条款。Docker Compose 和 Helm 使用独立 PostgreSQL 与持久化卷，私有模式在 SQL 检索前应用岗位范围。生成模式校验引用 ID 是否属于权限过滤后的检索结果，模型超时或响应格式无效时返回原文。

## 私有部署

### Docker Compose

```bash
cp .env.example .env
# 填写数据库密码和两个不同的访问令牌（每个至少 16 字符）
docker compose up -d --build --wait
curl -fsS http://127.0.0.1:8080/readyz
docker compose --profile monitoring up -d
```

打开 `http://127.0.0.1:8080`，用对应岗位的令牌访问。Prometheus 默认只绑定回环地址的 9090 端口，可执行 `rate(hospital_questions_total[5m])` 和 `histogram_quantile(0.95, sum by (le) (rate(hospital_retrieval_seconds_bucket[5m])))`。

挂载权重目录前，在可联网环境准备镜像和模型。启用生成时，将 `Qwen/Qwen3-0.6B` 权重放到 `models/qwen`，设置 `LLM_URL=http://vllm:8000/v1`，运行 `docker compose --profile gpu up -d`。GPU 模式需要 Linux、NVIDIA 驱动和 NVIDIA Container Toolkit。本机入口由 Nginx 转发，应用和数据库只接入内部网络。

离线节点先用 `docker load` 导入连接环境通过 `docker save` 导出的应用、pgvector、Nginx 和所选 profile 镜像，再运行 `docker compose up -d --no-build --pull never --wait`。模型准备阶段需要联网，运行时的 ONNX 模型已打进应用镜像。

### Kubernetes

```bash
kubectl create namespace hospital
kubectl -n hospital create secret generic hospital-ops-secrets --from-env-file=./.env
helm upgrade --install hospital helm/hospital-ops -n hospital \
  --set image=<节点可用的应用镜像> --wait --timeout 4m
kubectl -n hospital port-forward svc/hospital 8080:8080
```

集群需要支持动态 PVC（或通过 `storageClassName` 指定存储类）和支持 NetworkPolicy 的 CNI。预先把应用及 pgvector 镜像导入节点，或指定内网镜像仓库。chart 提供 ClusterIP、探针、资源限制、数据库持久卷和出站限制。可接同命名空间、标签为 `hospital-component: hospital-vllm`、监听 8000 的推理 Pod，通过 `llmUrl` 配置地址。

## 验收与排障

- 公开示例实测 Recall@3 为 BM25 10/12、向量 12/12、混合 12/12，4 道范围外问题均拒答。
- 运行网页的 16 题评测，查看三种策略的 Recall@3 和范围外样例拒答数。小样本用于复现行为。固定语料可在 `app/knowledge.json` 查看，问答样例在 `app/eval_cases.json`。
- 本地以 `STAFF_TOKEN`、`OPS_TOKEN` 和可选 `BASE_URL` 运行 `python scripts/smoke.py`，验证健康探针、带引用检索、拒答、岗位隔离与指标。
- `/healthz` 检查应用存活，`/readyz` 确认 pgvector 已连接。若数据库未就绪，先看 `docker compose logs app db` 或 `kubectl -n hospital describe pod`。检索阶段只上报耗时与状态，Uvicorn 访问日志默认关闭。
- Helm 回滚用 `helm history hospital -n hospital` 查看修订，再执行 `helm rollback hospital <修订号> -n hospital --wait`。备份可用 `docker compose exec -T db pg_dump -U hospital -d hospital -Fc > hospital.dump`（Linux shell）。示例条款由当前镜像版本管理，容器启动时同步。

## vLLM 推理实验

在 [Linux CPU 运行记录](https://github.com/Hyxxt/fde-hospital-ops/actions/runs/44054392588)中，vLLM 启动 Qwen3-0.6B 的 OpenAI 兼容服务。脚本在预热后分别用并发 1 和 4 请求同一组中文提示，读取 SSE 的首个可见 token，记录 P95 和总输出 token/s。

```bash
python scripts/bench_vllm.py --url http://127.0.0.1:8000/v1 --model qwen-hospital
```

公开报告展示 CPU FP32 实测。Compose 提供 GPU 启动配置，具体显卡的吞吐和显存需要按部署环境单独测量。

模型来源：[BAAI BGE-Small-ZH](https://huggingface.co/BAAI/bge-small-zh-v1.5)、[Xenova ONNX 权重](https://huggingface.co/Xenova/bge-small-zh-v1.5)。[pgvector](https://github.com/pgvector/pgvector) 负责向量检索，可在实际语料量下用 `EXPLAIN ANALYZE` 检查 HNSW 是否被选用。
