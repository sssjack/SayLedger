# SayLedger · 一笔

> Say it. Track it. — 一句话，记一笔。

**SayLedger** 由 Say（说）和 Ledger（账本）组成，呼应「说一句话就能记账」的核心体验，中文名为「一笔」。

应用名称为 `SayLedger`，前端 npm 包名为 `sayledger-web`；本地根目录名保留 `Clockwise-Ledger`。

说一句话、发一张小票照片，AI 帮你记账、分类、算钱。主界面是对话框，账单页也可手动补记。

- 线上地址：<https://jizhang.clockwise.asia/>
- 备用入口：<https://www.clockwise.asia/jizhang/>

## 它做什么

**记账**

- **对话记账**：文字或语音说「午饭花了 28」「昨天打车 38」，自动识别金额、分类、商户、付款方式、日期
- **图片记账**：拍小票发上来，识别商户、明细、总额、日期；金额看不清会追问
- **必要时才追问**：金额、资金性质、退款/回款关联不明时先确认；日期、商户和付款方式缺失不打断
- **收支与往来**：收入、退款、自有账户转账、信用还款、借出/借入、押金分别记录，避免重复计算消费
- **AA / 报销**：区分实际付款、个人承担和待收回款，支持部分到账、结清与待归还查询
- **查重与恢复**：同一句话或同一张图片的同日同额流水会提示核对，可明确继续记入；创建、修改、删除可撤销

**备忘录提醒**

- **一句话建备忘**：文字、语音（转文字后同一链路）或发一张提醒通知/海报截图，说「明天下午3点提醒我开会」即可
- **缺信息会追问**：只说日期没说时刻——「下周三提醒我交房租」会先确认「下周三（10月28日）几点提醒你？」，回「下午3点」就补齐创建；只说时间没说事——「每周三下午3:00提醒我」会再问「要提醒你什么事呢？」；草稿 30 分钟内有效，可回复「取消」
- **重复提醒**：支持一次性、每天、每周（如「每周三下午3:00提醒我交水电费」），重复备忘到点后自动顺延到下一周期
- **到点喊你**：提醒文案诙谐幽默可爱；网页端会在对话里出现，绑了微信还会在微信里发一条。微信主动提醒依赖最近一次微信会话的上下文（context），长时间没在微信里说话可能发不出，届时只在网页端提醒并如实标注推送状态
- **备忘页**：导航「备忘」里可看全部备忘、下一次提醒时间和重复徽标，可完成/取消，也可手动新建

**查账**

- **自然语言查询**：「我昨天花了哪些钱」「日本旅行一共花了多少」「上个月餐饮」「最近一周用微信付了多少」都能直接问
- **结果逐笔列出**：命中记录按天分组、每天带小计，每笔显示商户、分类、时间、付款方式、备注；
  不是只给一个总额卡片
- **账单页**：按日 / 月 / 年 / 自定义区间查看，可按付款方式筛选，可搜商户、备注、商品名
- **筛选与导出**：按账务类型、待结清状态筛选，分页加载，统计覆盖整个筛选范围，支持导出 CSV
- **区间对比**：可比较当前区间与前一个等长周期，列出分类差额；空结果保留原查询范围

**改账**

- **语音改账**：「刚才那笔记错了」「说错了，删掉」「那笔是支付宝付的」「把滴滴那笔改成 42」，
  AI 直接定位并修改/删除最近那笔
- **定位不到不撒谎**：目标模糊时不会回一句「已经删掉了」，而是把最近几笔摆出来让你点选

**看账**

- **付款方式 + 备注**：支付宝 / 微信 / 银行卡 / 信用卡 / 现金 / 其他，另有自由备注
  （和谁、是否报销、发票号…），账单页和报告页都按付款方式汇总与筛选
- **周期报告**：日 / 月 / 年 / 自定义区间，含趋势图、分类构成、付款方式构成、事件开销、最大几笔
- **AI 消费诊断**：数字全部由后端算，AI 只负责解读和给建议，不会算错账

