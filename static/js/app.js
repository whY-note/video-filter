const taskInput = document.getElementById('taskInput');
const loadBtn = document.getElementById('loadBtn');
const requirementView = document.getElementById('requirementView');
const filterProgress = document.getElementById('filterProgress');
const acceptProgress = document.getElementById('acceptProgress');
const filterCount = document.getElementById('filterCount');
const acceptCount = document.getElementById('acceptCount');
const acceptBtn = document.getElementById('acceptBtn');
const rejectBtn = document.getElementById('rejectBtn');
const playPauseBtn = document.getElementById('playPauseBtn');
const videoSeek = document.getElementById('videoSeek');
const videoTime = document.getElementById('videoTime');
const playbackSpeed = document.getElementById('playbackSpeed');
const playbackStatus = document.getElementById('playbackStatus');

const cameraViews = {
    head: document.getElementById('headCamera'),
    left: document.getElementById('leftCamera'),
    right: document.getElementById('rightCamera'),
};
let currentTask = null;
let currentTrajectory = null;
let totalTrajectories = 0;
let targetCount = 0;
let busy = false;

// Grid proportions stay independent of the video elements, so changing a
// trajectory or resizing the window preserves the user's layout.
function setupVideoDivider(id, axis, firstSize, secondSize, defaultShare) {
    const grid = document.getElementById('videoGrid');
    const divider = document.getElementById(id);
    const cursorClass = axis === 'y' ? 'resizing-rows' : 'resizing-columns';
    let share = defaultShare;
    let drag = null;

    function setShare(value) {
        share = Math.min(0.9, Math.max(0.1, value));
        grid.style.setProperty(firstSize, `${share}fr`);
        grid.style.setProperty(secondSize, `${1 - share}fr`);
        divider.setAttribute('aria-valuenow', String(Math.round(share * 100)));
    }

    function finish() {
        if (!drag) return;
        const pointerId = drag.pointerId;
        drag = null;
        divider.classList.remove('dragging');
        document.body.classList.remove(cursorClass);
        if (divider.hasPointerCapture(pointerId)) divider.releasePointerCapture(pointerId);
    }

    divider.addEventListener('pointerdown', event => {
        if (event.button !== 0 || drag) return;
        event.preventDefault();
        const bounds = grid.getBoundingClientRect();
        const thickness = axis === 'y' ? divider.offsetHeight : divider.offsetWidth;
        const available = (axis === 'y' ? bounds.height : bounds.width) - thickness;
        if (available <= 0) return;
        drag = {
            pointerId: event.pointerId,
            coordinate: axis === 'y' ? event.clientY : event.clientX,
            share,
            available,
        };
        divider.setPointerCapture(event.pointerId);
        divider.focus({ preventScroll: true });
        divider.classList.add('dragging');
        document.body.classList.add(cursorClass);
    });
    divider.addEventListener('pointermove', event => {
        if (!drag || drag.pointerId !== event.pointerId) return;
        const coordinate = axis === 'y' ? event.clientY : event.clientX;
        setShare(drag.share + (coordinate - drag.coordinate) / drag.available);
    });
    divider.addEventListener('pointerup', finish);
    divider.addEventListener('pointercancel', finish);
    divider.addEventListener('lostpointercapture', finish);
    window.addEventListener('blur', finish);
    window.addEventListener('resize', finish);
    divider.addEventListener('dblclick', () => setShare(defaultShare));
    divider.addEventListener('keydown', event => {
        const decrease = axis === 'y' ? 'ArrowUp' : 'ArrowLeft';
        const increase = axis === 'y' ? 'ArrowDown' : 'ArrowRight';
        if (event.key === decrease || event.key === increase) {
            event.preventDefault();
            setShare(share + (event.key === increase ? 0.02 : -0.02));
        } else if (event.key === 'Home' || event.key === 'End') {
            event.preventDefault();
            setShare(event.key === 'Home' ? 0.1 : 0.9);
        }
    });
}

setupVideoDivider('rowDivider', 'y', '--head-size', '--bottom-size', 2 / 3);
setupVideoDivider('columnDivider', 'x', '--left-size', '--right-size', 0.5);

function formatTime(seconds) {
    const value = Math.max(0, Math.floor(seconds || 0));
    return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
}

class SharedVideoPlayer {
    constructor() {
        this.entries = [];
        this.speed = 1;
        this.duration = 0;
        this.position = 0;
        this.wantsPlay = false;
        this.scrubbing = false;
        this.resumeAfterScrub = false;
        this.playPending = false;
        this.revision = 0;
        this.frame = null;
        this.events = null;
    }

    get videos() {
        return this.entries.filter(entry => entry.ready && !entry.failed).map(entry => entry.video);
    }

    get loaded() {
        return this.entries.length > 0 && this.entries.every(entry => entry.ready || entry.failed);
    }

    placeholder(view, message) {
        view.querySelector('video')?.remove();
        let text = view.querySelector('p');
        if (!text) {
            text = document.createElement('p');
            view.appendChild(text);
        }
        text.textContent = message;
    }

