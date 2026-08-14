# 实验 6.2：Codex 作为人工基准测试操作员

本文档记录了实验 6.2 中六个基准测试家族各自的一个简单、一个中等和一个困难案例。Codex 亲自操作了每个案例。这些是 **Codex 的运行轨迹**，并非仓库所有者或用户所执行的工作。

**最终结果：13/18 通过（72.2%）**。所有 18 个选定案例都达到了一个终端官方结果；五次首次尝试的失败被保留，未进行修复或寻求更好分数的重新运行。

## 方法论

任务选择在解决之前就已锁定，在检查黄金答案或参考补丁之前锁定。预注册文件是 [`selection_manifest.json`](selection_manifest.json)，在执行前单独提交。其 SHA-256 哈希值为 `0fa3f6f890e69c0e51db6ea50d46186af999c5ad0a24284055bbebd667fa15b7`。

每个案例的规则如下：

1. 使用选择清单中固定的任务和层级；不要用更有利的案例替换困难或失败的案例。
2. 扮演人工操作员的角色：推理任务、调用环境的正常工具，并直接创建所需的答案、补丁或工件。
3. 在冻结答案或工作产品之前，不要检查黄金答案、参考解决方案或评估器特定的预期工件。
4. 调用上游官方评估器一次并保留其第一个终端结果。
5. 根据保留的证据解释评估器失败，但不修订并重新提交失败的案例。

GAIA 的上游 Levels 1/2/3 提供其难度层级。AndroidWorld 和 Terminal-Bench 使用上游难度标签。SWE-bench Verified 使用上游人工时间桶 `<15 min`、`15 min - 1 hour` 和 `>4 hours`。τ²-bench 使用两个、三个和九个组合的电信故障。OSWorld-Verified 没有难度字段，因此预注册的操作代理是一个应用程序中的一个持久设置、一个应用程序中的一个结构化转换，以及一个跨应用程序工件转换。

[`results.json`](results.json) 是机器可读的 18 案例索引。以下文件是规范的逐步记录：

- [`runs/gaia/operator_answers.json`](runs/gaia/operator_answers.json)
- [`runs/androidworld/results.json`](runs/androidworld/results.json)
- [`runs/swe-bench-verified/results.json`](runs/swe-bench-verified/results.json)
- [`runs/tau2-bench/results.json`](runs/tau2-bench/results.json)
- [`runs/terminal-bench/results.json`](runs/terminal-bench/results.json)
- [`runs/osworld-verified/results.json`](runs/osworld-verified/results.json)

τ² 结果目录还保留了三个精确的基准测试记录，OSWorld 目录保留了精确提交的 `pyautogui` 操作日志。大型截图、基准测试图像、容器和源代码检出版本有意被排除。

## 结果概览

| 基准测试 | 简单 | 中等 | 困难 | 总计 |
| --- | --- | --- | --- | --- |
| GAIA | 通过 | 失败 | 通过 | 2/3 |
| AndroidWorld | 通过 | 通过 | 失败 | 2/3 |
| SWE-bench Verified | 通过 | 通过 | 失败 | 2/3 |
| τ²-bench | 通过 | 通过 | 失败 | 2/3 |
| Terminal-Bench | 通过 | 通过 | 失败 | 2/3 |
| OSWorld-Verified | 通过 | 通过 | 通过 | 3/3 |
| **总计** | **6/6** | **5/6** | **2/6** | **13/18** |

这个微小、故意分层的样本是一个动手的方法论练习，而非基准测试排行榜的声明。特别是，从简单到困难的接近单调的总计下降仅仅是描述性的。

## 兼容性边界

