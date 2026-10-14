# corerce 主页配置

当前实现按 moiz-codez 的终端布局独立制作：ASCII 欢迎标题、身份图、Neofetch 信息、生态图、时间线、语言统计、项目区及贡献贪吃蛇。资料源在 `profile.json`，修改后重新生成，勿手工修改生成的 README/SVG。

## 本地生成

使用 Python 3.12 或更高版本：

```sh
python scripts/generate.py --preview
```

离线生成只使用本地配置和已同步的数据。当前头像转换需要 Pillow：`python -m pip install Pillow`。`preview.html` 是本地排版预览，不参与 Git 跟踪。

```sh
python scripts/generate.py --sync --preview
```

`--sync` 读取配置账号的公开 GitHub 信息，以及未登记为 fork、未归档的公共仓库，排除同名主页仓库，然后聚合 GitHub Languages API 的字节数。未登记为 fork 不等同于全部原创；数据代表仓库代码组成，不代表个人熟练度。没有数据时明确显示未同步或空数据，失败时停止并保留之前生成的文件。

同一命令也会读取 `https://github.com/users/<username>/contributions` 的公开贡献日历，保存真实日期、贡献等级和可读出的贡献数量到 `data/contributions.json`。贪吃蛇按这些格子生成，未提供的数量保留为空，不补造贡献；公开日历无法解析或获取失败时，生成停止并保留旧文件。

`snake.svg` 和 `snake-dark.svg` 为深浅主题版本，README 通过 `<picture>` 自动选择；启用系统的减弱动态效果时展示静态贡献图。动画在本地和现有 Actions 构建中使用同一个 Python 生成器，无需另配密钥。离线生成使用上次保存的贡献日历，刷新浏览器不会同步贡献数据。

可通过环境变量 `GITHUB_TOKEN` 提升 API 限额。仅访问公开数据，无需提供私有仓库权限；不要把密钥写入配置或仓库。

## 填写个人内容

- `username`：GitHub 用户名；当前使用已确认的 `Core-RCE`。公开显示名称为 `CoreRCE`，两者不同。
- `display_name` / `tagline` / `bio`：显示名称、横幅短语与 0–3 行简介。
- `info`：系统卡字段。未知学历、生日、能力、联系方式未沿用原作者资料。
- `ecosystem`：最多 8 个技术方向及其条目，未填写的模块明确显示“待补充”。
- `timeline`：最多 7 个真实里程碑，当前使用账号创建、公开仓库创建时间及本次主页初始化。仓库创建时间不代表项目首次发布或职业履历。
- `projects`：最多 8 个项目，字段为 `name`、`url`、`description`，可选 `language`；当前的三个项目描述根据对应公开 README 填写。留空且成功同步后展示该账号最多 6 个未登记为 fork、未归档的公共仓库。
- `links`：最多 5 个外部入口，允许 HTTPS 或 mailto。
- `portrait`：当前为 `assets/profile.png`，来自 `Core-RCE` 公开的像素狐狸头像，安装 Pillow 后可转换成 ASCII。改为 `null` 时显示原创 ASCII 抽象核心符号；未使用参考作者的肖像。

修改账号后，原账号的数据不会继续展示；请重新运行 `--sync`。

## 验证

```sh
python -m unittest discover -s tests -v
python scripts/validate.py
```

校验会检查 SVG XML、本地资源、危险链接、外部 SVG 资源和残留原作者身份。离线默认主页不依赖外部统计图片服务。浏览器本地预览验证不能代替实际发布后的 GitHub 渲染与 Actions 验收。

## 发布

远程公开仓库名须与 GitHub 用户名一致。远程 `origin` 为 `Core-RCE/Core-RCE`，地址为 `https://github.com/Core-RCE/Core-RCE.git`，主页文件位于 `main` 分支。

工作流只生成并上传供下载的构建产物，不自动提交或推送文件；默认保持只读仓库权限。需要更新主页时可在本地重新生成，并按你自己的发布流程处理。

## 来源

- 当前账号资料：https://github.com/Core-RCE 。2026-10-14 已重新获取头像、账号创建日期、公开统计、仓库及贡献日历，数据源均为 `Core-RCE`。用户确认的中文标语、Blog 地址、邮箱和技术方向由本地配置维护，不由远程简介覆盖。
- 项目说明依据：https://github.com/Core-RCE/ARTEX-original-version 、https://github.com/Core-RCE/react-shadcn-admin 、https://github.com/Core-RCE/vue-vben-admin-lite 。ARTEX 项目注明为官方原始开源代码备份；Vben 项目注明基于 Vue Vben Admin。API 原始统计快照保存在 `data/github.json`，贡献快照保存在 `data/contributions.json`。
- 视觉参考：https://github.com/moiz-codez/moiz-codez 。该仓库没有根目录许可证，本项目没有复制其生成脚本或 SVG；原作者个人照片、履历、项目和联系方式均未沿用。
- JetBrains Mono 字体来自 https://github.com/JetBrains/JetBrainsMono ，嵌入 SVG 以保证 ASCII 排版，SIL OFL 1.1 许可证保存在 `assets/fonts/OFL.txt`。