    clear(message = '尚未加载视频') {
        this.revision++;
        this.wantsPlay = false;
        this.playPending = false;
        this.scrubbing = false;
        this.resumeAfterScrub = false;
        cancelAnimationFrame(this.frame);
        this.events?.abort();
        for (const entry of this.entries) {
            clearTimeout(entry.timeout);
            entry.video.pause();
            entry.video.removeAttribute('src');
            entry.video.load();
        }
        this.entries = [];
        this.duration = 0;
        this.position = 0;
        for (const view of Object.values(cameraViews)) this.placeholder(view, message);
        this.updateControls();
    }

    load(paths) {
        this.clear('相机视频缺失');
        this.events = new AbortController();
        this.wantsPlay = true;
        playbackStatus.textContent = '正在加载视频…';
        for (const [camera, view] of Object.entries(cameraViews)) {
            if (!paths[camera]) continue;
            const video = document.createElement('video');
            video.muted = true;
            video.playsInline = true;
            video.preload = 'auto';
            video.playbackRate = this.speed;
            video.setAttribute('aria-label', view.querySelector('.camera-label').textContent);
            const entry = { video, view, ready: false, failed: false, timeout: null };
            this.entries.push(entry);
            const listen = (event, handler) => video.addEventListener(event, handler, { signal: this.events.signal });
            listen('loadedmetadata', () => {
                if (!Number.isFinite(video.duration) || video.duration <= 0) {
                    this.fail(entry);
                    return;
                }
                clearTimeout(entry.timeout);
                entry.ready = true;
                this.refreshDuration();
            });
            listen('error', () => this.fail(entry));
            listen('waiting', () => {
                if (this.wantsPlay && !this.scrubbing) this.hold();
            });
            listen('ended', () => {
                if (this.wantsPlay && !this.scrubbing) this.seekTo(0);
            });
            entry.timeout = setTimeout(() => this.fail(entry), 20000);
            view.querySelector('p')?.remove();
            view.appendChild(video);
            const path = paths[camera].split('/').map(encodeURIComponent).join('/');
            video.src = `/api/video/${path}?task_name=${encodeURIComponent(currentTask)}`;
            video.load();
        }
        this.refreshDuration();
        this.tick();
    }

    fail(entry) {
        if (entry.failed) return;
        clearTimeout(entry.timeout);
        entry.failed = true;
        entry.video.pause();
        entry.video.removeAttribute('src');
        entry.video.load();
        this.placeholder(entry.view, '视频加载失败或格式不受浏览器支持');
        this.refreshDuration();
    }

    refreshDuration() {
        const videos = this.videos;
        this.duration = this.loaded && videos.length ? Math.min(...videos.map(video => video.duration)) : 0;
        if (this.duration) {
            this.position = Math.min(this.position, this.duration);
        } else if (this.loaded) {
            this.wantsPlay = false;
            playbackStatus.textContent = '没有可播放的视频，仍可接受或拒绝此轨迹';
        }
        this.updateControls();
    }

    pauseVideos() {
        this.revision++;
        this.playPending = false;
        this.videos.forEach(video => video.pause());
    }

    hold() {
        this.pauseVideos();
        playbackStatus.textContent = '正在缓冲…';
    }

    async startVideos() {
        if (this.playPending) return;
        this.playPending = true;
        const revision = ++this.revision;
        const videos = this.videos;
        // Bring cameras back to the shared position after buffering.
        for (const video of videos) {
            video.playbackRate = this.speed;
            if (Math.abs(video.currentTime - this.position) > 0.2) video.currentTime = this.position;
        }
        const results = await Promise.allSettled(videos.map(video => video.play()));
        if (revision !== this.revision) return;
        this.playPending = false;
        const failure = results.find(result => result.status === 'rejected');
        if (failure) {
            this.pauseVideos();
            this.wantsPlay = false;
            playbackStatus.textContent = '请点击播放继续；若无法播放，请检查视频格式';
        } else {
            playbackStatus.textContent = '三路视频联动播放';
        }
        this.updateControls();
    }

    toggle() {
        if (!this.duration) return;
        this.wantsPlay = !this.wantsPlay;
        if (!this.wantsPlay) {
            this.position = this.videos[0]?.currentTime || this.position;
            this.pauseVideos();
            playbackStatus.textContent = '已暂停';
        } else if (this.position >= this.duration - 0.03) {
            this.seekTo(0);
        }
        this.updateControls();
    }

    seekTo(time) {
        if (!this.duration) return;
        this.pauseVideos();
        this.position = Math.min(this.duration, Math.max(0, time));
        for (const video of this.videos) video.currentTime = this.position;
        this.updateControls();
    }

    beginScrub() {
        if (!this.duration || this.scrubbing) return;
        this.scrubbing = true;
        this.resumeAfterScrub = this.wantsPlay;
        this.pauseVideos();
    }

    endScrub() {
        if (!this.scrubbing) return;
        this.scrubbing = false;
        this.wantsPlay = this.resumeAfterScrub;
        this.updateControls();
    }