- **AndroidWorld：** 此服务器环境中的参考 gRPC 无障碍 feed/转发器失败。运行保留了上游 `HumanAgent`、任务初始化、确定性参数和官方评估器，但使用 AndroidWorld 的上游 `UIAUTOMATOR` 控制器进行观察。
- **τ²-bench：** 没有有效的托管模型凭证可用于基准测试的隐藏用户角色。OpenAI 凭证缺失，可用的 Anthropic 凭证返回 HTTP 401。本地缓存的 `Qwen/Qwen2.5-3B-Instruct` 在 CPU 上运行了标准的隐藏用户场景。Codex 仍然是支持代理操作员。模拟器的角色反转是困难案例失败的一部分，因此必须将此兼容性路径的结果呈现为与参考提供商不可比。
- **OSWorld-Verified：** 上游 Docker/KVM 镜像与 `/dev/kvm` 一起使用。所有计算机交互通过可见的 `pyautogui` 操作执行。执行期间保留了全分辨率截图，但从 Git 中省略；保留了精确提交的操作和首次官方分数。
- **SWE-bench Verified：** 本地设置失败仅用于诊断。冻结的补丁由运行 ID `exp6-2-human-20260803` 的官方容器化评估工具评分。

## GAIA

源代码提交：`682dd723ee1e1697e00360edccf2366dc8418dd9`。

### 简单 — `2d83110e-a098-4ebb-9987-066c06fa42d0` — 通过

**任务内容。** 解释一句倒着写的句子，并用单词 `left` 的反义词作为答案。

**运行轨迹。** 我从右到左阅读字符串，恢复了指令"如果你理解这句话，请写下单词 left 的反义词作为答案"，将 `left` 映射到其方向反义词，并冻结答案 `right`。

**评估。** 存储的验证答案是 `right`，因此精确答案检查器给予 `1.0` 分。任务成功是因为解码和反义词选择都是精确的。

### 中等 — `7dd30055-0198-452e-8c25-f73dbe27dcb8` — 失败

**任务内容。** 使用 Biopython 解析附加的 PDB 结构，测量其前两个列出的原子之间的距离，并报告四舍五入到最接近皮米的结果。

**运行轨迹。** 我仅获取了选定的 2,897,289 字节 LFS 附件。创建隔离的 Python 环境最初失败，因为缺少 `ensurepip`/`python3.10-venv`，所以我安装了该系统包，创建了 `/home/ubuntu/.venvs/exp6-2-gaia-v2`，并安装了 Biopython 1.85。`Bio.PDB.PDBParser(QUIET=True)` 识别了链 A、残基 2 中的原子 N 后跟原子 CA。Biopython 返回 `1.4564234018325806` Å。因为 1 pm 是 0.01 Å，我四舍五入到 `1.46` Å 并冻结了该答案。

**评估。** 官方存储的答案是数字 `1.456`，参考检查器精确比较它而不是接受提示请求的最接近皮米四舍五入。它给予 `0.0` 分。这被记录为失败：`1.46` 遵循了所述的四舍五入指令，但它不满足实际检查器。我在评估后没有用黄金值替换它。

### 困难 — `56db2318-640f-477a-a82f-bc93ad13e882` — 通过

**任务内容。** 从十个 ISBN 类似的记录中推断未知的交替校验和权重和相邻的交换列。

**运行轨迹。** 我删除了连字符并将每行 13 位数字转换为整数。我枚举了交替权重 2 到 9，并允许较小的索引为 3 到 10 的相邻交换，排除了固定前缀和校验和数字。对于每个候选，我对所有 13 位数字应用权重 `1,w,1,w,...`，并要求每行的加权和模 10 为零。恰好有一个候选幸存：`(7, 9)`。我冻结了 `7, 9`。

**评估。** 答案与存储的验证答案完全匹配，产生 `1.0` 分。

## AndroidWorld

源代码提交：`0e95d641e244504c22087cc29b013f3b2428a261`。套件种子为 6201、6202 和 6203。

### 简单 — `ContactsAddContact` — 通过

**任务内容。** 创建一个名为 Samuel Ali 的联系人，电话号码为 `+16237655787`。

**运行轨迹。** 我从启动器打开联系人，完成了其首次运行屏幕，选择**创建新联系人**，在名字字段中输入 `Samuel` 和 `Ali`，输入国际号码，保存，并观察到显示格式化号码 `1 (623) 765-5787` 的 Samuel Ali 详细页面。

**评估。** 上游状态评估器在联系人数据库中找到了请求的姓名和电话号码，并给予 `1.0` 分。显示标点符号没有改变存储的数字。

### 中等 — `CameraTakeVideo` — 通过

**任务内容。** 使用系统相机应用程序创建一个视频。

