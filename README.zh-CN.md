# WebLibre 中文测试版

为 [WebLibre](https://github.com/FaFre/WebLibre) 增加简体中文界面，并自动跟进上游、翻译新增文案、构建 Android 安装包。本仓库不是官方发布渠道。

## 下载与使用

成功构建后，安装包会放在 [zh-latest 发布页](https://github.com/huanxueshengmou/WebLibre-zh/releases/tag/zh-latest)。发布页还会列出源代码版本、安装包版本号和 SHA-256 校验值；如果没有 APK，说明尚未发布成功。

- 大多数较新的 Android 手机选择文件名含 `arm64-v8a` 的 APK；另外提供 `armeabi-v7a` 和 `x86_64`。
- 手机语言偏好列表中，中文排在英语前面时显示简体中文，英语排在中文前面时显示英语。两种语言都没有时回落英语。
- 软件界面语言与「网站能看到的浏览器语言」是不同设置，不会为了汉化修改网站语言、账号、Cookie 或网络配置。
- 改变手机语言后重新打开应用最稳妥；运行时会重新读取语言，但不承诺每个已经打开的页面立即重绘。

### 安装与升级注意

构建保留上游 alpha 包名。自签名版本不能直接覆盖异签名的官方 alpha 版；稳定版是否可共存取决于上游的包名配置。**不要为了安装而直接卸载有重要账号资料的旧版，先在应用内备份。**

未配置正式签名时，使用缓存的 Android 测试签名并标为预发布版。缓存失效可能使签名改变，届时无法覆盖升级。需要长期使用时，请为仓库配置并妥善备份固定签名：

| Repository secret | 内容 |
|---|---|
| `KEY_JKS` | 自有 keystore 文件的 base64 内容 |
| `KEY_PASSWORD` | 密钥库及密钥的密码 |
| `KEY_ALIAS` | 密钥别名 |

私钥不会进入 Git 或 APK 附件。测试签名缓存仅适合试用，不能代替正式私钥管理。

## 自动更新

工作流 `.github/workflows/i18n.yml` 会在北京时间每天 **11:17** 运行，也可在 Actions 中手动运行。推送工具、词典或工作流修改到 `main` 也会触发。

手动运行时可关闭 APK 构建，或开启「忽略缓存、重新翻译」。自动事件仍会构建，确保上次失败后能重试。

### 分支分工

| 分支 | 用途 |
|---|---|
| `main` | 上游参考代码、汉化工具、人工词典和翻译缓存；人工修改这里 |
| `zh` | 从干净上游重新生成的中文源码；不要手工修改 |

生成内容不是把数百处中文修改合并进上游，而是每次重新加工，因此避免了翻译源码合并冲突。上游若改变重要界面或构建接口，补丁会明确报错，仍需要维护，不能保证永远自动适配。

每次生成与远端 `zh` 的实际文件树比较。有变化则追加生成提交，没有变化则复用原提交；构建使用不可变的 `generated_sha`，不会误用运行过程中移动的分支。只有滚动标签 `zh-latest` 会在发布时移动。

应用源码继续同步最新上游，但 `.github/workflows/` 保留远端 `zh` 已有内容，避免默认 `GITHUB_TOKEN` 因修改工作流而拒绝整次推送。首次生成时使用触发任务的 `main` 提交中的工作流。中文版构建由 `main` 的 `i18n.yml` 控制；工作流与构建工具版本由维护者单独更新。

## 为什么这次使用官方 Dart 解析

Dart 常量初始化器不能调用运行时翻译函数。单靠逗号、括号和关键字猜测作用范围，容易把泛型参数中的逗号、三元表达式、构造函数初始化列表判断错。

现在扫描器只判断哪些文字可能属于界面；**Dart 官方 analyzer 的语法树负责决定能否改写**：

- 普通显示表达式：`const Text('Cancel')` → `Text(tr("Cancel"))`。
- 常量变量、常量构造函数、参数默认值、注解、枚举和常量模式保持合法，不盲目删除 `const`。
- 常量数据中的文字仍进入翻译清单。设置分类、搜索结果、代理表单、延迟提示等已确认的显示入口，在显示时取译文；内部标识符、表单实际值和用户内容不翻译。
- `include_strings` 只能补充识别，不能绕过语法安全限制。
- 每轮处理直到不再变化；再跑一遍必须保持源码及词条清单字节相同。

## 检查顺序

1. Python 工具回归、官方 Dart 语法检查、真实 Dart kernel 编译与运行。
2. 手机语言优先级及占位符测试；工作流 YAML 和 Bash 语法测试。
3. 在干净上游执行显示入口补丁、源码改写、语言接入、翻译、查找表生成。
4. 重新解析生成源码，检查常量上下文；验证重复执行无变化。
5. 在固定 Flutter SDK 下解析项目依赖、分析整份应用源码、执行真实界面冒烟测试。
6. 前面全部通过后才编译 NDK/Go 原生组件与 APK。
7. 检查三个架构的 APK 均存在并通过签名验证，生成校验值，再发布。

失败日志会提取为 Actions annotation；不会因为依赖失败就悄悄删除框架级中文。缓存保存失败只警告，不阻断本轮安装包构建。

## 翻译来源与统计口径

优先级：**人工词典 → 已有缓存 → Argos Translate**。Argos 是开源离线翻译引擎，不要求账号或 API Key；首次运行需要下载模型。有兼容接口时可配置 `I18N_LLM_API_KEY` Secret，以及 `I18N_LLM_BASE_URL`、`I18N_LLM_MODEL` Repository variables。

修改翻译请编辑 `tools/i18n/glossary.json`，不要修改生成分支。词典会覆盖机器翻译，并保留 `{0}`、`{1}` 等动态参数。

报告中的 `coverage` 是**进入清单的词条翻译率，不是全应用汉化率，也不是翻译质量评分**。即使达到 100%，也不能据此认定所有页面、网页内容、原生组件或上游新增界面都已汉化。未翻译的内容保留英文，不虚构译文。

`i18n/transform-report.json` 记录改写数量及不能直接改写的常量位置；这些位置是否有显示入口翻译需要单独审查。不能为提高数字而从统计中隐藏它们。

## 本地验证

需要 Python、Dart 3.13.3；整项目检查另需 Flutter 3.47.5。Dart AST 依赖固定在 `tools/i18n/dart_ast/pubspec.lock`。Windows 可设置 `DART` 为 `dart.exe` 的绝对路径。不要把 `.dart_tool`、SDK、虚拟环境或签名私钥提交进仓库。

```bash
# 在 tools/i18n/dart_ast 目录运行一次
# dart pub get

python tools/i18n/test_i18n.py
dart tools/i18n/test_locale_policy.dart
python tools/i18n/test_ci.py
python tools/i18n/test_preserve_workflows.py

# TARGET 必须是一份独立的、干净的上游 checkout
python tools/i18n/patch_ui.py "$TARGET"
python tools/i18n/codemod.py "$TARGET"
python tools/i18n/patch_app.py "$TARGET"
# 把 main 的 i18n/zh.json 复制到 TARGET/i18n/zh.json 后再翻译
python tools/i18n/translate.py --repo "$TARGET"
python tools/i18n/gen_table.py --repo "$TARGET"
python tools/i18n/verify.py "$TARGET"
python tools/i18n/ci_checks.py idempotency "$TARGET"
```

只验证已有词典和缓存时，可给翻译命令加 `--engine none`；此时缺失词条不会自动补译。安装 Python 翻译依赖时请使用隔离虚拟环境。

## 授权

保留上游版权和 AGPL-3.0 授权。本仓库改动沿用相同协议。构建对应的 `zh` 提交包含可获取的完整源代码和本轮汉化工具。
