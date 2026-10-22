import os
import json
import yaml
from pathlib import Path
from flask import Flask, jsonify, request, render_template
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='templates', static_folder='static')

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Session storage for current task
current_task = {
    'task_name': None,
    'images': [],
    'progress': {'processed': [], 'accepted': []},
    'accept_needed': 0,
    'requirements': [],
}


def load_yaml_config(task_name):
    """Load task configuration from YAML file."""
    yaml_path = os.path.join(BASE_DIR, 'Layout_Requirement', f'{task_name}.yaml')
    if not os.path.exists(yaml_path):
        return None
    
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        return config
    except Exception as e:
        print(f"Error reading YAML: {e}")
        return None


def gather_images(task_name):
    """Recursively gather all images under task folder."""
    images_path = os.path.join(BASE_DIR, 'images', task_name)
    if not os.path.isdir(images_path):
        return []
    
    images = []
    for root, _, files in os.walk(images_path):
        for fn in files:
            if fn.lower().endswith(IMAGE_EXTS):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, images_path)
                images.append(rel)
    
    return sorted(images)


def load_progress(task_name):
    """Load progress.json for a task."""
    progress_path = os.path.join(BASE_DIR, 'images', task_name, 'progress.json')
    if os.path.exists(progress_path):
        try:
            with open(progress_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'processed': [], 'accepted': []}


def save_progress(task_name):
    """Save progress.json for a task."""
    progress_path = os.path.join(BASE_DIR, 'images', task_name, 'progress.json')
    with open(progress_path, 'w', encoding='utf-8') as f:
        json.dump(current_task['progress'], f, ensure_ascii=False, indent=2)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/load-task', methods=['POST'])
def load_task_api():
    data = request.get_json()
    task_name = data.get('task_name', '').strip()
    
    if not task_name:
        return jsonify({'error': 'Please enter a Task name'}), 400
    
    # Load YAML config
    config = load_yaml_config(task_name)
    if config is None:
        return jsonify({'error': 'Task not found!'}), 404
    
    # Gather images
    images = gather_images(task_name)
    if not images:
        return jsonify({'error': 'No images found for this task'}), 404
    
    # Get target count
    target_needed = int(config.get('target_count', 1))
    if target_needed > len(images):
        return jsonify({'error': 'target_count cannot exceed total images'}), 400
    
    # Get requirements
    requirements = config.get('requirements', [])
    if isinstance(requirements, list):
        req_text = '\n'.join(f'{idx + 1}. {item}' for idx, item in enumerate(requirements))
    else:
        req_text = str(requirements)
    
    # Load progress
    progress = load_progress(task_name)
    
    # Update global state
    current_task['task_name'] = task_name
    current_task['images'] = images
    current_task['progress'] = progress
    current_task['accept_needed'] = target_needed
    current_task['requirements'] = req_text
    
    return jsonify({
        'task_name': task_name,
        'requirements': req_text,
        'total_images': len(images),
        'target_count': target_needed,
        'processed_count': len(progress.get('processed', [])),
        'accepted_count': len(progress.get('accepted', [])),
    })


@app.route('/api/current-image', methods=['GET'])
def get_current_image():
    if not current_task['task_name']:
        return jsonify({'error': 'No task loaded'}), 400
    
    images = current_task['images']
    processed = current_task['progress'].get('processed', [])
    
    # Find next unprocessed image
    next_image = None
    for img in images:
        if img not in processed:
            next_image = img
            break
    
    if next_image is None:
        return jsonify({'image': None, 'message': 'All images processed'})
    
    # Return relative path; frontend will fetch the image
    return jsonify({
        'image': next_image,
        'current_index': processed.__len__(),
        'total': len(images),
    })


@app.route('/api/image/<path:image_path>')
def serve_image(image_path):
    """Serve image file."""
    if not current_task['task_name']:
        return 'No task loaded', 400
    
    task_name = current_task['task_name']
    full_path = os.path.join(BASE_DIR, 'images', task_name, image_path)
    
    # Security: prevent directory traversal
    full_path = os.path.abspath(full_path)
    task_dir = os.path.abspath(os.path.join(BASE_DIR, 'images', task_name))
    if not full_path.startswith(task_dir):
        return 'Access denied', 403
    
    if os.path.exists(full_path):
        from flask import send_file
        return send_file(full_path)
    
    return 'Image not found', 404


@app.route('/api/mark-accept', methods=['POST'])
def mark_accept():
    if not current_task['task_name']:
        return jsonify({'error': 'No task loaded'}), 400
    
    data = request.get_json()
    image_rel = data.get('image')
    
    if image_rel not in current_task['progress']['processed']:
        current_task['progress']['processed'].append(image_rel)
    
    if image_rel not in current_task['progress']['accepted']:
        current_task['progress']['accepted'].append(image_rel)
    
    save_progress(current_task['task_name'])
    
    return jsonify({
        'processed_count': len(current_task['progress']['processed']),
        'accepted_count': len(current_task['progress']['accepted']),
        'target_count': current_task['accept_needed'],
    })


@app.route('/api/mark-reject', methods=['POST'])
def mark_reject():
    if not current_task['task_name']:
        return jsonify({'error': 'No task loaded'}), 400
    
    data = request.get_json()
    image_rel = data.get('image')
    
    if image_rel not in current_task['progress']['processed']:
        current_task['progress']['processed'].append(image_rel)
    
    save_progress(current_task['task_name'])
    
    return jsonify({
        'processed_count': len(current_task['progress']['processed']),
        'accepted_count': len(current_task['progress']['accepted']),
        'target_count': current_task['accept_needed'],
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8888)
