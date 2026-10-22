import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as video_filter


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(video_filter, 'BASE_DIR', tmp_path)
    video_filter.current_task.update(task_name=None, trajectories={},
                                     progress={'processed': [], 'accepted': []},
                                     accept_needed=0, requirements='')
    (tmp_path / 'Task_Requirement').mkdir()
    (tmp_path / 'Task_Requirement/demo.yaml').write_text('requirements: [test]\ntarget_count: 2\n')
    root = tmp_path / 'videos/demo'
    for name in ('traj_10_videos', 'traj_2_videos', 'traj_1_videos'):
        directory = root / name
        directory.mkdir(parents=True)
        (directory / 'head_camera.MP4').write_bytes(b'0123456789')
    (root / 'traj_2_videos/front_camera.webm').write_bytes(b'preferred alias')
    (root / 'traj_2_videos/front_camera.mp4').write_bytes(b'preferred format')
    (root / 'traj_2_videos/left_camera.ogv').write_bytes(b'left')
    (root / 'traj_2_videos/right_camera.ogg').write_bytes(b'right')
    (root / 'traj_0_videos').mkdir()
    (root / 'traj_0_videos/unrelated.mp4').write_bytes(b'ignored')
    (root / 'other').mkdir()
    video_filter.app.config.update(TESTING=True)
    with video_filter.app.test_client() as test_client:
        yield test_client


def load(client):
    return client.post('/api/load-task', json={'task_name': 'demo'})


def test_discovery_aliases_and_format_priority(client):
    response = load(client)
    assert response.status_code == 200
    assert response.json['total_trajectories'] == 3
    assert response.json['requirements'] == '1. test'
    assert list(video_filter.current_task['trajectories']) == ['traj_1_videos', 'traj_2_videos', 'traj_10_videos']
    assert client.get('/api/current-trajectory').json['videos'] == {
        'head': 'traj_1_videos/head_camera.MP4', 'left': None, 'right': None,
    }
    assert video_filter.current_task['trajectories']['traj_2_videos'] == {
        'head': 'traj_2_videos/front_camera.mp4',
        'left': 'traj_2_videos/left_camera.ogv',
        'right': 'traj_2_videos/right_camera.ogg',
    }


def test_mark_resume_duplicates_and_completion(client):
    load(client)
    result = client.post('/api/mark-accept', json={'trajectory': 'traj_1_videos'})
    assert result.json == {'processed_count': 1, 'accepted_count': 1, 'target_count': 2}
    assert client.post('/api/mark-accept', json={'trajectory': 'traj_1_videos'}).json == result.json
    assert client.post('/api/mark-reject', json={'trajectory': 'traj_1_videos'}).status_code == 409
    assert client.get('/api/current-trajectory').json['trajectory'] == 'traj_2_videos'
    client.post('/api/mark-reject', json={'trajectory': 'traj_2_videos'})
    resumed = load(client).json
    assert (resumed['processed_count'], resumed['accepted_count']) == (2, 1)
    assert client.get('/api/current-trajectory').json['trajectory'] == 'traj_10_videos'
    client.post('/api/mark-accept', json={'trajectory': 'traj_10_videos'})
    assert client.get('/api/current-trajectory').json['trajectory'] is None
    saved = json.loads((video_filter.BASE_DIR / 'videos/demo/progress.json').read_text())
    assert saved['processed'] == ['traj_1_videos', 'traj_2_videos', 'traj_10_videos']
    assert saved['accepted'] == ['traj_1_videos', 'traj_10_videos']
    assert (video_filter.BASE_DIR / 'videos/demo/traj_2_videos/head_camera.MP4').exists()


def test_stale_and_malformed_progress(client):
    path = video_filter.BASE_DIR / 'videos/demo/progress.json'
    path.write_text(json.dumps({'processed': ['traj_1_videos', 'traj_1_videos', 'gone', None],
                                'accepted': ['traj_1_videos', 'gone']}))
    assert load(client).json['processed_count'] == 1
    assert load(client).json['accepted_count'] == 1
    path.write_text('not json')
    assert load(client).json['processed_count'] == 0
    path.write_text(json.dumps({'processed': {}, 'accepted': [None, 'traj_2_videos']}))
    assert load(client).json['processed_count'] == 1