**运行轨迹。** 我打开相机，从静态照片模式切换到视频，按下录制，允许大约三秒的捕获，按下停止，并将创建的媒体工件留在设备存储中。

**评估。** 官方媒体状态评估器找到了一个新创建的视频，并给予 `1.0` 分。

### 困难 — `BrowserMultiply` — 失败

**任务内容。** 在 Chrome 中从下载打开 `task.html`，揭示一个确定性五数字序列，记住它，并提交乘积。

**运行轨迹。** 我打开文件，导航到下载，选择 `task.html`，选择 Chrome，并完成了 Chrome 的首次运行提示。我观察到初始值 `4`，然后点击页面按钮五次。随后显示的值是 `2`、`5`、`3` 和 `7`；第五次按下显示答案表单。我计算 `4 × 2 × 5 × 3 × 7 = 840`，尝试输入并提交 `840`，并冻结浏览器状态。

**评估。** 官方评估器没有观察到页面文本 `Success!`，因此它给予 `0.0` 分。评估后重播固定页面的种子 RNG 确认了 `[4, 2, 5, 3, 7]` 和乘积 `840`；因此推理是正确的，但最后的表单交互没有达到所需的 UI 状态。保留的证据无法区分未聚焦的字段、未注册的提交点击或另一个瞬态 UI 不匹配。我没有重新运行它。

## SWE-bench Verified

源代码提交：`5cd4be9fb23971679cbbafe5a0ecade27cef99be`。官方运行 ID：`exp6-2-human-20260803`；提交 3 个，解决 2 个，未解决 1 个，工具错误 0 个。

### 简单 — `django__django-11133` — 通过

**任务内容。** 使 Django 的 `HttpResponse` 保留由 `memoryview` 表示的字节，而不是序列化对象的表示。

**运行轨迹。** 我跟踪了 `HttpResponseBase.make_bytes` 和 `HttpResponse.content` setter。`make_bytes` 原子地处理字节，但 setter 将 `memoryview` 分类为通用可迭代。我更改了 `make_bytes` 以对字节或 memoryview 使用 `bytes(value)`，从 setter 的可迭代路径中排除 memoryview，并添加了构造函数和属性分配回归。安装缺少的 `sqlparse` 和 `pytz` 后，所有 12 个本地 `HttpResponseTests` 通过。我冻结并提交了一次补丁。

**评估。** 官方从失败到通过的测试通过，所有 64 个从通过到通过的测试也通过。案例解决了，因为字节转换和可迭代调度都得到了纠正。

### 中等 — `astropy__astropy-13033` — 通过

**任务内容。** 使 `TimeSeries` 所需列错误在多个列是强制性时显示完整的预期和观察前缀。

**运行轨迹。** 我阅读了 `astropy/timeseries/core.py` 中的问题、提示和检查器。当只需要一列时，我保留了已建立的标度措辞。对于多列，我格式化了整个所需列表和具有相等最大长度的观察前缀，然后添加了报告的时间/通量移除回归和精确消息。旧的本地检出版本无法构建其编译/版本堆栈，因此我将其视为设置证据而非产品测试结果。我冻结并提交了一次补丁。

**评估。** 官方报告问题测试和所有 20 个从通过到通过的组通过，解决了案例。

### 困难 — `sphinx-doc__sphinx-7590` — 失败

**任务内容。** 教 Sphinx 的 C++ 表达式解析器处理数字用户定义的字面后缀，如 `q_J` 和 `q_s`。

**运行轨迹。** 我重现了消耗浮动标记但其相邻后缀保留并触发"Expected end of definition"的路径。我添加了没有前导单词边界的后缀正则表达式，将后缀消耗到 `ASTNumberLiteral` 中，并添加了十进制和整数 UDL 测试。解决仅设置相关的 Jinja 和 `roman` 依赖失败后，完整的本地 C++ 表达式解析器测试通过，包括报告的普朗克常数声明。我冻结并提交了一次。

