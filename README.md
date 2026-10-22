# Video Filter

基于 Flask Web 的视频筛选工具。根据 `doc/design.md` 的设计实现，通过浏览器访问。

## 环境配置

```bash
pip install -r requirements.txt
```

## 启动应用

启动 Flask 服务器：

```bash
conda activate web_env
python app.py
```

用浏览器打开 `http://127.0.0.1:8888`

在页面中输入 `Task name`（例如 `hang_mugs`），点击 `Load Task`。左侧会显示图片，右侧会显示 Requirement、两个进度条和两个按钮（打勾/删除）。任务需要对应的 `Layout_Requirement/<Task name>.yaml` 配置文件和 `images/<Task name>/` 图片目录。

## 进度存储

- 将要筛选的图片放在 `./images/` 目录下
- 程序会在 `images/<Task name>/progress.json` 中保存进度
- 当用户未完成一个任务的筛选就退出程序时，可以从该json文件中读取上一次的进度，然后继续筛选
