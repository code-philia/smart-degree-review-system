# 登录页开发与交付

两套登录外观共用一个应用、一个 `AuthPage` 和原有认证逻辑。登录之外的业务页面、接口、额度和报告逻辑没有分叉。不要为了选登录页回退整个应用，也不要把旧的整份应用覆盖最新 main。

## 开发与比较

业务开发继续以 main 为准。需要更新备选登录页时，先获取最新 main，再把 main 合入 `feat/login-v2-split`；这一步只更新备选分支，不会修改 main。发布或比较前确认最新 main 已包含在当前候选提交中：

```text
git fetch origin
git merge origin/main
git merge-base --is-ancestor origin/main HEAD
```

前端目录中的命令在 Windows、Linux 均适用：

```text
npm run dev:login:campus
npm run dev:login:split
npm run build:login:campus
npm run build:login:split
```

这四条命令通过进程内的 `VITE_LOGIN_VARIANT` 临时选择外观，不修改账号配置和系统环境。普通 `npm run build` 则读取受版本管理的 `frontend/config/login-variant.json`。默认选择 `campus`，保持 main 当前外观。外部提供的 `VITE_LOGIN_VARIANT` 优先于配置文件，因此正式构建应使用现有发布器的干净环境，避免个人环境中的比较选项混入发布。

## 领导选定后的正式交付

1. 先同步最新 main。将 `frontend/config/login-variant.json` 的 `variant` 设为 `campus`（校园背景版）或 `split`（严肃版），作为明确的选择提交；业务代码无需复制或回退。
2. 对同一候选提交验证两种登录外观，检查中文、英文、宽屏与窄屏，以及认证失败重试、会话恢复、退出和原报告回跳。
3. 在干净构建中执行普通 `npm run build`。确认 `frontend/dist/login-variant.json` 的 `variant` 与选定值一致，并检查 `/auth` 的 Link 预加载指向该版本实际使用的图片。
4. 用户确定选择并授权发布后，按原有审核、合并 main 和标准发布流程交付。当前任务不合并、不更新 main，也不重启原 3000 站点。
5. 正式站直接运行正常后端 `backend/src/index.js`。沿用正式站点的已注册 jAccount 回调、域名及会话配置；无需运行 `loginSplitPreview.js`，也不依赖 443 预览入口。切换正式域名时，需要由有权限的管理员同步核对对应的 jAccount 注册回调。

构建输出会自动携带登录选择清单。正常后端和临时预览服务都会读取这个清单选择预加载图片；旧构建没有清单时保留原校园版行为；未知或损坏的清单拒绝启动，避免外观和预加载不一致。

## 当前比较入口

- 原站：`http://121.36.247.138:3000/auth`，main 的校园背景版。
- 严肃版比较入口：`http://121.36.247.138:443/auth`，显式 split 构建，转发到原站公共后端。

比较入口共用账号、额度和报告数据。由于不修改原站认证配置，其 jAccount 认证成功后进入原站主页；通过代理的试验账号登录共享后端的同一来源频率限制。它是比较入口，不是最终部署架构。正式交付不应保留这些代理约束。

## 验证范围和回退

认证自动化测试使用隔离测试数据库与受控身份提供方响应；它验证状态校验、会话和跳转，不等同于真实 jAccount 凭据验收。最终上线前，应由具备真实授权账号的使用者在正式域名完成一次真实认证及退出验收。

回退沿用原有不可变版本目录与发布器的回退机制，切回上一整套代码、构建产物和清单。不要单独替换图片或清单。备选登录页的提交不修改已保存报告、用户余额或检测规则。
