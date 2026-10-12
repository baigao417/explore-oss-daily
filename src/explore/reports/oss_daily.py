"""Source-derived L1/L2/L3 outline; metadata is never presented as code review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from explore.processors.oss import _hits


def matching_projects(project: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    from explore.oss_models import ProjectCandidate

    payload = {key: value for key, value in project.items() if key != "id"}
    hits = _hits(ProjectCandidate(**payload))
    return [item for item in profile["projects"] if hits & set(item["terms"])]


def write_oss_daily_report(
    ranked: list[dict[str, Any]], *, profile: dict[str, Any], errors: list[str],
    root: Path, issue_date: str, synthetic: bool, online: bool = False,
) -> Path:
    if not ranked:
        raise ValueError("cannot recommend from an empty pool")
    top = ranked[0]
    project, score = top["project"], top["score"]
    matched = matching_projects(project, profile)
    bindings = [f"- {p['name']}：{p['need']}（关键词匹配，尚未验证兼容性）" for p in matched]
    if not bindings:
        bindings = ["- 尚无明确需求交集：仅观察，不建议直接接入。"]
    outline = ["核验 README、许可、维护状态和运行前提。",
               "对照 profile 中的需求，验证接口、技术栈和部署约束。",
               "记录一个待验证的可迁移机制，必要时设计独立 POC。"]
    daily = root / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    path = daily / f"{issue_date}-oss-daily.md"
    kind = ("虚构示例，非真实项目或实时采集" if synthetic else
            "匿名 GitHub 公开元数据" if online else "离线候选，非实时采集")
    terms = ", ".join(score.get("binding_hints") or []) or "无配置标签匹配"
    text = f"""# Explore OSS Daily: {issue_date}

数据模式：{kind}。分析模式：metadata_only；未读取源码，未调用 LLM。

今日唯一推荐：[{project['full_name']}]({project['url']})

## L1：它是什么

- 描述：{project['description'] or '暂无描述'}
- 元数据规则评分：{score['total']} / 10，等级 {score['grade']}。
- stars={project['stars']}，language={project['language']}。
- 分类：{score['category']}。星数和描述不能证明代码质量或生产可用性。

## L2：与配置需求的关系

{chr(10).join(bindings)}

- 配置标签：{terms}。
- 当前只读取显式 profile 文件；不扫描工作站、个人笔记或其他目录。
- 配置关系不等于采纳建议，接入前需人工验证许可和技术约束。

## L3：待验证的方法迁移

- 观察项目如何划分核心对象、接口和测试边界。
- 对照示例、失败处理和评测机制，再判断能否迁移。
- 以上为学习问题，不是关于作者实现方式的已证实结论。

## 今日学习提纲

{chr(10).join(f'{i}. {line}' for i, line in enumerate(outline, 1))}

## 下一步

先阅读核验，选择 learn / watch / POC / adapt / avoid；不会自动修改其他项目。
可以使用 feedback 命令记录 1-10 分，再运行 daily 更新排序。

## 评分明细

```json
{json.dumps(score, ensure_ascii=False, indent=2)}
```

采集警告数：{len(errors)}。仅记录计数，不写入可能含敏感参数的异常正文。
"""
    path.write_text(text, encoding="utf-8")
    payload = {"schema_version": "1.0", "issue_date": issue_date,
               "synthetic": synthetic, "evidence_mode": "metadata_only",
               "recommendation_count": 1, "recommendation": top,
               "matched_needs": matched, "learning_outline": outline,
               "collection_warning_count": len(errors)}
    path.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    return path