**评估。** 补丁识别并渲染了数字 UDL，所有 24 个官方从通过到通过的组通过。隐藏的从失败到通过的测试还需要代表对字面运算符调用的 Itanium ABI 表达式 ID。我的补丁生成了 `IE1CIAL5_udlE_1aE`；预期的 ID 是 `IE1CIAclL_Zli4_udlEL5EE_1aE`。未解决的 ABI 身份缺陷使官方结果为 `0.0`；我没有修订或重新提交它。

## τ²-bench

源代码提交：`8d005b0e5b9e4af0bc055886fa7f95fc86d1710e`。支持代理轨迹由 Codex 手动编写。本地缓存的 Qwen 模型在上述兼容性边界下提供了基准测试的隐藏用户角色。

### 简单 — 两个故障 — 通过

任务 ID：`[mobile_data_issue]data_mode_off|data_usage_exceeded[PERSONA:None]`。

**任务内容。** 在移动数据关闭且其配额耗尽后恢复移动数据，包括正确的付费加油同意。

**运行轨迹。** 我识别了客户 C1001 和受影响的线路 L1002，请求网络诊断，指导用户启用移动数据，并要求进行速度测试。当仍然失败时，我检查了使用情况和计划 P1002，发现使用 15.1 GB 对比 15.0 GB 配额，以及 $2/GB 加油。我提供了高达 2 GB，明确确认了总共 $4，仅在同意后调用 `refuel_data`，并请求最终测试。结果是 275 Mbps（优秀），之后我总结了 $4 费用并结束了交互。

**评估。** 官方奖励 `1.0`：移动数据已启用，添加了 2 GB 并确认，最终连接为优秀。

### 中等 — 三个故障 — 通过

任务 ID：`[mobile_data_issue]bad_vpn|data_saver_mode_on|user_abroad_roaming_disabled_on[PERSONA:None]`。

**任务内容。** 修复由运营商侧漫游关闭、Data Saver 开启和降级 VPN 导致的国外数据不良。

**运行轨迹。** 我查找了客户，错误地调用了不存在的 `get_line_by_id`，保留了工具错误，并使用 `get_details_by_id` 恢复。我识别了 L1002，确定用户在国外，并启用了运营商侧漫游。我遵循了慢数据工作流程：请求限制状态，指导关闭 Data Saver，在更改之前检查 VPN 性能，然后指导降级的 OpenVPN 连接断开。最终速度测试报告 275 Mbps（优秀）。

**评估。** 官方奖励 `1.0`。三个所需的操作检查——`enable_roaming`、`toggle_data_saver_mode` 和 `disconnect_vpn`——都通过，最终环境断言也通过。早期的无效工具调用没有改变状态并得到了正确恢复。

### 困难 — 九个故障 — 失败

任务 ID：`[mms_issue]airplane_mode_on|bad_network_preference|bad_wifi_calling|break_apn_mms_setting|break_app_sms_permission|data_mode_off|data_usage_exceeded|unseat_sim_card|user_abroad_roaming_disabled_on[PERSONA:None]`。

**任务内容。** 修复包含九个独立故障的 MMS 故障，跨无线电状态、SIM、漫游、数据、配额、网络模式、Wi-Fi 呼叫、应用程序权限和 APN 设置。

**运行轨迹。** 我建立了受影响的线路和基线 MMS 故障；诊断并禁用了飞行模式；诊断并重新安装了 SIM；启用了运营商侧漫游；启用了移动数据；诊断了耗尽的配额；确认并应用了 2 GB 加油，费用 $4；将首选网络从 2G 更改为 `4g_5g_preferred`；禁用了 Wi-Fi 呼叫；授予了消息应用程序缺失的 SMS 权限；识别了缺失的 MMSC URL；重置 APN 设置并重新启动。最终检查显示可以发送 MMS，数据速度为 275 Mbps（优秀）。

轨迹还记录了从用户模拟器角色反转的重复恢复。Qwen 经常告诉支持代理执行手机侧工具，而不是作为用户执行它们。接近步数限制时，我明确要求在一次响应中进行多个有序的手机调用。确切的操作员轮次保留在 `runs/tau2-bench/hard-transcript.json` 中。

