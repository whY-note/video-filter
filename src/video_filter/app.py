import json
import re
from pathlib import Path
from threading import RLock

import yaml
from flask import Flask, jsonify, render_template, request, send_file

app = Flask(__name__, template_folder='templates', static_folder='static')
# Runtime data lives in the working directory, outside the installed package.
BASE_DIR = Path.cwd()
VIDEO_EXTS = ('.mp4', '.webm', '.ogg', '.ogv')
CAMERAS = {
    'head': ('front_camera', 'head_camera'),
    'left': ('left_wrist_camera', 'left_camera'),
    'right': ('right_wrist_camera', 'right_camera'),
}
TASK_LOCK = RLock()

# This local tool has one shared active task, as in the original Flask app.
current_task = {
    'task_name': None,
    'trajectories': {},
    'progress': {'processed': [], 'accepted': []},
    'accept_needed': 0,
    'requirements': '',
}


def within(path, root):
    return path.resolve().is_relative_to(root.resolve())


def task_directory(task_name):
    root = Path(BASE_DIR) / 'videos'
    directory = root / task_name
    if not within(directory, root):
        raise ValueError('Invalid task path')
    return directory


def load_yaml_config(task_name):
    root = Path(BASE_DIR) / 'Task_Requirement'
    path = root / f'{task_name}.yaml'
    if not within(path, root):
        raise ValueError('Invalid configuration path')
    try:
        with path.open(encoding='utf-8') as stream:
            config = yaml.safe_load(stream) or {}
    except FileNotFoundError:
        return None
    except (OSError, yaml.YAMLError) as error:
        raise ValueError('Unable to read task configuration') from error
    if not isinstance(config, dict):
        raise ValueError('Task configuration must be a YAML mapping')
    return config


def gather_trajectories(task_name):
    directory = task_directory(task_name)
    if not directory.is_dir():
        return {}
    candidates = []
    for path in directory.iterdir():
        match = re.fullmatch(r'traj_(\d+)_videos', path.name)
        if match and path.is_dir() and within(path, directory):
            candidates.append((int(match[1]), path.name, path))

    trajectories = {}
    for _, name, path in sorted(candidates):
        files = {
            file.name.lower(): file
            for file in sorted(path.iterdir())
            if file.is_file() and within(file, directory)
        }
        videos = {}
        for camera, aliases in CAMERAS.items():
            video = next((files[alias + extension]
                          for alias in aliases for extension in VIDEO_EXTS
                          if alias + extension in files), None)
            videos[camera] = video.relative_to(directory).as_posix() if video else None
        if any(videos.values()):
            trajectories[name] = videos
    return trajectories


def load_progress(task_name, trajectories):
    path = task_directory(task_name) / 'progress.json'
    if not within(path, task_directory(task_name)):
        raise ValueError('Invalid progress path')
    try:
        with path.open(encoding='utf-8') as stream:
            saved = json.load(stream)
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    valid = {}
    for key in ('processed', 'accepted'):
        entries = saved.get(key, [])
        valid[key] = {entry for entry in entries if isinstance(entry, str)} if isinstance(entries, list) else set()
    # Accepted records are necessarily processed, including in hand-edited files.
    valid['processed'].update(valid['accepted'])
    return {key: [name for name in trajectories if name in entries]
            for key, entries in valid.items()}


