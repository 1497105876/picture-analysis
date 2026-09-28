# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 SemVer。

## [Unreleased]

### Added

- 需求基线：`docs/需求与功能清单.md`（F1-F15、G1-G18、效果要求、里程碑）
- 工程文档集：SRS、架构、详细设计（含 SQLite 直读契约）、质量属性与工程规范、测试计划、集成与持续交付
- ADR-001~005（SQLite 唯一存储 / 不做 MCP / FastAPI+Vue3 / OCR 按需触发 / 限速 20 次每分）
- 工程骨架：FastAPI 应用装配、健康端点、pytest + ruff + mypy 门禁、本地 CI 脚本、打包脚本
- GitHub Actions CI（backend lint/type/test + 条件 frontend build + package）
