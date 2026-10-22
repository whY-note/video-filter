import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'clean_not_accepted.py'


def run_script(directory, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(directory), *args],
        capture_output=True, text=True,
    )


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / 'data'
    root.mkdir()
    for number in range(3):
        directory = root / f'traj_{number:04d}_videos'
        directory.mkdir()
        (directory / 'front_camera.mp4').write_bytes(b'video')
        (root / f'traj_{number:04d}.vla').write_bytes(b'vla')
    (root / 'progress.json').write_text(json.dumps({
        'accepted': ['traj_0000_videos'],
        'processed': ['traj_0000_videos', 'traj_0001_videos'],
    }))
    return root


def test_keeps_accepted_pair_and_progress_and_deletes_everything_else(dataset):
    progress = (dataset / 'progress.json').read_bytes()
    (dataset / 'notes.txt').write_text('remove')
    (dataset / 'backup').mkdir()
    (dataset / 'backup/nested.txt').write_text('remove')
    result = run_script(dataset)
    assert result.returncode == 0, result.stderr
    assert {path.name for path in dataset.iterdir()} == {
        'progress.json', 'traj_0000_videos', 'traj_0000.vla',
    }
    assert (dataset / 'traj_0000_videos/front_camera.mp4').read_bytes() == b'video'
    assert (dataset / 'traj_0000.vla').read_bytes() == b'vla'
    assert (dataset / 'progress.json').read_bytes() == progress
    assert run_script(dataset).returncode == 0


def test_dry_run_does_not_change_files(dataset):
    before = {path.relative_to(dataset): path.read_bytes()
              for path in dataset.rglob('*') if path.is_file()}
    result = run_script(dataset, '--dry-run')
    assert result.returncode == 0, result.stderr
    assert 'traj_0001_videos' in result.stdout
    assert 'traj_0002.vla' in result.stdout
    assert before == {path.relative_to(dataset): path.read_bytes()
                      for path in dataset.rglob('*') if path.is_file()}


@pytest.mark.parametrize('progress', [
    'not json', '[]', '{}', '{"accepted": null}',
    '{"accepted": "traj_0000_videos"}', '{"accepted": [null]}',
    '{"accepted": ["../traj_0000_videos"]}',
    '{"accepted": ["traj_0000_videos", "invalid"]}',
])
def test_invalid_progress_leaves_data_untouched(dataset, progress):
    (dataset / 'progress.json').write_text(progress)
    before = set(dataset.rglob('*'))
    result = run_script(dataset)
    assert result.returncode != 0
    assert 'error:' in result.stderr.lower()
    assert set(dataset.rglob('*')) == before


@pytest.mark.parametrize('missing', [
    'progress.json', 'traj_0000.vla', 'traj_0000_videos',
])
def test_missing_required_data_prevents_any_deletion(dataset, missing):
    path = dataset / missing
    if path.is_dir():
        (path / 'front_camera.mp4').unlink()
        path.rmdir()
    else:
        path.unlink()
    before = set(dataset.rglob('*'))
    result = run_script(dataset)
    assert result.returncode != 0
    assert 'error:' in result.stderr.lower()
    assert set(dataset.rglob('*')) == before


def test_empty_accepted_deletes_all_data_except_progress(dataset):
    (dataset / 'progress.json').write_text('{"accepted": []}')
    result = run_script(dataset)
    assert result.returncode == 0, result.stderr
    assert [path.name for path in dataset.iterdir()] == ['progress.json']


def test_linked_data_directory_and_nested_symlinks(dataset, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'keep.txt').write_text('outside')
    (dataset / 'outside_link').symlink_to(outside, target_is_directory=True)
    (dataset / 'traj_0001_videos/outside_link').symlink_to(
        outside, target_is_directory=True,
    )
    (dataset / 'broken_link').symlink_to(tmp_path / 'missing')
    linked_root = tmp_path / 'linked_data'
    linked_root.symlink_to(dataset, target_is_directory=True)
    result = run_script(linked_root)
    assert result.returncode == 0, result.stderr
    assert (outside / 'keep.txt').read_text() == 'outside'
    assert not (dataset / 'outside_link').is_symlink()
    assert not (dataset / 'broken_link').is_symlink()
    assert (dataset / 'traj_0000.vla').exists()