def save_progress(task_name, progress):
    directory = task_directory(task_name)
    path = directory / 'progress.json'
    temporary = directory / 'progress.json.tmp'
    if not within(path, directory) or not within(temporary, directory):
        raise ValueError('Invalid progress path')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(progress, stream, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def progress_counts():
    return {
        'processed_count': len(current_task['progress']['processed']),
        'accepted_count': len(current_task['progress']['accepted']),
        'target_count': current_task['accept_needed'],
    }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/load-task', methods=['POST'])
def load_task_api():
    data = request.get_json(silent=True)
    task_name = data.get('task_name') if isinstance(data, dict) else None
    if not isinstance(task_name, str) or not task_name.strip():
        return jsonify(error='Please enter a Task name'), 400
    task_name = task_name.strip()
    if task_name in ('.', '..') or any(char in task_name for char in ('/', '\\', '\x00')):
        return jsonify(error='Invalid Task name'), 400

    with TASK_LOCK:
        try:
            config = load_yaml_config(task_name)
            if config is None:
                return jsonify(error='Task not found!'), 404
            trajectories = gather_trajectories(task_name)
            if not trajectories:
                return jsonify(error='No camera videos found for this task'), 404
            value = config.get('target_count')
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                raise ValueError('target_count must be a positive integer')
            try:
                target = int(value)
            except ValueError as error:
                raise ValueError('target_count must be a positive integer') from error
            if target <= 0:
                raise ValueError('target_count must be a positive integer')
            if target > len(trajectories):
                raise ValueError('target_count cannot exceed total trajectories')
            progress = load_progress(task_name, trajectories)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except OSError:
            return jsonify(error='Unable to read task files'), 500

        requirements = config.get('requirements', [])
        text = '\n'.join(f'{index + 1}. {item}' for index, item in enumerate(requirements)) if isinstance(requirements, list) else str(requirements)
        current_task.update(task_name=task_name, trajectories=trajectories,
                            progress=progress, accept_needed=target, requirements=text)
        return jsonify(task_name=task_name, requirements=text,
                       total_trajectories=len(trajectories), **progress_counts())


@app.route('/api/current-trajectory')
def get_current_trajectory():
    with TASK_LOCK:
        if not current_task['task_name']:
            return jsonify(error='No task loaded'), 400
        processed = set(current_task['progress']['processed'])
        for name, videos in current_task['trajectories'].items():
            if name not in processed:
                return jsonify(trajectory=name, videos=videos, current_index=len(processed),
                               total=len(current_task['trajectories']))
        return jsonify(trajectory=None, videos=None, message='All trajectories processed')


@app.route('/api/video/<path:video_path>')
def serve_video(video_path):
    with TASK_LOCK:
        if not current_task['task_name']:
            return jsonify(error='No task loaded'), 400
        requested_task = request.args.get('task_name')
        if requested_task is not None and requested_task != current_task['task_name']:
            return jsonify(error='Task changed; please reload the task'), 409
        directory = task_directory(current_task['task_name'])
        path = directory / video_path
        allowed = {video for videos in current_task['trajectories'].values()
                   for video in videos.values() if video}
        if video_path not in allowed or not within(path, directory):
            return jsonify(error='Access denied'), 403
        if not path.is_file():
            return jsonify(error='Video not found'), 404
        return send_file(path, conditional=True)


def mark_trajectory(accept):
    data = request.get_json(silent=True)
    name = data.get('trajectory') if isinstance(data, dict) else None
    with TASK_LOCK:
        if not current_task['task_name']:
            return jsonify(error='No task loaded'), 400
        if not isinstance(name, str) or name not in current_task['trajectories']:
            return jsonify(error='Unknown trajectory'), 400
        progress = current_task['progress']
        if name in progress['processed']:
            if (name in progress['accepted']) != accept:
                return jsonify(error='Trajectory already marked with a different result'), 409
            return jsonify(**progress_counts())
        updated = {key: list(entries) for key, entries in progress.items()}
        updated['processed'].append(name)
        if accept:
            updated['accepted'].append(name)
        try:
            save_progress(current_task['task_name'], updated)
        except (OSError, ValueError):
            return jsonify(error='Unable to save progress; please retry'), 500
        current_task['progress'] = updated
        return jsonify(**progress_counts())


@app.route('/api/mark-accept', methods=['POST'])
def mark_accept():
    return mark_trajectory(True)


@app.route('/api/mark-reject', methods=['POST'])
def mark_reject():
    return mark_trajectory(False)


def main():
    app.run(debug=True, host='0.0.0.0', port=8888)


if __name__ == '__main__':
    main()