**管理**

- **月预算**：总额、分类、事件预算，显示已用、剩余和超支；事件预算也按指定自然月计算
- **个人规则**：默认付款方式与商户分类规则，可在对话中设置，在管理页查看、修改、取消
- **原账关联**：退款、报销到账、借款收回、借入归还必须关联原账；金额超过未退款/待结清额会拒绝执行

统计口径：个人净支出 = 消费的个人承担 − 当期退款的个人部分；真实收入不含借款、退款和回款。
已知待报销/代垫部分从个人承担中分离，后续回款只减少待结清金额。
退款按到账日期冲减当期支出，因此跨月退款可能使某日或某分类净支出为负。
AA 发生分角舍入时，个人份额四舍五入，剩余金额作为待收回款，两者之和始终等于实付。
涉及已有退款/回款的原账，金额、类型、分类、事件等关联字段需先撤销关联流水后再调整。

可直接试说：

```text
今天发工资8500
下周三提醒我交房租（会追问几点，回“下午3点”即可）
每周三下午3:00提醒我交水电费
半小时后提醒我吃药
聚餐我付了300，含我3个人AA
打车86，公司报销
公司上次打车费报销到账了
昨天买的鞋退回来80元
还有谁没还我
这个月餐饮预算1500
以后没说付款方式就默认微信
以后瑞幸都归到餐饮
导出这个月的账单
撤销上一步
```

当前边界：以人民币实际流水为准；外币需提供人民币实付。尚未提供银行账户实时余额、
周期扣款、账单文件导入、多人共享、持久储蓄目标；助手不会声称这些操作已完成。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS + ECharts |
| 后端 | FastAPI + SQLAlchemy 2 + SQLite（WAL 模式） |
| AI | apiyi `gpt-6-luna`（文本 + 视觉，OpenAI 兼容 `/chat/completions`） |
| 语音 | 浏览器 Web Speech API（需 HTTPS），识别结果走同一条记账链路 |
| 部署 | Docker Compose + nginx 反代 |

## 关键设计

**AI 只出结构化决策。** 模型输出 JSON 意图，除记账、查改删外，还支持 `refund` / `settle` /
`undo` / `compare` / `budget_*` / `preference_set` / `export`；由服务端校验并执行：

```json
{"action":"record","reply":"记好了","transactions":[{"amount":28,"category":"餐饮","payment_method":"微信"}]}
```

查询时模型只给过滤条件（时间、分类、关键词、付款方式、事件），由 `app/query.py` 翻译成 SQL 并聚合，
避免模型算错账；命中的每一笔再原样回传给前端逐条渲染。

**相对日期在服务端解析。** 模型对「上个月」「昨晚」「上周五」「上个月3号」的换算会漂移，所以
`app/dateparse.py` 用确定性规则换算，模型只负责原样回填用户说的时间词。
单日说法（昨天 / 前天 / 上周五 / 上个月3号）会解析成 `start == end`，
问「我昨天花了哪些钱」不会退化成查全部记录。

**改删的目标服务端兜底。** 模型给的 `target_id` 可能缺失或过期，`main.resolve_change_targets`
会按用户原话里的金额、商户、付款方式、关键词在最近 20 笔里打分重定位；
真定位不到就返回 `candidates` 让用户点选，绝不谎称「已经删掉了」。

**关键歧义不强行落账。** 不再将“资金性质或关联目标不明确”的追问强制改成支出；
非金额默认值由协议和服务端处理，`app/fallback.py` 保留为旧解析实现，当前对话链路不调用。

**老库自动备份、补列。** 启动时先检查旧表；需要升级时，在数据库同目录的 `backups/` 下用 SQLite
backup API 备份，再建新表、补列及索引。旧记录默认保留为支出，个人承担为空时按原金额解释。
退款/回款的校验和写入在同一个 SQLite 写事务中完成，防止并发超额。

