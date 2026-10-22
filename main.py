import os
import sys
import json

import yaml

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QProgressBar,
    QHBoxLayout,
    QVBoxLayout,
    QMessageBox,
    QScrollArea,
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt


IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')

class ImageFilterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Image Filter')
        self.resize(1000, 700)

        self.task_name = None
        self.images_root = None
        self.images = []  # list of relative paths under task folder
        self.current_relpath = None
        self.progress = {'processed': [], 'accepted': []}
        self.accept_needed = 0

        central = QWidget()
        self.setCentralWidget(central)
        h = QHBoxLayout(central)

        # Left: image display inside scroll area
        self.image_label = QLabel('No image loaded')
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 400)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.image_label)
        h.addWidget(scroll, 3)

        # Right: controls
        right = QVBoxLayout()

        task_row = QHBoxLayout()
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText('Enter Task name')
        self.load_btn = QPushButton('Load Task')
        self.load_btn.clicked.connect(self.load_task)
        task_row.addWidget(self.task_input)
        task_row.addWidget(self.load_btn)
        right.addLayout(task_row)

        self.requirement_view = QTextEdit()
        self.requirement_view.setReadOnly(True)
        self.requirement_view.setPlaceholderText('Requirement will appear here')
        right.addWidget(self.requirement_view)

        # Filter progress section
        filter_label = QLabel('筛选进度:')
        right.addWidget(filter_label)

        self.filter_progress = QProgressBar()
        self.filter_progress.setFormat('')
        self.filter_progress.setStyleSheet('''
            QProgressBar {
                border: 2px solid #87CEFA;
                border-radius: 10px;
                background-color: #FFFFFF;
            }
            QProgressBar::chunk {
                background-color: #87CEFA;
                border-radius: 8px;
            }
        ''')
        right.addWidget(self.filter_progress)

        # count label for filter progress (右下)
        self.filter_count_label = QLabel('0/0')
        self.filter_count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        right.addWidget(self.filter_count_label)

        # Accept progress section
        accept_label = QLabel('达标进度:')
        right.addWidget(accept_label)

        self.accept_progress = QProgressBar()
        self.accept_progress.setFormat('')
        self.accept_progress.setStyleSheet('''
            QProgressBar {
                border: 2px solid #FF69B4;
                border-radius: 10px;
                background-color: #FFFFFF;
            }
            QProgressBar::chunk {
                background-color: #FF69B4;
                border-radius: 8px;
            }
        ''')
        right.addWidget(self.accept_progress)

        # count label for accept progress (右下)
        self.accept_count_label = QLabel('0/0')
        self.accept_count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        right.addWidget(self.accept_count_label)

        btn_row = QHBoxLayout()
        self.accept_btn = QPushButton('✔')
        self.accept_btn.setStyleSheet('background-color: #4CAF50; color: white; font-size:18px;')
        self.accept_btn.clicked.connect(self.mark_accept)
        self.delete_btn = QPushButton('🗑')
        self.delete_btn.setStyleSheet('background-color: #F44336; color: white; font-size:18px;')
        self.delete_btn.clicked.connect(self.mark_reject)
        btn_row.addWidget(self.accept_btn)
        btn_row.addWidget(self.delete_btn)
        right.addLayout(btn_row)

        h.addLayout(right, 1)

    def show_error(self, text):
        QMessageBox.critical(self, 'Error', text)

    def load_task(self):
        task = self.task_input.text().strip()
        if not task:
            self.show_error('Please enter a Task name')
            return

        # check requirement yaml
        req_path = os.path.join('Layout_Requirement', f'{task}.yaml')
        if not os.path.exists(req_path):
            self.show_error('Task not found!')
            return

        with open(req_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        requirements = config.get('requirements', [])
        if isinstance(requirements, list):
            req_text = '\n'.join(f'{idx + 1}. {item}' for idx, item in enumerate(requirements))
        else:
            req_text = str(requirements)
        self.requirement_view.setPlainText(req_text)

        images_path = os.path.join('images', task)
        if not os.path.isdir(images_path):
            self.show_error('Images folder for this task not found')
            return

        # gather images recursively
        imgs = []
        for root, _, files in os.walk(images_path):
            for fn in files:
                if fn.lower().endswith(IMAGE_EXTS):
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, images_path)
                    imgs.append(rel)

        imgs.sort()
        self.task_name = task
        self.images_root = images_path
        self.images = imgs

        if 'target_count' not in config:
            self.show_error('YAML missing target_count')
            return
        try:
            target_needed = int(config['target_count'])
        except (TypeError, ValueError):
            self.show_error('Invalid target_count in YAML')
            return
        total = len(self.images)
        if target_needed > total:
            self.show_error('达标数量参数不能大于该任务下的图片总数')
            return
        self.accept_needed = target_needed

        # load or init progress.json in images task folder
        progress_path = os.path.join(images_path, 'progress.json')
        if os.path.exists(progress_path):
            try:
                with open(progress_path, 'r', encoding='utf-8') as f:
                    self.progress = json.load(f)
            except Exception:
                self.progress = {'processed': [], 'accepted': []}
        else:
            self.progress = {'processed': [], 'accepted': []}
            self._save_progress(progress_path)

        self.filter_progress.setMaximum(total)
        self.accept_progress.setMaximum(self.accept_needed)
        self.filter_progress.setValue(len(self.progress.get('processed', [])))
        self.accept_progress.setValue(min(len(self.progress.get('accepted', [])), self.accept_needed))

        # update count labels
        self.filter_count_label.setText(f"{len(self.progress.get('processed', []))}/{total}")
        self.accept_count_label.setText(f"{len(self.progress.get('accepted', []))}/{self.accept_needed}")

        self.show_next_image()

    def _save_progress(self, progress_path=None):
        if not self.images_root:
            return
        if progress_path is None:
            progress_path = os.path.join(self.images_root, 'progress.json')
        with open(progress_path, 'w', encoding='utf-8') as f:
            json.dump(self.progress, f, ensure_ascii=False, indent=2)

    def show_next_image(self):
        if not self.images:
            self.image_label.setText('No images found for this task')
            return

        next_rel = None
        for rel in self.images:
            if rel not in self.progress.get('processed', []):
                next_rel = rel
                break

        if next_rel is None:
            QMessageBox.information(self, 'Completed', 'All images processed for this task')
            self.image_label.setText('All images processed')
            self.current_relpath = None
            return

        self.current_relpath = next_rel
        full = os.path.join(self.images_root, next_rel)
        pix = QPixmap(full)
        if pix.isNull():
            self.image_label.setText('Unable to load image: ' + next_rel)
            return

        # scale to label width while keeping aspect
        max_w = max(400, self.image_label.width())
        scaled = pix.scaledToWidth(max_w, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)

    def mark_accept(self):
        if not self.current_relpath:
            return
        if self.current_relpath not in self.progress['processed']:
            self.progress['processed'].append(self.current_relpath)
        if self.current_relpath not in self.progress['accepted']:
            self.progress['accepted'].append(self.current_relpath)
        self._save_progress()
        self.filter_progress.setValue(len(self.progress['processed']))
        self.accept_progress.setValue(min(len(self.progress['accepted']), self.accept_needed))
        # update count labels
        total = len(self.images)
        self.filter_count_label.setText(f"{len(self.progress.get('processed', []))}/{total}")
        self.accept_count_label.setText(f"{len(self.progress.get('accepted', []))}/{self.accept_needed}")
        self.show_next_image()

    def mark_reject(self):
        if not self.current_relpath:
            return
        if self.current_relpath not in self.progress['processed']:
            self.progress['processed'].append(self.current_relpath)
        self._save_progress()
        self.filter_progress.setValue(len(self.progress['processed']))
        # update count labels
        total = len(self.images)
        self.filter_count_label.setText(f"{len(self.progress.get('processed', []))}/{total}")
        self.accept_count_label.setText(f"{len(self.progress.get('accepted', []))}/{self.accept_needed}")
        self.show_next_image()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # rescale current image to fit new width
        if self.current_relpath and self.images_root:
            full = os.path.join(self.images_root, self.current_relpath)
            pix = QPixmap(full)
            if not pix.isNull():
                max_w = max(400, self.image_label.width())
                scaled = pix.scaledToWidth(max_w, Qt.SmoothTransformation)
                self.image_label.setPixmap(scaled)


def main():
    app = QApplication(sys.argv)
    win = ImageFilterApp()
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
