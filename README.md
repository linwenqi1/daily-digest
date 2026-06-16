# daily-digest

Daily Digest 会每天抓取多源科技新闻，提取网页正文，用 DeepSeek 生成中文摘要，并通过 GitHub Actions 提交 Markdown 摘要、发送邮件。

## Sources

当前采集源：

- Hacker News Top Stories：保留分数、评论数和部分社区评论。
- Lobsters RSS
- The Verge Tech RSS
- Ars Technica Technology Lab RSS
- MIT Technology Review RSS

脚本会按来源配额抓取并去重，默认生成最多 12 条新闻。

## Output

每条新闻包含：

- 关键概念：列出理解新闻需要的概念并解释。
- 文章摘要：概括事实、影响和重要数据。
- 社区讨论：仅在有评论时总结主要观点；没有评论会标记为暂无社区评论。

## GitHub Actions

workflow 位于 `.github/workflows/daily-digest.yml`。

- 定时触发：每天 `14:00 UTC`，也就是北京时间/上海时间 `22:00`。
- 手动触发：GitHub Actions 页面中的 `workflow_dispatch`。

需要配置这些 repository secrets：

- `DEEPSEEK_API_KEY`
- `EMAIL_USER`
- `EMAIL_PASSWORD`
- `EMAIL_TO`

模型默认使用 `deepseek-v4-pro`，也可以通过环境变量 `DEEPSEEK_MODEL` 覆盖。

## Local Run

```bash
pip install -r requirements.txt
python scripts/fetch_news.py
python scripts/enrich_news.py
python scripts/generate_digest.py
python scripts/generate_email.py
```