**备忘录的时间也由服务端解析。** `app/memo.py` 用确定性规则解析「下周三」「明天下午3点半」
「每周三15:00」「半小时后」等说法（中文数字、上午/下午/点半、这周 vs 下周、每天/每周），
解析器能处理的先走解析器；图片里的提醒通知由视觉模型返回 `memo` 意图，服务端校验后执行。

**短期上下文联系。** 同一入口内最近30分钟的对话会带上上一动作和待补充提醒；“这个、上一张、按照这个”可引用最近相关图片，最多回看3条用户消息、重读2张图片。
图片和文字分开发送也可接着理解；“28元”“微信付的”“只看交通”“下午三点”等简短回答会结合上一轮处理，新消费或新查账不会被提醒草稿接走。
“今天是第二天”用作计划阶段锚点；多步骤图片可安排最多8条提醒，具体日期由服务器按阶段换算。缺少信息或时间已经过去时先追问，整份计划补齐后才创建。
旧图缺失、超过短期窗口或指代不明时会要求重新说明，不会凭空补内容；操作说明和购买计划不会自动记成已发生的支出。
缺时刻或缺事件时草稿存入 `memo_pending`（30 分钟过期），用户下一句补齐才创建，网页与微信共用。
`app/memo_worker.py` 约每 30 秒扫描到期备忘：写一条对话消息供网页查看；绑了微信时用绑定上
保存的最近会话 context 造一条主动投递交给微信发送队列。iLink 的 context 会随时间失效，
所以长时间没有微信往来时主动提醒可能发不出，后台会把推送状态记为仅网页提醒，不谎称已发。

**撤销保留审计记录。** `ledger_operations` 保存操作前后快照，撤销前检查当前状态与关联流水，
通过软删除或还原字段恢复账单。测试只在本地 `backend/tests/`，已由 `.gitignore` 排除。

## 本地开发

```bash
# 后端（Python 3.11+，开发机实测 3.13）
cd backend
python -m venv .venv && ./.venv/Scripts/pip install -r requirements.txt   # Windows
LEDGER_DATA_DIR=../.localdata ./.venv/Scripts/python -m uvicorn app.main:app --port 8791

# 前端（Node 18+，实测 24）
cd frontend
npm install
npm run dev        # http://127.0.0.1:5288，已把 /api 代理到 8791
```

`backend/.env` 里的关键变量：

| 变量 | 说明 |
| --- | --- |
| `LEDGER_PASSWORD` | 首次启动时据此创建唯一账户的登录密码 |
| `AI_API_KEY` | apiyi 的 key；未填时无法识别自由语言/图片，手动记账、预算与规则管理仍可用 |
| `LEDGER_JWT_SECRET` | 签发登录令牌；调用同一个库的多个实例必须一致 |
| `LEDGER_DATA_DIR` | 数据库和图片目录，本地开发指向 `../.localdata`，容器内是 `/data` |
| `LEDGER_TZ` | 默认 `Asia/Shanghai`，决定「今天/昨天」按哪个时区算 |

## 微信聊天记账

