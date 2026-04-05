---
name: Git 助手
description: 帮助用户执行 Git 相关操作，包括提交、推送、分支管理、查看日志等。
version: 1.0.0
---

# Git 助手

## 概述

当用户的任务与 Git 版本控制相关时，使用此技能来辅助完成操作。

## 使用说明

1. 提交前先用 `git status` 查看当前状态
2. commit message 使用简洁的中文描述
3. 推送前确认当前分支名称
4. 涉及危险操作（force push、reset --hard）时需要先确认

## 示例

- 用户说"帮我提交代码" → 先 `git status`，再 `git add .`，再 `git commit`
- 用户说"看看最近的提交" → 执行 `git log --oneline -10`