    setSpeed(speed) {
        if (![1, 2, 4, 8].includes(speed)) return;
        this.speed = speed;
        for (const video of this.videos) video.playbackRate = speed;
    }

    updateControls() {
        const enabled = Boolean(this.duration);
        playPauseBtn.disabled = !enabled || this.scrubbing;
        videoSeek.disabled = !enabled;
        playbackSpeed.disabled = !enabled;
        playPauseBtn.classList.toggle('is-playing', this.wantsPlay);
        playPauseBtn.title = this.wantsPlay ? '暂停' : '播放';
        playPauseBtn.setAttribute('aria-label', this.wantsPlay ? '暂停三路视频' : '播放三路视频');
        videoSeek.max = String(this.duration);
        videoSeek.value = String(this.position);
        videoTime.textContent = `${formatTime(this.position)} / ${formatTime(this.duration)}`;
    }

    tick() {
        const videos = this.videos;
        if (this.duration && this.wantsPlay && !this.scrubbing) {
            if (videos.some(video => video.ended) || this.position >= this.duration - 0.03) {
                this.seekTo(0);
            }
            const ready = videos.every(video => video.readyState >= 3 && !video.seeking);
            if (!ready) {
                if (videos.some(video => !video.paused)) this.hold();
            } else if (videos.some(video => video.paused)) {
                this.startVideos();
            } else {
                this.position = Math.min(videos[0].currentTime, this.duration);
                for (const video of videos.slice(1)) {
                    if (Math.abs(video.currentTime - this.position) > 0.2) video.currentTime = this.position;
                }
                this.updateControls();
            }
        }
        this.frame = requestAnimationFrame(() => this.tick());
    }
}

const player = new SharedVideoPlayer();
player.updateControls();

playPauseBtn.addEventListener('click', () => player.toggle());
playbackSpeed.addEventListener('change', () => player.setSpeed(Number(playbackSpeed.value)));
videoSeek.addEventListener('pointerdown', () => player.beginScrub());
videoSeek.addEventListener('input', () => {
    player.beginScrub();
    player.seekTo(Number(videoSeek.value));
});
videoSeek.addEventListener('change', () => player.endScrub());
window.addEventListener('pointerup', () => player.endScrub());
window.addEventListener('pointercancel', () => player.endScrub());
window.addEventListener('blur', () => player.endScrub());

function setBusy(value) {
    busy = value;
    loadBtn.disabled = value;
    taskInput.disabled = value;
    acceptBtn.disabled = value || !currentTrajectory;
    rejectBtn.disabled = value || !currentTrajectory;
}

async function api(url, data) {
    const options = data === undefined ? {} : {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    };
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '请求失败');
    return result;
}

async function loadTask() {
    if (busy) return;
    const taskName = taskInput.value.trim();
    if (!taskName) return alert('Please enter a Task name');
    setBusy(true);
    try {
        const data = await api('/api/load-task', { task_name: taskName });
        currentTask = data.task_name;
        currentTrajectory = null;
        player.clear();
        totalTrajectories = data.total_trajectories;
        targetCount = data.target_count;
        requirementView.value = data.requirements;
        updateProgress(data.processed_count, data.accepted_count);
        await loadNextTrajectory();
    } catch (error) {
        alert(error.message);
    } finally {
        setBusy(false);
    }
}

async function loadNextTrajectory() {
    currentTrajectory = null;
    player.clear('正在加载轨迹…');
    playbackStatus.textContent = '正在加载轨迹…';
    try {
        const data = await api('/api/current-trajectory');
        if (!data.trajectory) {
            player.clear('所有轨迹已筛选完成');
            playbackStatus.textContent = '可重新加载任务查看已保存进度';
            return;
        }
        currentTrajectory = data.trajectory;
        player.load(data.videos);
    } catch (error) {
        player.clear('加载轨迹失败，请重新加载任务');
        playbackStatus.textContent = error.message;
        throw error;
    }
}

async function markTrajectory(accept) {
    if (busy || !currentTrajectory) return;
    setBusy(true);
    try {
        const data = await api(accept ? '/api/mark-accept' : '/api/mark-reject', {
            trajectory: currentTrajectory,
        });
        updateProgress(data.processed_count, data.accepted_count);
        await loadNextTrajectory();
    } catch (error) {
        alert(error.message);
    } finally {
        setBusy(false);
    }
}

function updateProgress(processed, accepted) {
    filterProgress.style.width = `${totalTrajectories ? processed / totalTrajectories * 100 : 0}%`;
    filterCount.textContent = `${processed}/${totalTrajectories}`;
    acceptProgress.style.width = `${targetCount ? Math.min(accepted / targetCount * 100, 100) : 0}%`;
    acceptCount.textContent = `${accepted}/${targetCount}`;
}

loadBtn.addEventListener('click', loadTask);
acceptBtn.addEventListener('click', () => markTrajectory(true));
rejectBtn.addEventListener('click', () => markTrajectory(false));
taskInput.addEventListener('keydown', event => {
    if (event.key === 'Enter') loadTask();
});
window.addEventListener('pagehide', () => player.clear());
