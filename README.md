# Image Filter

PyQt5 和 Flask Web 两种版本的图像筛选工具。根据 `doc/design.md` 的设计实现。

## 环境配置

```bash
pip install -r requirements.txt
```

## 方式1：PyQt5 桌面应用

激活你的 conda 环境，然后运行程序：

```bash
conda activate ML_env
python main.py
```

在程序中输入 `Task name`（例如 `mug_hanging`），点击 `Load Task`。左侧会显示图片，右侧会显示 Requirement、两个进度条和两个按钮（打勾/删除）。

## 方式2：Flask Web 应用（浏览器访问）

启动 Flask 服务器：

```bash
conda activate web_env
python app.py
```

用浏览器打开 `http://127.0.0.1:5000`

## 进度存储

- 将要筛选的图片放在 `./images/` 目录下
- 程序会在 `images/<Task name>/progress.json` 中保存进度
- 当用户未完成一个任务的筛选就退出程序时，可以从该json文件中读取上一次的进度，然后继续筛选
