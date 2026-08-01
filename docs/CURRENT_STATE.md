# Current State

Date: 2026-07-20

## Live Environment

- Domain: `https://jps-one.com`
- AWS region: `ap-southeast-2`
- EC2 instance name: `auto-find`
- EC2 instance ID: `i-0a2275c1e58d79847`
- Public IP / Elastic IP: `16.176.89.104`
- Runtime: conda `ai-hunter`
- Backend entry: `api.app:app`
- Frontend title after rebrand: `JPS One 智能获客工作台`
- Frontend shell: JPS One Web 工作台，桌面左侧导航，移动端顶部横向导航。

## Confirmed Capabilities

- Hunt task dashboard and new hunt flow exist.
- Automation queue and embedded consumer exist.
- Email center and settings exist.
- Integration center exists.
- Search capability has detected Tavily and Jina Reader.
- Meta/Facebook OAuth configuration exists.

## Known Gaps

- Meta/Facebook is connected but Page count was observed as `0`, so Page-based workflows are not ready.
- Instagram and WhatsApp are foundation placeholders.
- Customer pool, product catalog, matching center, quote center, RAG knowledge center, and integration center are Web UI foundations first.
- README and docs are JPS One-specific and should keep following each new module.

## Safety Notes

- Do not overwrite `API_ACCESS_TOKEN`.
- Do not commit or publish real secrets.
- Deploy only after backup, local tests, frontend build, and health checks.