**评估。** 官方奖励 `0.0`。尽管最终环境状态已修复，但剧集在达到公认的终端停止之前达到了基准测试的 100 步上限。官方评估器将其分类为提前终止，并未对修复的状态进行评分。这是由本地用户模型兼容性路径引起的剧集级失败，而非基准测试成功的声明；我没有重新运行它。

## Terminal-Bench

源代码提交：`8384a179b1b8688f6ea5233a4d9d51218df1ac96`。

### 简单 — `fix-permissions` — 通过

**任务内容。** 诊断为什么 `/app/process_data.sh` 无法执行并修复它。

**运行轨迹。** 我列出了 `/app`，阅读了公共脚本，并观察到模式 `664` (`-rw-rw-r--`)。运行它产生了 `Permission denied` 和退出代码 126。我运行 `chmod +x`，确认模式 `775`，成功运行脚本，观察到 `Data processed successfully!`，并调用了上游测试脚本。

**评估。** 单个官方测试 `test_script_permissions` 通过。缺少执行位是完整的缺陷。

### 中等 — `simple-sheets-put` — 通过

**任务内容。** 在创建一个电子表格的同时填充有状态电子表格 REST 服务。

**运行轨迹。** 我查询了 `/spreadsheets/` 并确认零初始对象，然后使用 `/docs/json` 映射电子表格、工作表、单个单元格和批量单元格端点。我创建了一个 `Financial Report` 电子表格和一个 `Q1 Data` 工作表。宣传的批量单元格 PUT 返回 HTTP 400 而无突变，因此我对 A1:D4 使用了记录的单个单元格 PUT。我输入了四个标题、一月到三月行以及利润 2000、3000 和 5000。最终 GET 确认了一个电子表格和评估前的所有 16 个单元格。

**评估。** 所有三个官方测试——电子表格、工作表和单元格创建——都通过。回退保留了单例约束并完成了每个值。

### 困难 — `dna-assembly` — 失败

**任务内容。** 设计最小 Golden Gate 引物组，将骨架、EGFP、FLAG 链接器和 SNAP 组装成精确的圆形目标质粒，同时满足引物约束。

**运行轨迹。** 我解析了五个 FASTA 记录，确认没有内部 BsaI 位点，对齐目标，并推断预期的组件边界。我选择了四个引物对，具有连接重叠 `ATGA`、`GGTA`、`GACA` 和 `TAAT`。模拟四个消化的片段产生精确的 3,591-nt 圆形目标直到旋转。我安装了 primer3，选择了具有所需热力学参数的退火tracts，写了八个非空 FASTA 记录，并调用了一次官方评估器。

**评估。** `test_primers` 失败。FLAG 正向重叠的四碱基后缀也与相邻模板匹配，因此评估器正确地将其包含在退火tract中。该引物的评估 Tm 是 `66.056662°C`，对比 FLAG 反向的 `60.610114°C`——`5.446548°C` 差距，超过了最多 5°C 约束。我的预评估检查仅测量了显式的 15 碱基结合后缀。组装本身是精确的，但引物对热力学约束使官方结果成为失败；评估后没有进行修订。

## OSWorld-Verified

源代码提交：`8365edc975efd0477a0d62444a5beed562ab5a7b`。每个工件在其官方评估器运行之前被冻结。

### 简单 — `2cd43775-7085-45d8-89fa-9e35c0a915cf` — 通过

**任务内容。** 每三分钟启用 LibreOffice 自动恢复。

**运行轨迹。** 我使用 Alt+F12 打开了 LibreOffice 选项，展开加载/保存，打开常规，启用**每保存自动恢复信息**，将间隔从 10 更改为 3，提交对话框，重新打开它以视觉验证持久性，并在没有进一步突变的情况下关闭它。

**评估。** 官方结果 `1`。评估器发现自动恢复已启用，间隔为三分钟。

### 中等 — `7e429b8d-a3f0-4ed0-9b58-08957d00b127` — 通过

**任务内容。** 通过将每行的分支与查找表匹配来填充 Calc 表中的官员姓名。

**运行轨迹。** 我在 F2 中输入 `=VLOOKUP(E2;$A$2:$B$7;2;0)`，选择 F2:F12，使用 Ctrl+D 向下填充，视觉检查结果姓名，并就地保存工作簿。