微信入口使用腾讯 iLink 协议，独立运行在现有 Python 后端内，不需要安装 OpenClaw。
协议适配依据 [Tencent/openclaw-weixin 2.4.10](https://github.com/Tencent/openclaw-weixin)
及其 [后端协议说明](https://github.com/Tencent/openclaw-weixin/blob/main/docs/protocol_zh_CN.md)。
该说明并非完整服务端契约，接口兼容性及账号可用性需以微信实际授权和联调结果为准。

### 连接和使用

1. 安装更新后的 `backend/requirements.txt`，启动后端及前端。
2. 登录账本，进入「管理 → 微信记账」，点击「扫码连接微信」。
3. 用自己的手机微信扫码，并按手机提示完成确认；若显示验证数字，在网页输入。
4. 绑定成功后，在微信 ClawBot 对话中发送「帮助」，再尝试「午饭花了28，微信付的」。
5. 可以继续发送「改成32」「这个月餐饮花了多少」「撤销上一步」；网页和微信使用同一账本及对话上下文。

微信支持文字、小票/付款截图、微信语音：记账、查询、修改、删除、撤销、退款/回款、预算和个人规则。
图片通过微信官方 CDN 下载并按协议解密，复用现有视觉识别和查重流程；每条最多4张、每张8MB。
语音优先使用微信附带的转写；没有转写时下载解密，SILK 转 WAV 后调用语音识别。每条最多2分钟，回复附上识别文字供核对。
支持同条消息中的文字、图片、语音组合；任一部分下载或识别失败，整条消息提示未记账，避免部分执行。文件、视频、引用内容暂不解析。
账单明细以文字返回，较长结果和 CSV 导出通过网页查看。图片保存在当前用户的上传目录，沿用网页鉴权；原始音频仅临时处理，不持久保存。
疑似重复的记账会先列出候选；确认是另一笔时，在10分钟内回复「确认重复记账」。

### 服务配置

| 环境变量 | 说明 |
| --- | --- |
| `WECHAT_ENABLED` | 默认 `1`；设为 `0` 停止微信后台任务并禁止新扫码 |
| `WECHAT_ENCRYPTION_KEY` | 可选 Fernet 密钥；未设置时自动生成数据目录下的 `wechat.key` |
| `LEDGER_PUBLIC_URL` | 微信回复中的网页入口，例如 `https://jizhang.clockwise.asia`；子路径部署填写完整 `/jizhang` 路径 |
| `ASR_BASE_URL` / `ASR_API_KEY` | 备用语音识别服务，留空沿用 `AI_BASE_URL` / `AI_API_KEY`；Gemini 使用原生 `/v1beta/models/...:generateContent`，其他模型使用 `/audio/transcriptions` |
| `ASR_MODEL` | 默认 `gemini-2.5-flash`，也可配置有可用通道的 `whisper-1` 等转写模型；微信附带有效转写时不调用备用识别服务 |
| `ASR_TIMEOUT_SEC` | 语音识别超时秒数，默认 `45` |

**备份、升级、迁移时必须同时保留数据库和 `wechat.key`，或保留原有的 `WECHAT_ENCRYPTION_KEY`。**
密钥丢失后无法恢复旧微信凭证，可在网页断开连接后重新扫码；已有账单不受影响。
不要把密钥、数据库、扫码二维码或 Bot token 提交到 Git 或发给其他人。

后台通过 HTTPS 长轮询连接微信，服务器需能访问 `ilinkai.weixin.qq.com`、微信返回的官方重定向域名及 `novac2c.cdn.weixin.qq.com` 媒体 CDN。
不需要新增公网回调地址或开放端口。后端必须持续运行，重启后自动恢复已保存的绑定和接收位置。
同一数据目录通过文件锁选出一个消息服务进程；只支持同一主机的本地数据目录，不适用于多主机或网络文件系统共享。

消息先存入收件箱，再提交接收游标；同一微信消息 ID 只执行一次。
账本变更、操作审计和待发送回复在一个事务内保存。回复失败仅重发原回复，保持同一 `client_id`，不会再次执行记账。
网络中断会自动退避重连，回复最多自动尝试8次；用「重新发送回复」继续重发。
收件、账务处理和回复发送使用独立队列；账务仍按消息先后执行，一条回复退避重试不会阻塞后续记账和可发送回复。
发送接口允许成功响应省略 `ret`，仅显式错误码或 HTTP 错误触发重试。
升级时会修正旧版因缺少 `ret` 而误判失败的已接受回复，不重发这些回复，也不重新执行业务。
微信服务端对重发 `client_id` 的去重行为仍需实测，网络响应丢失时可能收到重复回复，但不会重复入账。
登录失效会显示重新连接提示。断开连接会清除绑定凭证、扫码信息和消息内容，保留已有账单及匿名消息去重指纹。

微信回复采用「一笔，小账本搭子」的轻松语气，带记账、分类和查询表情；金额、日期和执行结果仍由服务端生成。
查询回复先显示日期范围和汇总金额，再分行列出明细；同一天只显示一次日期，账单编号置于末尾。短回复不重复附长链接，帮助、导出和未展示完的明细提供账本入口。
澄清、失败和未定位到目标的修改不会显示成功文案。网页对话的提示词保持原样。

### 接口与本地验证

所有 `/api/wechat/*` 接口均要求账本登录，且只操作当前用户的数据：

| 方法和路径 | 用途 |
| --- | --- |
| `GET /api/wechat/status` | 连接、扫码、服务心跳及回复投递状态 |
| `POST /api/wechat/login` | 获取扫码会话，进行中的二维码会复用 |
| `GET /api/wechat/login/{id}/qr` | 本地渲染二维码 PNG，不返回凭证 |
| `POST /api/wechat/login/{id}/verify` | 提交手机显示的验证数字 |
| `DELETE /api/wechat/connection` | 取消扫码或断开连接，保留账单 |
| `POST /api/wechat/replies/retry` | 重新投递未送达回复，不重复执行业务 |

本地测试保留在已忽略的 `backend/tests/`。为隔离临时 SQLite 目录，分别运行：

```powershell
backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_finance.py -q
backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_wechat.py -q
```

测试覆盖消息去重、跨用户隔离、扫码取消/过期、配对验证、重启恢复、发送重试、账本与收件箱原子回滚和解绑并发。
首次上线还需用手机完成扫码，依次验证文字记账、连续修改、查询和撤销；未扫码前不能视为微信端到端验证完成。

## 部署

线上服务器：`root@8.141.121.133`，目录 `/opt/clockwise-ledger`，
容器 `clockwise-ledger`（compose 服务名 `ledger`），对外监听 `8421`。

应用已更名为 SayLedger；线上目录、容器名、域名及数据路径沿用现有配置，保持部署兼容。

### 完整流程

```bash
# 1. 构建前端 —— 必须构建两套产物，缺一套就会有一个入口白屏
cd frontend
npm run build && cp -r dist dist-root          # 根路径版，子域名用（nginx root 指向 web -> dist-root）
npm run build -- --base=/jizhang/              # 子路径版，/jizhang/ 入口用（输出到 dist）

# 2. 上传（含两套 dist 产物）
python deploy/upload.py --with-dist

# 3. 服务器上重建并启动
ssh root@<host> 'cd /opt/clockwise-ledger && docker compose up -d --build'
```

### 构建时必须注意

**Windows / Git Bash 下要关掉路径转换。** `--base=/jizhang/` 会被 MSYS 改写成
`/Program Files/Git/jizhang/`，构建不报错但产物全废，线上直接 404。正确写法：

```bash
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" npm run build -- --base=/jizhang/
```

构建后自检：`grep -o 'src="[^"]*"' dist/index.html` 应该看到 `/jizhang/assets/...`，
如果是 `/Program Files/Git/...` 就说明又被转换了。

### 升级线上库前先备份

新版本启动时会 `ALTER TABLE` 补列。改动涉及数据库时，先做一次热备份（`sqlite3` 的
backup API 会连 WAL 里未落盘的数据一起带走，比直接 `cp` 数据库文件安全）：

```bash
mkdir -p /opt/clockwise-ledger/data/backups
docker exec clockwise-ledger python -c "
import sqlite3
src = sqlite3.connect('/data/ledger.db')
dst = sqlite3.connect('/data/backups/ledger-before-<日期>.db')
src.backup(dst); dst.close(); src.close()
"
```

回滚时停容器、用备份覆盖 `data/ledger.db`、再启动即可。

### 其他注意事项

- **容器名不要改**：compose 里改服务名/镜像名会让 compose 当成新服务建容器，
  而旧容器还占着 8421，启动必失败。应用对外叫什么都和内部命名无关。
- **`deploy/upload.py` 保留线上配置与数据**：跳过 `.env` / `.env.*`、部署凭据、数据库、测试目录及本地运行产物。
  首次部署需单独配置服务器 `backend/.env`；后续升级不会用本地配置覆盖线上环境。
- **`deploy/upload.py` 依赖 `paramiko`**，它不在 `requirements.txt` 里（那是运行时依赖），
  需要单独 `pip install paramiko`。
- **部署凭据**：`deploy/upload.py` 优先读取 `LEDGER_DEPLOY_HOST`、`LEDGER_DEPLOY_USER`（默认 `root`）和
  `LEDGER_DEPLOY_PASSWORD`；也可使用本地 `deploy/.credentials.json`，格式为
  `{"host":"<host>","user":"root","password":"<password>"}`。
  该配置已加入 `.gitignore`，上传脚本也会跳过它，服务器密码不进入仓库。
- nginx 反代配置见 `deploy/nginx-sayledger.conf`（HTTP）与 `deploy/nginx-sayledger-ssl.conf`（HTTPS）。
  注意两套产物的归属不同，别搞混：

  | 入口 | nginx 指向 | 需要的产物 |
  | --- | --- | --- |
  | `jizhang.clockwise.asia/` | `/opt/clockwise-ledger/web`（软链到 `frontend/dist-root`） | 根路径版 |
  | `www.clockwise.asia/jizhang/` | `alias /opt/clockwise-ledger/frontend/dist/` | `--base=/jizhang/` 版 |

  `deploy/nginx-sayledger.conf` 里写的是 `root .../frontend/dist`，与线上子域名实际使用的
  `web -> dist-root` 不一致；以线上配置为准，仓库里的这份是子路径部署的写法。

- 数据落在宿主机 `./data`（SQLite + 上传的图片），换容器不丢账。

## 改名

应用名只定义在两处，其余地方都引用这两个常量：

- `backend/app/branding.py` — `APP_NAME` / `APP_NAME_EN` / `APP_TAGLINE`
- `frontend/src/brand.ts` — 与后端对应

界面标题、AI 人格和 API 品牌信息统一使用 `SayLedger`，中文宣传语保留「一句话，记一笔」。
再改一次应用展示名称只需要动这两个文件，加上 `frontend/index.html` 的 `<title>` 与 `description`；
调整 npm 包名时，同时更新 `frontend/package.json` 与 `frontend/package-lock.json`。
部署路径、容器名、数据库文件名、`LEDGER_*` 环境变量都不含产品名，改名不影响线上数据。

## 目录

```
backend/app/
  main.py        # 路由：登录、对话、账单 CRUD、统计、报告
  finance.py     # 账务类型、关联退款/回款、撤销、预算和个人规则
  conversation.py # 意图执行、必要澄清、区间对比与导出决策
  ai.py          # prompt、模型调用、JSON 提取、token 扩容重试
  query.py       # 查询条件 → SQL → 聚合
  dateparse.py   # 中文相对日期 / 区间解析
  memo.py        # 备忘录解析、待确认草稿、提醒文案
  memo_worker.py # 备忘到点扫描与推送（网页消息 + 微信主动投递）
  fallback.py    # 无 AI 兜底时的金额抽取
  categories.py  # 12 个消费分类及配色
  payments.py    # 6 种付款方式、配色、口语别名收敛
  branding.py    # 应用名等品牌常量
  db.py          # 模型定义、SQLite 连接、老库补列迁移
  auth.py        # 密码哈希、JWT、登录依赖
frontend/src/
  App.tsx                        # 布局、路由、状态
  api.ts                         # 接口封装与类型
  brand.ts                       # 品牌常量
  components/Composer.tsx        # 输入框：文字 / 语音 / 图片
  components/MessageBubble.tsx   # 消息、查询结果与逐笔明细
  components/TransactionCard.tsx # 单笔卡片：改金额 / 分类 / 付款方式 / 备注 / 删除
  components/BillsPanel.tsx      # 账单列表与日/月/年/区间筛选
  components/ReportPanel.tsx     # 周期报告与 AI 诊断
deploy/
  upload.py          # SFTP 上传（--with-dist 带上前端产物）
  nginx-sayledger.conf      # HTTP 反代
  nginx-sayledger-ssl.conf  # HTTPS 反代
```
