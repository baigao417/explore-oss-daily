# Explore

Explore selects one open-source project per day using explainable metadata ranking
and a configurable profile, then produces an L1/L2/L3 learning outline. This
standalone snapshot runs offline by default and needs only Python's standard library.

每天只看一个值得研究的开源项目，减少候选过多却无法决定学什么的问题。
本公开版从原应用抽取每日推荐主链：可解释评分、可配置需求匹配、三层报告和本地反馈。
作者：`baigao417`。不包含原工作站扫描器、私人画像、历史产物或账号投递模块。

## 核心机制

```text
离线候选 JSON -------------------+
匿名 GitHub 元数据（显式启用）---+--> 去重 / 分类 / 分项评分 --> 每日 Top 1
显式 profile JSON --------------+                                 |
本地 1-10 分反馈 ---------------+                                 v
                           L1 项目概况 / L2 需求交集 / L3 学习问题
                                          |
                                          v
                               Markdown + JSON + 学习提纲
```

评分保留 relevance、production_value、activity、momentum、readme_quality、
architecture_learnability、workstation_fit、noise_penalty 和反馈调整项。
这些只是元数据启发式信号，不代表已核验源码质量、README 内容或生产适用性。
`evidence_mode` 始终为 `metadata_only`，高分不会自动升级为深度研究。
L2 的关键词与项目需求来自指定文件，不自动遍历电脑、笔记或其他仓库。

## 快速开始

需要 Python 3.11 或更高版本。在仓库根目录运行；不需要安装依赖或配置密钥。

```sh
python -B -m explore --help
python -B -m explore daily
python -B -m explore feedback --project fictional-lab/retrieval-kit --score 8
python -B -m explore daily
python -B -m unittest discover -s tests -v
```

默认输出：`outputs/daily/<日期>-oss-daily.md`、同名 JSON、
`outputs/data/project_pool.json` 和 `outputs/feedback/oss_feedback.jsonl`。
同一天再次运行会覆盖该日推荐文件；这是一次每日选择，不是自动调度或防重复投递。
样例项目完全虚构，`example.invalid` 链接不可访问。
`examples/daily/` 中两份报告由虚构数据生成，不是历史生产日刊。

可以把所有运行状态写到仓库外指定目录：

```sh
python -B -m explore daily --output ../local-explore-state
python -B -m explore feedback --project fictional-lab/retrieval-kit --score 8 --output ../local-explore-state
```

## 配置

复制 `config/profile.example.json` 为 `config/profile.local.json`，填入自己的需求。
本地文件会被忽略。示例只含两个虚构软件项目，无身份、学校或工作站路径。

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 固定为 `1.0` |
| `terms` | 用于排名的英文关键词；匹配大小写不敏感 |
| `binding_hints` | 关键词到通用业务标签的映射 |
| `projects[].name` | 自定义项目名，可使用别名 |
| `projects[].need` | 该项目需要解决的问题 |
| `projects[].terms` | 判断需求交集的关键词，也用于评分 |

```sh
python -B -m explore daily --profile config/profile.local.json
```

离线候选按 `examples/projects.json` 结构编写，使用 `--candidates` 指定。
`synthetic: true` 表示虚构数据；普通离线数据不会被当成实时采集。
候选字段对应 `ProjectCandidate`；数量类字段要求非负整数，URL 要求 HTTPS 且不能含凭证。
`raw` 仅保留 archived、disabled、license、size 四个元数据字段。
给候选文件使用 `*.local.json` 命名，并且不要把个人信息、凭证或第三方文章正文放进去。

信息源只有通用示例查询 `config/sources.example.json`，可复制为
`config/sources.local.json`。配置项 `github_queries` 允许 1-10 个公开仓库查询。
**只有显式使用 `--online` 才会请求 GitHub 公开 API**，不读取 token，也不登录账号。

```sh
python -B -m explore daily --online --sources config/sources.example.json --per-query-limit 10
```

本地准备阶段未执行此在线命令。匿名请求受限流、网络和平台条款约束，失败按查询降级；
全部查询失败时不生成推荐。每次每个查询最多读取一页，1-100 个结果，不下载仓库或文章。
`.env.example` 仅说明可选环境变量 `EXPLORE_HTTP_USER_AGENT`，不自动加载 `.env`。
客户端标识不能伪装成浏览器，也不应包含个人联系方式。

## 测试

```sh
python -B -m unittest discover -s tests -v
```

测试使用标准库 unittest、虚构数据和 mocked HTTP，不访问网络。
测试临时文件默认位于被忽略的 `outputs/test-tmp/`；可设置
`EXPLORE_TEST_TMPDIR` 指向仓库外目录。
仓库根目录的 `explore/` 是不安装即可运行的引导包，实际源码位于 `src/explore/`。
如需安装，项目元数据与 console entry point 已在 `pyproject.toml` 声明；安装方式本轮未验证。

## 已知限制

- 当前为 CLI + 文件报告，没有原应用的网页、数据库、多源信息流、深读、播客、调度或消息投递。
- L1 基于公开元数据，L2 是关键词匹配，L3 是待验证问题，不是自动完成的源码分析。
- 默认关注软件与 AI 工具，规则权重未经过大规模用户研究或推荐效果验证。
- 一个日期只输出一个推荐；不会自动剔除前几天看过的项目，同项目可以再次入选。
- 反馈会影响后续排序，但不是机器学习训练；缺少时间戳时 activity 使用中性分。
- profile、候选输入与运行输出可能包含使用者自行填写的信息，必须保持本地且不提交。
- `.gitignore` 是防误提交措施，不是敏感信息审计的替代品；发布前仍需扫描新文件。

## 免责声明与许可

本工具用于学习与研究，不保证推荐质量、信息实时性、合规性或商业收益。
采纳任何项目之前，独立核验其许可证、安全风险、维护状态及平台 API 条款。
不提供投资、健康或法律建议，不对其他系统做自动改动。
本应用采用 MIT 许可证，第三方项目的许可证与内容权利不会因此改变。
本快照不包含第三方文章、逐字稿、下载包或 vendored 代码，见 `THIRD_PARTY_NOTICES.md`。