@pytest.mark.parametrize('target', ['0', '-1', '4', 'true', '1.5', 'abc', 'null'])
def test_invalid_target(client, target):
    (video_filter.BASE_DIR / 'Task_Requirement/demo.yaml').write_text(f'target_count: {target}\n')
    assert load(client).status_code == 400
    assert video_filter.current_task['task_name'] is None


def test_validation_and_unloaded_endpoints(client):
    assert client.get('/api/current-trajectory').status_code == 400
    assert client.get('/api/video/traj_1_videos/head_camera.MP4').status_code == 400
    assert client.post('/api/mark-accept', json={}).status_code == 400
    for data in ({}, [], {'task_name': 1}, {'task_name': '../demo'}, {'task_name': 'a\\b'}, {'task_name': '\x00'}):
        assert client.post('/api/load-task', json=data).status_code == 400
    assert client.post('/api/load-task', json={'task_name': 'missing'}).status_code == 404
    (video_filter.BASE_DIR / 'Task_Requirement/empty.yaml').write_text('target_count: 1')
    assert client.post('/api/load-task', json={'task_name': 'empty'}).status_code == 404
    load(client)
    for data in ({}, {'image': 'old.jpg'}, {'trajectory': '../outside'}, {'trajectory': []}):
        assert client.post('/api/mark-accept', json=data).status_code == 400
    assert client.get('/api/current-image').status_code == 404


def test_video_range_and_path_restrictions(client):
    load(client)
    assert client.get('/api/video/traj_1_videos/head_camera.MP4?task_name=other').status_code == 409
    response = client.get('/api/video/traj_1_videos/head_camera.MP4', headers={'Range': 'bytes=2-5'})
    assert response.status_code == 206
    assert response.data == b'2345'
    assert response.headers['Content-Range'] == 'bytes 2-5/10'
    assert response.mimetype == 'video/mp4'
    response.close()
    assert client.get('/api/video/traj_1_videos/head_camera.MP4', headers={'Range': 'bytes=99-100'}).status_code == 416
    for path in ('../demo/progress.json', 'traj_0_videos/unrelated.mp4', 'traj_2_videos/head_camera.MP4'):
        assert client.get('/api/video/' + path).status_code == 403
    directory = video_filter.BASE_DIR / 'videos/demo/traj_1_videos'
    video = directory / 'head_camera.MP4'
    video.unlink()
    video.symlink_to(video_filter.BASE_DIR / 'Task_Requirement/demo.yaml')
    assert client.get('/api/video/traj_1_videos/head_camera.MP4').status_code == 403


def test_symlink_discovery_and_failed_save(client, monkeypatch):
    root = video_filter.BASE_DIR / 'videos/demo'
    (root / 'traj_3_videos').symlink_to(video_filter.BASE_DIR / 'Task_Requirement', target_is_directory=True)
    assert load(client).json['total_trajectories'] == 3
    def fail_save(*args):
        raise OSError('disk full')
    monkeypatch.setattr(video_filter, 'save_progress', fail_save)
    assert client.post('/api/mark-accept', json={'trajectory': 'traj_1_videos'}).status_code == 500
    assert client.get('/api/current-trajectory').json['trajectory'] == 'traj_1_videos'
    assert video_filter.current_task['progress']['processed'] == []


def test_real_stack_blocks_read_only(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    if not (root / 'videos/stack_blocks').exists():
        pytest.skip('Local sample videos are not installed')
    monkeypatch.setattr(video_filter, 'BASE_DIR', root)
    monkeypatch.setattr(video_filter, 'load_yaml_config', lambda _: {'target_count': 6, 'requirements': ['test']})
    # Never read or write sample progress; this check only discovers and streams.
    monkeypatch.setattr(video_filter, 'load_progress', lambda *args: {'processed': [], 'accepted': []})
    with video_filter.app.test_client() as client:
        assert client.post('/api/load-task', json={'task_name': 'stack_blocks'}).json['total_trajectories'] == 6
        videos = client.get('/api/current-trajectory').json['videos']
        assert all(videos.values())
        for video in videos.values():
            response = client.get('/api/video/' + video, headers={'Range': 'bytes=0-31'})
            assert response.status_code == 206
            assert len(response.data) == 32
            assert b'ftyp' in response.data
            response.close()
