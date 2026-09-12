# WebLibre 中文版

把 [WebLibre](https://github.com/FaFre/WebLibre)（一个基于 Gecko 引擎的独立隐私浏览器）
自动汉化，并自动打包成可以直接安装的 APK。

原版 WebLibre 的界面**只有英文**，而且它的源码里没有任何多语言框架
（没有 `.arb` 文件，没有 `app_localizations`），所以不存在「切成中文」这个开关。
这个仓库做的是：**在每次构建时，从上游最新代码自动生成一套中文界面。**

---

## 它是怎么工作的

关键设计：**中文版的 Dart 源码不存在这个仓库里**，而是每次运行时重新生成的。

```
upstream/main  ──►  ① 改写：把英文字符串包成 tr("...")
                    ② 打补丁：接上语言检测
                    ③ 翻译：查词典 + 机器翻译
                    ④ 生成：中文查找表
                    ⑤ 校验：结构检查
                        │
                        ▼
                     zh 分支  ──►  ⑥ 编译 APK  ──►  Release
```

这样做的好处是：**上游怎么重构都不会产生冲突**。因为不是「合并」，
而是「拿一份干净的上游代码重新加工一遍」。这个仓库真正需要维护的只有三样东西：
工具、词典、翻译缓存。

分支分工：

| 分支 | 内容 | 能不能手改 |
|---|---|---|
| `main` | 上游代码镜像 + 工具 + 翻译缓存 | ✅ 要改就改这里 |
| `zh` | 生成出来的中文版源码（自动覆盖） | ❌ 改了下次会被冲掉 |

### 六个步骤分别在做什么

1. **改写**（`tools/i18n/codemod.py`）
   扫描全部 1400 多个 Dart 文件，找出用户能看到的英文字符串，替换成 `tr("原文")`。
   原文**保留下来当查询键**，所以没翻译的字符串会自然地显示英文，而不是报错或显示乱码。

   这一步最难的地方是 `const`。约 63% 的字符串位于 `const` 表达式里
   （例如 `const Text('Cancel')`），而函数调用不能是编译期常量，所以必须把 `const` 去掉。
   绝大多数情况去掉是安全的，但有五种地方 Dart 强制要求编译期常量，
   去掉会让代码编译不过——这些地方会被识别出来并**跳过**，而不是硬改：

   | 场景 | 例子 |
   |---|---|
   | 参数默认值 | `void f({String s = 'x'})` |
   | 变量初始化 | `const kName = 'x';` |
   | 注解参数 | `@Foo('x')` |
   | switch case 标签 | `case 'x':` |
   | 枚举常量参数 | `enum E { a('x') }` |

   跳过的一共约 150 处，全部记录在 `i18n/transform-report.json` 里，不靠猜。

2. **打补丁**（`tools/i18n/patch_app.py`）
   加 `flutter_localizations`、在启动时读取手机语言、给 `MaterialApp` 声明支持的语言。
   没有这一步，软件自己的文字是中文，但 Flutter 自带的日期选择器、
   文本选择菜单还是英文，看起来很割裂。

   这一步同时踩到上游的两个约束，都做了处理：

   | 约束 | 问题 | 处理 |
   |---|---|---|
   | `melos` 用 `enforceLockfile: true` 引导 | 新增依赖必然使 lockfile 与 pubspec 不一致，引导直接失败 | 改为 `false` 并注明原因 |
   | `flutter_localizations` 把 `intl` 钉在 SDK 版本上 | app 声明的是 `intl: ^0.20.3`，两者无法同时满足 | app 的约束放宽为 `intl: any`，原始值记在注释里 |

   **框架级汉化是可选项。** 因为没有 Flutter SDK 就无法验证依赖解析，
   所以如果 `melos bootstrap` 仍然失败，工作流会自动执行
   `patch_app.py --revert-l10n`，只摘掉 `flutter_localizations` 和它的委托
   （并把 `intl` 约束还原），`tr()` 翻译完全不受影响，构建继续。
   代价只是 Flutter 自带的那几十条文字保持英文——好过整个构建失败。

3. **翻译**（`tools/i18n/translate.py`）
   三个来源，优先级从高到低：
   - `tools/i18n/glossary.json` —— **手工词典**，永远优先。界面用词高度重复，
     几百条就能覆盖用户最常看到的部分，所以这部分质量比翻译引擎重要得多。
   - `i18n/zh.json` —— **缓存**，已经翻过的直接用。因为缓存提交在仓库里，
     所以日常定时任务只需要翻译真正新增的那几条。
   - **机器翻译** —— 长尾部分。默认用 **Argos Translate**：
     纯 Python、完全离线、不需要 API Key、不需要账号，是能在 CI 里跑起来的最简单的开源方案。

   任何翻译结果都会过一道质检：占位符 `{0}` 有没有丢、有没有真的翻成中文、
   有没有原样返回。不合格的**宁可不写入**，让它显示英文，并记录到报告里。

4. **生成**（`tools/i18n/gen_table.py`）
   把 `i18n/zh.json` 变成 `lib/i18n/zh_table.dart` 里的一张 `const` 表。
   必须是 Dart 源码而不是 JSON 资源，因为 `tr()` 要在 `build()` 里同步调用，
   没法等异步加载。

5. **校验**（`tools/i18n/verify.py`）
   本地没有 Dart SDK，所以用自己写的词法分析器检查六类已知的破坏方式：
   括号不平衡、`tr("...")` 后面还跟着字符串字面量（拼接没合并）、
   还有 `const` 管着 `tr()`、默认值位置出现 `tr()`、枚举常量参数里出现 `tr()`、
   注解参数里出现 `tr()`。

6. **编译**（`.github/workflows/i18n.yml`）
   完全复用上游自己的构建流程：Flutter 3.47.0、Go 1.25、NDK、melos 脚本。

---

## 自动运行

| 触发方式 | 说明 |
|---|---|
| 每天 03:17 UTC | 自动拉上游最新代码、翻译、推送、打包 |
| 手动 `Run workflow` | 可以勾选「强制全部重翻」 |

推送 `zh` 分支时用 `--force`，因为它是生成物，没有保留历史的价值。

---

## 怎么装

到 [Releases](../../releases) 下载 `zh-latest` 里的 APK。
APK 按 CPU 架构分开了，现在的手机基本都是 `arm64-v8a`。

**签名说明**：如果没有配置签名密钥，构建会退回用 debug 密钥签名，
这样 APK 能正常安装，但**无法覆盖安装官方版或之前用别的密钥签的版本**。
要正常升级，需要自己生成一个 keystore 并配置下面三个 Secret。

---

## 翻译错了怎么办

**改词典，不要改 `i18n/zh.json`。**

在 `tools/i18n/glossary.json` 里加上或修正对应条目：

```json
{
  "Container": "容器",
  "Cookie Isolation": "Cookie 隔离"
}
```

词典的优先级高于机器翻译，所以改完永久生效，下次重翻也不会被覆盖。
键名必须和 `i18n/strings.json` 里的英文**完全一致**（包括大小写和空格）。

改完提交到 `main`，工作流会自动重新跑一遍。

### 发现某个字符串没被翻译

先看 `i18n/transform-report.json` 里的 `skipped` 列表——
如果在那里，说明它落在上面说的五种「不能改」的场景里。

如果**根本不在**翻译范围内，可能是扫描器没识别出它。两个办法：

- `tools/i18n/overrides.json` 里的 `include_strings`：直接指定这个字符串必须翻译。
- `extra_named_args` / `extra_callees`：如果是一整类参数名没被识别，
  把参数名加进去。

### 翻译完全没生效

看 `i18n/translation-report.json` 的覆盖率。
如果覆盖率很低，多半是 Argos 模型没下载成功——检查构建日志里
`[argos] installing en->zh model` 那一行。

---

## 想加别的语言

1. `tools/i18n/runtime/i18n.dart` 里 `kShippedLanguages` 加上语言代码，
   并在 `_table` 的 `switch` 里加一个分支。
2. `translate.py` 里给 `ArgosEngine` 传不同的 `to_code`。
3. `gen_table.py` 加一个 `--out` 目标。
4. `patch_app.py` 里 `supportedLocales` 加上该语言。

---

## 本地跑一遍

不需要 Flutter，工具链是纯 Python：

```bash
python -m pip install argostranslate

# 拿一份干净的上游代码
git clone --depth 1 https://github.com/FaFre/WebLibre.git /tmp/upstream

# 跑完整流程
python tools/i18n/test_i18n.py                 # 单元测试
python tools/i18n/codemod.py      /tmp/upstream
python tools/i18n/patch_app.py    /tmp/upstream
python tools/i18n/translate.py --repo /tmp/upstream
python tools/i18n/gen_table.py   --repo /tmp/upstream
python tools/i18n/verify.py      /tmp/upstream --baseline /tmp/upstream-orig
```

想只看结构、不装翻译引擎（很快，但只有词典部分生效）：

```bash
python tools/i18n/translate.py --repo /tmp/upstream --engine none
```

---

## 可选配置

### 用大模型翻译（质量更好）

设置 Secret `I18N_LLM_API_KEY`，可选 `I18N_LLM_BASE_URL`（默认 OpenAI）
和 `I18N_LLM_MODEL`。设了之后自动切换成大模型翻译，不用改代码。

### 正式签名

| Secret | 说明 |
|---|---|
| `KEY_JKS` | keystore 的 base64（`base64 -w0 your.jks`） |
| `KEY_PASSWORD` | keystore 密码 |
| `KEY_ALIAS` | 密钥别名 |

---

## 目录结构

```
tools/i18n/
  dart_lexer.py       Dart 词法分析（只做定位，不做完整解析）
  scan_strings.py     找出用户可见的英文字符串
  codemod.py          改写成 tr()，并处理 const
  patch_app.py        接上语言检测和 flutter_localizations
  translate.py        词典 + 缓存 + 机器翻译
  gen_table.py        生成 Dart 查找表
  verify.py           检查生成的代码结构是否正确
  test_i18n.py        单元测试
  glossary.json       手工词典（要改翻译改这里）
  overrides.json      扫描器的例外名单
  runtime/i18n.dart   运行时 tr() 实现

i18n/
  zh.json             翻译缓存（自动维护）
  strings.json        所有待翻译字符串清单（自动维护）
```

---

## 授权

上游 WebLibre 使用 AGPL-3.0，本仓库的改动沿用同一协议。