**评估。** 官方结果 `1.0`。工件评估器发现每个官员姓名与其总部正确匹配。

### 困难 — `51f5801c-18b3-4f25-b0c3-02f85507a078` — 通过

**任务内容。** 从 `Dickinson_Slides.pptx` 中提取每个演示者注释，仅将注释文本写入无格式的 Word 文档，并将其保存为 `Desktop/notes.docx`。

**运行轨迹。** 我将 Impress 切换到注释视图并按顺序访问幻灯片 1 到 9。我转录了：`This is opening slide.`、`Cover slide option #1`、`Cover slide option #3`、`This is a graph.`、`This is a table.`、`This is item lists.`、`This is an inserted image.` 和 `Blank ending slide`。幻灯片 7 仅包含空的"Click to add Notes"占位符，因此我省略了它。我从可见的启动器打开 Writer，将八个文本作为纯段落输入，没有标签或页码，打开另存为，选择桌面，选择 Word 2007–365 格式，命名文件为 `notes.docx`，并在冻结之前视觉验证了文件名和内容。

**评估。** 官方结果 `1`。评估器接受了文档、排序、省略空占位符、位置、文件名和缺乏添加的格式。

## 解释

五个失败暴露了五个不同的边界：

1. **答案规范化：** GAIA 中等的请求四舍五入与严格的存储数值不一致。
2. **最后一英里 UI 状态：** AndroidWorld 困难有正确的算术但未达到页面的可见成功状态。
3. **隐藏语义契约：** SWE-bench 困难处理了语法，但错过了官方测试所需的 ABI 调用身份。
4. **约束验证：** Terminal-Bench 困难组装了精确产品，但错误识别了一个引物的完整退火tract。
5. **剧集协议：** τ²-bench 困难修复了环境，但在角色反转的本地用户模拟器下耗尽了轮次预算。

这种多样性是练习的主要价值："答案看起来正确"弱于官方终端结果，失败经常发生在规范化、交互、表示、次要约束或协议终止，而不是明显的核心任务。

## 项目结构

```
chapter6/experiment-6-2-human-benchmark/
├── README.md              # 本文档
├── run_android_human.py  # AndroidWorld 基准测试运行器
├── selection_manifest.json  # 预注册任务选择清单
├── results.json          # 18 案例的机器可读索引
├── results/              # 结果输出目录
├── logs/                 # 日志目录
└── runs/                 # 各基准测试的运行记录
    ├── gaia/
    ├── androidworld/
    ├── swe-bench-verified/
    ├── tau2-bench/
    ├── terminal-bench/
    └── osworld-verified/
```

## 使用说明

### 环境要求

此项目需要以下依赖：

- Python 3.10+
- AndroidWorld 框架
- 相应的基准测试环境

### 运行 AndroidWorld 测试

```bash
# 从项目根目录运行
python3 chapter6/experiment-6-2-human-benchmark/run_android_human.py \
    --checkout /path/to/androidworld \
    --task ContactsAddContact \
    --tier easy \
    --seed 6201 \
    --output chapter6/experiment-6-2-human-benchmark/results/androidworld_contacts.json
```

### 查看结果

每个基准测试的结果存储在 `runs/` 目录中：

```bash
# 查看 AndroidWorld 结果
cat chapter6/experiment-6-2-human-benchmark/runs/androidworld/results.json

# 查看所有案例摘要
cat chapter6/experiment-6-2-human-benchmark/results.json
```

## 注意事项

1. 此项目记录的是 Codex 的人工基准测试运行，不是自动化测试
2. 所有结果都是第一次运行的终端结果，没有重新运行或修复
3. 兼容性边界可能导致某些结果与提供商不可比
4. 大型截图和容器工件未包含在 Git 中

## 参考资料

- [AndroidWorld 文档](https://github.com/microsoft/AndroidWorld)
- [SWE-bench Verified](https://www.swebench.com/)
- [GAIA 基准测试](https://huggingface.co/datasets/gaia-benchmark/GAIA)
- [τ²-bench](https://tau2-bench.github.io/)
- [OSWorld](https://osworld.github.io/)
- [Terminal-Bench](https://github.com/NVIDIA/terminal-bench)
